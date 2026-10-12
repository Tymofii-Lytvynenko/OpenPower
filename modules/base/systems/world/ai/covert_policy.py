from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import country_frame
from modules.base.systems.military.covert_operations_system import MISSION_PROFILES
from modules.base.systems.military.covert_policy import skill_profile
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import (
    ActionCreateCovertCell,
    ActionStartCovertMission,
    ActionTrainCovertCell,
    GameAction,
)


_ACTIVE_MISSION_STATES = frozenset({"preparation", "executing", "cleanup"})
_MISSION_TYPE = "civilian_espionage"
_CANDIDATE_SCHEMA = {
    "target_country_id": pl.Utf8,
    "cell_id": pl.Utf8,
    "cell_name": pl.Utf8,
    "training_points": pl.Float64,
    "mission_type": pl.Utf8,
}


class CovertOperationsPolicy:
    """Submit ordinary covert actions through the shared validated action path."""

    id = "covert_operations"
    required_tables = frozenset(
        {"countries", "regions", "covert_cells", "covert_missions"}
    )
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        scheduled = country_frame(context, self.cadence_days).select("country_id").collect()
        if scheduled.is_empty():
            return empty_candidates(_CANDIDATE_SCHEMA)
        country_table = context.table("countries")
        regions_table = context.table("regions")
        cells_table = context.table("covert_cells")
        missions_table = context.table("covert_missions")
        if any(table is None for table in (country_table, regions_table, cells_table, missions_table)):
            return empty_candidates(_CANDIDATE_SCHEMA)

        scheduled_ids = scheduled.get_column("country_id").drop_nulls().unique().to_list()
        countries = country_table.collect()
        country_columns = set(countries.columns)
        if "id" not in country_columns:
            return empty_candidates(_CANDIDATE_SCHEMA)
        funds = (
            countries.select(
                pl.col("id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("country_id"),
                (
                    pl.when(pl.col("money_reserves").cast(pl.Float64, strict=False).is_finite())
                    .then(pl.col("money_reserves").cast(pl.Float64, strict=False))
                    .otherwise(0.0)
                    if "money_reserves" in country_columns
                    else pl.lit(0.0)
                ).alias("funds"),
            )
            .join(scheduled, on="country_id", how="inner")
        )
        owned_regions = (
            regions_table.collect()
            .select(pl.col("owner").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("country_id"))
            .filter(pl.col("country_id").is_not_null() & (pl.col("country_id") != ""))
            .unique()
        )
        all_cells = cells_table.collect()
        active_cells = self._active_cell_frame(all_cells, scheduled_ids)
        active_missions = self._active_mission_frame(missions_table.collect())
        active_cells = active_cells.join(
            active_missions,
            left_on="cell_id",
            right_on="active_cell_id",
            how="anti",
        )
        all_active_cells = self._active_cell_frame(all_cells, scheduled_ids)
        active_cell_counts = all_active_cells.group_by("country_id").agg(
            pl.len().alias("active_cell_count")
        )

        relations_table = context.table("countries_relations")
        treaties_table = context.table("countries_treaties")
        treaties = pl.DataFrame() if treaties_table is None else treaties_table.collect()
        allied_pairs = self._allied_pairs_from_frame(treaties)
        creation_cost = max(0.0, self._finite(context.globals.get("covert_cell_creation_cost", 10.0)))
        training_points = max(1.0, self._finite(context.globals.get("covert_training_points_per_level", 100.0)))
        training_cost = training_points * max(0.0, self._finite(context.globals.get("covert_training_cost_per_point", 0.1)))
        mission_cost = max(0.0, self._finite(context.globals.get("covert_mission_cost", 2.0)))
        mission_risk = MISSION_PROFILES[_MISSION_TYPE][0]
        cell_candidates = self._cell_candidates(
            active_cells,
            funds,
            training_points,
            training_cost,
            mission_cost,
            mission_risk,
        )
        candidates = [
            self._candidate(
                str(row["country_id"]),
                str(row["action_kind"]),
                str(row["reason_code"]),
                float(row["utility"]),
                cell_id=str(row.get("cell_id") or ""),
                target_country_id=str(row.get("target_country_id") or ""),
                training_points=float(row.get("training_points") or 0.0),
                mission_type=str(row.get("mission_type") or ""),
            )
            for row in cell_candidates.to_dicts()
        ]

        creation_owners = (
            funds.join(active_cell_counts, on="country_id", how="left")
            .with_columns(pl.col("active_cell_count").fill_null(0))
            .filter(
                (pl.col("active_cell_count") == 0)
                & (pl.col("funds") >= creation_cost)
            )
            .join(owned_regions, on="country_id", how="inner")
            .join(
                cell_candidates.select("country_id").unique(),
                on="country_id",
                how="anti",
            )
            .select("country_id")
        )
        if not creation_owners.is_empty():
            relation_by_pair = self._index_relations(
                pl.DataFrame() if relations_table is None else relations_table.collect()
            )
            creation_targets = self._creation_targets(
                creation_owners,
                countries,
                owned_regions,
                allied_pairs,
                relation_by_pair,
            )
            candidates.extend(
                self._candidate(
                    str(row["country_id"]),
                    "create_cell",
                    "establish_covert_capability",
                    0.45,
                    target_country_id=str(row["target_country_id"]),
                    cell_name="Government Intelligence Cell",
                )
                for row in creation_targets.to_dicts()
            )

        if not candidates:
            return empty_candidates(_CANDIDATE_SCHEMA)
        candidates.sort(key=lambda row: self._tag(row.get("country_id")))
        return pl.DataFrame(candidates).lazy()

    @staticmethod
    def _active_cell_frame(cells: pl.DataFrame, scheduled_ids: list[str]) -> pl.DataFrame:
        columns = set(cells.columns)
        if not {"id", "country_id"}.issubset(columns):
            return pl.DataFrame(schema={"cell_id": pl.Utf8, "country_id": pl.Utf8})
        expressions = [
            pl.col("id").cast(pl.Utf8).alias("cell_id"),
            pl.col("country_id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("country_id"),
            (pl.col("status").cast(pl.Utf8).fill_null("") if "status" in columns else pl.lit("")).alias("status"),
            (pl.col("skill_level").cast(pl.Utf8).fill_null("Recruit") if "skill_level" in columns else pl.lit("Recruit")).alias("skill_level"),
            (pl.col("target_country_id").cast(pl.Utf8).fill_null("").str.to_uppercase() if "target_country_id" in columns else pl.lit("")).alias("target_country_id"),
            (pl.col("location_country_id").cast(pl.Utf8).fill_null("").str.to_uppercase() if "location_country_id" in columns else pl.lit("")).alias("location_country_id"),
            (pl.col("communications_ready").cast(pl.Boolean, strict=False).fill_null(False) if "communications_ready" in columns else pl.lit(True)).alias("communications_ready"),
            (pl.col("assignment").cast(pl.Utf8).fill_null("unassigned") if "assignment" in columns else pl.lit("unassigned")).alias("assignment"),
        ]
        return (
            cells.select(expressions)
            .filter(
                pl.col("country_id").is_in(scheduled_ids)
                & ~pl.col("status").str.to_lowercase().is_in(["retired", "lost", "captured"])
            )
            .sort(["country_id", "cell_id"])
        )

    @staticmethod
    def _active_mission_frame(missions: pl.DataFrame) -> pl.DataFrame:
        if not {"cell_id", "status"}.issubset(missions.columns):
            return pl.DataFrame(schema={"active_cell_id": pl.Utf8})
        return (
            missions.filter(pl.col("status").cast(pl.Utf8).fill_null("").str.to_lowercase().is_in(list(_ACTIVE_MISSION_STATES)))
            .select(pl.col("cell_id").cast(pl.Utf8).alias("active_cell_id"))
            .unique()
        )

    def _cell_candidates(
        self,
        cells: pl.DataFrame,
        funds: pl.DataFrame,
        training_points: float,
        training_cost: float,
        mission_cost: float,
        mission_risk: float,
    ) -> pl.DataFrame:
        if cells.is_empty():
            return pl.DataFrame(schema={"country_id": pl.Utf8, "cell_id": pl.Utf8, "action_kind": pl.Utf8, "reason_code": pl.Utf8, "utility": pl.Float64, "target_country_id": pl.Utf8, "training_points": pl.Float64, "mission_type": pl.Utf8})
        skill_rows = cells.select("skill_level").unique().to_series().to_list()
        mission_skills = [
            str(skill)
            for skill in skill_rows
            if skill != "Recruit" and skill_profile(str(skill)).max_mission_risk >= mission_risk
        ]
        eligible = (
            cells.join(funds, on="country_id", how="inner")
            .filter(pl.col("status").str.to_lowercase().is_in(["active", "idle"]))
            .with_columns(
                pl.when(pl.col("skill_level") == "Recruit")
                .then(pl.lit("train_cell"))
                .otherwise(pl.lit("start_mission"))
                .alias("action_kind"),
                pl.when(pl.col("skill_level") == "Recruit")
                .then(pl.lit("prepare_cell"))
                .otherwise(pl.lit("collect_bounded_intelligence"))
                .alias("reason_code"),
                pl.when(pl.col("skill_level") == "Recruit")
                .then(pl.lit(0.7))
                .otherwise(pl.lit(0.65))
                .alias("utility"),
            )
            .filter(
                ((pl.col("action_kind") == "train_cell") & (pl.col("funds") >= training_cost))
                | (
                    (pl.col("action_kind") == "start_mission")
                    & pl.col("skill_level").is_in(mission_skills)
                    & (pl.col("funds") >= mission_cost)
                    & (pl.col("target_country_id") != "")
                    & (pl.col("location_country_id").str.to_uppercase() == pl.col("target_country_id").str.to_uppercase())
                    & pl.col("communications_ready")
                    & pl.col("assignment").is_in(["unassigned", "espionage"])
                )
            )
            .sort(["country_id", "cell_id"])
            .unique(subset="country_id", keep="first", maintain_order=True)
            .with_columns(
                pl.when(pl.col("action_kind") == "train_cell")
                .then(pl.lit(training_points))
                .otherwise(pl.lit(0.0))
                .alias("training_points"),
                pl.when(pl.col("action_kind") == "start_mission")
                .then(pl.lit(_MISSION_TYPE))
                .otherwise(pl.lit(""))
                .alias("mission_type"),
            )
        )
        return eligible.select(
            "country_id", "cell_id", "action_kind", "reason_code", "utility",
            "target_country_id", "training_points", "mission_type",
        )

    def _creation_targets(
        self,
        owners: pl.DataFrame,
        countries: pl.DataFrame,
        owned_regions: pl.DataFrame,
        allied_pairs: set[tuple[str, str]],
        relation_by_pair: Mapping[tuple[str, str], list[float]],
    ) -> pl.DataFrame:
        country_ids = (
            countries.select(pl.col("id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("target_country_id"))
            .join(owned_regions.rename({"country_id": "target_country_id"}), on="target_country_id", how="inner")
            .filter(pl.col("target_country_id") != "")
            .unique()
        )
        pairs = owners.join(country_ids, how="cross").filter(
            pl.col("country_id") != pl.col("target_country_id")
        )
        if allied_pairs:
            allied_frame = pl.DataFrame(
                sorted(allied_pairs),
                schema={"country_id": pl.Utf8, "target_country_id": pl.Utf8},
                orient="row",
            )
            pairs = pairs.join(allied_frame, on=["country_id", "target_country_id"], how="anti")
        pairs = pairs.with_columns(pl.lit(0.0).alias("relation"))
        relation_rows = [
            {"country_id": source, "target_country_id": target, "relation": value}
            for (source, target), values in relation_by_pair.items()
            for value in values
        ]
        relation_rows.extend(
            {"country_id": target, "target_country_id": source, "relation": value}
            for (source, target), values in relation_by_pair.items()
            for value in values
        )
        if relation_rows:
            relation_scores = (
                pl.DataFrame(relation_rows)
                .group_by(["country_id", "target_country_id"])
                .agg(pl.col("relation").mean())
            )
            pairs = pairs.drop("relation").join(
                relation_scores,
                on=["country_id", "target_country_id"],
                how="left",
            ).with_columns(pl.col("relation").fill_null(0.0))
        return (
            pairs.sort(["country_id", "relation", "target_country_id"], maintain_order=True)
            .unique(subset="country_id", keep="first", maintain_order=True)
            .select("country_id", "target_country_id")
        )

    @staticmethod
    def _allied_pairs_from_frame(treaties: pl.DataFrame) -> set[tuple[str, str]]:
        required = {"status", "treaty_type", "members"}
        if not required.issubset(treaties.columns):
            return set()
        status = pl.col("status").cast(pl.Utf8).fill_null("").str.to_lowercase()
        alliances = treaties.filter(
            status.is_in(["", "active"])
            & (pl.col("treaty_type").cast(pl.Utf8).fill_null("").str.to_lowercase() == "alliance")
        ).select("members").to_dicts()
        return CovertOperationsPolicy._allied_pairs(
            [{"status": "active", "treaty_type": "alliance", "members": row["members"]} for row in alliances]
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        owner = str(row.get("country_id") or "")
        kind = str(row.get("action_kind") or "")
        if kind == "create_cell":
            return ActionCreateCovertCell(
                "ai_system",
                owner,
                str(row.get("target_country_id") or ""),
                str(row.get("cell_name") or "Government Intelligence Cell"),
            )
        if kind == "train_cell":
            return ActionTrainCovertCell(
                "ai_system",
                str(row.get("cell_id") or ""),
                max(1.0, self._finite(row.get("training_points"), 100.0)),
            )
        if kind == "start_mission":
            return ActionStartCovertMission(
                "ai_system",
                str(row.get("cell_id") or ""),
                str(row.get("mission_type") or _MISSION_TYPE),
                str(row.get("target_country_id") or ""),
            )
        return None

    def _cell_action(
        self,
        owner: str,
        funds: float,
        cells: list[dict[str, Any]],
        active_missions: set[str],
        training_points: float,
        training_cost: float,
        mission_cost: float,
        mission_risk: float,
    ) -> dict[str, Any] | None:
        for cell in cells:
            cell_id = str(cell.get("id") or "")
            status = str(cell.get("status") or "").lower()
            if not cell_id or status not in {"active", "idle"} or cell_id in active_missions:
                continue
            skill = str(cell.get("skill_level") or "Recruit")
            if skill == "Recruit":
                if funds < training_cost:
                    continue
                return self._candidate(
                    owner, "train_cell", "prepare_cell", 0.7,
                    cell_id=cell_id, training_points=training_points,
                )
            if skill_profile(skill).max_mission_risk < mission_risk or funds < mission_cost:
                continue
            target = self._tag(cell.get("target_country_id"))
            if (
                not target
                or self._tag(cell.get("location_country_id")) != target
                or not bool(cell.get("communications_ready", True))
                or str(cell.get("assignment") or "unassigned") not in {"unassigned", "espionage"}
            ):
                continue
            return self._candidate(
                owner, "start_mission", "collect_bounded_intelligence", 0.65,
                cell_id=cell_id, target_country_id=target, mission_type=_MISSION_TYPE,
            )
        return None

    def _index_relations(
        self, relations: list[dict[str, Any]] | pl.DataFrame
    ) -> dict[tuple[str, str], list[float]]:
        relation_by_pair: dict[tuple[str, str], list[float]] = {}
        if isinstance(relations, pl.DataFrame):
            required = {"source", "target", "value"}
            if not required.issubset(relations.columns):
                return relation_by_pair
            rows = relations.select("source", "target", "value").iter_rows(named=False)
        else:
            rows = (
                (row.get("source"), row.get("target"), row.get("value"))
                for row in relations
            )
        for source, target, value in rows:
            left, right = self._tag(source), self._tag(target)
            if left and right:
                relation_by_pair.setdefault((left, right), []).append(self._finite(value))
        return relation_by_pair

    def _choose_target(
        self,
        owner: str,
        countries: list[dict[str, Any]],
        relation_by_pair: Mapping[tuple[str, str], list[float]],
        allied_pairs: set[tuple[str, str]],
        owned_regions: set[str],
    ) -> str:
        eligible = []
        for country in countries:
            target = self._tag(country.get("id"))
            if not target or target == owner or target not in owned_regions or (owner, target) in allied_pairs:
                continue
            values = relation_by_pair.get((owner, target), []) + relation_by_pair.get((target, owner), [])
            relation = sum(values) / len(values) if values else 0.0
            eligible.append((relation, target))
        return min(eligible)[1] if eligible else ""

    @staticmethod
    def _allied_pairs(treaties: list[dict[str, Any]]) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for row in treaties:
            if (
                str(row.get("status") or "active").lower() != "active"
                or str(row.get("treaty_type") or "").lower() != "alliance"
            ):
                continue
            members = row.get("members") or []
            if isinstance(members, str):
                try:
                    members = json.loads(members)
                except (TypeError, ValueError):
                    members = []
            if not isinstance(members, (list, tuple, set)):
                continue
            normalized = sorted({str(item).strip().upper() for item in members if str(item).strip()})
            for index, left in enumerate(normalized):
                for right in normalized[index + 1 :]:
                    pairs.add((left, right))
                    pairs.add((right, left))
        return pairs

    @staticmethod
    def _candidate(
        country: str,
        kind: str,
        reason: str,
        utility: float,
        **payload: Any,
    ) -> dict[str, Any]:
        row = {
            "country_id": country,
            "policy_id": CovertOperationsPolicy.id,
            "domain": "covert",
            "utility": utility,
            "conflict_key": f"covert:{country}",
            "action_kind": kind,
            "reason_code": reason,
            "quota": 1,
        }
        row.update(
            {
                name: "" if dtype == pl.Utf8 else 0.0
                for name, dtype in _CANDIDATE_SCHEMA.items()
            }
        )
        row.update(payload)
        return row

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _finite(value: Any, default: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return result if math.isfinite(result) else default
