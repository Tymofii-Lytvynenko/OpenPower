import polars as pl
from modules.base.systems.demographics.population_growth import (
    CHILDBEARING_YEARS,
    DAYS_PER_YEAR,
    DAILY_CHILDREN_AGING,
    DAILY_WORKING_AGE_AGING,
    FEMALE_RATIO,
    COHORT_COLUMNS,
    DEATH_RATE_COLUMN,
    calculate_population_growth,
    store_cohorts,
    with_birth_rate,
)
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.state import GameState
from src.shared.events import EventRealSecond

DEFAULT_DEATH_RATE_PER_1000 = 10.0


class PopulationSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions'}),
        writes=frozenset({'countries', 'regions'}),
        phase=SystemPhase.POPULATION,
    )
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_parameter_cache": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._missing_columns = set()
        self._parameter_cache = None

    @property
    def id(self) -> str:
        return "base.population"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Filter for the real-second heartbeat
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
                
            days_passed = event.game_seconds_passed / 86400.0
            self._apply_tfr_growth(state, days_passed)

    def _apply_tfr_growth(self, state: GameState, days_passed: float):
        days_passed = max(0.0, days_passed)
        regions = state.get_table("regions")
        
        countries = state.get_table("countries")
        for column in COHORT_COLUMNS:
            if column not in regions.columns:
                self._warn_missing("regions", column, 0)
                regions = regions.with_columns(pl.lit(0).alias(column))

        if "fertility_rate" not in countries.columns:
            self._warn_missing("countries", "fertility_rate", 2.7)
            countries = countries.with_columns(pl.lit(2.7).alias("fertility_rate"))

        if DEATH_RATE_COLUMN not in countries.columns:
            rate = pl.lit(None, dtype=pl.Float64)
            if "death_rate" in countries.columns:
                rate = pl.col("death_rate").cast(pl.Float64, strict=False)
                if "death_rate_available" in countries.columns:
                    rate = pl.when(pl.col("death_rate_available").fill_null(False)).then(rate)
            # Use one explicit scenario fallback where the national observation is missing.
            countries = countries.with_columns(
                pl.when(rate.is_finite() & rate.is_between(0.0, 1000.0))
                .then(rate)
                .otherwise(DEFAULT_DEATH_RATE_PER_1000)
                .alias(DEATH_RATE_COLUMN)
            )
            state.update_table(
                "countries",
                state.get_table("countries").with_columns(countries.get_column(DEATH_RATE_COLUMN)),
            )

        fertility, mortality = self._get_region_parameters(state, regions, countries)
        updated = calculate_population_growth(
            regions, days_passed=days_passed, fertility_rates=fertility, death_rates=mortality,
        )
        if updated is None:
            updated = self._update_cohorts_polars(regions, fertility, mortality, days_passed)
        self._store_updated_regions(state, updated)

    def _warn_missing(self, table: str, column: str, default: float) -> None:
        if column not in self._missing_columns:
            print(f"[{self.id}] Column '{column}' not found in '{table}'. Defaulting to {default}.")
            self._missing_columns.add(column)

    @staticmethod
    def _update_cohorts_polars(
        regions: pl.DataFrame, fertility: pl.Series, mortality: pl.Series, days: float
    ) -> pl.DataFrame:
        survival = 1.0 - (mortality / 1000.0 / DAYS_PER_YEAR * days).clip(0.0, 1.0)
        children, working, older = (
            pl.col(column).fill_null(0).clip(lower_bound=0)
            for column in COHORT_COLUMNS
        )
        annual_births = fertility * FEMALE_RATIO / CHILDBEARING_YEARS
        aged_children = children * survival * min(1.0, DAILY_CHILDREN_AGING * days)
        aged_workers = working * survival * min(1.0, DAILY_WORKING_AGE_AGING * days)
        cohorts = regions.select(
            (children * survival + working * (annual_births / DAYS_PER_YEAR * days) - aged_children).alias("children"),
            (working * survival + aged_children - aged_workers).alias("working"),
            (older * survival + aged_workers).alias("older"),
        )
        return with_birth_rate(store_cohorts(regions, cohorts.get_columns()), annual_births)

    def _store_updated_regions(self, state: GameState, regions: pl.DataFrame) -> None:
        state.update_table("regions", regions)
        if self._parameter_cache is not None:
            cache = self._parameter_cache
            self._parameter_cache = (*cache[:5], state.get_table("regions"))

    def _get_region_parameters(
        self,
        state: GameState,
        regions: pl.DataFrame,
        countries: pl.DataFrame,
    ) -> tuple[pl.Series, pl.Series]:
        country_revision = state.table_revisions.get("countries", 0)
        cached = self._parameter_cache
        if cached is not None and cached[0] == country_revision:
            # Reuse the join after population-only updates; replaced frames still validate
            # owner alignment below.
            if cached[5] is regions:
                return cached[3], cached[4]
        region_ids = (
            regions.get_column("id")
            if "id" in regions.columns
            else pl.Series("_region_index", range(regions.height), dtype=pl.UInt32)
        )
        if cached is not None and cached[0] == country_revision:
            region_owners = regions.get_column("owner")
            if cached[1].equals(region_ids) and cached[2].equals(region_owners):
                self._parameter_cache = (*cached[:5], regions)
                return cached[3], cached[4]

        region_owners = regions.get_column("owner")

        if DEATH_RATE_COLUMN not in countries.columns:
            countries = countries.with_columns(
                pl.lit(DEFAULT_DEATH_RATE_PER_1000).alias(DEATH_RATE_COLUMN)
            )
        indexed_regions = regions.with_row_index("_region_order").select(
            ["_region_order", "owner"]
        )
        parameter_frame = indexed_regions.join(
            countries.select("id", "fertility_rate", DEATH_RATE_COLUMN),
            left_on="owner",
            right_on="id",
            how="left",
        ).sort("_region_order")
        fertility_values = (
            parameter_frame.get_column("fertility_rate")
            .cast(pl.Float64)
            .fill_null(2.7)
            .fill_nan(2.7)
            .clip(lower_bound=0.0)
        )
        mortality_values = (
            parameter_frame.get_column(DEATH_RATE_COLUMN)
            .cast(pl.Float64)
            .fill_null(DEFAULT_DEATH_RATE_PER_1000)
            .fill_nan(DEFAULT_DEATH_RATE_PER_1000)
            .clip(0.0, 1000.0)
        )
        self._parameter_cache = (
            country_revision,
            region_ids.clone(),
            region_owners.clone(),
            fertility_values,
            mortality_values,
            regions,
        )
        return fertility_values, mortality_values
