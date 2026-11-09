import polars as pl

from modules.base.systems.economy.economic_country_value_updater import (
    AddCountryValue,
    DeterministicEconomicCountryValueUpdater,
)


def test_missing_columns_are_ignored_when_building_country_update() -> None:
    frame = pl.DataFrame({"id": ["country-a"], "money_reserves": [100.0]})
    updater = DeterministicEconomicCountryValueUpdater()

    result = updater.apply(
        frame,
        "country-a",
        {
            "unknown_policy": AddCountryValue(2.0),
            "money_reserves": AddCountryValue(25.0),
        },
    )

    assert result is not None
    assert result.get_column("money_reserves").to_list() == [125.0]
    assert "unknown_policy" not in result.columns
