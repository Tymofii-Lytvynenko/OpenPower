from __future__ import annotations

from typing import Any, Iterable

import polars as pl

from modules.base.systems.military.combat_round_resolver import (
    CombatOutcome as CombatOutcome,
    CombatResolutionPolicy as CombatResolutionPolicy,
    CombatRoundResolver,
    normalize_country_tag,
)

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.events import EventBattleEnded, EventBattleUpdated, EventNewHour, EventOccupationChanged
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState
from modules.base.systems.military.alliance_policy import AlliancePolicy
from modules.base.systems.military.battle_anchor_policy import BattleAnchor
from modules.base.systems.military.battle_occupation_policy import (
    BattleOccupationPolicy,
    UNCLAIMED_TAGS as UNCLAIMED_TAGS,
)
from modules.base.systems.military.battle_public_counts import public_battle_counts
from modules.base.systems.military.battle_region_processor import (
    BattleRegionProcessor,
    BattleRegionScanRequest,
)
from modules.base.systems.military.battle_snapshot_builder import (
    BattleRowRequest,
    BattleSnapshotBuilder,
    BattleStrengthDelta,
)
from modules.base.systems.military.war_index import (
    ConflictContext as ConflictContext,
    WarIndex as WarIndex,
    WarRecord as WarRecord,
)
from modules.base.systems.military.battle_victory_finalizer import (
    BattleEndedEventRequest,
    BattleVictoryFinalizer,
    ConcludedBattleRowRequest,
    ConcludedOccupationUpdateRequest,
    VictoryFinalizationOperations,
    VictoryResolutionBatch as _VictoryResolutionBatch,
)
from modules.base.systems.military.readiness_policy import ReadinessPolicy


BATTLE_TABLE = "battles"
BATTLE_UNITS_TABLE = "battle_units"
COUNTRIES_WARS_TABLE = "countries_wars"
REGIONS_TABLE = "regions"
UNITS_TABLE = "units"

BATTLE_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "war_id": pl.Utf8,
    "region_id": pl.Int32,
    "anchor_latitude": pl.Float64,
    "anchor_longitude": pl.Float64,
    "anchor_source": pl.Utf8,
    "attacker_side": pl.Utf8,
    "mode": pl.Utf8,
    "defender_side": pl.Utf8,
    "balance": pl.Float64,
    "side_a_strength": pl.Float64,
    "side_b_strength": pl.Float64,
    "side_a_losses": pl.Int64,
    "side_b_losses": pl.Int64,
    "round": pl.Int32,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "concluded_at_minute": pl.Int64,
    "victor_side": pl.Utf8,
    "status": pl.Utf8,
}

BATTLE_UNITS_SCHEMA: dict[str, pl.DataType] = {
    "battle_id": pl.Utf8,
    "unit_id": pl.Utf8,
    "country_id": pl.Utf8,
    "side": pl.Utf8,
    "role": pl.Utf8,
    "readiness_status": pl.Utf8,
    "contribution_weight": pl.Float64,
    "effective_strength": pl.Float64,
    "strength_share": pl.Float64,
}

BATTLE_PARTICIPANTS_SCHEMA: dict[str, pl.DataType] = {
    "battle_id": pl.Utf8,
    "country_id": pl.Utf8,
    "side": pl.Utf8,
    "role": pl.Utf8,
    "eligibility_basis": pl.Utf8,
    "unit_count": pl.Int32,
    "weighted_strength": pl.Float64,
}

OCCUPATION_SCHEMA: dict[str, pl.DataType] = {
    "region_id": pl.Int32,
    "controller_country_id": pl.Utf8,
    "garrison_strength": pl.Int64,
    "resistance": pl.Float64,
    "occupation_status": pl.Utf8,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "contested": pl.Boolean,
}

UNIT_REQUIRED_COLUMNS: dict[str, tuple[pl.DataType, Any]] = {
    "id": (pl.Utf8, ""),
    "owner": (pl.Utf8, ""),
    "strength": (pl.Int64, 0),
    "engagement_mode": (pl.Utf8, ""),
    "current_region_id": (pl.Int32, 0),
    "is_moving": (pl.Boolean, False),
    "readiness_status": (pl.Utf8, "ready"),
    "combat_posture": (pl.Utf8, "hold"),
    "combat_strength_modifier": (pl.Float64, 1.0),
    "war_exhaustion_modifier": (pl.Float64, 1.0),
    "combat_casualty_modifier": (pl.Float64, 1.0),
    "combat_defense_modifier": (pl.Float64, 1.0),
    "combat_attack_risk_modifier": (pl.Float64, 1.0),
    "combat_readiness_modifier": (pl.Float64, 1.0),
    "combat_holding_modifier": (pl.Float64, 1.0),
    "combat_counterattack_modifier": (pl.Float64, 1.0),
}


class CombatSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'countries_wars', 'countries_treaties', 'battles', 'unit_readiness_transitions', 'unit_capability_projections', 'battle_casualty_records', 'battle_public_counts'}),
        writes=frozenset({'regions', 'units', 'battles', 'battle_units', 'battle_participants', 'battle_casualty_records', 'occupations', 'battle_public_counts'}),
        handles=frozenset({ActionAttackUnit, ActionMoveUnit}),
        phase=SystemPhase.COMBAT,
    )
    runtime_state_contract = {
        "_policy": SYSTEM_STATE_HELPER,
        "_readiness": SYSTEM_STATE_HELPER,
        "_alliances": SYSTEM_STATE_HELPER,
        "_victory_finalizer": SYSTEM_STATE_HELPER,
        "_combat_round_resolver": SYSTEM_STATE_HELPER,
        "_battle_snapshot_builder": SYSTEM_STATE_HELPER,
        "_occupation_policy": SYSTEM_STATE_HELPER,
        "_battle_region_processor": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._policy = CombatResolutionPolicy()
        self._readiness = ReadinessPolicy()
        self._combat_round_resolver = CombatRoundResolver(
            policy=self._policy,
            readiness=self._readiness,
        )
        self._battle_snapshot_builder = BattleSnapshotBuilder(self._readiness)
        self._alliances = AlliancePolicy()
        self._occupation_policy = BattleOccupationPolicy(self._combat_round_resolver)
        self._battle_region_processor = BattleRegionProcessor(
            alliances=self._alliances,
            combat_resolver=self._combat_round_resolver,
            snapshot_builder=self._battle_snapshot_builder,
            occupation_policy=self._occupation_policy,
        )
        self._victory_finalizer = BattleVictoryFinalizer(
            VictoryFinalizationOperations(
                battle_row_lookup=self._battle_row,
                concluded_battle_row_builder=self._concluded_battle_row,
                battle_ended_event_factory=self._battle_ended_event,
                concluded_occupation_updater=self._update_concluded_occupation,
            )
        )
        self._capability_index: dict[str, dict[str, Any]] = {}

    @property
    def _capability_index(self) -> dict[str, dict[str, Any]]:
        return self._combat_round_resolver.capability_index

    @_capability_index.setter
    def _capability_index(self, value: dict[str, dict[str, Any]]) -> None:
        self._combat_round_resolver.set_capability_index(value)

    def _apply_combat_round(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        mode: str,
    ) -> str | None:
        return self._combat_round_resolver.apply_combat_round(local_units, conflict, mode)

    def _total_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        return self._combat_round_resolver.total_strength(local_units, eligible_tags)

    def _casualty_modifier(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> float:
        return self._combat_round_resolver._casualty_modifier(local_units, eligible_tags)

    def _side_damage_factor(
        self,
        local_units: list[dict[str, Any]],
        attacking_tags: Iterable[str],
        defending_tags: Iterable[str],
    ) -> float:
        return self._combat_round_resolver._side_damage_factor(
            local_units,
            attacking_tags,
            defending_tags,
        )

    def _capability_damage_factor(
        self,
        unit: dict[str, Any],
        defenders: list[dict[str, Any]],
    ) -> float:
        return self._combat_round_resolver._capability_damage_factor(unit, defenders)

    def _raw_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        return self._combat_round_resolver.raw_strength(local_units, eligible_tags)

    @property
    def id(self) -> str:
        return "base.combat"

    @property
    def dependencies(self) -> list[str]:
        return ["base.military", "base.diplomacy"]

    def _prepare_battle_regions(self, regions, unit_rows):
        return self._battle_region_processor.prepare_battle_regions(regions, unit_rows)

    def _battle_iteration_key(self, region_id: int, stationary_units, wars) -> tuple[int, str, int]:
        return self._battle_region_processor.battle_iteration_key(region_id, stationary_units, wars)


    def _expand_battle_participants(self, state, wars, conflict, local_units, region_id, present_owners):
        return self._battle_region_processor.expand_battle_participants(
            state,
            wars,
            conflict,
            local_units,
            region_id,
            present_owners,
        )

    @staticmethod
    def _cancel_contact_readiness(state: GameState, local_units) -> None:
        BattleRegionProcessor.cancel_contact_readiness(state, local_units)


    def update(self, state: GameState, delta_time: float) -> None:
        if REGIONS_TABLE not in state.tables or UNITS_TABLE not in state.tables:
            self._reset_battle_tables(state)
            return

        regions = self._ensure_regions_table(state.get_table(REGIONS_TABLE))
        units = self._ensure_units_table(state.get_table(UNITS_TABLE))
        projection_table = state.tables.get("unit_capability_projections")
        self._combat_round_resolver.load_capability_projections(projection_table)
        wars = WarIndex.from_table(state.tables.get(COUNTRIES_WARS_TABLE))
        existing_battles = self._existing_active_battle_ids(state.tables.get(BATTLE_TABLE))
        should_resolve = (not state.time.is_paused) and any(
            isinstance(event, EventNewHour) for event in state.events
        )
        assaulting_unit_ids = {
            action.attacker_unit_id if isinstance(action, ActionAttackUnit) else action.unit_id
            for action in state.current_actions
            if isinstance(action, (ActionAttackUnit, ActionMoveUnit))
        }

        casualty_table = state.tables.get("battle_casualty_records")
        scan = self._battle_region_processor.scan(
            BattleRegionScanRequest(
                state=state,
                regions=regions,
                unit_rows=units.to_dicts(),
                wars=wars,
                existing_battles=existing_battles,
                should_resolve=should_resolve,
                assaulting_unit_ids=assaulting_unit_ids,
                casualty_table=casualty_table,
                occupation_table=state.tables.get("occupations"),
            )
        )

        scan.occupation_rows = self._finalize_victories(
            state,
            _VictoryResolutionBatch(
                scan.victorious_battles,
                scan.victorious_sides,
                scan.active_battle_ids,
                scan.battle_regions,
                scan.battle_metadata,
                scan.battle_rows,
                scan.unit_rows,
                scan.region_rows,
                scan.occupation_rows,
            ),
        )

        scan.unit_rows = [
            row for row in scan.unit_rows if int(row.get("strength") or 0) > 0
        ]
        self._update_table_if_changed(
            state,
            UNITS_TABLE,
            self._frame_from_rows(units.schema, scan.unit_rows),
        )
        self._publish_controller_changes(
            state,
            regions,
            scan.region_rows,
            scan.original_controllers,
        )
        self._update_table_if_changed(
            state,
            BATTLE_TABLE,
            self._frame_from_rows(BATTLE_SCHEMA, scan.battle_rows),
        )
        self._update_table_if_changed(
            state,
            BATTLE_UNITS_TABLE,
            self._frame_from_rows(BATTLE_UNITS_SCHEMA, scan.battle_unit_rows),
        )
        alive_ids = {str(row.get("id")) for row in scan.unit_rows}
        self._update_table_if_changed(
            state,
            "battle_public_counts",
            public_battle_counts(
                scan.battle_rows,
                [
                    row
                    for row in scan.battle_unit_rows
                    if str(row.get("unit_id")) in alive_ids
                ],
                scan.unit_rows,
            ),
        )
        self._update_table_if_changed(
            state,
            "battle_participants",
            self._frame_from_rows(BATTLE_PARTICIPANTS_SCHEMA, scan.participant_rows),
        )
        self._publish_casualties(state, scan.casualty_rows, casualty_table)
        self._update_table_if_changed(
            state,
            "occupations",
            self._frame_from_rows(OCCUPATION_SCHEMA, scan.occupation_rows),
        )

        if "countries" in state.tables:
            self._update_table_if_changed(
                state,
                "countries",
                self._sync_country_strengths(state.get_table("countries"), scan.unit_rows),
            )

    def _finalize_victories(
        self,
        state: GameState,
        batch: _VictoryResolutionBatch,
    ) -> list[dict[str, Any]]:
        return self._victory_finalizer.finalize(state, batch)

    def _replace_occupation(self, occupation_rows, region_id, controller, local_units, now):
        return self._occupation_policy.replace_occupation(
            occupation_rows,
            region_id,
            controller,
            local_units,
            now,
        )

    def _update_uncontested_region(
        self, region_id, region_row, local_units, wars, occupation_rows, now,
    ):
        return self._occupation_policy.update_uncontested_region(
            region_id,
            region_row,
            local_units,
            wars,
            occupation_rows,
            now,
        )

    def _concluded_battle_row(
        self,
        request: ConcludedBattleRowRequest,
    ) -> dict[str, Any]:
        prior_row = request.prior_row
        battle_id = request.battle_id
        region_id = request.region_id
        metadata = request.metadata
        now = request.now
        victor_side = request.victor_side
        concluded_row = dict(prior_row)
        if not concluded_row:
            side_a_strength = int(metadata.get("side_a_strength", 0))
            side_b_strength = int(metadata.get("side_b_strength", 0))
            previous_a = int(metadata.get("previous_a", 0))
            previous_b = int(metadata.get("previous_b", 0))
            round_number = 1 if bool(metadata.get("round_resolved")) else 0
            concluded_row = self._build_battle_row(
                battle_id=battle_id,
                mode=str(metadata.get("mode") or "positional"),
                region_id=region_id,
                side_a_tags=frozenset(metadata.get("side_a_tags") or ()),
                side_b_tags=frozenset(metadata.get("side_b_tags") or ()),
                side_a_strength=side_a_strength,
                side_b_strength=side_b_strength,
                war_id=str(metadata.get("war_id") or ""),
                now=now,
                side_a_losses=max(0, previous_a - side_a_strength) if bool(metadata.get("round_resolved")) else 0,
                side_b_losses=max(0, previous_b - side_b_strength) if bool(metadata.get("round_resolved")) else 0,
                status="concluded",
                round_number=round_number,
                anchor=metadata.get("anchor"),
            )
        else:
            if bool(metadata.get("round_resolved")):
                current_a = int(metadata.get("side_a_strength", concluded_row.get("side_a_strength") or 0))
                current_b = int(metadata.get("side_b_strength", concluded_row.get("side_b_strength") or 0))
                previous_a = int(metadata.get("previous_a", current_a))
                previous_b = int(metadata.get("previous_b", current_b))
                concluded_row["side_a_strength"] = float(current_a)
                concluded_row["side_b_strength"] = float(current_b)
                concluded_row["balance"] = float(current_a / max(1, current_a + current_b))
                concluded_row["side_a_losses"] = int(concluded_row.get("side_a_losses") or 0) + max(0, previous_a - current_a)
                concluded_row["side_b_losses"] = int(concluded_row.get("side_b_losses") or 0) + max(0, previous_b - current_b)
                concluded_row["round"] = int(concluded_row.get("round") or 0) + 1
        concluded_row["status"] = "concluded"
        concluded_row["updated_at_minute"] = now
        concluded_row["concluded_at_minute"] = now
        concluded_row["victor_side"] = victor_side
        return concluded_row

    def _update_concluded_occupation(
        self,
        request: ConcludedOccupationUpdateRequest,
    ) -> list[dict[str, Any]]:
        return self._occupation_policy.update_concluded_occupation(request)

    @staticmethod
    def _battle_updated_event(row: dict[str, Any], conflict: ConflictContext, now: int) -> EventBattleUpdated:
        return BattleSnapshotBuilder.build_updated_event(row, conflict, now)

    @staticmethod
    def _battle_ended_event(
        request: BattleEndedEventRequest,
    ) -> EventBattleEnded:
        # Outcomes are emitted after scanning every region. The loop's last
        # local_units/conflict belongs to another battle when several end
        # together; recipient and side metadata must come from this result.
        concluded_row = request.concluded_row
        side_a_countries = WarIndex._normalize_side(concluded_row.get("attacker_side"))
        side_b_countries = WarIndex._normalize_side(concluded_row.get("defender_side"))
        return EventBattleEnded(
            battle_id=request.battle_id,
            victor_tag=request.victor,
            victor_side=str(concluded_row.get("victor_side") or ""),
            region_id=request.region_id,
            concluded_at_minute=request.now,
            side_a_losses=int(concluded_row.get("side_a_losses") or 0),
            side_b_losses=int(concluded_row.get("side_b_losses") or 0),
            participant_countries=tuple(sorted(side_a_countries | side_b_countries)),
            side_a_country_ids=tuple(sorted(side_a_countries)),
            side_b_country_ids=tuple(sorted(side_b_countries)),
        )

    def _publish_controller_changes(self, state, regions, region_rows, original_controllers) -> None:
        controller_updates = {
            int(row.get("id") or 0): str(row.get("controller") or "")
            for row in region_rows
            if str(row.get("controller") or "")
            != original_controllers.get(int(row.get("id") or 0), "")
        }
        updated_regions = regions
        if controller_updates:
            all_region_rows = regions.to_dicts()
            for region_id, controller in controller_updates.items():
                state.events.append(EventOccupationChanged(
                    region_id=region_id,
                    previous_controller=str(original_controllers.get(region_id) or ""),
                    controller=controller,
                    source="battle_resolution",
                    at_minute=int(state.time.total_minutes),
                ))
                self._set_region_controller(all_region_rows, region_id, controller)
            updated_regions = self._frame_from_rows(regions.schema, all_region_rows)
        self._update_table_if_changed(state, REGIONS_TABLE, updated_regions)

    def _publish_casualties(self, state, casualty_rows, casualty_table) -> None:
        if casualty_rows != ([] if casualty_table is None else casualty_table.to_dicts()):
            casualty_schema = {
                "id": pl.Utf8, "battle_id": pl.Utf8, "unit_id": pl.Utf8,
                "country_id": pl.Utf8, "side": pl.Utf8, "unit_type": pl.Utf8,
                "losses": pl.Int64, "round": pl.Int32, "created_at_minute": pl.Int64,
            }
            updated_casualties = pl.DataFrame(sorted(casualty_rows, key=lambda row: str(row.get("id") or "")), schema=casualty_schema) if casualty_rows else pl.DataFrame(schema=casualty_schema)
            self._update_table_if_changed(state, "battle_casualty_records", updated_casualties)

    def _ensure_regions_table(self, regions: pl.DataFrame) -> pl.DataFrame:
        if "controller" not in regions.columns:
            return regions.with_columns(pl.col("owner").alias("controller"))
        return regions

    def _ensure_units_table(self, units: pl.DataFrame) -> pl.DataFrame:
        for column, (_, default_value) in UNIT_REQUIRED_COLUMNS.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        if "equipment_quantity" not in units.columns:
            # Match the unit-table migration so legacy group strength remains a usable quantity.
            units = units.with_columns(
                pl.col("strength").cast(pl.Int64, strict=False).fill_null(0).alias("equipment_quantity")
            )

        casted_columns = []
        for column, (dtype, _) in UNIT_REQUIRED_COLUMNS.items():
            casted_columns.append(pl.col(column).cast(dtype).alias(column))

        return units.with_columns(casted_columns)

    def _stationary_units_by_region(self, unit_rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        return self._battle_region_processor.stationary_units_by_region(unit_rows)

    def engagement_anchor_region(self, contact_units: Iterable[dict[str, Any]]) -> int:
        """Return the deterministic region anchor for an engagement contact."""
        candidates = sorted(
            (
                int(row.get("current_region_id") or 0),
                str(row.get("id") or ""),
            )
            for row in contact_units
            if int(row.get("current_region_id") or 0) > 0
        )
        return candidates[0][0] if candidates else 0

    def _battle_mode(self, local_units: list[dict[str, Any]]) -> str:
        return self._battle_region_processor.battle_mode(local_units)

    def _lifecycle_status(
        self,
        prior_row: dict[str, Any],
        round_resolved: bool,
        previous_a: int,
        previous_b: int,
        current_a: int,
        current_b: int,
    ) -> str:
        return self._battle_snapshot_builder.lifecycle_status(
            prior_row,
            BattleStrengthDelta(
                round_resolved=round_resolved,
                previous_a=previous_a,
                previous_b=previous_b,
                current_a=current_a,
                current_b=current_b,
            ),
        )

    def _battle_units_changed(
        self,
        battle_units: pl.DataFrame | None,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> bool:
        return self._battle_snapshot_builder.battle_units_changed(
            battle_units,
            battle_id,
            local_units,
            conflict,
        )


    def _build_battle_row(
        self,
        battle_id: str,
        war_id: str,
        mode: str,
        region_id: int,
        side_a_tags: frozenset[str],
        side_b_tags: frozenset[str],
        side_a_strength: int,
        side_b_strength: int,
        now: int,
        side_a_losses: int = 0,
        side_b_losses: int = 0,
        status: str = "active",
        round_number: int | None = None,
        prior_row: dict[str, Any] | None = None,
        anchor: BattleAnchor | None = None,
    ) -> dict[str, Any]:
        return self._battle_snapshot_builder.build_battle_row(
            BattleRowRequest(
                battle_id=battle_id,
                war_id=war_id,
                mode=mode,
                region_id=region_id,
                side_a_tags=side_a_tags,
                side_b_tags=side_b_tags,
                side_a_strength=side_a_strength,
                side_b_strength=side_b_strength,
                now=now,
                side_a_losses=side_a_losses,
                side_b_losses=side_b_losses,
                status=status,
                round_number=round_number,
                prior_row=prior_row,
                anchor=anchor,
            )
        )

    def _build_battle_units(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        total_strength: int,
    ) -> list[dict[str, Any]]:
        return self._battle_snapshot_builder.build_battle_units(
            battle_id,
            local_units,
            conflict,
            total_strength,
        )

    def _build_participants(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> list[dict[str, Any]]:
        return self._battle_snapshot_builder.build_participants(
            battle_id,
            local_units,
            conflict,
        )

    def _occupation_row(
        self,
        region_id: int,
        occupier: str,
        local_units: list[dict[str, Any]],
        now: int,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._occupation_policy.occupation_row(
            region_id,
            occupier,
            local_units,
            now,
            previous,
        )

    def _occupation_candidate(
        self,
        local_units: list[dict[str, Any]],
        current_controller: str,
        wars: WarIndex,
    ) -> str | None:
        return self._occupation_policy.occupation_candidate(
            local_units,
            current_controller,
            wars,
        )


    def _existing_active_battle_ids(self, battles: pl.DataFrame | None) -> set[str]:
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return set()
        if "status" not in battles.columns:
            return {str(value) for value in battles["id"].to_list()}
        return {
            str(row["id"])
            for row in battles.select(["id", "status"]).iter_rows(named=True)
            if str(row.get("status") or "").lower() == "active"
        }

    def _battle_row(self, battles: pl.DataFrame | None, battle_id: str) -> dict[str, Any]:
        return self._battle_region_processor.battle_row(battles, battle_id)

    def _sync_country_strengths(self, countries: pl.DataFrame, unit_rows: list[dict[str, Any]]) -> pl.DataFrame:
        if "id" not in countries.columns:
            return countries

        if "military_count" not in countries.columns:
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        strength_by_owner: dict[str, int] = {}
        for row in unit_rows:
            owner = self._clean_tag(row.get("owner"))
            if not owner:
                continue
            strength_by_owner[owner] = strength_by_owner.get(owner, 0) + max(0, int(row.get("strength") or 0))

        return countries.with_columns(
            pl.col("id").map_elements(
                lambda country_id: int(strength_by_owner.get(str(country_id), 0)),
                return_dtype=pl.Int64,
            ).alias("military_count")
        )

    def _set_region_controller(self, region_rows: list[dict[str, Any]], region_id: int, controller_tag: str) -> None:
        self._occupation_policy.set_region_controller(region_rows, region_id, controller_tag)

    def _battle_id(self, region_id: int, war_id: str) -> str:
        return self._battle_region_processor.battle_id(region_id, war_id)

    def _clean_tag(self, value: Any) -> str:
        return normalize_country_tag(value)

    def _reset_battle_tables(self, state: GameState) -> None:
        self._update_table_if_changed(state, BATTLE_TABLE, pl.DataFrame(schema=BATTLE_SCHEMA))
        self._update_table_if_changed(state, BATTLE_UNITS_TABLE, pl.DataFrame(schema=BATTLE_UNITS_SCHEMA))
        self._update_table_if_changed(
            state,
            "battle_participants",
            pl.DataFrame(schema=BATTLE_PARTICIPANTS_SCHEMA),
        )
        self._update_table_if_changed(state, "occupations", pl.DataFrame(schema=OCCUPATION_SCHEMA))

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True

    def _frame_from_rows(self, schema: dict[str, pl.DataType], rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=schema)
        return pl.DataFrame(rows, schema=schema)
