from __future__ import annotations

from collections.abc import Callable

import polars as pl

from modules.base.systems.economy.market_cycle_calculations import (
    ConstrainedMarketReconciler,
    MarketBalanceCalculator,
    TreatyProductionBonusPolicy,
)
from modules.base.systems.economy.market_cycle_publisher import MarketCyclePublisher
from modules.base.systems.economy.market_flow_resolver import (
    MarketCountryBudgetUpdater,
    MarketFlowResolver,
)
from modules.base.systems.economy.market_frame_builder import MarketFrameBuilder
from modules.base.systems.economy.market_input_validator import MarketInputValidator
from modules.base.systems.economy.missing_column_warning_registry import (
    MissingColumnWarningRegistry,
)
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from src.shared.state import GameState


class DataFrameMarketSimulator:
    """Coordinate the policy-aware Polars path for market cycles."""

    def __init__(
        self,
        input_validator: MarketInputValidator,
        frame_builder: MarketFrameBuilder,
        production_bonus_policy: TreatyProductionBonusPolicy,
        balance_calculator: MarketBalanceCalculator,
        flow_resolver: MarketFlowResolver,
        cycle_publisher: MarketCyclePublisher,
    ) -> None:
        self._input_validator = input_validator
        self._frame_builder = frame_builder
        self._production_bonus_policy = production_bonus_policy
        self._balance_calculator = balance_calculator
        self._flow_resolver = flow_resolver
        self._cycle_publisher = cycle_publisher

    @classmethod
    def create_default(
        cls,
        input_validator: MarketInputValidator,
        frame_builder: MarketFrameBuilder,
        treaty_trade_policy: TreatyTradePolicy,
        regional_trade_access: Callable[[GameState, int, str, str], bool],
    ) -> DataFrameMarketSimulator:
        flow_resolver = MarketFlowResolver(
            treaty_trade_policy=treaty_trade_policy,
            constrained_market_reconciler=ConstrainedMarketReconciler(),
            country_budget_updater=MarketCountryBudgetUpdater(),
            regional_trade_access=regional_trade_access,
        )
        return cls(
            input_validator=input_validator,
            frame_builder=frame_builder,
            production_bonus_policy=TreatyProductionBonusPolicy(),
            balance_calculator=MarketBalanceCalculator(),
            flow_resolver=flow_resolver,
            cycle_publisher=MarketCyclePublisher(),
        )

    def simulate(
        self,
        state: GameState,
        fraction: float,
        resource_physics: pl.DataFrame,
        warning_registry: MissingColumnWarningRegistry,
    ) -> None:
        # Invalid quantities otherwise contaminate global ratios and every country's closing stock.
        self._input_validator.validate(state)
        production = state.get_table("domestic_production")
        production_with_bonuses = self._production_bonus_policy.apply(
            state,
            production.lazy(),
        )
        market = self._frame_builder.build(
            state,
            production_with_bonuses,
            resource_physics,
            warning_registry,
        )
        balanced_market = self._balance_calculator.calculate(market, fraction)
        resolution = self._flow_resolver.resolve(state, balanced_market, fraction)
        self._cycle_publisher.publish(state, resolution)

    def apply_treaty_production_bonus(
        self,
        state: GameState,
        production: pl.LazyFrame,
    ) -> pl.LazyFrame:
        return self._production_bonus_policy.apply(state, production)

    def apply_constrained_flows(
        self,
        market: pl.DataFrame,
        flows: pl.DataFrame,
        fraction: float,
    ) -> pl.DataFrame:
        return self._flow_resolver.reconcile_constrained_flows(
            market,
            flows,
            fraction,
        )

    def countries_from_constrained_market(
        self,
        state: GameState,
        market: pl.DataFrame,
    ) -> pl.DataFrame:
        return self._flow_resolver.countries_from_market(state, market)
