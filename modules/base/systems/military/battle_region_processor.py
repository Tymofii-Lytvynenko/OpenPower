"""Scan regions and collect the battle changes for one combat tick."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.alliance_policy import AlliancePolicy
from modules.base.systems.military.battle_anchor_policy import resolve_battle_anchor
from modules.base.systems.military.battle_occupation_policy import BattleOccupationPolicy
from modules.base.systems.military.battle_snapshot_builder import (
    ActiveBattleSnapshotRequest,
    BattleSnapshotBuilder,
)
from modules.base.systems.military.combat_round_resolver import (
    CombatRoundResolver,
    normalize_country_tag,
)
from modules.base.systems.military.readiness_system import cancel_readiness_for_contact
from modules.base.systems.military.war_index import ConflictContext, WarIndex
from src.shared.events import EventBattleParticipantRejected, EventBattleStarted
from src.shared.state import GameState


BATTLE_TABLE = "battles"
BATTLE_UNITS_TABLE = "battle_units"


@dataclass(frozen=True, slots=True)
class BattleRegionScanRequest:
    state: GameState
    regions: pl.DataFrame
    unit_rows: list[dict[str, Any]]
    wars: WarIndex
    existing_battles: set[str]
    should_resolve: bool
    assaulting_unit_ids: set[str]
    casualty_table: pl.DataFrame | None
    occupation_table: pl.DataFrame | None


@dataclass(slots=True)
class BattleRegionScanResult:
    unit_rows: list[dict[str, Any]]
    casualty_rows: list[dict[str, Any]]
    occupation_rows: list[dict[str, Any]]
    stationary_units: dict[int, list[dict[str, Any]]]
    region_rows: list[dict[str, Any]]
    original_controllers: dict[int, str]
    battle_rows: list[dict[str, Any]]
    battle_unit_rows: list[dict[str, Any]]
    participant_rows: list[dict[str, Any]]
    active_battle_ids: set[str]
    victorious_battles: dict[str, str]
    victorious_sides: dict[str, str]
    battle_regions: dict[str, int]
    battle_metadata: dict[str, dict[str, Any]]


class BattleRegionProcessor:
    """Resolve per-region encounters and collect deterministic tick outputs."""

    def __init__(
        self,
        alliances: AlliancePolicy,
        combat_resolver: CombatRoundResolver,
        snapshot_builder: BattleSnapshotBuilder,
        occupation_policy: BattleOccupationPolicy,
    ) -> None:
        self._alliances = alliances
        self._combat_resolver = combat_resolver
        self._snapshot_builder = snapshot_builder
        self._occupation_policy = occupation_policy

    def scan(self, request: BattleRegionScanRequest) -> BattleRegionScanResult:
        unit_rows = request.unit_rows
        casualty_rows = (
            [] if request.casualty_table is None else request.casualty_table.to_dicts()
        )
        occupation_rows = (
            []
            if request.occupation_table is None or request.occupation_table.is_empty()
            else request.occupation_table.to_dicts()
        )
        stationary_units, region_rows, original_controllers = self.prepare_battle_regions(
            request.regions,
            unit_rows,
        )
        result = BattleRegionScanResult(
            unit_rows=unit_rows,
            casualty_rows=casualty_rows,
            occupation_rows=occupation_rows,
            stationary_units=stationary_units,
            region_rows=region_rows,
            original_controllers=original_controllers,
            battle_rows=[],
            battle_unit_rows=[],
            participant_rows=[],
            active_battle_ids=set(),
            victorious_battles={},
            victorious_sides={},
            battle_regions={},
            battle_metadata={},
        )
        regions_by_id = {
            int(row.get("id") or 0): row
            for row in region_rows
            if int(row.get("id") or 0) > 0
        }

        # Stable battle-ID ordering keeps multi-region event sequences replayable
        # even when numeric region IDs do not share the same lexical order.
        region_order = sorted(
            stationary_units,
            key=lambda region_id: self.battle_iteration_key(
                region_id,
                stationary_units,
                request.wars,
            ),
        )
        for region_id in region_order:
            region_row = regions_by_id.get(region_id)
            if region_row is not None:
                self._process_region(request, result, region_id, region_row)
        return result

    def _process_region(
        self,
        request: BattleRegionScanRequest,
        result: BattleRegionScanResult,
        region_id: int,
        region_row: dict[str, Any],
    ) -> None:
        local_units = result.stationary_units[region_id]
        present_owners = {
            normalize_country_tag(row.get("owner"))
            for row in local_units
            if normalize_country_tag(row.get("owner"))
        }
        if not present_owners:
            return

        conflict = request.wars.active_battle_for_region(present_owners)
        if conflict is None:
            result.occupation_rows = self._occupation_policy.update_uncontested_region(
                region_id,
                region_row,
                local_units,
                request.wars,
                result.occupation_rows,
                int(request.state.time.total_minutes),
            )
            return

        self._process_contested_region(
            request,
            result,
            region_id,
            region_row,
            local_units,
            present_owners,
            conflict,
        )

    def _process_contested_region(
        self,
        request: BattleRegionScanRequest,
        result: BattleRegionScanResult,
        region_id: int,
        region_row: dict[str, Any],
        local_units: list[dict[str, Any]],
        present_owners: set[str],
        conflict: ConflictContext,
    ) -> None:
        state = request.state
        wars = request.wars
        self._mark_occupation_contested(result.occupation_rows, region_id, state)
        conflict = self.expand_battle_participants(
            state,
            wars,
            conflict,
            local_units,
            region_id,
            present_owners,
        )
        battle_mode = self.battle_mode(local_units)
        battle_id = self.battle_id(region_id, conflict.war_id)
        result.battle_regions[battle_id] = region_id
        result.active_battle_ids.add(battle_id)
        if battle_id not in request.existing_battles:
            state.events.append(EventBattleStarted(
                battle_id=battle_id,
                region_id=region_id,
                war_id=conflict.war_id,
                side_a_countries=tuple(sorted(conflict.side_a_members)),
                side_b_countries=tuple(sorted(conflict.side_b_members)),
                started_at_minute=int(state.time.total_minutes),
            ))

        self.cancel_contact_readiness(state, local_units)
        prior_row = self.battle_row(state.tables.get(BATTLE_TABLE), battle_id)
        anchor = resolve_battle_anchor(local_units, region_row, prior_row)
        previous_a = self._combat_resolver.total_strength(local_units, conflict.side_a_members)
        previous_b = self._combat_resolver.total_strength(local_units, conflict.side_b_members)
        result.battle_metadata[battle_id] = {
            "war_id": conflict.war_id,
            "mode": battle_mode,
            "side_a_tags": conflict.side_a_tags,
            "side_b_tags": conflict.side_b_tags,
            "prior_row": prior_row,
            "anchor": anchor,
            "previous_a": previous_a,
            "previous_b": previous_b,
            "round_resolved": False,
        }

        resolve_this_tick = request.should_resolve or (
            battle_mode == "assault"
            and any(
                str(row.get("id") or "") in request.assaulting_unit_ids
                for row in local_units
            )
        )
        self._resolve_round_if_needed(
            request,
            result,
            battle_id,
            battle_mode,
            local_units,
            conflict,
            prior_row,
            resolve_this_tick,
        )

        side_a_strength = self._combat_resolver.total_strength(local_units, conflict.side_a_members)
        side_b_strength = self._combat_resolver.total_strength(local_units, conflict.side_b_members)
        result.battle_metadata[battle_id]["side_a_strength"] = side_a_strength
        result.battle_metadata[battle_id]["side_b_strength"] = side_b_strength
        if side_a_strength > 0 and side_b_strength > 0:
            snapshot = self._snapshot_builder.build_active_battle_snapshot(
                ActiveBattleSnapshotRequest(
                    battle_units_table=state.tables.get(BATTLE_UNITS_TABLE),
                    region_id=region_id,
                    local_units=local_units,
                    conflict=conflict,
                    battle_id=battle_id,
                    battle_mode=battle_mode,
                    now=int(state.time.total_minutes),
                    prior_row=prior_row,
                    anchor=anchor,
                    previous_a=previous_a,
                    previous_b=previous_b,
                    side_a_strength=side_a_strength,
                    side_b_strength=side_b_strength,
                    resolve_this_tick=resolve_this_tick,
                )
            )
            result.battle_rows.append(snapshot.battle_row)
            result.battle_unit_rows.extend(snapshot.battle_unit_rows)
            result.participant_rows.extend(snapshot.participant_rows)
            if snapshot.updated_event is not None:
                state.events.append(snapshot.updated_event)
            return

        winner = self._combat_resolver.winning_country(local_units, conflict)
        if winner:
            result.victorious_battles[battle_id] = winner
            result.victorious_sides[battle_id] = (
                "SIDE_A" if winner in conflict.side_a_members else "SIDE_B"
            )

    def _resolve_round_if_needed(
        self,
        request: BattleRegionScanRequest,
        result: BattleRegionScanResult,
        battle_id: str,
        battle_mode: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        prior_row: dict[str, Any],
        resolve_this_tick: bool,
    ) -> None:
        if not resolve_this_tick:
            return
        result.battle_metadata[battle_id]["round_resolved"] = True
        pre_round_strength = {
            str(row.get("id") or ""): max(0, int(row.get("strength") or 0))
            for row in local_units
        }
        victor = self._combat_resolver.apply_combat_round(
            local_units,
            conflict,
            battle_mode,
        )
        self._combat_resolver.record_round_casualties(
            result.casualty_rows,
            battle_id,
            int(prior_row.get("round") or 0) + 1,
            local_units,
            conflict,
            pre_round_strength,
            int(request.state.time.total_minutes),
        )
        if victor is not None:
            result.victorious_battles[battle_id] = victor
            result.victorious_sides[battle_id] = (
                "SIDE_A" if victor in conflict.side_a_members else "SIDE_B"
            )
        post_a = self._combat_resolver.total_strength(local_units, conflict.side_a_members)
        post_b = self._combat_resolver.total_strength(local_units, conflict.side_b_members)
        if post_a <= 0 and post_b <= 0:
            result.victorious_battles[battle_id] = ""
            result.victorious_sides[battle_id] = ""

    def prepare_battle_regions(
        self,
        regions: pl.DataFrame,
        unit_rows: list[dict[str, Any]],
    ) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]], dict[int, str]]:
        stationary_units = self.stationary_units_by_region(unit_rows)
        relevant_region_ids = sorted(stationary_units)
        region_rows = (
            regions.filter(pl.col("id").is_in(relevant_region_ids)).to_dicts()
            if relevant_region_ids
            else []
        )
        original_controllers = {
            int(row.get("id") or 0): str(row.get("controller") or "")
            for row in region_rows
        }
        return stationary_units, region_rows, original_controllers

    @staticmethod
    def stationary_units_by_region(
        unit_rows: list[dict[str, Any]],
    ) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in sorted(unit_rows, key=lambda unit: str(unit.get("id") or "")):
            # Tactical withdrawals remain attached to their battle until the route lifecycle resolves.
            if bool(row.get("is_moving", False)) and str(row.get("unit_lifecycle") or "") not in {
                "battle_retreating",
                "battle_disengaging",
            }:
                continue
            region_id = int(row.get("current_region_id") or 0)
            if region_id <= 0:
                continue
            grouped.setdefault(region_id, []).append(row)
        return grouped

    def battle_iteration_key(
        self,
        region_id: int,
        stationary_units: dict[int, list[dict[str, Any]]],
        wars: WarIndex,
    ) -> tuple[int, str, int]:
        owners = {
            normalize_country_tag(row.get("owner"))
            for row in stationary_units[region_id]
            if normalize_country_tag(row.get("owner"))
        }
        conflict = wars.active_battle_for_region(owners)
        if conflict is not None:
            return (0, self.battle_id(region_id, conflict.war_id), region_id)
        return (1, f"region-{region_id:010d}", region_id)

    def expand_battle_participants(
        self,
        state: GameState,
        wars: WarIndex,
        conflict: ConflictContext,
        local_units: list[dict[str, Any]],
        region_id: int,
        present_owners: set[str],
    ) -> ConflictContext:
        eligibility = self._alliances.expand(
            next(war for war in wars._active_wars if war.war_id == conflict.war_id),
            local_units,
            state.tables.get("countries_treaties"),
        )
        conflict = ConflictContext(
            war_id=conflict.war_id,
            side_a_members=eligibility.side_a,
            side_b_members=eligibility.side_b,
            side_a_tags=frozenset(tag for tag in present_owners if tag in eligibility.side_a),
            side_b_tags=frozenset(tag for tag in present_owners if tag in eligibility.side_b),
            roles=eligibility.roles,
            bases=eligibility.bases,
        )
        for country_id, reason in eligibility.rejected:
            state.events.append(EventBattleParticipantRejected(
                battle_id=self.battle_id(region_id, conflict.war_id),
                country_id=country_id,
                reason=reason,
                at_minute=int(state.time.total_minutes),
            ))
        return conflict

    @staticmethod
    def cancel_contact_readiness(
        state: GameState,
        local_units: list[dict[str, Any]],
    ) -> None:
        # Contact and explicit assaults interrupt a readiness change before the same tick can complete it.
        contact_ids = [
            str(row.get("id") or "")
            for row in local_units
            if str(row.get("engagement_mode") or "").lower() in {"assault", "positional"}
        ]
        if contact_ids:
            contact_id_set = set(contact_ids)
            cancel_readiness_for_contact(state, contact_ids)
            for unit in local_units:
                if str(unit.get("id") or "") in contact_id_set:
                    unit["readiness_transition_id"] = ""
                    unit["readiness_progress"] = 0.0
                    unit["readiness_eta_minute"] = 0

    @staticmethod
    def battle_mode(local_units: list[dict[str, Any]]) -> str:
        return (
            "assault"
            if any(str(row.get("engagement_mode") or "").lower() == "assault" for row in local_units)
            else "positional"
        )

    @staticmethod
    def battle_id(region_id: int, war_id: str) -> str:
        return f"battle-region-{region_id}-{war_id}"

    @staticmethod
    def battle_row(battles: pl.DataFrame | None, battle_id: str) -> dict[str, Any]:
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return {}
        matches = battles.filter(pl.col("id") == battle_id)
        return matches.to_dicts()[0] if not matches.is_empty() else {}

    @staticmethod
    def _mark_occupation_contested(
        occupation_rows: list[dict[str, Any]],
        region_id: int,
        state: GameState,
    ) -> None:
        for occupation in occupation_rows:
            if int(occupation.get("region_id") or 0) == region_id:
                if not bool(occupation.get("contested")) or str(occupation.get("occupation_status")) != "contested":
                    occupation["contested"] = True
                    occupation["occupation_status"] = "contested"
                    occupation["updated_at_minute"] = int(state.time.total_minutes)
