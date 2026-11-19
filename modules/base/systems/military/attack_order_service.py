"""Prepare validated unit attack orders for the tactical combat system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import polars as pl

from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.unit_order_workflow import sync_unit_readiness

from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState


class _ReadinessPreparer(Protocol):
    def prepare_order(self, state: GameState, unit_id: str) -> bool: ...


class _UnitMovement(Protocol):
    def unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate: ...

    def stop_unit_at(self, row: dict[str, Any], geo: GeoCoordinate, current_minute: int) -> None: ...


class _UnitOrderWorkflow(Protocol):
    def release_fortified_for_order(self, state: GameState, unit: dict[str, Any]) -> bool: ...

    def queue_attack(self, state: GameState, action: ActionAttackUnit) -> str: ...

    def clear_pending_order(self, state: GameState, unit_id: str) -> None: ...


@dataclass
class _AttackOrderContext:
    state: GameState
    rows: list[dict[str, Any]]
    units_by_id: dict[str, dict[str, Any]]
    hostile_pairs: set[frozenset[str]]
    current_minute: int


class MilitaryAttackOrderService:
    """Validate attack commands and put eligible forces into assault posture."""

    def __init__(
        self,
        readiness_preparer: _ReadinessPreparer,
        unit_movement: _UnitMovement,
        hostility_policy: Callable[[list[dict[str, Any]]], set[frozenset[str]]],
        unit_order_workflow: _UnitOrderWorkflow,
        units_from_rows: Callable[[list[dict[str, Any]]], pl.DataFrame],
    ) -> None:
        self._readiness_preparer = readiness_preparer
        self._unit_movement = unit_movement
        self._hostility_policy = hostility_policy
        self._unit_order_workflow = unit_order_workflow
        self._units_from_rows = units_from_rows

    def process(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions = []
        owners = dict(units.select("id", "owner").iter_rows()) if {"id", "owner"}.issubset(units.columns) else {}
        for action in state.current_actions:
            if isinstance(action, ActionAttackUnit):
                unit_id = str(action.attacker_unit_id)
                owner = owners.get(unit_id)
                if not owner or not player_controls_country(state, action.player_id, owner):
                    self._reject_action(state, action, "The attacker is unavailable or is not controlled by the actor.")
                    continue
                actions.append(action)
        if not actions or units.is_empty():
            return units

        context = self._build_context(state, units)
        changed = any([
            self._process_action(context, action)
            for action in actions
        ])
        return self._units_from_rows(context.rows) if changed else units

    def _build_context(self, state: GameState, units: pl.DataFrame) -> _AttackOrderContext:
        war_table = state.tables.get("countries_wars")
        wars = [] if war_table is None else war_table.to_dicts()
        rows = units.to_dicts()
        return _AttackOrderContext(
            state=state,
            rows=rows,
            units_by_id={str(row.get("id") or ""): row for row in rows},
            hostile_pairs=self._hostility_policy(wars),
            current_minute=int(state.time.total_minutes),
        )

    def _process_action(
        self,
        context: _AttackOrderContext,
        action: ActionAttackUnit,
    ) -> bool:
        attacker = context.units_by_id.get(str(action.attacker_unit_id or ""))
        if attacker is None or not attacker.get("owner") or not player_controls_country(
            context.state, action.player_id, attacker.get("owner")
        ):
            self._reject_action(context.state, action, "The attacker is unavailable or is not controlled by the actor.")
            return False
        targets = self._resolve_targets(action, context)
        if targets is None:
            self._reject_action(context.state, action, "The target must be a hostile unit with combat strength in the same region.")
            return False
        attacker, defender = targets
        if not self._prepare_attack(context.state, action, attacker):
            sync_unit_readiness(context.state, attacker)
            return True
        self._begin_assault(attacker, defender, context.current_minute)
        self._interrupt_routes(context.state, attacker, defender, context.current_minute)
        context.state.journal.append_command_result({
            "tick": int(context.state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": "applied",
            "reason": "The unit began its assault.",
            "unit_id": str(action.attacker_unit_id),
        })
        return True

    @staticmethod
    def _interrupt_routes(state: GameState, attacker: dict[str, Any], defender: dict[str, Any], now: int) -> None:
        routes = state.tables.get("unit_movement_routes")
        if routes is None or routes.is_empty() or not {"unit_id", "status"}.issubset(routes.columns):
            return
        unit_ids = [str(attacker.get("id") or ""), str(defender.get("id") or "")]
        active = pl.col("unit_id").is_in(unit_ids) & (pl.col("status") == "in_transit")
        if routes.filter(active).is_empty():
            return
        changes = [pl.when(active).then(pl.lit("interrupted")).otherwise(pl.col("status")).alias("status")]
        if "rejection_reason" in routes.columns:
            changes.append(pl.when(active).then(pl.lit("Movement interrupted by combat contact."))
                           .otherwise(pl.col("rejection_reason")).alias("rejection_reason"))
        if "updated_at_minute" in routes.columns:
            changes.append(pl.when(active).then(pl.lit(now)).otherwise(pl.col("updated_at_minute"))
                           .alias("updated_at_minute"))
        # Route rows must agree with the stopped unit positions before movement advances again.
        state.update_table("unit_movement_routes", routes.with_columns(changes))

    @staticmethod
    def _reject_action(state: GameState, action: ActionAttackUnit, reason: str) -> None:
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": "rejected",
            "reason": reason,
            "unit_id": str(action.attacker_unit_id),
        })

    def _resolve_targets(
        self,
        action: ActionAttackUnit,
        context: _AttackOrderContext,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        attacker = context.units_by_id.get(str(action.attacker_unit_id or ""))
        defender = context.units_by_id.get(str(action.defender_unit_id or ""))
        if not self._is_valid_target_pair(attacker, defender, context.hostile_pairs):
            return None
        return attacker, defender

    def _is_valid_target_pair(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
        hostile_pairs: set[frozenset[str]],
    ) -> bool:
        if not self._are_distinct_units(attacker, defender):
            return False
        if not self._has_combat_strength(attacker):
            return False
        if not self._has_combat_strength(defender):
            return False
        # Direct attacks represent contact, while travel to another region uses movement orders.
        attacker_region = int(attacker.get("current_region_id") or 0)
        defender_region = int(defender.get("current_region_id") or 0)
        if attacker_region <= 0 or attacker_region != defender_region:
            return False
        return self._are_hostile(attacker, defender, hostile_pairs)

    def _are_distinct_units(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
    ) -> bool:
        return attacker is not None and defender is not None and attacker is not defender

    def _has_combat_strength(self, unit: dict[str, Any] | None) -> bool:
        return unit is not None and int(unit.get("strength") or 0) > 0

    def _are_hostile(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
        hostile_pairs: set[frozenset[str]],
    ) -> bool:
        if attacker is None or defender is None:
            return False
        attacker_owner = str(attacker.get("owner") or "").strip().upper()
        defender_owner = str(defender.get("owner") or "").strip().upper()
        return frozenset((attacker_owner, defender_owner)) in hostile_pairs

    def _prepare_attack(
        self,
        state: GameState,
        action: ActionAttackUnit,
        attacker: dict[str, Any],
    ) -> bool:
        attacker_id = str(attacker.get("id") or "")
        released_fortification = self._unit_order_workflow.release_fortified_for_order(
            state,
            attacker,
        )
        can_execute = released_fortification or self._readiness_preparer.prepare_order(
            state,
            attacker_id,
        )
        if can_execute:
            self._unit_order_workflow.clear_pending_order(state, attacker_id)
            self._reset_attacker_readiness(attacker)
            return True
        self._unit_order_workflow.queue_attack(state, action)
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "status": "queued",
            "reason": "The attack will begin when the unit is ready.",
            "unit_id": attacker_id,
        })
        return False

    def _reset_attacker_readiness(self, attacker: dict[str, Any]) -> None:
        attacker["readiness_status"] = "ready"
        attacker["readiness_progress"] = 0.0
        attacker["readiness_transition_id"] = ""
        attacker["readiness_eta_minute"] = 0

    def _begin_assault(
        self,
        attacker: dict[str, Any],
        defender: dict[str, Any],
        current_minute: int,
    ) -> None:
        defender_geo = self._unit_movement.unit_geo_at(defender, current_minute)
        self._unit_movement.stop_unit_at(attacker, defender_geo, current_minute)
        self._unit_movement.stop_unit_at(defender, defender_geo, current_minute)
        attacker["current_region_id"] = int(defender.get("current_region_id") or 0)
        attacker["engagement_mode"] = "assault"
        defender["engagement_mode"] = "assault"
