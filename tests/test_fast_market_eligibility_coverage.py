import polars as pl

from modules.base.systems.economy.fast_market_eligibility import FastMarketEligibilityPolicy
from src.shared.state import GameState


def _state(production: pl.DataFrame, countries: pl.DataFrame, ledger: pl.DataFrame) -> GameState:
    return GameState(
        tables={
            "domestic_production": production,
            "countries": countries,
            "resource_ledger": ledger,
        }
    )


def test_fast_market_rejects_tables_missing_required_columns():
    state = _state(
        production=pl.DataFrame({"country_id": ["AAA"], "game_resource_id": ["cereals"]}),
        countries=pl.DataFrame({"id": ["AAA"]}),
        ledger=pl.DataFrame(
            {"country_id": ["AAA"], "game_resource_id": ["cereals"], "consumption_usd": [10.0]}
        ),
    )

    assert FastMarketEligibilityPolicy.select_context(state) is None


def test_fast_market_rejects_non_string_join_keys():
    state = _state(
        production=pl.DataFrame(
            {
                "country_id": [1],
                "game_resource_id": ["cereals"],
                "domestic_production": [10.0],
            }
        ),
        countries=pl.DataFrame({"id": [1]}),
        ledger=pl.DataFrame(
            {"country_id": [1], "game_resource_id": ["cereals"], "consumption_usd": [5.0]}
        ),
    )

    assert FastMarketEligibilityPolicy.select_context(state) is None
