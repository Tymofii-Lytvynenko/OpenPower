import polars as pl

from modules.base.systems.economy.market_index_layout import MarketIndexLayoutResolver
from modules.base.systems.economy.market_data import _FastMarketContext
from src.shared.state import GameState


_RESOURCE_PHYSICS = {"cereals": {"is_storable": True, "decay_rate": 0.1}}


def _context(
    *,
    country_ids=("AAA",),
    production_country_ids=("AAA",),
    resource_ids=("cereals",),
    ledger_country_ids=None,
    ledger_resource_ids=None,
    production_values=None,
    stockpiles=None,
):
    ledger_country_ids = ledger_country_ids or production_country_ids
    ledger_resource_ids = ledger_resource_ids or resource_ids
    production = pl.DataFrame(
        {
            "country_id": list(production_country_ids),
            "game_resource_id": list(resource_ids),
            "domestic_production": production_values or [10.0] * len(resource_ids),
            "tax_rate": [0.1] * len(resource_ids),
        }
    )
    countries = pl.DataFrame(
        {
            "id": list(country_ids),
            "economic_trade_modifier": [1.0] * len(country_ids),
        }
    )
    ledger = pl.DataFrame(
        {
            "country_id": list(ledger_country_ids),
            "game_resource_id": list(ledger_resource_ids),
            "consumption_usd": [5.0] * len(ledger_resource_ids),
        }
    )
    tables = {} if stockpiles is None else {"stockpiles": stockpiles}
    return _FastMarketContext(
        state=GameState(tables=tables),
        production=production,
        countries=countries,
        ledger=ledger,
        country_id_series=countries.get_column("id"),
        production_country_ids=production.get_column("country_id"),
        production_resource_ids=production.get_column("game_resource_id"),
        key_columns=("country_id", "game_resource_id"),
    )


def _resolve(context):
    return MarketIndexLayoutResolver().resolve(context, _RESOURCE_PHYSICS)


def test_layout_rejects_misaligned_ledger_and_stockpile_rows():
    assert _resolve(
        _context(ledger_country_ids=("BBB",))
    ) is None

    stockpiles = pl.DataFrame(
        {
            "country_id": ["BBB"],
            "game_resource_id": ["cereals"],
            "stock_amount": [2.0],
        }
    )
    assert _resolve(_context(stockpiles=stockpiles)) is None


def test_layout_rejects_duplicate_keys_and_unsupported_numeric_columns():
    assert _resolve(
        _context(
            production_country_ids=("AAA", "AAA"),
            resource_ids=("cereals", "cereals"),
        )
    ) is None
    assert _resolve(_context(production_values=["ten"])) is None


def test_layout_rejects_duplicate_country_ids_and_unknown_resource_indices():
    assert _resolve(_context(country_ids=("AAA", "AAA"))) is None
    assert _resolve(_context(resource_ids=("unknown-resource",))) is None
