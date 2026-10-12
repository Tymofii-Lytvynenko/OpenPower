from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import country_frame
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionSetBattleStrategy, GameAction


class BattleStrategyPolicy:
    """Suggests deterministic posture orders for AI-controlled battle forces."""

    id = "battle_strategy"
    required_tables = frozenset({"countries", "battles", "battle_units", "units"})
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        battles_frame = context.table("battles")
        participants_frame = context.table("battle_units")
        units_frame = context.table("units")
        if battles_frame is None or participants_frame is None or units_frame is None:
            return self._empty_candidates()

        battle_columns = set(battles_frame.collect_schema().names())
        participant_columns = set(participants_frame.collect_schema().names())
        unit_columns = set(units_frame.collect_schema().names())
        if not {"id", "status"}.issubset(battle_columns):
            return self._empty_candidates()
        if not {"battle_id", "unit_id", "country_id", "side"}.issubset(participant_columns):
            return self._empty_candidates()
        if not {"id", "owner", "strength"}.issubset(unit_columns):
            return self._empty_candidates()

        controlled = {
            str(row.get("country_id") or "").strip().upper()
            for row in country_frame(context, self.cadence_days).select("country_id").collect().to_dicts()
        }
        if not controlled:
            return self._empty_candidates()

        active_battle_frame = battles_frame.filter(
            pl.col("status").cast(pl.Utf8).fill_null("").replace("", "active").str.strip_chars().str.to_lowercase().is_in(
                ["active", "ongoing", "stalemate"]
            )
        ).select("id").collect()
        active_battles = {
            str(value or "") for value in active_battle_frame.get_column("id").to_list()
        }
        if not active_battles:
            return self._empty_candidates()

        participant_rows = participants_frame.filter(
            pl.col("battle_id").cast(pl.Utf8).is_in(active_battles)
        ).collect().to_dicts()
        participant_unit_ids = sorted({str(row.get("unit_id") or "") for row in participant_rows if row.get("unit_id")})
        if not participant_unit_ids:
            return self._empty_candidates()
        unit_rows = (
            units_frame.filter(pl.col("id").cast(pl.Utf8).is_in(participant_unit_ids))
            .collect()
            .to_dicts()
        )
        unit_by_id = {str(row.get("id") or ""): row for row in unit_rows}
        regions_frame = context.table("regions")
        safe_region_ids = set()
        if regions_frame is not None:
            region_columns = set(regions_frame.collect_schema().names())
            region_ids = sorted({int(row.get("current_region_id") or 0) for row in unit_rows if int(row.get("current_region_id") or 0) > 0})
            if "id" in region_columns and region_ids:
                region_frame = regions_frame.filter(pl.col("id").is_in(region_ids)).select(
                    "id",
                    *( [pl.col("owner")] if "owner" in region_columns else [pl.lit("").alias("owner")] ),
                    *( [pl.col("controller")] if "controller" in region_columns else [pl.lit("").alias("controller")] ),
                ).collect()
                for region in region_frame.to_dicts():
                    region_owner = str(region.get("owner") or "").strip().upper()
                    controller = str(region.get("controller") or region_owner).strip().upper()
                    if region_owner or controller:
                        safe_region_ids.add((int(region.get("id") or 0), region_owner, controller))
        country_frame_data = context.table("countries")
        reserves_by_country = {}
        if country_frame_data is not None:
            country_columns = set(country_frame_data.collect_schema().names())
            if {"id", "money_reserves"}.issubset(country_columns):
                reserves_by_country = {
                    str(row.get("id") or "").strip().upper(): max(0.0, self._finite(row.get("money_reserves")))
                    for row in country_frame_data.filter(
                        pl.col("id").cast(pl.Utf8).str.to_uppercase().is_in(sorted(controlled))
                    ).select("id", "money_reserves").collect().to_dicts()
                }
        reorganization_cost = max(0.0, self._finite(context.globals.get("battle_reorganization_cost_per_strength", 0.01)))
        cohesion_threshold = max(0.0, min(1.0, self._finite(context.globals.get("battle_ai_reorganize_cohesion_threshold", 0.4))))
        retreat_ratio_threshold = max(0.0, min(1.0, self._finite(context.globals.get("battle_ai_retreat_ratio", 0.35))))
        existing_postures = context.table("battle_force_postures")
        active_unit_ids = set()
        if existing_postures is not None:
            posture_columns = set(existing_postures.collect_schema().names())
            if {"unit_id", "status"}.issubset(posture_columns):
                active_unit_ids = {
                    str(row.get("unit_id") or "")
                    for row in existing_postures.filter(
                        pl.col("unit_id").cast(pl.Utf8).is_in(participant_unit_ids)
                    ).select("unit_id", "status").collect().to_dicts()
                    if str(row.get("status") or "").strip().lower()
                    in {"active", "retreating", "reorganizing", "returning"}
                }

        battle_units: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        blocked_groups: set[tuple[str, str, str, str]] = set()
        side_strengths: dict[tuple[str, str], float] = {}
        remaining_budget = dict(reserves_by_country)
        for participant in participant_rows:
            battle_id = str(participant.get("battle_id") or "")
            unit_id = str(participant.get("unit_id") or "")
            unit = unit_by_id.get(unit_id)
            country = str(participant.get("country_id") or "").strip().upper()
            owner = str((unit or {}).get("owner") or "").strip().upper()
            side = str(participant.get("side") or "").strip().upper()
            if (
                battle_id not in active_battles
                or not unit
                or country != owner
                or not side
                or int(unit.get("strength") or 0) <= 0
                or bool(unit.get("is_moving"))
            ):
                continue
            strength = float(unit.get("strength") or 0.0)
            side_key = (battle_id, side)
            side_strengths[side_key] = side_strengths.get(side_key, 0.0) + strength
            if country not in controlled:
                continue
            unit_type = str(unit.get("unit_type") or "unit").strip().lower().replace(" ", "_")
            key = (battle_id, country, unit_type, side)
            if (
                unit_id in active_unit_ids
                or str(unit.get("combat_posture") or "hold").strip().lower()
                in {"attack", "defend", "back_off", "retreat", "reorganize"}
            ):
                # Orders target every matching force in a country/type group, so one existing order blocks a replacement for the whole group.
                blocked_groups.add(key)
                continue
            group = battle_units.setdefault(key, {"strength": 0.0, "unit_ids": []})
            group["strength"] += strength
            group["unit_ids"].append(unit_id)
            cohesion = 1.0 if unit.get("cohesion") is None else max(0.0, min(1.0, self._finite(unit.get("cohesion"))))
            group["weighted_cohesion"] = group.get("weighted_cohesion", 0.0) + strength * cohesion
            region_id = int(unit.get("current_region_id") or 0)
            group_safe = any(
                known_region_id == region_id and country in {region_owner, controller}
                for known_region_id, region_owner, controller in safe_region_ids
            )
            group["all_safe"] = group.get("all_safe", True) and group_safe

        candidates = []
        for (battle_id, country, unit_type, side), group in sorted(battle_units.items()):
            if (battle_id, country, unit_type, side) in blocked_groups:
                continue
            friendly_strength = side_strengths.get((battle_id, side), 0.0)
            hostile_strength = sum(
                strength for (other_battle, other_side), strength in side_strengths.items()
                if other_battle == battle_id and other_side != side
            )
            ratio = friendly_strength / max(1.0, friendly_strength + hostile_strength)
            group_cohesion = group.get("weighted_cohesion", 0.0) / max(1.0, group["strength"])
            group_cost = group["strength"] * reorganization_cost
            can_reorganize = (
                group_cohesion <= cohesion_threshold
                and bool(group.get("all_safe"))
                and remaining_budget.get(country, 0.0) >= group_cost
            )
            if can_reorganize:
                strategy = "reorganize"
                reason_code = "low_cohesion_at_safe_location"
                remaining_budget[country] -= group_cost
            elif hostile_strength > 0 and friendly_strength / hostile_strength <= retreat_ratio_threshold:
                strategy = "retreat"
                reason_code = "severe_local_disadvantage"
            else:
                strategy = "attack" if friendly_strength > hostile_strength else "defend"
                reason_code = "local_superiority" if strategy == "attack" else "local_disadvantage"
            candidates.append({
                "country_id": country,
                "policy_id": self.id,
                "domain": "military_orders",
                "utility": 0.95 if strategy in {"retreat", "reorganize"} else 0.55 + min(0.4, abs(ratio - 0.5)),
                "conflict_key": f"battle-posture:{battle_id}:{country}:{unit_type}",
                "action_kind": "set_battle_strategy",
                "reason_code": reason_code,
                "quota": 1,
                "battle_id": battle_id,
                "strategy": strategy,
                "unit_type": unit_type,
            })
        return pl.DataFrame(candidates).lazy() if candidates else self._empty_candidates()

    @staticmethod
    def _finite(value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "set_battle_strategy":
            return None
        return ActionSetBattleStrategy(
            "ai_system",
            str(row.get("battle_id") or ""),
            str(row.get("strategy") or "hold"),
            country_tag=str(row.get("country_id") or ""),
            unit_type=str(row.get("unit_type") or "all"),
        )

    def _empty_candidates(self) -> pl.LazyFrame:
        return empty_candidates({
            "battle_id": pl.Utf8,
            "strategy": pl.Utf8,
            "unit_type": pl.Utf8,
        })
