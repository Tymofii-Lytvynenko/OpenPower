"""Prepare validated unit attack orders for the tactical combat system."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import polars as pl

from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit
from src.shared.state import GameState


class _ReadinessPreparer(Protocol):
    def prepare_order(self, state: GameState, unit_id: str) -> bool: ...


class _UnitMovement(Protocol):
    def unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate: ...

    def stop_unit_at(self, row: dict[str, Any], geo: GeoCoordinate, current_minute: int) -> None: ...


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
        fortification_release: Callable[[GameState, dict[str, Any]], bool],
        pending_order_queue: Callable[[GameState, ActionAttackUnit], str],
        units_from_rows: Callable[[list[dict[str, Any]]], pl.DataFrame],
    ) -> None:
        self._readiness_preparer = readiness_preparer
        self._unit_movement = unit_movement
        self._hostility_policy = hostility_policy
        self._fortification_release = fortification_release
        self._pending_order_queue = pending_order_queue
        self._units_from_rows = units_from_rows

    def process(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions = [action for action in state.current_actions if isinstance(action, ActionAttackUnit)]
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
        targets = self._resolve_targets(action, context)
        if targets is None:
            return False
        attacker, defender = targets
        if not self._prepare_attack(context.state, action, attacker):
            return False
        self._begin_assault(attacker, defender, context.current_minute)
        return True

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
        released_fortification = self._fortification_release(state, attacker)
        can_execute = released_fortification or self._readiness_preparer.prepare_order(
            state,
            attacker_id,
        )
        if can_execute:
            self._reset_attacker_readiness(attacker)
            return True
        self._pending_order_queue(state, action)
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
