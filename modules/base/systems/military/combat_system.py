from __future__ import annotations

from typing import Any, Iterable

import polars as pl

from modules.base.systems.military.combat_round_resolver import (
    CombatOutcome as CombatOutcome,
    CombatResolutionPolicy as CombatResolutionPolicy,
    CombatRoundResolver,
    normalize_country_tag as normalize_country_tag,
)

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.events import EventNewHour
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState
from modules.base.systems.military.alliance_policy import AlliancePolicy
from modules.base.systems.military.battle_conclusion_builder import BattleConclusionBuilder
from modules.base.systems.military.battle_occupation_policy import (
    BattleOccupationPolicy,
    UNCLAIMED_TAGS as UNCLAIMED_TAGS,
)
from modules.base.systems.military.battle_region_processor import (
    BattleRegionProcessor,
    BattleRegionScanRequest,
)
from modules.base.systems.military.combat_state_publisher import (
    BATTLE_TABLE,
    BATTLE_UNITS_TABLE as BATTLE_UNITS_TABLE,
    COUNTRIES_WARS_TABLE,
    REGIONS_TABLE,
    UNITS_TABLE,
    CombatStatePublisher,
)
from modules.base.systems.military.battle_snapshot_builder import (
    BattleSnapshotBuilder,
)
from modules.base.systems.military.war_index import (
    ConflictContext as ConflictContext,
    WarIndex as WarIndex,
    WarRecord as WarRecord,
)
from modules.base.systems.military.battle_victory_finalizer import (
    BattleVictoryFinalizer,
    VictoryFinalizationOperations,
    VictoryResolutionBatch as _VictoryResolutionBatch,
)
from modules.base.systems.military.readiness_policy import ReadinessPolicy


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
        "_battle_conclusion_builder": SYSTEM_STATE_HELPER,
        "_occupation_policy": SYSTEM_STATE_HELPER,
        "_battle_region_processor": SYSTEM_STATE_HELPER,
        "_state_publisher": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._policy = CombatResolutionPolicy()
        self._readiness = ReadinessPolicy()
        self._combat_round_resolver = CombatRoundResolver(
            policy=self._policy,
            readiness=self._readiness,
        )
        self._battle_snapshot_builder = BattleSnapshotBuilder(self._readiness)
        self._battle_conclusion_builder = BattleConclusionBuilder(
            self._battle_snapshot_builder
        )
        self._alliances = AlliancePolicy()
        self._occupation_policy = BattleOccupationPolicy(self._combat_round_resolver)
        self._battle_region_processor = BattleRegionProcessor(
            alliances=self._alliances,
            combat_resolver=self._combat_round_resolver,
            snapshot_builder=self._battle_snapshot_builder,
            occupation_policy=self._occupation_policy,
        )
        self._state_publisher = CombatStatePublisher(
            battle_schema=BATTLE_SCHEMA,
            battle_units_schema=BATTLE_UNITS_SCHEMA,
            participants_schema=BATTLE_PARTICIPANTS_SCHEMA,
            occupation_schema=OCCUPATION_SCHEMA,
        )
        self._victory_finalizer = BattleVictoryFinalizer(
            VictoryFinalizationOperations(
                battle_row_lookup=self._battle_region_processor.battle_row,
                concluded_battle_row_builder=(
                    self._battle_conclusion_builder.build_concluded_battle_row
                ),
                battle_ended_event_factory=(
                    self._battle_conclusion_builder.build_battle_ended_event
                ),
                concluded_occupation_updater=(
                    self._occupation_policy.update_concluded_occupation
                ),
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

    def update(self, state: GameState, delta_time: float) -> None:
        if REGIONS_TABLE not in state.tables or UNITS_TABLE not in state.tables:
            self._state_publisher.reset_battle_tables(state)
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

        scan.occupation_rows = self._victory_finalizer.finalize(
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

        self._state_publisher.publish_tick(
            state,
            regions,
            units.schema,
            casualty_table,
            scan,
        )

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
