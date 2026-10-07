from __future__ import annotations

import polars as pl

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
        life_expectancies=pl.Series([50.0], dtype=pl.Float64),
        economic_health=pl.Series([1.0], dtype=pl.Float64),
    )

    assert updated is not None
    assert updated.select("pop_14", "pop_15_64", "pop_65").row(0) == (
        14_500,
        35_300,
        10_500,
    )
    assert updated.get_column("custom_region_data").to_list() == ["retained"]
    assert updated.schema["pop_14"] == pl.Int64


def test_health_event_modifier_is_aligned_by_region_without_changing_order() -> None:
    regions = pl.DataFrame(
        {
            "id": [1, 2],
            "owner": ["AAA", "AAA"],
            "pop_14": [0, 0],
            "pop_15_64": [0, 0],
            "pop_65": [100_000, 100_000],
            "health_capacity": [1.0, 1.0],
        }
    )

    updated = calculate_population_growth(
        regions,
        days_passed=365.25,
        fertility_rates=pl.Series([2.0, 2.0], dtype=pl.Float64),
        life_expectancies=pl.Series([50.0, 50.0], dtype=pl.Float64),
        economic_health=pl.Series([1.0, 1.0], dtype=pl.Float64),
        event_health_by_region={2: 0.25},
    )

    assert updated is not None
    assert updated.get_column("id").to_list() == [1, 2]
    assert updated.item(1, "pop_65") > updated.item(0, "pop_65")


def test_nonstandard_or_unsafe_population_values_request_polars_fallback() -> None:
    fertility = pl.Series([2.0], dtype=pl.Float64)
    life_expectancy = pl.Series([67.0], dtype=pl.Float64)
    economic_health = pl.Series([1.0], dtype=pl.Float64)
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
            life_expectancies=life_expectancy,
            economic_health=economic_health,
        ) is None
