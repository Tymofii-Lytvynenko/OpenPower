from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from modules.base.systems.economy.market_cycle_calculations import (
    ConstrainedMarketReconciler,
)
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from src.shared.numeric import stable_group_sums
from src.shared.state import GameState


@dataclass(frozen=True)
class MarketFlowResolution:
    market: pl.DataFrame
    constrained_flows: pl.DataFrame | None
    countries: pl.DataFrame


class MarketCountryBudgetUpdater:
    """Build country income and expense columns from market fiscal totals."""

    @staticmethod
    def build(state: GameState, market: pl.DataFrame) -> pl.DataFrame:
        updates = stable_group_sums(
            market,
            ("country_id",),
            {
                "gov_tax_revenue": "trade_income",
                "gov_import_expense": "trade_expense",
            },
        )
        return (
            state.get_table("countries")
            .drop(["trade_income", "trade_expense"], strict=False)
            .join(updates, left_on="id", right_on="country_id", how="left")
            .with_columns(pl.col(["trade_income", "trade_expense"]).fill_null(0.0))
        )


class MarketFlowResolver:
    """Choose treaty-aware market flows and reconcile the resulting balances."""

    def __init__(
        self,
        treaty_trade_policy: TreatyTradePolicy,
        constrained_market_reconciler: ConstrainedMarketReconciler,
        country_budget_updater: MarketCountryBudgetUpdater,
        regional_trade_access: Callable[[GameState, int, str, str], bool],
    ) -> None:
        self._treaty_trade_policy = treaty_trade_policy
        self._constrained_market_reconciler = constrained_market_reconciler
        self._country_budget_updater = country_budget_updater
        self._regional_trade_access = regional_trade_access

    def resolve(
        self,
        state: GameState,
        market: pl.DataFrame,
        fraction: float,
    ) -> MarketFlowResolution:
        treaty_effects = state.tables.get("treaty_effects")
        regional_production = state.tables.get("regional_production")
        constrained_flows = None

        if regional_production is not None and not regional_production.is_empty():
            effects = treaty_effects if treaty_effects is not None else pl.DataFrame()
            constrained_flows = self._treaty_trade_policy.allocate_with_regional_sources(
                market,
                effects,
                regional_production,
                lambda region_id, exporter_id, importer_id: self._regional_trade_access(
                    state,
                    region_id,
                    exporter_id,
                    importer_id,
                ),
            )
        elif self._treaty_trade_policy.has_constraints(treaty_effects):
            constrained_flows = self._treaty_trade_policy.allocate(market, treaty_effects)

        if constrained_flows is not None:
            market = self._constrained_market_reconciler.reconcile(
                market,
                constrained_flows,
                fraction,
            )

        countries = self._country_budget_updater.build(state, market)
        return MarketFlowResolution(
            market=market,
            constrained_flows=constrained_flows,
            countries=countries,
        )

    def reconcile_constrained_flows(
        self,
        market: pl.DataFrame,
        flows: pl.DataFrame,
        fraction: float,
    ) -> pl.DataFrame:
        return self._constrained_market_reconciler.reconcile(market, flows, fraction)

    def countries_from_market(self, state: GameState, market: pl.DataFrame) -> pl.DataFrame:
        return self._country_budget_updater.build(state, market)
