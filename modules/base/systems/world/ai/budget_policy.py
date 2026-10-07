from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import active_war_members, country_frame, with_defaults
from src.core.ai_framework import AITableContext
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


class BudgetSurvivalPolicy:
    id = "budget_survival"
    required_tables = frozenset({"countries"})
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        discretionary_defaults = {
            column: (pl.Float64, 0.5) for column in DISCRETIONARY_COLUMNS
        }
        discretionary_defaults["budget_imf_ratio"] = (pl.Float64, 0.0)
        countries = with_defaults(
            country_frame(context, self.cadence_days),
            discretionary_defaults,
        )
        return (
            countries.with_columns(
                (pl.col("total_annual_revenue") - pl.col("total_annual_expense")).alias("_annual_balance")
            )
            .with_columns(
                pl.when(pl.col("_annual_balance") < 0.0)
                .then(
                    (pl.col("money_reserves").clip(lower_bound=0.0) * 12.0)
                    / pl.col("_annual_balance").abs().clip(lower_bound=1.0)
                )
                .otherwise(999.0)
                .alias("_runway_months")
            )
            .filter(
                (pl.col("_annual_balance") < 0.0)
                & ((pl.col("_runway_months") < 12.0) | (pl.col("money_reserves") < 0.0))
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("budget").alias("domain"),
                (1.0 - pl.col("_runway_months") / 12.0).alias("utility"),
                pl.concat_str([pl.lit("budget:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("update_budget").alias("action_kind"),
                pl.lit("critical_deficit").alias("reason_code"),
                pl.lit(1).alias("quota"),
                pl.lit("__discretionary__").alias("allocation_column"),
                pl.lit(None, dtype=pl.Float64).alias("allocation_value"),
                (pl.col("personal_income_tax_rate") + 0.02)
                .clip(upper_bound=0.50)
                .alias("tax_value"),
            )
            .select(
                "country_id",
                "policy_id",
                "domain",
                "utility",
                "conflict_key",
                "action_kind",
                "reason_code",
                "quota",
                "allocation_column",
                "allocation_value",
                "tax_value",
                "_runway_months",
                *DISCRETIONARY_COLUMNS,
            )
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if row.get("tax_value") is None:
            return None
        allocations = {
            column: max(0.0, float(row.get(column) or 0.0) * 0.80)
            for column in DISCRETIONARY_COLUMNS
        }
        allocations["personal_income_tax_rate"] = min(0.50, float(row["tax_value"]))
        return ActionUpdateBudget(
            "ai_system",
            str(row.get("country_id") or ""),
            allocations,
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

        wars_table = context.tables.get("countries_wars")
        if wars_table is None or wars_table.is_empty():
            base = countries.with_columns(pl.lit(0).alias("_active_wars"))
        else:
            wars = (
                active_war_members(context)
                .group_by("country_id")
                .agg(pl.len().alias("_active_wars"))
            )
            base = countries.join(wars, on="country_id", how="left").with_columns(
                pl.col("_active_wars").fill_null(0)
            )
        base = base.with_columns(
            (pl.col("total_annual_revenue") - pl.col("total_annual_expense")).alias("_annual_balance")
        ).with_columns(
            pl.when(pl.col("_annual_balance") < 0.0)
            .then(
                (pl.col("money_reserves").clip(lower_bound=0.0) * 12.0)
                / pl.col("_annual_balance").abs().clip(lower_bound=1.0)
            )
            .otherwise(999.0)
            .alias("_runway_months"),
            (pl.col("_active_wars") > 0).cast(pl.Float64).alias("_at_war"),
        )
        category_scores = self._category_scores()
        score_expressions: list[pl.Expr] = []
        utility_columns: list[tuple[str, str, str]] = []
        for index, (column, score) in enumerate(sorted(category_scores.items())):
            deficit_name = f"_deficit_utility_{index:02d}"
            surplus_name = f"_surplus_utility_{index:02d}"
            deficit_eligible = (
                (pl.col("_annual_balance") < 0.0)
                & (pl.col("_runway_months") >= 12.0)
                & (pl.col(column) > 0.0)
            )
            surplus_eligible = (
                (pl.col("_annual_balance") > 0.0)
                & (
                    pl.col("money_reserves")
                    > pl.col("total_annual_expense").clip(lower_bound=1.0) * 0.5
                )
                & (pl.col(column) < 1.0)
            )
            deficit_utility = (
                0.45
                + (
                    pl.col("_annual_balance").abs()
                    / pl.col("total_annual_revenue").abs().clip(lower_bound=1.0)
                ).clip(0.0, 0.45)
                + (1.0 - score.clip(0.0, 1.0)) * 0.10
            )
            surplus_utility = (
                0.35
                + (
                    pl.col("_annual_balance")
                    / pl.col("total_annual_revenue").abs().clip(lower_bound=1.0)
                ).clip(0.0, 0.35)
                + score.clip(0.0, 1.0) * 0.20
            )
            score_expressions.extend(
                (
                    pl.when(deficit_eligible & deficit_utility.is_finite())
                    .then(deficit_utility)
                    .otherwise(None)
                    .alias(deficit_name),
                    pl.when(surplus_eligible & surplus_utility.is_finite())
                    .then(surplus_utility)
                    .otherwise(None)
                    .alias(surplus_name),
                )
            )
            utility_columns.append((column, deficit_name, surplus_name))

        scored = base.with_columns(score_expressions).with_columns(
            pl.max_horizontal(
                [pl.col(name) for _, deficit_name, surplus_name in utility_columns for name in (deficit_name, surplus_name)]
            ).alias("_best_utility")
        )
        best_category = pl.coalesce(
            [
                pl.when(
                    pl.any_horizontal(
                        pl.col(deficit_name) == pl.col("_best_utility"),
                        pl.col(surplus_name) == pl.col("_best_utility"),
                    )
                )
                .then(pl.lit(column))
                .otherwise(None)
                for column, deficit_name, surplus_name in utility_columns
            ]
        )
        allocation_value = pl.coalesce(
            [
                pl.when(pl.col("allocation_column") == column)
                .then(
                    pl.when(pl.col("_annual_balance") < 0.0)
                    .then((pl.col(column) - 0.05).clip(lower_bound=0.0))
                    .otherwise((pl.col(column) + 0.05).clip(upper_bound=1.0))
                )
                .otherwise(None)
                for column, _, _ in utility_columns
            ]
        )
        ordinary = (
            scored.with_columns(best_category.alias("allocation_column"))
            .with_columns(
                allocation_value.alias("allocation_value"),
                pl.col("_best_utility").alias("utility"),
                pl.when(pl.col("_annual_balance") < 0.0)
                .then(pl.lit("managed_deficit"))
                .otherwise(pl.lit("sustained_surplus"))
                .alias("reason_code"),
                pl.lit(None, dtype=pl.Float64).alias("tax_value"),
            )
            .filter(pl.col("_best_utility").is_not_null())
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("budget").alias("domain"),
                pl.concat_str([pl.lit("budget:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("update_budget").alias("action_kind"),
                pl.lit(1).alias("quota"),
            )
        )
        candidate_columns = [
            "country_id",
            "policy_id",
            "domain",
            "utility",
            "conflict_key",
            "action_kind",
            "reason_code",
            "quota",
            "allocation_column",
            "allocation_value",
            "tax_value",
            "_runway_months",
        ]
        return ordinary.select(candidate_columns)

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
