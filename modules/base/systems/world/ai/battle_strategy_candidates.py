from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

import polars as pl

from modules.base.systems.world.ai.common import country_frame
from src.core.ai_framework import AITableContext


BattleGroupKey: TypeAlias = tuple[str, str, str, str]
BattleSideKey: TypeAlias = tuple[str, str]
RegionSafetyKey: TypeAlias = tuple[int, str, str]
Row: TypeAlias = dict[str, Any]


@dataclass
class BattleStrategyInputs:
    controlled_countries: set[str]
    active_battles: set[str]
    participant_rows: list[Row]
    unit_by_id: dict[str, Row]
    safe_region_ids: set[RegionSafetyKey]
    reserves_by_country: dict[str, float]
    active_unit_ids: set[str]
    reorganization_cost: float
    cohesion_threshold: float
    retreat_ratio_threshold: float


@dataclass
class BattleStrategyLoadedRows:
    controlled_countries: set[str]
    active_battles: set[str]
    participant_rows: list[Row]
    participant_unit_ids: list[str]
    unit_rows: list[Row]
    unit_by_id: dict[str, Row]


@dataclass
class BattleForceGroup:
    strength: float = 0.0
    weighted_cohesion: float = 0.0
    all_safe: bool = True


@dataclass
class BattleForceGroups:
    units: dict[BattleGroupKey, BattleForceGroup]
    blocked_groups: set[BattleGroupKey]
    side_strengths: dict[BattleSideKey, float]


@dataclass(frozen=True)
class EligibleBattleParticipant:
    battle_id: str
    unit_id: str
    unit: Mapping[str, Any]
    country: str
    side: str
    strength: float


@dataclass(frozen=True)
class BattlePostureContext:
    battle_id: str
    country: str
    unit_type: str
    friendly_strength: float
    hostile_strength: float
    strength_ratio: float
    group_cohesion: float
    group_strength: float
    all_safe: bool


@dataclass(frozen=True)
class BattlePostureDecision:
    strategy: str
    reason_code: str
    utility: float


class BattleStrategyCandidateProvider(Protocol):
    def build(
        self,
        context: AITableContext,
        *,
        policy_id: str,
        cadence_days: int,
    ) -> list[Row]:
        ...


class BattleStrategyDataLoader:
    def load(self, context: AITableContext, cadence_days: int) -> BattleStrategyInputs | None:
        required_frames = self._load_required_frames(context)
        if required_frames is None:
            return None
        battles_frame, participants_frame, units_frame = required_frames

        controlled = self._load_controlled_countries(context, cadence_days)
        if not controlled:
            return None

        active_battles = self._load_active_battle_ids(battles_frame)
        if not active_battles:
            return None

        participant_rows, participant_unit_ids = self._load_participants(
            participants_frame,
            active_battles,
        )
        if not participant_unit_ids:
            return None

        unit_rows, unit_by_id = self._load_units(units_frame, participant_unit_ids)
        loaded_rows = BattleStrategyLoadedRows(
            controlled_countries=controlled,
            active_battles=active_battles,
            participant_rows=participant_rows,
            participant_unit_ids=participant_unit_ids,
            unit_rows=unit_rows,
            unit_by_id=unit_by_id,
        )
        return self._assemble_inputs(context, loaded_rows)

    @staticmethod
    def _load_required_frames(
        context: AITableContext,
    ) -> tuple[pl.LazyFrame, pl.LazyFrame, pl.LazyFrame] | None:
        battles_frame = context.table("battles")
        participants_frame = context.table("battle_units")
        units_frame = context.table("units")
        if battles_frame is None or participants_frame is None or units_frame is None:
            return None

        battle_columns = set(battles_frame.collect_schema().names())
        participant_columns = set(participants_frame.collect_schema().names())
        unit_columns = set(units_frame.collect_schema().names())
        if not {"id", "status"}.issubset(battle_columns):
            return None
        if not {"battle_id", "unit_id", "country_id", "side"}.issubset(participant_columns):
            return None
        if not {"id", "owner", "strength"}.issubset(unit_columns):
            return None
        return battles_frame, participants_frame, units_frame

    @staticmethod
    def _load_controlled_countries(context: AITableContext, cadence_days: int) -> set[str]:
        controlled = {
            str(row.get("country_id") or "").strip().upper()
            for row in country_frame(context, cadence_days).select("country_id").collect().to_dicts()
        }
        return controlled

    @staticmethod
    def _load_active_battle_ids(battles_frame: pl.LazyFrame) -> set[str]:
        active_battle_frame = battles_frame.filter(
            pl.col("status")
            .cast(pl.Utf8)
            .fill_null("")
            .replace("", "active")
            .str.strip_chars()
            .str.to_lowercase()
            .is_in(["active", "ongoing", "stalemate"])
        ).select("id").collect()
        return {
            str(value or "") for value in active_battle_frame.get_column("id").to_list()
        }

    @staticmethod
    def _load_participants(
        participants_frame: pl.LazyFrame,
        active_battles: set[str],
    ) -> tuple[list[Row], list[str]]:
        participant_rows = participants_frame.filter(
            pl.col("battle_id").cast(pl.Utf8).is_in(active_battles)
        ).collect().to_dicts()
        participant_unit_ids = sorted({
            str(row.get("unit_id") or "")
            for row in participant_rows
            if row.get("unit_id")
        })
        return participant_rows, participant_unit_ids

    @staticmethod
    def _load_units(
        units_frame: pl.LazyFrame,
        participant_unit_ids: list[str],
    ) -> tuple[list[Row], dict[str, Row]]:
        unit_rows = (
            units_frame.filter(pl.col("id").cast(pl.Utf8).is_in(participant_unit_ids))
            .collect()
            .to_dicts()
        )
        unit_by_id = {str(row.get("id") or ""): row for row in unit_rows}
        return unit_rows, unit_by_id

    def _assemble_inputs(
        self,
        context: AITableContext,
        loaded_rows: BattleStrategyLoadedRows,
    ) -> BattleStrategyInputs:
        safe_region_ids = self._load_safe_region_ids(context, loaded_rows.unit_rows)
        reserves_by_country = self._load_reserves(context, loaded_rows.controlled_countries)
        reorganization_cost = max(
            0.0,
            _finite(context.globals.get("battle_reorganization_cost_per_strength", 0.01)),
        )
        cohesion_threshold = max(
            0.0,
            min(1.0, _finite(context.globals.get("battle_ai_reorganize_cohesion_threshold", 0.4))),
        )
        retreat_ratio_threshold = max(
            0.0,
            min(1.0, _finite(context.globals.get("battle_ai_retreat_ratio", 0.35))),
        )
        active_unit_ids = self._load_active_unit_ids(context, loaded_rows.participant_unit_ids)

        return BattleStrategyInputs(
            controlled_countries=loaded_rows.controlled_countries,
            active_battles=loaded_rows.active_battles,
            participant_rows=loaded_rows.participant_rows,
            unit_by_id=loaded_rows.unit_by_id,
            safe_region_ids=safe_region_ids,
            reserves_by_country=reserves_by_country,
            active_unit_ids=active_unit_ids,
            reorganization_cost=reorganization_cost,
            cohesion_threshold=cohesion_threshold,
            retreat_ratio_threshold=retreat_ratio_threshold,
        )

    @staticmethod
    def _load_safe_region_ids(
        context: AITableContext,
        unit_rows: list[Row],
    ) -> set[RegionSafetyKey]:
        regions_frame = context.table("regions")
        if regions_frame is None:
            return set()

        region_columns = set(regions_frame.collect_schema().names())
        region_ids = BattleStrategyDataLoader._unit_region_ids(unit_rows)
        if "id" not in region_columns or not region_ids:
            return set()

        owner_column = pl.col("owner") if "owner" in region_columns else pl.lit("").alias("owner")
        controller_column = (
            pl.col("controller")
            if "controller" in region_columns
            else pl.lit("").alias("controller")
        )
        region_rows = regions_frame.filter(pl.col("id").is_in(region_ids)).select(
            "id", owner_column, controller_column,
        ).collect().to_dicts()
        return BattleStrategyDataLoader._index_safe_regions(region_rows)

    @staticmethod
    def _unit_region_ids(unit_rows: list[Row]) -> list[int]:
        return sorted({
            int(row.get("current_region_id") or 0)
            for row in unit_rows
            if int(row.get("current_region_id") or 0) > 0
        })

    @staticmethod
    def _index_safe_regions(region_rows: list[Row]) -> set[RegionSafetyKey]:
        safe_region_ids: set[RegionSafetyKey] = set()
        for region in region_rows:
            region_owner = str(region.get("owner") or "").strip().upper()
            controller = str(region.get("controller") or region_owner).strip().upper()
            if region_owner or controller:
                safe_region_ids.add((int(region.get("id") or 0), region_owner, controller))
        return safe_region_ids

    @staticmethod
    def _load_reserves(context: AITableContext, controlled: set[str]) -> dict[str, float]:
        countries_frame = context.table("countries")
        if countries_frame is None:
            return {}

        country_columns = set(countries_frame.collect_schema().names())
        if not {"id", "money_reserves"}.issubset(country_columns):
            return {}

        return {
            str(row.get("id") or "").strip().upper(): max(
                0.0,
                _finite(row.get("money_reserves")),
            )
            for row in countries_frame.filter(
                pl.col("id").cast(pl.Utf8).str.to_uppercase().is_in(sorted(controlled))
            ).select("id", "money_reserves").collect().to_dicts()
        }

    @staticmethod
    def _load_active_unit_ids(
        context: AITableContext,
        participant_unit_ids: list[str],
    ) -> set[str]:
        postures_frame = context.table("battle_force_postures")
        if postures_frame is None:
            return set()

        posture_columns = set(postures_frame.collect_schema().names())
        if not {"unit_id", "status"}.issubset(posture_columns):
            return set()

        active_statuses = {"active", "retreating", "reorganizing", "returning"}
        return {
            str(row.get("unit_id") or "")
            for row in postures_frame.filter(
                pl.col("unit_id").cast(pl.Utf8).is_in(participant_unit_ids)
            ).select("unit_id", "status").collect().to_dicts()
            if str(row.get("status") or "").strip().lower() in active_statuses
        }


class BattleParticipantEligibilityResolver:
    def resolve(
        self,
        participant: Mapping[str, Any],
        inputs: BattleStrategyInputs,
    ) -> EligibleBattleParticipant | None:
        battle_id = _string_value(participant, "battle_id")
        unit_id = _string_value(participant, "unit_id")
        unit = inputs.unit_by_id.get(unit_id)
        country = _country_code(participant.get("country_id"))
        owner = _unit_owner(unit)
        side = _country_code(participant.get("side"))
        if battle_id not in inputs.active_battles:
            return None
        if not unit:
            return None
        if country != owner:
            return None
        if not side:
            return None
        if not _has_positive_strength(unit):
            return None
        if bool(unit.get("is_moving")):
            return None

        return EligibleBattleParticipant(
            battle_id=battle_id,
            unit_id=unit_id,
            unit=unit,
            country=country,
            side=side,
            strength=float(unit.get("strength") or 0.0),
        )


class BattleForceGroupAggregator:
    def __init__(
        self,
        eligibility_resolver: BattleParticipantEligibilityResolver | None = None,
    ) -> None:
        self._eligibility_resolver = (
            eligibility_resolver
            if eligibility_resolver is not None
            else BattleParticipantEligibilityResolver()
        )

    def aggregate(self, inputs: BattleStrategyInputs) -> BattleForceGroups:
        units: dict[BattleGroupKey, BattleForceGroup] = {}
        blocked_groups: set[BattleGroupKey] = set()
        side_strengths: dict[BattleSideKey, float] = {}
        for participant in inputs.participant_rows:
            self._add_participant(participant, inputs, units, blocked_groups, side_strengths)
        return BattleForceGroups(units, blocked_groups, side_strengths)

    def _add_participant(
        self,
        participant_row: Mapping[str, Any],
        inputs: BattleStrategyInputs,
        units: dict[BattleGroupKey, BattleForceGroup],
        blocked_groups: set[BattleGroupKey],
        side_strengths: dict[BattleSideKey, float],
    ) -> None:
        participant = self._eligibility_resolver.resolve(participant_row, inputs)
        if participant is None:
            return

        side_key = (participant.battle_id, participant.side)
        side_strengths[side_key] = side_strengths.get(side_key, 0.0) + participant.strength
        if participant.country not in inputs.controlled_countries:
            return

        unit_type = str(participant.unit.get("unit_type") or "unit").strip().lower().replace(" ", "_")
        group_key = (participant.battle_id, participant.country, unit_type, participant.side)
        if self._has_existing_order(participant, inputs):
            # One order targets every matching force in a country/type group, so any existing order blocks the whole group.
            blocked_groups.add(group_key)
            return

        group = units.setdefault(group_key, BattleForceGroup())
        self._add_force_metrics(group, participant, inputs.safe_region_ids)

    @staticmethod
    def _has_existing_order(
        participant: EligibleBattleParticipant,
        inputs: BattleStrategyInputs,
    ) -> bool:
        if participant.unit_id in inputs.active_unit_ids:
            return True
        posture = str(participant.unit.get("combat_posture") or "hold").strip().lower()
        return posture in {"attack", "defend", "back_off", "retreat", "reorganize"}

    @staticmethod
    def _add_force_metrics(
        group: BattleForceGroup,
        participant: EligibleBattleParticipant,
        safe_region_ids: set[RegionSafetyKey],
    ) -> None:
        group.strength += participant.strength
        cohesion_value = participant.unit.get("cohesion")
        cohesion = 1.0 if cohesion_value is None else max(0.0, min(1.0, _finite(cohesion_value)))
        group.weighted_cohesion += participant.strength * cohesion
        region_id = int(participant.unit.get("current_region_id") or 0)
        group_safe = any(
            known_region_id == region_id
            and participant.country in {region_owner, controller}
            for known_region_id, region_owner, controller in safe_region_ids
        )
        group.all_safe = group.all_safe and group_safe


class BattlePostureSelector:
    def select(
        self,
        posture: BattlePostureContext,
        inputs: BattleStrategyInputs,
        remaining_budget: dict[str, float],
    ) -> BattlePostureDecision:
        group_cost = posture.group_strength * inputs.reorganization_cost
        if self._can_reorganize(posture, inputs, remaining_budget, group_cost):
            remaining_budget[posture.country] -= group_cost
            strategy, reason_code = "reorganize", "low_cohesion_at_safe_location"
        elif self._should_retreat(posture, inputs):
            strategy, reason_code = "retreat", "severe_local_disadvantage"
        elif posture.friendly_strength > posture.hostile_strength:
            strategy, reason_code = "attack", "local_superiority"
        else:
            strategy, reason_code = "defend", "local_disadvantage"

        utility = (
            0.95
            if strategy in {"retreat", "reorganize"}
            else 0.55 + min(0.4, abs(posture.strength_ratio - 0.5))
        )
        return BattlePostureDecision(strategy, reason_code, utility)

    @staticmethod
    def _can_reorganize(
        posture: BattlePostureContext,
        inputs: BattleStrategyInputs,
        remaining_budget: dict[str, float],
        group_cost: float,
    ) -> bool:
        return (
            posture.group_cohesion <= inputs.cohesion_threshold
            and posture.all_safe
            and remaining_budget.get(posture.country, 0.0) >= group_cost
        )

    @staticmethod
    def _should_retreat(posture: BattlePostureContext, inputs: BattleStrategyInputs) -> bool:
        return (
            posture.hostile_strength > 0
            and posture.friendly_strength / posture.hostile_strength <= inputs.retreat_ratio_threshold
        )


class BattleCandidateRowBuilder:
    def __init__(self, posture_selector: BattlePostureSelector | None = None) -> None:
        self._posture_selector = (
            posture_selector if posture_selector is not None else BattlePostureSelector()
        )

    def build_candidate_rows(
        self,
        inputs: BattleStrategyInputs,
        groups: BattleForceGroups,
        policy_id: str,
    ) -> list[Row]:
        candidates = []
        remaining_budget = dict(inputs.reserves_by_country)
        for group_key, group in sorted(groups.units.items()):
            if group_key in groups.blocked_groups:
                continue
            posture = self._build_posture_context(group_key, group, groups.side_strengths)
            decision = self._posture_selector.select(posture, inputs, remaining_budget)
            candidates.append(self._candidate_row(posture, decision, policy_id))
        return candidates

    @staticmethod
    def _build_posture_context(
        group_key: BattleGroupKey,
        group: BattleForceGroup,
        side_strengths: dict[BattleSideKey, float],
    ) -> BattlePostureContext:
        battle_id, country, unit_type, side = group_key
        friendly_strength = side_strengths.get((battle_id, side), 0.0)
        hostile_strength = sum(
            strength
            for (other_battle, other_side), strength in side_strengths.items()
            if other_battle == battle_id and other_side != side
        )
        return BattlePostureContext(
            battle_id=battle_id,
            country=country,
            unit_type=unit_type,
            friendly_strength=friendly_strength,
            hostile_strength=hostile_strength,
            strength_ratio=friendly_strength / max(1.0, friendly_strength + hostile_strength),
            group_cohesion=group.weighted_cohesion / max(1.0, group.strength),
            group_strength=group.strength,
            all_safe=group.all_safe,
        )

    @staticmethod
    def _candidate_row(
        posture: BattlePostureContext,
        decision: BattlePostureDecision,
        policy_id: str,
    ) -> Row:
        return {
            "country_id": posture.country,
            "policy_id": policy_id,
            "domain": "military_orders",
            "utility": decision.utility,
            "conflict_key": (
                f"battle-posture:{posture.battle_id}:{posture.country}:{posture.unit_type}"
            ),
            "action_kind": "set_battle_strategy",
            "reason_code": decision.reason_code,
            "quota": 1,
            "battle_id": posture.battle_id,
            "strategy": decision.strategy,
            "unit_type": posture.unit_type,
        }


class BattleStrategyCandidateBuilder:
    def __init__(
        self,
        data_loader: BattleStrategyDataLoader | None = None,
        force_aggregator: BattleForceGroupAggregator | None = None,
        candidate_row_builder: BattleCandidateRowBuilder | None = None,
    ) -> None:
        self._data_loader = data_loader if data_loader is not None else BattleStrategyDataLoader()
        self._force_aggregator = (
            force_aggregator if force_aggregator is not None else BattleForceGroupAggregator()
        )
        self._candidate_row_builder = (
            candidate_row_builder
            if candidate_row_builder is not None
            else BattleCandidateRowBuilder()
        )

    def build(
        self,
        context: AITableContext,
        *,
        policy_id: str,
        cadence_days: int,
    ) -> list[Row]:
        inputs = self._data_loader.load(context, cadence_days)
        if inputs is None:
            return []

        groups = self._force_aggregator.aggregate(inputs)
        return self._candidate_row_builder.build_candidate_rows(inputs, groups, policy_id)


def _finite(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0


def _string_value(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "")


def _country_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _unit_owner(unit: Mapping[str, Any] | None) -> str:
    return _country_code((unit or {}).get("owner"))


def _has_positive_strength(unit: Mapping[str, Any]) -> bool:
    return int(unit.get("strength") or 0) > 0
