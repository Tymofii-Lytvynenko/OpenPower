from __future__ import annotations

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
BIRTH_RATE_COLUMN = "birth_rate_per_1000"
DEATH_RATE_COLUMN = "death_rate_per_1000"
COHORT_COLUMNS = ("pop_14", "pop_15_64", "pop_65")


def calculate_population_growth(
    regions: pl.DataFrame,
    *,
    days_passed: float,
    fertility_rates: pl.Series,
    death_rates: pl.Series,
) -> pl.DataFrame | None:
    """Calculate one bounded cohort update without materializing a lazy plan.

    Return ``None`` for schemas or numeric ranges that need Polars' broader
    casting behavior; the caller can then use its compatibility implementation.
    """
    if not set(COHORT_COLUMNS).issubset(regions.columns):
        return None
    if any(
        regions.schema[column] not in _SUPPORTED_NUMERIC_DTYPES
        for column in COHORT_COLUMNS
    ):
        return None
    row_count = regions.height
    fertility = np.asarray(fertility_rates.to_numpy(), dtype=np.float64)
    mortality = np.asarray(death_rates.to_numpy(), dtype=np.float64)
    if fertility.size != row_count or mortality.size != row_count:
        return None

    population = tuple(
        np.maximum(
            regions.get_column(column).fill_null(0).to_numpy(),
            0.0,
        )
        for column in COHORT_COLUMNS
    )
    children, working_age, retirement_age = population
    days = max(0.0, float(days_passed))
    aging_children_step = min(1.0, DAILY_CHILDREN_AGING * days)
    aging_working_step = min(1.0, DAILY_WORKING_AGE_AGING * days)
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        annual_births_per_worker = fertility * FEMALE_RATIO / CHILDBEARING_YEARS
        birth_step = annual_births_per_worker / DAYS_PER_YEAR * days
        # Apply age transitions to survivors so one person cannot both age and die.
        survival = 1.0 - np.clip(mortality / 1000.0 / DAYS_PER_YEAR * days, 0.0, 1.0)
        children, working_age, retirement_age = (
            cohort * survival for cohort in population
        )
        updated_cohorts = (
            children + population[1] * birth_step - children * aging_children_step,
            working_age + children * aging_children_step - working_age * aging_working_step,
            retirement_age + working_age * aging_working_step,
        )

    columns = []
    rounded_cohorts = []
    for cohort, values in zip(COHORT_COLUMNS, updated_cohorts, strict=True):
        remainder = f"{cohort}_remainder"
        # Carry sub-person changes across ticks while publishing integer populations.
        if remainder in regions.columns:
            values = values + regions.get_column(remainder).fill_null(0.0).to_numpy()
        values = np.maximum(values, 0.0)
        rounded = np.rint(values)
        if not np.isfinite(rounded).all() or (rounded >= _INT64_UPPER_BOUND).any():
            return None
        rounded_cohorts.append(rounded)
        columns.extend((
            pl.Series(cohort, rounded.astype(np.int64)),
            pl.Series(remainder, values - rounded),
        ))

    total = sum(rounded_cohorts)
    birth_rate = np.divide(
        1000.0 * rounded_cohorts[1] * annual_births_per_worker,
        total,
        out=np.full(row_count, np.nan),
        where=total > 0,
    )
    columns.append(pl.Series(BIRTH_RATE_COLUMN, birth_rate, nan_to_null=True))
    return regions.with_columns(columns)


def store_cohorts(
    regions: pl.DataFrame, cohort_values: list[pl.Series]
) -> pl.DataFrame:
    columns = []
    for cohort, values in zip(COHORT_COLUMNS, cohort_values, strict=True):
        remainder = f"{cohort}_remainder"
        # Persist sub-person changes so short ticks do not repeatedly lose them.
        if remainder in regions.columns:
            values = values + regions.get_column(remainder).fill_null(0.0)
        values = values.clip(lower_bound=0.0)
        rounded = values.round().cast(pl.Int64)
        columns.extend((rounded.alias(cohort), (values - rounded).alias(remainder)))
    return regions.with_columns(columns)


def with_birth_rate(
    regions: pl.DataFrame, annual_births_per_worker: np.ndarray | pl.Series
) -> pl.DataFrame:
    population = pl.sum_horizontal(*COHORT_COLUMNS)
    return regions.with_columns(
        (
            1000.0 * pl.col("pop_15_64") * pl.Series(annual_births_per_worker)
            / pl.when(population > 0).then(population)
        ).alias(BIRTH_RATE_COLUMN)
    )
