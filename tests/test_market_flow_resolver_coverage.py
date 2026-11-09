from unittest.mock import Mock

import polars as pl

from modules.base.systems.economy.market_flow_resolver import MarketFlowResolver


def test_countries_from_market_delegates_to_injected_budget_updater() -> None:
    state = Mock()
    market = pl.DataFrame({"country_id": ["USA"]})
    expected_countries = pl.DataFrame({"id": ["USA"]})
    country_budget_updater = Mock()
    country_budget_updater.build.return_value = expected_countries
    resolver = MarketFlowResolver(
        treaty_trade_policy=Mock(),
        constrained_market_reconciler=Mock(),
        country_budget_updater=country_budget_updater,
        regional_trade_access=Mock(),
    )

    result = resolver.countries_from_market(state, market)

    assert result is expected_countries
    country_budget_updater.build.assert_called_once_with(state, market)
