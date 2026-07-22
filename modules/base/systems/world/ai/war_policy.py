from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import (
    active_war_pairs,
    canonical_pair_key,
    country_frame,
    country_strength,
    relation_matrix,
    treaty_member_rows,
)
from src.core.ai_framework import AITableContext
from src.shared.actions import ActionDeclareWar, ActionOfferPeace, GameAction


class WarPolicy:
    id = "war"
    required_tables = frozenset({"countries"})
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        return pl.concat(
            [self._declaration_candidates(context), self._peace_candidates(context)],
            how="diagonal_relaxed",
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        action_kind = str(row.get("action_kind") or "")
        country = str(row.get("country_id") or "")
        if action_kind == "declare_war":
            return ActionDeclareWar(
                "ai_system",
                country,
                str(row.get("target_country") or ""),
                str(row.get("reason_code") or "strategic_pressure"),
            )
        if action_kind == "offer_peace":
            return ActionOfferPeace(
                "ai_system",
                str(row.get("war_id") or ""),
                country,
                "Negotiated settlement",
            )
        return None

    def _declaration_candidates(self, context: AITableContext) -> pl.LazyFrame:
        countries = country_frame(context, self.cadence_days)
        relations = relation_matrix(context)
        strengths = self._coalition_strength(context)
        target_countries = context.table("countries")
        if target_countries is None:
            return countries.filter(pl.lit(False))

        targets = target_countries.select(
            pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
        )
        existing = active_war_pairs(context).select(
            canonical_pair_key().alias("_war_pair")
        ).unique()

        return (
            countries.join(
                relations,
                left_on="country_id",
                right_on="source_country",
                how="inner",
            )
            .join(targets, on="target_country", how="inner")
            .join(
                strengths.rename(
                    {
                        "country_id": "country_id",
                        "coalition_strength": "source_strength",
                    }
                ),
                on="country_id",
                how="left",
            )
            .join(
                strengths.rename(
                    {
                        "country_id": "target_country",
                        "coalition_strength": "target_strength",
                    }
                ),
                on="target_country",
                how="left",
            )
            .with_columns(
                canonical_pair_key("country_id", "target_country").alias("_war_pair"),
                (-pl.col("relation") / 100.0).clip(0.0, 1.0).alias("_hostility"),
                (
                    pl.col("source_strength").fill_null(0.0)
                    / pl.col("target_strength").fill_null(0.0).clip(lower_bound=1.0)
                ).alias("_strength_ratio"),
                pl.when(pl.col("total_annual_expense") > pl.col("total_annual_revenue"))
                .then(
                    pl.col("money_reserves").clip(lower_bound=0.0) * 12.0
                    / (pl.col("total_annual_expense") - pl.col("total_annual_revenue")).clip(lower_bound=1.0)
                )
                .otherwise(1200.0)
                .alias("_runway_months"),
            )
            .join(existing, on="_war_pair", how="anti")
            .filter(
                (pl.col("_hostility") >= 0.65)
                & (pl.col("_strength_ratio") > 1.25)
                & (pl.col("_runway_months") > 18.0)
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("war").alias("domain"),
                (
                    pl.col("_hostility") * 0.45
                    + ((pl.col("_strength_ratio") - 1.25) / 2.0).clip(0.0, 1.0) * 0.35
                    + (pl.col("_runway_months") / 60.0).clip(0.0, 1.0) * 0.20
                ).alias("utility"),
                pl.concat_str([pl.lit("war-pair:"), pl.col("_war_pair")]).alias("conflict_key"),
                pl.lit("declare_war").alias("action_kind"),
                pl.lit("hostile_advantage").alias("reason_code"),
                pl.lit(1).alias("quota"),
            )
        )

    def _peace_candidates(self, context: AITableContext) -> pl.LazyFrame:
        controlled = country_frame(context, 1)
        pairs = active_war_pairs(context).filter(pl.col("source_is_leader"))
        strengths = country_strength(context)
        occupied = self._occupied_home_regions(context)

        opponents = (
            pairs.join(
                strengths.rename(
                    {"country_id": "target_country", "military_strength": "_opponent_strength"}
                ),
                on="target_country",
                how="left",
            )
            .group_by(["war_id", "source_country", "source_side", "created_at"])
            .agg(pl.col("_opponent_strength").fill_null(0.0).sum().alias("opponent_strength"))
        )

        current_date = pl.lit(context.date_text[:10]).str.to_date(format="%Y-%m-%d", strict=False)
        return (
            controlled.join(
                opponents,
                left_on="country_id",
                right_on="source_country",
                how="inner",
            )
            .join(strengths, on="country_id", how="left")
            .join(occupied, on="country_id", how="left")
            .with_columns(
                pl.col("_occupied_home_regions").fill_null(0),
                (
                    pl.col("military_strength").fill_null(0.0)
                    / (
                        pl.col("military_strength").fill_null(0.0)
                        + pl.col("opponent_strength").fill_null(0.0)
                    ).clip(lower_bound=1.0)
                ).alias("_strength_share"),
                pl.when(pl.col("total_annual_expense") > pl.col("total_annual_revenue"))
                .then(
                    pl.col("money_reserves").clip(lower_bound=0.0) * 12.0
                    / (pl.col("total_annual_expense") - pl.col("total_annual_revenue")).clip(lower_bound=1.0)
                )
                .otherwise(1200.0)
                .alias("_runway_months"),
                (
                    current_date
                    - pl.col("created_at").str.slice(0, 10).str.to_date(format="%Y-%m-%d", strict=False)
                ).dt.total_days().fill_null(31).alias("_war_age_days"),
            )
            .with_columns(
                (
                    pl.col("_strength_share") * 0.50
                    + (pl.col("_runway_months") / 60.0).clip(0.0, 1.0) * 0.30
                    + pl.col("stability").clip(0.0, 1.0) * 0.20
                ).alias("_continuation_utility"),
                (
                    (pl.col("_strength_share") < 0.35)
                    | (pl.col("_runway_months") < 3.0)
                    | (pl.col("money_reserves") < 0.0)
                ).alias("_emergency"),
            )
            .filter(
                (pl.col("_war_age_days") >= 1825)
                | (
                    ((pl.col("source_side") != "a") | (pl.col("_war_age_days") >= 31))
                    & (
                        (
                            pl.col("_emergency")
                            & ~(
                                (pl.col("source_side") == "b")
                                & (pl.col("_occupied_home_regions") > 0)
                                & (pl.col("_strength_share") >= 0.35)
                            )
                        )
                        | (
                            (pl.col("_war_age_days") >= 31)
                            & (pl.col("_continuation_utility") < 0.35)
                        )
                    )
                )
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("war").alias("domain"),
                (
                    pl.when(pl.col("_war_age_days") >= 1825)
                    .then(1.5)
                    .otherwise((1.0 - pl.col("_continuation_utility")).clip(0.0, 1.0))
                ).alias("utility"),
                pl.concat_str(
                    [pl.lit("peace:"), pl.col("war_id"), pl.lit(":"), pl.col("country_id")]
                ).alias("conflict_key"),
                pl.lit("offer_peace").alias("action_kind"),
                pl.when(pl.col("_war_age_days") >= 1825)
                .then(pl.lit("prolonged_war"))
                .when(pl.col("_strength_share") < 0.35)
                .then(pl.lit("combat_losses"))
                .otherwise(pl.lit("war_exhaustion"))
                .alias("reason_code"),
                pl.lit(1).alias("quota"),
            )
        )

    def _coalition_strength(self, context: AITableContext) -> pl.LazyFrame:
        strengths = country_strength(context)
        members = treaty_member_rows(context).filter(
            (pl.col("status").str.to_lowercase() == "active")
            & (pl.col("treaty_type") == "alliance")
        )
        treaty_totals = (
            members.join(strengths, on="country_id", how="left")
            .group_by("treaty_id")
            .agg(pl.col("military_strength").fill_null(0.0).sum().alias("_alliance_strength"))
        )
        allied = (
            members.join(treaty_totals, on="treaty_id", how="left")
            .group_by("country_id")
            .agg(pl.col("_alliance_strength").max().alias("_alliance_strength"))
        )
        return (
            strengths.join(allied, on="country_id", how="left")
            .with_columns(
                pl.max_horizontal(
                    pl.col("military_strength"),
                    pl.col("_alliance_strength").fill_null(0.0),
                ).alias("coalition_strength")
            )
            .select("country_id", "coalition_strength")
        )

    def _occupied_home_regions(self, context: AITableContext) -> pl.LazyFrame:
        regions = context.table("regions")
        empty = pl.DataFrame(
            schema={"country_id": pl.Utf8, "_occupied_home_regions": pl.UInt32}
        ).lazy()
        if regions is None:
            return empty
        schema = set(regions.collect_schema().names())
        if not {"owner", "controller"}.issubset(schema):
            return empty
        return (
            regions.filter(
                pl.col("owner").is_not_null()
                & pl.col("controller").is_not_null()
                & (pl.col("owner") != pl.col("controller"))
            )
            .with_columns(
                pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("country_id")
            )
            .group_by("country_id")
            .agg(pl.len().cast(pl.UInt32).alias("_occupied_home_regions"))
        )
