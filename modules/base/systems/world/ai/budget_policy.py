from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import active_war_members, country_frame, with_defaults
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionUpdateBudget, GameAction


BUDGET_COLUMNS = (
    "budget_health_ratio",
    "budget_edu_ratio",
    "budget_social_ratio",
    "budget_gov_ratio",
    "budget_env_ratio",
    "budget_research_ratio",
    "budget_infra_ratio",
    "budget_telecom_ratio",
    "budget_imf_ratio",
    "budget_propaganda_ratio",
    "budget_tourism_promo_ratio",
)
DISCRETIONARY_COLUMNS = (
    "budget_gov_ratio",
    "budget_env_ratio",
    "budget_imf_ratio",
    "budget_propaganda_ratio",
    "budget_tourism_promo_ratio",
)


class BudgetPolicy:
    id = "budget"
    required_tables = frozenset({"countries"})
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        countries = country_frame(context, self.cadence_days)
        defaults = {column: (pl.Float64, 0.5) for column in BUDGET_COLUMNS}
        defaults["budget_imf_ratio"] = (pl.Float64, 0.0)
        countries = with_defaults(countries, defaults)

        wars = (
            active_war_members(context)
            .group_by("country_id")
            .agg(pl.len().alias("_active_wars"))
        )
        base = (
            countries.join(wars, on="country_id", how="left")
            .with_columns(
                pl.col("_active_wars").fill_null(0),
                (pl.col("total_annual_revenue") - pl.col("total_annual_expense")).alias("_annual_balance"),
            )
            .with_columns(
                pl.when(pl.col("_annual_balance") < 0.0)
                .then(
                    (pl.col("money_reserves").clip(lower_bound=0.0) * 12.0)
                    / pl.col("_annual_balance").abs().clip(lower_bound=1.0)
                )
                .otherwise(1200.0)
                .alias("_runway_months"),
                (pl.col("_active_wars") > 0).cast(pl.Float64).alias("_at_war"),
            )
        )

        critical = (
            base.filter(
                (pl.col("_annual_balance") < 0.0)
                & ((pl.col("_runway_months") < 12.0) | (pl.col("money_reserves") < 0.0))
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("budget").alias("domain"),
                (
                    1.0
                    + (12.0 - pl.col("_runway_months")).clip(0.0, 12.0) / 12.0
                    + pl.col("_at_war") * 0.1
                ).alias("utility"),
                pl.concat_str([pl.lit("budget:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("update_budget").alias("action_kind"),
                pl.lit("critical_deficit").alias("reason_code"),
                pl.lit(1).alias("quota"),
                pl.lit("__discretionary__").alias("allocation_column"),
                pl.lit(None, dtype=pl.Float64).alias("allocation_value"),
                (pl.col("personal_income_tax_rate") + 0.05).clip(upper_bound=0.50).alias("tax_value"),
            )
        )

        category_scores = self._category_scores()
        ordinary: list[pl.LazyFrame] = []
        for column, score in category_scores.items():
            deficit = (
                base.filter(
                    (pl.col("_annual_balance") < 0.0)
                    & (pl.col("_runway_months") >= 12.0)
                    & (pl.col(column) > 0.0)
                )
                .with_columns(
                    pl.lit(self.id).alias("policy_id"),
                    pl.lit("budget").alias("domain"),
                    (
                        0.45
                        + (
                            pl.col("_annual_balance").abs()
                            / pl.col("total_annual_revenue").abs().clip(lower_bound=1.0)
                        ).clip(0.0, 0.45)
                        + (1.0 - score.clip(0.0, 1.0)) * 0.10
                    ).alias("utility"),
                    pl.concat_str([pl.lit("budget:"), pl.col("country_id")]).alias("conflict_key"),
                    pl.lit("update_budget").alias("action_kind"),
                    pl.lit("managed_deficit").alias("reason_code"),
                    pl.lit(1).alias("quota"),
                    pl.lit(column).alias("allocation_column"),
                    (pl.col(column) - 0.05).clip(lower_bound=0.0).alias("allocation_value"),
                    pl.lit(None, dtype=pl.Float64).alias("tax_value"),
                )
            )
            surplus = (
                base.filter(
                    (pl.col("_annual_balance") > 0.0)
                    & (pl.col("money_reserves") > pl.col("total_annual_expense").clip(lower_bound=1.0) * 0.5)
                    & (pl.col(column) < 1.0)
                )
                .with_columns(
                    pl.lit(self.id).alias("policy_id"),
                    pl.lit("budget").alias("domain"),
                    (
                        0.35
                        + (
                            pl.col("_annual_balance")
                            / pl.col("total_annual_revenue").abs().clip(lower_bound=1.0)
                        ).clip(0.0, 0.35)
                        + score.clip(0.0, 1.0) * 0.20
                    ).alias("utility"),
                    pl.concat_str([pl.lit("budget:"), pl.col("country_id")]).alias("conflict_key"),
                    pl.lit("update_budget").alias("action_kind"),
                    pl.lit("sustained_surplus").alias("reason_code"),
                    pl.lit(1).alias("quota"),
                    pl.lit(column).alias("allocation_column"),
                    (pl.col(column) + 0.05).clip(upper_bound=1.0).alias("allocation_value"),
                    pl.lit(None, dtype=pl.Float64).alias("tax_value"),
                )
            )
            ordinary.extend((deficit, surplus))

        if not ordinary:
            return empty_candidates()
        return pl.concat([critical, *ordinary], how="diagonal_relaxed")

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        allocations: dict[str, float] = {}
        allocation_column = str(row.get("allocation_column") or "")
        if allocation_column == "__discretionary__":
            for column in DISCRETIONARY_COLUMNS:
                allocations[column] = max(0.0, float(row.get(column) or 0.0) * 0.80)
        elif allocation_column in BUDGET_COLUMNS and row.get("allocation_value") is not None:
            allocations[allocation_column] = float(row["allocation_value"])

        if row.get("tax_value") is not None:
            allocations["personal_income_tax_rate"] = min(0.50, float(row["tax_value"]))
        if not allocations:
            return None
        return ActionUpdateBudget("ai_system", str(row["country_id"]), allocations)

    def _category_scores(self) -> dict[str, pl.Expr]:
        hd = pl.col("human_dev").clip(0.0, 1.0)
        corruption = pl.col("corruption").clip(0.0, 1.0)
        stability = pl.col("stability").clip(0.0, 1.0)
        at_war = pl.col("_at_war")
        runway_pressure = (18.0 - pl.col("_runway_months")).clip(0.0, 18.0) / 18.0
        return {
            "budget_health_ratio": (1.0 - hd) * 0.75 + (1.0 - stability) * 0.25,
            "budget_edu_ratio": (1.0 - hd) * 0.80 + 0.20,
            "budget_social_ratio": (1.0 - stability) * 0.75 + runway_pressure * 0.25,
            "budget_gov_ratio": corruption * 0.75 + (1.0 - stability) * 0.25,
            "budget_env_ratio": hd * 0.25 + 0.20,
            "budget_research_ratio": hd * 0.65 + at_war * 0.20 + 0.15,
            "budget_infra_ratio": (1.0 - hd) * 0.35 + 0.45,
            "budget_telecom_ratio": hd * 0.45 + 0.25,
            "budget_imf_ratio": pl.lit(0.10),
            "budget_propaganda_ratio": (1.0 - stability) * 0.55 + at_war * 0.25,
            "budget_tourism_promo_ratio": stability * 0.45 + 0.10,
        }
