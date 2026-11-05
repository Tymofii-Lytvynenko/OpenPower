from __future__ import annotations

from collections.abc import Callable, Mapping

from modules.base.systems.economy.fast_market_eligibility import FastMarketEligibilityPolicy
from modules.base.systems.economy.fast_market_input_builder import FastMarketInputBuilder
from modules.base.systems.economy.market_clearing_kernel import (
    UnconstrainedMarketResult,
    calculate_unconstrained_market,
)
from modules.base.systems.economy.market_data import (
    _MarketIndexCache,
)
from modules.base.systems.economy.market_index_layout import MarketIndexLayoutResolver
from modules.base.systems.economy.fast_market_output_publisher import FastMarketOutputPublisher
from modules.base.systems.economy.missing_column_warning_registry import MissingColumnWarningRegistry
from src.shared.state import GameState


class UnconstrainedMarketSimulator:
    """Coordinate the composable stages of the unconstrained NumPy market path."""

    def __init__(
        self,
        eligibility_policy: FastMarketEligibilityPolicy | None = None,
        index_resolver: MarketIndexLayoutResolver | None = None,
        input_builder: FastMarketInputBuilder | None = None,
        output_publisher: FastMarketOutputPublisher | None = None,
        market_kernel: Callable[..., UnconstrainedMarketResult] | None = None,
    ) -> None:
        self._eligibility_policy = (
            eligibility_policy
            if eligibility_policy is not None
            else FastMarketEligibilityPolicy()
        )
        self._index_resolver = (
            index_resolver if index_resolver is not None else MarketIndexLayoutResolver()
        )
        self._input_builder = (
            input_builder if input_builder is not None else FastMarketInputBuilder()
        )
        self._output_publisher = (
            output_publisher
            if output_publisher is not None
            else FastMarketOutputPublisher()
        )
        self._market_kernel = (
            market_kernel if market_kernel is not None else calculate_unconstrained_market
        )

    @property
    def market_index_cache(self) -> _MarketIndexCache | None:
        return self._index_resolver.market_index_cache

    @market_index_cache.setter
    def market_index_cache(self, value: _MarketIndexCache | None) -> None:
        self._index_resolver.market_index_cache = value

    def simulate(
        self,
        state: GameState,
        fraction: float,
        resource_physics: Mapping[str, Mapping[str, bool | float]],
        warning_registry: MissingColumnWarningRegistry,
    ) -> bool:
        context = self._eligibility_policy.select_context(state)
        if context is None:
            return False
        layout = self._index_resolver.resolve(context, resource_physics)
        if layout is None:
            return False
        arrays = self._input_builder.build(layout, warning_registry)
        if arrays is None:
            return False

        clearing = self._market_kernel(
            production_values=arrays.production_values,
            demand=arrays.demand,
            stock=arrays.stock,
            trade_modifiers=arrays.trade_modifiers,
            resource_indices=layout.resource_indices,
            country_indices=layout.country_indices,
            decay_rates_by_resource=layout.decay_rates_by_resource,
            storable_by_resource=layout.storable_by_resource,
            government_controlled=arrays.government_controlled,
            legal=arrays.legal,
            tax_rates=arrays.tax_rates,
            fraction=fraction,
            row_count=layout.context.production.height,
            country_count=layout.context.countries.height,
        )
        prepared = self._output_publisher.prepare(layout, arrays, clearing)
        self._index_resolver.remember_layout(layout, prepared)
        self._output_publisher.publish(state, layout, prepared, clearing)
        return True
