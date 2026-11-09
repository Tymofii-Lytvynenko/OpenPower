from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.trade_options import country_options, regions_for_owner


def test_trade_options_are_empty_when_country_or_region_schema_is_missing():
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame({"name": ["Unknown"]}),
            "regions": pl.DataFrame({"id": [1]}),
        }
    )

    assert country_options(state, "UKR") == []
    assert regions_for_owner(state, "UKR") == []
