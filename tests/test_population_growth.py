from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.demographics.population_growth import calculate_population_growth


def test_vectorized_growth_matches_cohort_formula_and_preserves_region_columns() -> None:
    regions = pl.DataFrame(
        {
            "id": [1],
            "owner": ["AAA"],
            "pop_14": [15_000],
            "pop_15_64": [35_000],
            "pop_65": [10_000],
            "health_capacity": [1.0],
            "custom_region_data": ["retained"],
        }
    )

    updated = calculate_population_growth(
        regions,
        days_passed=365.25,
        fertility_rates=pl.Series([2.0], dtype=pl.Float64),
        death_rates=pl.Series([10.0]),
    )

    assert updated is not None
    assert updated.select("pop_14", "pop_15_64", "pop_65").row(0) == (
        14_360,
        34_947,
        10_593,
    )
    assert updated.get_column("custom_region_data").to_list() == ["retained"]
    assert updated.schema["pop_14"] == pl.Int64
    population = 14_360 + 34_947 + 10_593
    assert updated.item(0, "birth_rate_per_1000") == pytest.approx(1000 * 34_947 * 2 * 0.25 / 35 / population)


def test_mortality_applies_even_without_retirement_age_residents() -> None:
    regions = pl.DataFrame({"pop_14": [0], "pop_15_64": [10_000], "pop_65": [0]})
    updated = calculate_population_growth(
        regions,
        days_passed=365.25,
        fertility_rates=pl.Series([0.0]),
        death_rates=pl.Series([10.0]),
    )
    assert updated is not None
    assert sum(updated.select("pop_14", "pop_15_64", "pop_65").row(0)) == 9_900

    for _ in range(10):
        regions = calculate_population_growth(
            regions,
            days_passed=365.25 / 1000,
            fertility_rates=pl.Series([0.0]),
            death_rates=pl.Series([10.0]),
        )
        assert regions is not None
    assert sum(regions.select("pop_14", "pop_15_64", "pop_65").row(0)) == 9_999


def test_nonstandard_or_unsafe_population_values_request_polars_fallback() -> None:
    fertility = pl.Series([2.0], dtype=pl.Float64)
    mortality = pl.Series([10.0])
    nonnumeric = pl.DataFrame(
        {
            "pop_14": ["unknown"],
            "pop_15_64": [100],
            "pop_65": [0],
        }
    )
    unsafe = pl.DataFrame(
        {
            "pop_14": [float("inf")],
            "pop_15_64": [100.0],
            "pop_65": [0.0],
        }
    )

    for regions in (nonnumeric, unsafe):
        assert calculate_population_growth(
            regions,
            days_passed=1.0,
            fertility_rates=fertility,
            death_rates=mortality,
        ) is None


def test_missing_population_cohort_column_requests_polars_fallback() -> None:
    regions = pl.DataFrame({"pop_14": [10], "pop_15_64": [20]})

    assert calculate_population_growth(
        regions,
        days_passed=1.0,
        fertility_rates=pl.Series([2.0], dtype=pl.Float64),
        death_rates=pl.Series([10.0]),
    ) is None


def test_parameter_array_length_mismatch_requests_polars_fallback() -> None:
    regions = pl.DataFrame(
        {"pop_14": [10, 20], "pop_15_64": [20, 30], "pop_65": [5, 10]}
    )

    assert calculate_population_growth(
        regions,
        days_passed=1.0,
        fertility_rates=pl.Series([2.0], dtype=pl.Float64),
        death_rates=pl.Series([10.0]),
    ) is None
