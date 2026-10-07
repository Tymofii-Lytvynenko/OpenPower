from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import polars as pl


_SUPPORTED_NUMERIC_DTYPES = frozenset(
    {
        pl.Float32,
        pl.Float64,
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    }
)
_INT64_UPPER_BOUND = float(2**63)
DAYS_PER_YEAR = 365.25
FEMALE_RATIO = 0.25
CHILDBEARING_YEARS = 35
CHILDREN_BRACKET_YEARS = 15
WORKING_AGE_BRACKET_YEARS = 50
DAILY_CHILDREN_AGING = 1 / (CHILDREN_BRACKET_YEARS * DAYS_PER_YEAR)
DAILY_WORKING_AGE_AGING = 1 / (WORKING_AGE_BRACKET_YEARS * DAYS_PER_YEAR)


def calculate_population_growth(
    regions: pl.DataFrame,
    *,
    days_passed: float,
    fertility_rates: pl.Series,
    life_expectancies: pl.Series,
    economic_health: pl.Series,
    event_health_by_region: Mapping[int, float] | None = None,
) -> pl.DataFrame | None:
    """Calculate one bounded cohort update without materializing a lazy plan.

    Return ``None`` for schemas or numeric ranges that need Polars' broader
    casting behavior; the caller can then use its compatibility implementation.
    """
    cohort_columns = ("pop_14", "pop_15_64", "pop_65")
    if not set(cohort_columns).issubset(regions.columns):
        return None
    if any(
        regions.schema[column] not in _SUPPORTED_NUMERIC_DTYPES
        for column in cohort_columns
    ):
        return None
    if (
        "health_capacity" in regions.columns
        and regions.schema["health_capacity"] not in _SUPPORTED_NUMERIC_DTYPES
    ):
        return None

    row_count = regions.height
    parameter_arrays = tuple(
        np.asarray(values.to_numpy(), dtype=np.float64)
        for values in (fertility_rates, life_expectancies, economic_health)
    )
    if any(values.size != row_count for values in parameter_arrays):
        return None
    fertility, life_expectancy, economic_health_values = parameter_arrays

    population = tuple(
        np.maximum(
            regions.get_column(column).fill_null(0).to_numpy(),
            0.0,
        )
        for column in cohort_columns
    )
    children, working_age, retirement_age = population
    if "health_capacity" in regions.columns:
        health_capacity = np.clip(
            regions.get_column("health_capacity").fill_null(1.0).to_numpy(),
            0.0,
            1.0,
        )
    else:
        health_capacity = 1.0

    event_modifier: float | np.ndarray = 0.0
    if event_health_by_region and "id" in regions.columns:
        event_modifier = np.fromiter(
            (
                max(
                    -0.5,
                    min(0.25, float(event_health_by_region.get(region_id, 0.0))),
                )
                for region_id in regions.get_column("id").to_list()
            ),
            dtype=np.float64,
            count=row_count,
        )

    days = max(0.0, float(days_passed))
    aging_children_step = min(1.0, DAILY_CHILDREN_AGING * days)
    aging_working_step = min(1.0, DAILY_WORKING_AGE_AGING * days)
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        adjusted_life_expectancy = np.maximum(
            life_expectancy
            * (0.9 + 0.1 * health_capacity)
            * (0.9 + 0.1 * economic_health_values)
            * (1.0 + event_modifier),
            1.0,
        )
        birth_step = (
            fertility
            * FEMALE_RATIO
            / CHILDBEARING_YEARS
            / DAYS_PER_YEAR
            * days
        )
        death_step = np.clip(
            1.0 / (adjusted_life_expectancy * DAYS_PER_YEAR) * days,
            0.0,
            1.0,
        )
        updated_cohorts = (
            np.maximum(
                children + working_age * birth_step - children * aging_children_step,
                0.0,
            ),
            np.maximum(
                working_age + children * aging_children_step - working_age * aging_working_step,
                0.0,
            ),
            np.maximum(
                retirement_age + working_age * aging_working_step - retirement_age * death_step,
                0.0,
            ),
        )

    if any(
        not np.isfinite(values).all() or (values >= _INT64_UPPER_BOUND).any()
        for values in updated_cohorts
    ):
        return None

    return regions.with_columns(
        pl.Series(column, values.astype(np.int64), dtype=pl.Int64)
        for column, values in zip(cohort_columns, updated_cohorts)
    )
