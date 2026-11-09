from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.economy.consumption_fast_path import (
    calculate_formulaic_consumption,
)


_FORMULAS = {
    "resource_a": {
        "solvent_base_consumption": 1.0,
        "general_base_consumption": 1.0,
        "output_multiplier": 1.0,
    }
}


def _countries() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id": ["AAA"],
            "gdp": [100.0],
            "gdp_per_capita": [100.0],
        }
    )


def _population() -> pl.DataFrame:
    return pl.DataFrame({"country_id": ["AAA"], "population": [1.0]})


def _calculate(
    countries: pl.DataFrame | None = None,
    population: pl.DataFrame | None = None,
) -> pl.DataFrame | None:
    return calculate_formulaic_consumption(
        countries if countries is not None else _countries(),
        population if population is not None else _population(),
        _FORMULAS,
        ("resource_a",),
    )


@pytest.mark.parametrize(
    ("countries", "population"),
    [
        (pl.DataFrame({"name": ["AAA"]}), _population()),
        (_countries(), pl.DataFrame({"country_id": ["AAA"]})),
    ],
)
def test_fast_path_rejects_missing_identity_or_population_columns(
    countries: pl.DataFrame,
    population: pl.DataFrame,
) -> None:
    assert _calculate(countries, population) is None


def test_fast_path_rejects_non_string_identifiers() -> None:
    countries = pl.DataFrame({"id": [1], "gdp": [100.0], "gdp_per_capita": [100.0]})

    assert _calculate(countries) is None


def test_fast_path_rejects_null_and_duplicate_identifiers() -> None:
    null_country_ids = _countries().with_columns(
        pl.Series("id", [None], dtype=pl.String)
    )
    assert _calculate(null_country_ids) is None

    duplicate_country_ids = pl.DataFrame(
        {"id": ["AAA", "AAA"], "gdp": [100.0, 100.0], "gdp_per_capita": [100.0, 100.0]}
    )
    assert _calculate(duplicate_country_ids) is None


def test_fast_path_rejects_unparseable_population() -> None:
    population = pl.DataFrame(
        {"country_id": ["AAA"], "population": ["not-a-number"]}
    )

    assert _calculate(population=population) is None


@pytest.mark.parametrize("value", [-1.0, float("inf")])
def test_fast_path_rejects_negative_or_non_finite_population(value: float) -> None:
    population = pl.DataFrame({"country_id": ["AAA"], "population": [value]})

    assert _calculate(population=population) is None


@pytest.mark.parametrize(
    "column",
    [
        "poverty_rate",
        "human_dev",
        "gdp_per_capita",
        "real_income_index",
        "economic_trade_modifier",
    ],
)
def test_fast_path_rejects_unparseable_optional_metrics(column: str) -> None:
    countries = _countries().with_columns(pl.lit("not-a-number").alias(column))

    assert _calculate(countries) is None


def test_fast_path_rejects_unparseable_total_gdp() -> None:
    countries = _countries().with_columns(pl.lit("not-a-number").alias("gdp"))

    assert _calculate(countries) is None
