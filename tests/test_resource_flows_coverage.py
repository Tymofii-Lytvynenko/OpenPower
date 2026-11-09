import polars as pl
import pytest

from src.client.ui.panels.resource_flows import build_resource_flows, validate_resource_ledger


def _ledger():
    return pl.DataFrame(
        {
            "country_id": ["USA"],
            "game_resource_id": ["grain"],
            "category": ["food"],
            "production_usd": [10.0],
            "consumption_usd": [8.0],
            "trade_usd": [0.0],
            "balance_usd": [2.0],
        }
    )


def test_resource_flow_validation_requires_the_ledger_table():
    with pytest.raises(ValueError, match="requires the resource_ledger table"):
        validate_resource_ledger(None)


def test_resource_flows_reject_trade_tables_without_required_columns():
    with pytest.raises(ValueError, match="Trade network is missing required columns"):
        build_resource_flows(_ledger(), pl.DataFrame({"invalid": [1]}), "USA")
