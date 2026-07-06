from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from src.shared.actions import ActionCreateTreaty, ActionDeclareWar, ActionOfferPeace


STRATEGIC_AI_SCHEMA_DEFAULTS: dict[str, Any] = {
    "preferred_treaty_target": "",
    "preferred_treaty_score": 0.0,
    "preferred_treaty_type": "trade_accord",
    "war_target_tag": "",
    "war_target_hostility": 0.0,
    "war_target_strength": 0,
    "peace_war_id": "",
    "peace_enemy_strength": 0,
    "peace_own_strength": 0,
    "active_war_count": 0,
    "allied_country_count": 0,
    "hostile_country_count": 0,
    "war_strength_ratio": 0.0,
    "peace_strength_ratio": 1.0,
    "bankruptcy_pressure": 0.0,
}


def evaluate_alliance_opportunities(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        preferred_treaty_type=pl.when(pl.col("hostile_country_count") > 0)
        .then(pl.lit("defensive_pact"))
        .otherwise(pl.lit("trade_accord")),
        alliance_pressure=(
            pl.col("trait_threat_perception") * (1.0 + (pl.col("hostile_country_count") * 0.15))
        ).clip(0.5, 2.0),
    ).with_columns(
        utility_seek_alliance=pl.when(
            (pl.col("preferred_treaty_target") != "")
            & (pl.col("preferred_treaty_score") >= 0.55)
            & (pl.col("active_war_count") == 0)
            & (pl.col("months_to_bankruptcy") >= 12.0)
        )
        .then(
            (
                pl.col("preferred_treaty_score")
                * pl.col("alliance_pressure")
                / (1.0 + (pl.col("allied_country_count") * 0.25))
            ).clip(0.0, 1.0)
        )
        .otherwise(0.0)
    )


def evaluate_war_opportunities(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        war_strength_ratio=(pl.col("current_military_strength") + 1.0) / (pl.col("war_target_strength") + 1.0)
    ).with_columns(
        utility_declare_war=pl.when(
            (pl.col("war_target_tag") != "")
            & (pl.col("active_war_count") == 0)
            & (pl.col("war_strength_ratio") > 1.25)
            & (pl.col("money_reserves") > 0.0)
            & (pl.col("months_to_bankruptcy") > 18.0)
            & (pl.col("war_target_hostility") >= 0.65)
        )
        .then(
            (
                pl.col("war_target_hostility")
                * (pl.col("war_strength_ratio") - 1.0)
                * pl.col("trait_threat_perception")
            ).clip(0.0, 1.0)
        )
        .otherwise(0.0)
    )


def evaluate_peace_pressure(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        peace_strength_ratio=(pl.col("peace_own_strength") + 1.0) / (pl.col("peace_enemy_strength") + 1.0),
        bankruptcy_pressure=pl.when(pl.col("months_to_bankruptcy") < 12.0)
        .then((1.0 - (pl.col("months_to_bankruptcy") / 12.0)).clip(0.0, 1.0))
        .otherwise(0.0),
    ).with_columns(
        utility_offer_peace=pl.when(
            (pl.col("peace_war_id") != "")
            & (
                (pl.col("peace_strength_ratio") < 0.75)
                | (pl.col("money_reserves") < 0.0)
                | (pl.col("months_to_bankruptcy") < 9.0)
            )
        )
        .then(
            (
                ((1.0 - pl.col("peace_strength_ratio").clip(0.0, 1.0)) * 0.65)
                + (pl.col("bankruptcy_pressure") * 0.35)
            ).clip(0.0, 1.0)
        )
        .otherwise(0.0)
    )


def build_ai_alliance_action(row: dict) -> ActionCreateTreaty | None:
    source = _clean_tag(row.get("id"))
    target = _clean_tag(row.get("preferred_treaty_target"))
    treaty_type = str(row.get("preferred_treaty_type") or "trade_accord")
    if not source or not target:
        return None

    label = treaty_type.replace("_", " ").title()
    return ActionCreateTreaty(
        "ai_system",
        source_country_tag=source,
        target_country_tag=target,
        treaty_type=treaty_type,
        title=f"{source}-{target} {label}",
        terms=f"AI-generated {label.lower()} to improve strategic alignment.",
    )


def build_ai_war_action(row: dict) -> ActionDeclareWar | None:
    source = _clean_tag(row.get("id"))
    target = _clean_tag(row.get("war_target_tag"))
    if not source or not target:
        return None

    return ActionDeclareWar(
        "ai_system",
        source_country_tag=source,
        target_country_tag=target,
        casus_belli="Strategic containment",
    )


def build_ai_peace_action(row: dict) -> ActionOfferPeace | None:
    source = _clean_tag(row.get("id"))
    war_id = str(row.get("peace_war_id") or "").strip()
    if not source or not war_id:
        return None

    return ActionOfferPeace(
        "ai_system",
        war_id=war_id,
        source_country_tag=source,
        terms="AI ceasefire proposal",
    )


@dataclass(slots=True)
class WarPressureSummary:
    active_war_count: int = 0
    peace_war_id: str = ""
    peace_enemy_strength: int = 0
    peace_own_strength: int = 0
    enemies: set[str] | None = None

    def __post_init__(self) -> None:
        if self.enemies is None:
            self.enemies = set()


class StrategicDiplomacySnapshotBuilder:
    def build(
        self,
        countries: pl.DataFrame,
        relations: pl.DataFrame | None,
        treaties: pl.DataFrame | None,
        wars: pl.DataFrame | None,
        strength_by_country: dict[str, int],
    ) -> pl.DataFrame:
        if countries.is_empty() or "id" not in countries.columns:
            return pl.DataFrame(schema=self._schema())

        allied_map = self._build_allied_map(treaties)
        war_map = self._build_war_map(wars, strength_by_country)
        relation_map = self._build_relation_map(relations)

        rows: list[dict[str, Any]] = []
        for country_id in countries["id"].to_list():
            tag = _clean_tag(country_id)
            allies = allied_map.get(tag, set())
            war_summary = war_map.get(tag, WarPressureSummary())
            enemies = war_summary.enemies or set()
            relation_rows = relation_map.get(tag, [])
            excluded = {tag, *allies, *enemies}

            treaty_target, treaty_score = self._find_best_target(relation_rows, excluded)
            war_target, war_hostility = self._find_worst_target(relation_rows, excluded)

            rows.append(
                {
                    "id": tag,
                    "preferred_treaty_target": treaty_target,
                    "preferred_treaty_score": treaty_score,
                    "preferred_treaty_type": "trade_accord",
                    "war_target_tag": war_target,
                    "war_target_hostility": war_hostility,
                    "war_target_strength": int(strength_by_country.get(war_target, 0)),
                    "peace_war_id": war_summary.peace_war_id,
                    "peace_enemy_strength": war_summary.peace_enemy_strength,
                    "peace_own_strength": war_summary.peace_own_strength or int(strength_by_country.get(tag, 0)),
                    "active_war_count": war_summary.active_war_count,
                    "allied_country_count": len(allies),
                    "hostile_country_count": len(enemies),
                }
            )

        return pl.DataFrame(rows, schema=self._schema())

    def _build_relation_map(self, relations: pl.DataFrame | None) -> dict[str, list[dict[str, Any]]]:
        if relations is None or relations.is_empty() or not {"source", "target", "value"}.issubset(set(relations.columns)):
            return {}

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in relations.select(["source", "target", "value"]).iter_rows(named=True):
            source = _clean_tag(row.get("source"))
            target = _clean_tag(row.get("target"))
            if not source or not target or source == target:
                continue
            grouped.setdefault(source, []).append(
                {"target": target, "value": float(row.get("value") or 0.0)}
            )
        return grouped

    def _build_allied_map(self, treaties: pl.DataFrame | None) -> dict[str, set[str]]:
        allied_types = {"alliance", "defensive_alliance", "military_alliance", "defensive_pact", "military_pact"}
        allied_map: dict[str, set[str]] = {}
        if treaties is None or treaties.is_empty():
            return allied_map

        for row in treaties.to_dicts():
            treaty_type = str(row.get("type") or "").strip().lower()
            if treaty_type not in allied_types or str(row.get("status") or "active").lower() != "active":
                continue

            members = _normalize_side(row.get("members"))
            if not members:
                members = _normalize_side(row.get("side_a")) | _normalize_side(row.get("side_b"))

            for member in members:
                allied_map.setdefault(member, set()).update(members - {member})

        return allied_map

    def _build_war_map(self, wars: pl.DataFrame | None, strength_by_country: dict[str, int]) -> dict[str, WarPressureSummary]:
        summaries: dict[str, WarPressureSummary] = {}
        if wars is None or wars.is_empty():
            return summaries

        for index, row in enumerate(wars.to_dicts(), start=1):
            status = str(row.get("status") or "active").lower()
            if status not in {"active", "ongoing", ""}:
                continue

            side_a = _normalize_side(row.get("side_a"))
            side_b = _normalize_side(row.get("side_b"))
            if not side_a or not side_b:
                continue

            war_id = str(row.get("id") or f"war-{index:03d}")
            side_a_strength = sum(int(strength_by_country.get(tag, 0)) for tag in side_a)
            side_b_strength = sum(int(strength_by_country.get(tag, 0)) for tag in side_b)

            for member in side_a:
                summary = summaries.setdefault(member, WarPressureSummary())
                summary.active_war_count += 1
                summary.enemies.update(side_b)
                if side_b_strength >= summary.peace_enemy_strength:
                    summary.peace_war_id = war_id
                    summary.peace_enemy_strength = side_b_strength
                    summary.peace_own_strength = side_a_strength

            for member in side_b:
                summary = summaries.setdefault(member, WarPressureSummary())
                summary.active_war_count += 1
                summary.enemies.update(side_a)
                if side_a_strength >= summary.peace_enemy_strength:
                    summary.peace_war_id = war_id
                    summary.peace_enemy_strength = side_a_strength
                    summary.peace_own_strength = side_b_strength

        return summaries

    def _find_best_target(self, relation_rows: list[dict[str, Any]], excluded: set[str]) -> tuple[str, float]:
        best_target = ""
        best_score = 0.0
        for row in sorted(relation_rows, key=lambda item: (-float(item["value"]), item["target"])):
            target = _clean_tag(row.get("target"))
            value = float(row.get("value") or 0.0)
            if target in excluded or value <= 0.0:
                continue
            best_target = target
            best_score = min(1.0, value / 100.0)
            break
        return best_target, best_score

    def _find_worst_target(self, relation_rows: list[dict[str, Any]], excluded: set[str]) -> tuple[str, float]:
        worst_target = ""
        worst_score = 0.0
        for row in sorted(relation_rows, key=lambda item: (float(item["value"]), item["target"])):
            target = _clean_tag(row.get("target"))
            value = float(row.get("value") or 0.0)
            if target in excluded or value >= 0.0:
                continue
            worst_target = target
            worst_score = min(1.0, abs(value) / 100.0)
            break
        return worst_target, worst_score

    def _schema(self) -> dict[str, pl.DataType]:
        return {
            "id": pl.Utf8,
            "preferred_treaty_target": pl.Utf8,
            "preferred_treaty_score": pl.Float64,
            "preferred_treaty_type": pl.Utf8,
            "war_target_tag": pl.Utf8,
            "war_target_hostility": pl.Float64,
            "war_target_strength": pl.Int64,
            "peace_war_id": pl.Utf8,
            "peace_enemy_strength": pl.Int64,
            "peace_own_strength": pl.Int64,
            "active_war_count": pl.Int64,
            "allied_country_count": pl.Int64,
            "hostile_country_count": pl.Int64,
        }


def _normalize_side(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {_clean_tag(tag) for tag in value if _clean_tag(tag)}
    if isinstance(value, tuple):
        return {_clean_tag(tag) for tag in value if _clean_tag(tag)}
    if isinstance(value, str):
        return {_clean_tag(tag) for tag in value.split(",") if _clean_tag(tag)}
    return set()


def _clean_tag(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()
