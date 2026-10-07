from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import country_frame, with_defaults
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionResolveDebtContract,
    GameAction,
)


class EconomicPolicy:
    """Chooses conservative economic commands that the server validates identically to player commands."""

    id = "economic_health"
    required_tables = frozenset({"countries"})
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        raw = context.table("countries")
        if raw is None:
            return empty_candidates()
        base = with_defaults(country_frame(context, self.cadence_days), {
            "gdp": (pl.Float64, 0.0),
            "money_reserves": (pl.Float64, 0.0),
            "total_annual_revenue": (pl.Float64, 0.0),
            "total_annual_expense": (pl.Float64, 0.0),
            "inflation_rate": (pl.Float64, 0.0),
            "unemployment_rate": (pl.Float64, 0.0),
            "interest_rate": (pl.Float64, 0.05),
            "minimum_wage": (pl.Float64, 0.0),
            "poverty_rate": (pl.Float64, 0.0),
        }).with_columns(
            pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            pl.col("inflation_rate").cast(pl.Float64, strict=False).fill_null(0.0).alias("inflation_rate"),
            pl.col("interest_rate").cast(pl.Float64, strict=False).fill_null(0.05).alias("interest_rate"),
            pl.col("minimum_wage").cast(pl.Float64, strict=False).fill_null(0.0).alias("minimum_wage"),
            pl.col("poverty_rate").cast(pl.Float64, strict=False).fill_null(0.0).alias("poverty_rate"),
            pl.col("money_reserves").cast(pl.Float64, strict=False).fill_null(0.0).alias("money_reserves"),
            pl.col("gdp").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0).alias("gdp"),
            pl.col("total_annual_revenue").cast(pl.Float64, strict=False).fill_null(0.0).alias("total_annual_revenue"),
            pl.col("total_annual_expense").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0).alias("total_annual_expense"),
        )
        terms = context.globals.get("economic_health_terms", {})
        terms = terms if isinstance(terms, dict) else {}
        max_rate = self._bound(terms.get("max_interest_rate"), 0.0, 0.5, 0.5)
        inflation_threshold = self._bound(terms.get("inflation_warning_rate"), 0.0, 1.0, 0.1)
        unemployment_threshold = self._bound(terms.get("unemployment_warning_rate"), 0.0, 1.0, 0.2)
        poverty_threshold = self._bound(terms.get("poverty_warning_rate"), 0.0, 1.0, 0.35)
        maximum_wage = self._bound(terms.get("max_minimum_wage"), 0.0, 1_000_000_000.0, 1_000_000.0)

        candidates: list[pl.LazyFrame] = []
        high_inflation = (
            base.filter((pl.col("inflation_rate") > inflation_threshold) & (pl.col("interest_rate") < max_rate))
            .with_columns(
                pl.lit(self.id).alias("policy_id"), pl.lit("economy").alias("domain"),
                (0.6 + pl.col("inflation_rate").clip(0.0, 0.4)).alias("utility"),
                pl.concat_str([pl.lit("economic-policy:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("change_interest").alias("action_kind"), pl.lit("inflation_control").alias("reason_code"),
                pl.lit(1).alias("quota"), pl.lit("interest_rate").alias("policy_name"),
                (pl.col("interest_rate") + 0.01).clip(upper_bound=max_rate).alias("target_value"),
            )
        )
        candidates.append(high_inflation)

        low_inflation = (
            base.filter(
                (pl.col("inflation_rate") < max(0.01, inflation_threshold * 0.25))
                & (pl.col("interest_rate") > 0.01)
                & pl.col("unemployment_rate").cast(pl.Float64, strict=False).fill_null(0.0).gt(unemployment_threshold)
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"), pl.lit("economy").alias("domain"),
                (0.45 + pl.col("unemployment_rate").cast(pl.Float64, strict=False).fill_null(0.0).clip(0.0, 0.5)).alias("utility"),
                pl.concat_str([pl.lit("economic-policy:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("change_interest").alias("action_kind"), pl.lit("employment_support").alias("reason_code"),
                pl.lit(1).alias("quota"), pl.lit("interest_rate").alias("policy_name"),
                (pl.col("interest_rate") - 0.01).clip(lower_bound=0.0).alias("target_value"),
            )
        )
        candidates.append(low_inflation)

        wage_support = (
            base.filter(
                (pl.col("poverty_rate").cast(pl.Float64, strict=False).fill_null(0.0) >= poverty_threshold)
                & (pl.col("money_reserves") > pl.col("total_annual_expense") * 0.25)
                & (pl.col("minimum_wage") < maximum_wage)
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"), pl.lit("economy").alias("domain"),
                (0.4 + pl.col("poverty_rate").cast(pl.Float64, strict=False).fill_null(0.0).clip(0.0, 0.5)).alias("utility"),
                pl.concat_str([pl.lit("economic-policy:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("change_wage").alias("action_kind"), pl.lit("poverty_support").alias("reason_code"),
                pl.lit(1).alias("quota"), pl.lit("minimum_wage").alias("policy_name"),
                pl.max_horizontal(pl.col("minimum_wage") * 1.05, pl.lit(1.0)).clip(upper_bound=maximum_wage).alias("target_value"),
            )
        )
        candidates.append(wage_support)

        transition_table = context.table("economic_policy_transitions")
        if transition_table is not None:
            locks = transition_table.filter(
                pl.col("status").is_in(["scheduled", "applied"])
                & (pl.col("cooldown_until_minute") > int(context.total_minutes))
            ).select(
                pl.col("country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
                pl.col("policy_name").alias("_locked_policy"),
            ).unique()
            candidates = [
                frame.join(locks, left_on=["country_id", "policy_name"], right_on=["country_id", "_locked_policy"], how="anti")
                for frame in candidates
            ]

        debt_candidates = self._debt_candidates(context, base)
        if debt_candidates is not None:
            candidates.append(debt_candidates)
        return pl.concat(candidates, how="diagonal_relaxed") if candidates else empty_candidates()

    def _debt_candidates(self, context: AITableContext, base: pl.LazyFrame) -> pl.LazyFrame | None:
        contracts = context.table("debt_contracts")
        raw_countries = context.table("countries")
        if contracts is None or raw_countries is None:
            return None
        schema = set(contracts.collect_schema().names())
        if not {"id", "debtor_country_id", "creditor_country_id", "principal_original", "status"}.issubset(schema):
            return None

        active_debtors = contracts.filter(
            pl.col("status").is_in(["pending", "current", "arrears", "restructured"])
        ).select(pl.col("debtor_country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id")).unique()
        borrowing = (
            base.join(active_debtors, on="country_id", how="anti")
            .filter(
                (pl.col("total_annual_expense") > pl.col("total_annual_revenue"))
                & (pl.col("money_reserves") < pl.max_horizontal(1.0, pl.col("total_annual_expense") * 0.05))
            )
        )

        creditor_source = with_defaults(raw_countries, {
            "money_reserves": (pl.Float64, 0.0),
        }).select(
            pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("creditor_country_id"),
            pl.col("money_reserves").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0).alias("creditor_reserves"),
        ).filter(
            pl.col("creditor_country_id") != str(context.player_tag or "").strip().upper()
        ).sort(["creditor_reserves", "creditor_country_id"], descending=[True, False]).limit(2).collect()
        if creditor_source.height < 2:
            return None
        richest, second = creditor_source.to_dicts()
        creditor_expr = pl.when(pl.col("country_id") == richest["creditor_country_id"])
        creditor_expr = creditor_expr.then(pl.lit(second["creditor_country_id"])).otherwise(pl.lit(richest["creditor_country_id"]))
        reserve_expr = pl.when(pl.col("country_id") == richest["creditor_country_id"])
        reserve_expr = reserve_expr.then(pl.lit(second["creditor_reserves"])).otherwise(pl.lit(richest["creditor_reserves"]))
        terms = context.globals.get("economic_health_terms", {})
        terms = terms if isinstance(terms, dict) else {}
        requested_rate = self._bound(terms.get("ai_loan_interest_rate"), 0.0, 0.5, 0.05)
        max_ratio = self._bound(terms.get("max_principal_multiple_of_gdp"), 0.0, 100.0, 3.0)
        borrowing = borrowing.with_columns(
            creditor_expr.alias("creditor_country_id"),
            reserve_expr.alias("creditor_reserves"),
        ).with_columns(
            pl.min_horizontal(
                (pl.col("total_annual_expense") - pl.col("total_annual_revenue")).clip(lower_bound=1.0) * 0.25,
                pl.col("gdp") * max_ratio,
                pl.col("creditor_reserves"),
            ).alias("_principal")
        ).filter((pl.col("creditor_country_id") != pl.col("country_id")) & (pl.col("_principal") > 0.0))
        borrowing = borrowing.with_columns(
            pl.lit(self.id).alias("policy_id"), pl.lit("debt").alias("domain"),
            pl.lit(2.0).alias("utility"),
            pl.concat_str([pl.lit("debt-request:"), pl.col("country_id")]).alias("conflict_key"),
            pl.lit("request_debt").alias("action_kind"), pl.lit("fiscal_liquidity_shortfall").alias("reason_code"),
            pl.lit(1).alias("quota"), pl.col("creditor_country_id"), pl.col("_principal").alias("principal"),
            pl.lit(requested_rate).alias("annual_interest_rate"),
            (pl.col("_principal") / 12.0).alias("principal_installment"),
        )

        borrower_creditworthiness = with_defaults(raw_countries, {
            "economic_creditworthiness_modifier": (pl.Float64, 1.0),
        }).select(
            pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("_debtor_country_id"),
            pl.col("economic_creditworthiness_modifier")
            .cast(pl.Float64, strict=False)
            .fill_null(1.0)
            .clip(0.5, 1.0)
            .alias("_borrower_creditworthiness"),
        )
        pending = contracts.filter(pl.col("status") == "pending").select(
            pl.col("id").alias("contract_id"),
            pl.col("debtor_country_id").cast(pl.Utf8).str.to_uppercase().alias("debtor_country_id"),
            pl.col("creditor_country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            pl.col("principal_original").cast(pl.Float64, strict=False).fill_null(0.0).alias("principal"),
        ).join(
            borrower_creditworthiness,
            left_on="debtor_country_id",
            right_on="_debtor_country_id",
            how="left",
        ).with_columns(
            pl.col("_borrower_creditworthiness").fill_null(1.0)
        )
        ai_creditors = base.select("country_id", "money_reserves")
        approvals = (
            pending.join(ai_creditors, on="country_id", how="inner")
            .filter(pl.col("money_reserves") >= pl.col("principal"))
            .with_columns(
                pl.lit(self.id).alias("policy_id"), pl.lit("debt").alias("domain"),
                (1.5 * pl.col("_borrower_creditworthiness")).alias("utility"),
                pl.concat_str([pl.lit("debt-approval:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("approve_debt").alias("action_kind"), pl.lit("creditor_capacity_available").alias("reason_code"),
                pl.lit(1).alias("quota"),
            )
            .drop("money_reserves")
        )
        return pl.concat([borrowing, approvals], how="diagonal_relaxed")

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        country_id = str(row.get("country_id") or "")
        kind = str(row.get("action_kind") or "")
        if kind == "change_interest":
            return ActionChangeEconomicPolicy("ai_system", country_id, "interest_rate", float(row["target_value"]))
        if kind == "change_wage":
            return ActionChangeEconomicPolicy("ai_system", country_id, "minimum_wage", float(row["target_value"]))
        if kind == "request_debt":
            principal = max(1.0, float(row.get("principal") or 0.0))
            return ActionRequestDebtContract(
                "ai_system", country_id, str(row.get("creditor_country_id") or ""), principal,
                float(row.get("annual_interest_rate") or 0.05), 1,
                max(1.0, float(row.get("principal_installment") or principal / 12.0)), 12,
                "USD", "AI liquidity request; subject to creditor approval.",
            )
        if kind == "approve_debt":
            return ActionResolveDebtContract("ai_system", str(row.get("contract_id") or ""), True)
        return None

    def _bound(self, value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not (resolved == resolved and abs(resolved) != float("inf")):
            return default
        return min(max(resolved, minimum), maximum)
