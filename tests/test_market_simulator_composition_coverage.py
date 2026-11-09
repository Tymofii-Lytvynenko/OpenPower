from unittest.mock import Mock

import polars as pl

from modules.base.systems.economy.dataframe_market_simulator import DataFrameMarketSimulator
from modules.base.systems.economy.market_frame_builder import MarketFrameBuilder
from modules.base.systems.economy.missing_column_warning_registry import MissingColumnWarningRegistry
from modules.base.systems.economy.unconstrained_market_simulator import UnconstrainedMarketSimulator


def test_market_frame_builder_adds_defaults_and_reports_missing_columns(capsys):
    market = pl.DataFrame({"country_id": ["AAA"]}).lazy()

    result = MarketFrameBuilder._with_default_column(
        market,
        production_columns=[],
        warning_registry=MissingColumnWarningRegistry("trade"),
        column="tax_rate",
        default=0.05,
    ).collect()

    assert result["tax_rate"].to_list() == [0.05]
    assert "Column 'tax_rate' not found" in capsys.readouterr().out


def test_dataframe_simulator_delegates_to_composed_policy_and_resolver():
    bonus_policy = Mock()
    flow_resolver = Mock()
    simulator = DataFrameMarketSimulator(
        input_validator=Mock(),
        frame_builder=Mock(),
        production_bonus_policy=bonus_policy,
        balance_calculator=Mock(),
        flow_resolver=flow_resolver,
        cycle_publisher=Mock(),
    )
    state = object()
    production = pl.DataFrame({"country_id": ["AAA"]}).lazy()
    market = pl.DataFrame({"country_id": ["AAA"]})

    assert simulator.apply_treaty_production_bonus(state, production) is bonus_policy.apply.return_value
    assert simulator.countries_from_constrained_market(state, market) is flow_resolver.countries_from_market.return_value
    bonus_policy.apply.assert_called_once_with(state, production)
    flow_resolver.countries_from_market.assert_called_once_with(state, market)


def test_unconstrained_simulator_caches_index_and_rejects_missing_layout():
    eligibility_policy = Mock()
    eligibility_policy.select_context.return_value = object()
    index_resolver = Mock()
    index_resolver.resolve.return_value = None
    simulator = UnconstrainedMarketSimulator(
        eligibility_policy=eligibility_policy,
        index_resolver=index_resolver,
    )
    cache = object()
    simulator.market_index_cache = cache

    assert simulator.market_index_cache is cache
    assert not simulator.simulate(
        state=object(),
        fraction=0.5,
        resource_physics={},
        warning_registry=Mock(),
    )
    index_resolver.resolve.assert_called_once()
