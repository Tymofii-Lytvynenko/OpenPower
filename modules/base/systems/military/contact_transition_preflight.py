"""Detect known combat contact before readiness transitions complete."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

import polars as pl

from src.core.map.engagement_geometry import interpolate_geo
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit
from src.shared.state import GameState


class _ReadinessTransitions(Protocol):
    def cancel_transition_for_unit(
        self,
        state: GameState,
        unit_id: str,
        reason: str,
    ) -> None: ...


class _UnitOrderWorkflow(Protocol):
    def unit_is_transitioning(self, state: GameState, unit_id: str) -> bool: ...


class _UnitMovement(Protocol):
    def first_hostile_contact(
        self,
        moving_unit: dict[str, Any],
        unit_rows: Iterable[dict[str, Any]],
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> tuple[dict[str, Any], float] | None: ...


class MilitaryContactTransitionPreflight:
    """Cancel readiness transitions when the current phase already predicts contact."""

    def __init__(
        self,
        readiness_transitions: _ReadinessTransitions,
        unit_order_workflow: _UnitOrderWorkflow,
        unit_movement: _UnitMovement,
        hostility_policy: Callable[[list[dict[str, Any]]], set[frozenset[str]]],
    ) -> None:
        self._readiness_transitions = readiness_transitions
        self._unit_order_workflow = unit_order_workflow
        self._unit_movement = unit_movement
        self._hostility_policy = hostility_policy

    def process(self, state: GameState, units: pl.DataFrame) -> None:
        """Preserve contact-before-readiness-completion ordering in the military phase."""
        war_table = state.tables.get("countries_wars")
        war_rows = [] if war_table is None else war_table.to_dicts()
        hostile_pairs = self._hostility_policy(war_rows)
        if not hostile_pairs or units.is_empty() or "owner" not in units.columns:
            return

        unit_rows = self._hostile_unit_rows(units, hostile_pairs)
        if not unit_rows:
            return

        by_id = {str(row.get("id") or ""): row for row in unit_rows}
        ordered_rows = sorted(unit_rows, key=lambda row: str(row.get("id") or ""))
        owners_by_country = self._units_by_country(ordered_rows)
        contact_ids = self._attack_contact_ids(state, by_id, hostile_pairs)
        contact_ids.update(
            self._engagement_contact_ids(ordered_rows, owners_by_country, hostile_pairs)
        )
        contact_ids.update(
            self._moving_contact_ids(
                ordered_rows,
                owners_by_country,
                hostile_pairs,
                int(state.time.total_minutes),
            )
        )
        self._cancel_contact_transitions(state, contact_ids)

    def _hostile_unit_rows(
        self,
        units: pl.DataFrame,
        hostile_pairs: set[frozenset[str]],
    ) -> list[dict[str, Any]]:
        hostile_countries = sorted({country for pair in hostile_pairs for country in pair})
        return units.filter(
            pl.col("owner")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.strip_chars()
            .str.to_uppercase()
            .is_in(hostile_countries)
        ).to_dicts()

    def _attack_contact_ids(
        self,
        state: GameState,
        by_id: dict[str, dict[str, Any]],
        hostile_pairs: set[frozenset[str]],
    ) -> set[str]:
        contact_ids: set[str] = set()
        for action in state.current_actions:
            contact_ids.update(
                self._attack_contact_for_action(state, action, by_id, hostile_pairs)
            )
        return contact_ids

    def _attack_contact_for_action(
        self,
        state: GameState,
        action: Any,
        by_id: dict[str, dict[str, Any]],
        hostile_pairs: set[frozenset[str]],
    ) -> set[str]:
        if not isinstance(action, ActionAttackUnit):
            return set()
        attacker = by_id.get(str(action.attacker_unit_id or ""))
        defender = by_id.get(str(action.defender_unit_id or ""))
        if not self.valid_hostile_attack(attacker, defender, hostile_pairs):
            return set()
        attacker_id = str(attacker.get("id") or "")
        if not self._attacker_can_start_contact(state, attacker, attacker_id):
            return set()
        return {attacker_id, str(defender.get("id") or "")}

    def _attacker_can_start_contact(
        self,
        state: GameState,
        attacker: dict[str, Any],
        attacker_id: str,
    ) -> bool:
        if self._unit_order_workflow.unit_is_transitioning(state, attacker_id):
            return False
        return str(attacker.get("readiness_status") or "").strip().lower() != "parked"

    def _units_by_country(
        self,
        ordered_rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        owners_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in ordered_rows:
            owner = str(row.get("owner") or "").strip().upper()
            if owner:
                owners_by_country.setdefault(owner, []).append(row)
        return owners_by_country

    def _engagement_contact_ids(
        self,
        ordered_rows: list[dict[str, Any]],
        owners_by_country: dict[str, list[dict[str, Any]]],
        hostile_pairs: set[frozenset[str]],
    ) -> set[str]:
        contact_ids: set[str] = set()
        for row in ordered_rows:
            if str(row.get("engagement_mode") or "").lower() not in {
                "assault",
                "positional",
            }:
                continue
            owner = str(row.get("owner") or "").strip().upper()
            hostile_units = self._hostile_units_for_owner(
                owner,
                owners_by_country,
                hostile_pairs,
                active_only=True,
            )
            if hostile_units:
                contact_ids.add(str(row.get("id") or ""))
                contact_ids.update(str(candidate.get("id") or "") for candidate in hostile_units)
        return contact_ids

    def _moving_contact_ids(
        self,
        ordered_rows: list[dict[str, Any]],
        owners_by_country: dict[str, list[dict[str, Any]]],
        hostile_pairs: set[frozenset[str]],
        current_minute: int,
    ) -> set[str]:
        contact_ids: set[str] = set()
        for row in ordered_rows:
            predicted_contact_ids = self._predicted_moving_contact_ids(
                row,
                owners_by_country,
                hostile_pairs,
                current_minute,
            )
            if predicted_contact_ids:
                contact_ids.update(predicted_contact_ids)
        return contact_ids

    def _predicted_moving_contact_ids(
        self,
        row: dict[str, Any],
        owners_by_country: dict[str, list[dict[str, Any]]],
        hostile_pairs: set[frozenset[str]],
        current_minute: int,
    ) -> set[str]:
        if not bool(row.get("is_moving")):
            return set()
        owner = str(row.get("owner") or "").strip().upper()
        hostile_candidates = self._hostile_units_for_owner(
            owner,
            owners_by_country,
            hostile_pairs,
        )
        if not hostile_candidates:
            return set()

        start, end = self._movement_segment(row, current_minute)
        contact = self._unit_movement.first_hostile_contact(
            row,
            hostile_candidates,
            start,
            end,
            current_minute,
        )
        if contact is None:
            return set()
        return {str(row.get("id") or ""), str(contact[0].get("id") or "")}

    def _movement_segment(
        self,
        row: dict[str, Any],
        current_minute: int,
    ) -> tuple[GeoCoordinate, GeoCoordinate]:
        departed_value = row.get("departed_at_minute")
        arrival_value = row.get("arrival_at_minute")
        departed = int(departed_value if departed_value is not None else current_minute)
        arrival = int(arrival_value if arrival_value is not None else current_minute)
        duration = max(1, arrival - departed)
        previous_progress = max(
            0.0,
            min(1.0, float(row.get("movement_progress") or 0.0)),
        )
        next_progress = max(
            0.0,
            min(1.0, (current_minute - departed) / duration),
        )
        return (
            self.interpolate_row_geo(row, previous_progress),
            self.interpolate_row_geo(row, next_progress),
        )

    def _cancel_contact_transitions(
        self,
        state: GameState,
        contact_ids: set[str],
    ) -> None:
        for unit_id in sorted(contact_ids):
            self._readiness_transitions.cancel_transition_for_unit(
                state,
                unit_id,
                "combat_contact",
            )

    def valid_hostile_attack(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
        hostile_pairs: set[frozenset[str]],
    ) -> bool:
        if attacker is None or defender is None:
            return False
        if attacker is defender:
            return False
        if not self._unit_has_active_strength(attacker):
            return False
        if not self._unit_has_active_strength(defender):
            return False
        attacker_owner = str(attacker.get("owner") or "").strip().upper()
        defender_owner = str(defender.get("owner") or "").strip().upper()
        return frozenset((attacker_owner, defender_owner)) in hostile_pairs

    def _hostile_units_for_owner(
        self,
        owner: str,
        owners_by_country: dict[str, list[dict[str, Any]]],
        hostile_pairs: set[frozenset[str]],
        *,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        candidates = [
            candidate
            for enemy in sorted(owners_by_country)
            if frozenset((owner, enemy)) in hostile_pairs
            for candidate in owners_by_country[enemy]
        ]
        if not active_only:
            return candidates
        return [candidate for candidate in candidates if self._unit_has_active_strength(candidate)]

    def _unit_has_active_strength(self, unit: dict[str, Any]) -> bool:
        return int(unit.get("strength") or 0) > 0

    def interpolate_row_geo(
        self,
        row: dict[str, Any],
        progress: float,
    ) -> GeoCoordinate:
        source = GeoCoordinate(
            latitude=self._row_float(row, "source_latitude", row.get("latitude")),
            longitude=self._row_float(row, "source_longitude", row.get("longitude")),
        )
        target = GeoCoordinate(
            latitude=self._row_float(row, "target_latitude", row.get("latitude")),
            longitude=self._row_float(row, "target_longitude", row.get("longitude")),
        )
        return interpolate_geo(source, target, progress)

    def _row_float(
        self,
        row: dict[str, Any],
        key: str,
        fallback: Any = 0.0,
    ) -> float:
        value = row.get(key)
        if value is None:
            value = fallback
        try:
            return float(value if value is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0
