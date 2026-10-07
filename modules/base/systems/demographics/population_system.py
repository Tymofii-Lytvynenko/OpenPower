import polars as pl
from modules.base.systems.demographics.population_growth import (
    CHILDBEARING_YEARS,
    DAYS_PER_YEAR,
    DAILY_CHILDREN_AGING,
    DAILY_WORKING_AGE_AGING,
    FEMALE_RATIO,
    calculate_population_growth,
)
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.state import GameState
from src.shared.events import EventRealSecond

class PopulationSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'random_event_effects'}),
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
        
        # Ensure core population columns exist in regions
        required_regions = {"pop_14": 0, "pop_15_64": 0, "pop_65": 0}
        for col, default in required_regions.items():
            if col not in regions.columns:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found in 'regions'. Defaulting to {default}.")
                    self._missing_columns.add(col)
                regions = regions.with_columns(pl.lit(default).alias(col))
        output_region_columns = regions.columns

        countries = state.get_table("countries")

        event_health = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            int(state.time.total_minutes),
            categories={"health"},
            subject_type="region",
        )
        event_health_by_region = {}
        if event_health and "id" in regions.columns:
            event_health_by_region = {
                int(subject_id): max(-0.5, min(0.25, magnitude))
                for (_, subject_id, _), magnitude in event_health.items()
                if subject_id.lstrip("-").isdigit()
            }
        
        # Merge regions with country demographics
        # We need fertility_rate and life_expectancy
        required = {"fertility_rate": 2.7, "life_expectancy": 67.0}
        required["economic_health"] = 1.0
        for col, default in required.items():
            if col not in countries.columns:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found in 'countries'. Defaulting to {default}.")
                    self._missing_columns.add(col)
                countries = countries.with_columns(pl.lit(default).alias(col))

        regional_health_capacity = (
            pl.col("health_capacity").fill_null(1.0).clip(0.0, 1.0)
            if "health_capacity" in regions.columns
            else pl.lit(1.0)
        )
        fertility_values, life_expectancy_values, economic_health_values = self._get_region_parameters(
            state, regions, countries
        )
        updated_regions = calculate_population_growth(
            regions,
            days_passed=days_passed,
            fertility_rates=fertility_values,
            life_expectancies=life_expectancy_values,
            economic_health=economic_health_values,
            event_health_by_region=event_health_by_region,
        )
        if updated_regions is not None:
            self._store_updated_regions(state, updated_regions)
            return

        parameter_columns = [
            fertility_values.alias("_fertility_rate"),
            life_expectancy_values.alias("_life_expectancy"),
            economic_health_values.alias("_economic_health"),
        ]
        if event_health_by_region:
            region_ids = regions.get_column("id").to_list()
            event_health_values = pl.Series(
                "_event_health_modifier",
                [event_health_by_region.get(region_id, 0.0) for region_id in region_ids],
                dtype=pl.Float64,
            )
            parameter_columns.append(event_health_values)
        regions_with_parameters = regions.hstack(parameter_columns)
        pop_data = regions_with_parameters.lazy()

        # 1. Calculate Births based on TFR
        # Math: (Total Pop * % Women * TFR) / (Years of fertility) = Births per Year
        # Then multiply by (days_passed / 365) to get current step.
        # A delayed tick may span years; one population update cannot move more than one full cohort.
        aging_kids_step = min(1.0, DAILY_CHILDREN_AGING * days_passed)
        aging_work_step = min(1.0, DAILY_WORKING_AGE_AGING * days_passed)

        fertility_rate = pl.col("_fertility_rate")
        life_expectancy = pl.col("_life_expectancy")
        regional_life_expectancy = (
            life_expectancy
            * (0.9 + 0.1 * regional_health_capacity)
            * (0.9 + 0.1 * pl.col("_economic_health"))
            * (
                1.0 + pl.col("_event_health_modifier").clip(-0.5, 0.25)
                if event_health_by_region
                else 1.0
            )
        ).clip(lower_bound=1.0)
        birth_step = (
            fertility_rate * FEMALE_RATIO / CHILDBEARING_YEARS / DAYS_PER_YEAR
            * days_passed
        )
        death_step = (
            1.0 / (regional_life_expectancy * DAYS_PER_YEAR) * days_passed
        ).clip(0.0, 1.0)

        updated = pop_data.with_columns([
            (
                pl.col("pop_14").fill_null(0).clip(lower_bound=0)
                + pl.col("pop_15_64").fill_null(0).clip(lower_bound=0) * birth_step
                - pl.col("pop_14").fill_null(0).clip(lower_bound=0) * aging_kids_step
            ).clip(lower_bound=0).cast(pl.Int64).alias("pop_14"),
            (
                pl.col("pop_15_64").fill_null(0).clip(lower_bound=0)
                + pl.col("pop_14").fill_null(0).clip(lower_bound=0) * aging_kids_step
                - pl.col("pop_15_64").fill_null(0).clip(lower_bound=0) * aging_work_step
            ).clip(lower_bound=0).cast(pl.Int64).alias("pop_15_64"),
            (
                pl.col("pop_65").fill_null(0).clip(lower_bound=0)
                + pl.col("pop_15_64").fill_null(0).clip(lower_bound=0) * aging_work_step
                - pl.col("pop_65").fill_null(0).clip(lower_bound=0) * death_step
            ).clip(lower_bound=0).cast(pl.Int64).alias("pop_65"),
        ])
        # Keep formula evaluation in one Polars plan to avoid repeated eager materialization per tick.
        self._store_updated_regions(state, updated.select(output_region_columns).collect())

    def _store_updated_regions(self, state: GameState, regions: pl.DataFrame) -> None:
        state.update_table("regions", regions)
        if self._parameter_cache is not None:
            cache = self._parameter_cache
            self._parameter_cache = (*cache[:6], state.get_table("regions"))

    def _get_region_parameters(
        self,
        state: GameState,
        regions: pl.DataFrame,
        countries: pl.DataFrame,
    ) -> tuple[pl.Series, pl.Series, pl.Series]:
        country_revision = state.table_revisions.get("countries", 0)
        cached = self._parameter_cache
        if cached is not None and cached[0] == country_revision:
            # Reuse the join after population-only updates; replaced frames still validate
            # owner alignment below.
            if cached[6] is regions:
                return cached[3], cached[4], cached[5]
        region_ids = (
            regions.get_column("id")
            if "id" in regions.columns
            else pl.Series("_region_index", range(regions.height), dtype=pl.UInt32)
        )
        if cached is not None and cached[0] == country_revision:
            region_owners = regions.get_column("owner")
            if cached[1].equals(region_ids) and cached[2].equals(region_owners):
                self._parameter_cache = (*cached[:6], regions)
                return cached[3], cached[4], cached[5]

        region_owners = regions.get_column("owner")

        indexed_regions = regions.with_row_index("_region_order").select(
            ["_region_order", "owner"]
        )
        parameter_frame = indexed_regions.join(
            countries.select(["id", "fertility_rate", "life_expectancy", "economic_health"]),
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
        life_expectancy_values = (
            parameter_frame.get_column("life_expectancy")
            .cast(pl.Float64)
            .fill_null(67.0)
            .fill_nan(67.0)
            .clip(lower_bound=1.0)
        )
        economic_health_values = (
            parameter_frame.get_column("economic_health")
            .cast(pl.Float64)
            .fill_null(1.0)
            .fill_nan(1.0)
            .clip(0.0, 1.0)
        )
        self._parameter_cache = (
            country_revision,
            region_ids.clone(),
            region_owners.clone(),
            fertility_values,
            life_expectancy_values,
            economic_health_values,
            regions,
        )
        return fertility_values, life_expectancy_values, economic_health_values
