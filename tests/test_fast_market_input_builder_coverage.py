import numpy as np
import polars as pl
import pytest

from modules.base.systems.economy.fast_market_input_builder import FastMarketInputBuilder
from modules.base.systems.economy.market_data import _FastMarketContext, _FastMarketLayout
from modules.base.systems.economy.missing_column_warning_registry import MissingColumnWarningRegistry
from src.shared.state import GameState


def _layout(production: pl.DataFrame, countries: pl.DataFrame, ledger: pl.DataFrame):
    context = _FastMarketContext(
        state=GameState(),
        production=production,
        countries=countries,
        ledger=ledger,
        country_id_series=countries.get_column("id"),
        production_country_ids=production.get_column("country_id"),
        production_resource_ids=production.get_column("game_resource_id"),
        key_columns=("country_id", "game_resource_id"),
    )
    return _FastMarketLayout(
        context=context,
        stockpiles=None,
        physics_entries=(),
        country_indices=np.array([0], dtype=np.int64),
        resource_indices=np.array([0], dtype=np.int64),
        decay_rates_by_resource=np.array([0.1], dtype=np.float64),
        storable_by_resource=np.array([True]),
        cache_hit=False,
        keys_are_sorted=True,
        country_ids_precede_world=True,
    )


def test_fast_market_input_builder_rejects_null_production_inputs():
    production = pl.DataFrame({"domestic_production": [None]})

    assert FastMarketInputBuilder()._production_values(production) is None


def test_fast_market_input_builder_rejects_nonfinite_country_trade_modifiers():
    production = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "game_resource_id": ["cereals"],
            "domestic_production": [10.0],
        }
    )
    countries = pl.DataFrame(
        {"id": ["AAA"], "economic_trade_modifier": [float("inf")]}
    )
    ledger = pl.DataFrame(
        {
            "country_id": ["AAA"],
            "game_resource_id": ["cereals"],
            "consumption_usd": [5.0],
        }
    )

    with pytest.raises(ValueError, match="economic_trade_modifier must contain finite values"):
        FastMarketInputBuilder().build(
            _layout(production, countries, ledger),
            MissingColumnWarningRegistry("trade"),
        )
