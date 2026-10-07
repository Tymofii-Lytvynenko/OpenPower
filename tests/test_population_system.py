import unittest
from datetime import datetime

import polars as pl

from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.world.time_system import TimeSystem
from src.shared.events import EventRealSecond
from src.shared.state import GAME_EPOCH, GameState


class TestPopulationSystem(unittest.TestCase):
    def test_natural_demographic_update_does_not_apply_pending_migration(self):
        without_flow = self._state()
        with_flow = self._state()
        with_flow.tables["migration_flows"] = pl.DataFrame({
            "id": ["pending"],
            "origin_region_id": [1],
            "destination_region_id": [2],
            "population_count": [20],
            "status": ["pending"],
        })

        PopulationSystem().update(without_flow, 1.0)
        PopulationSystem().update(with_flow, 1.0)

        self.assertEqual(
            with_flow.get_table("regions").select("pop_14", "pop_15_64", "pop_65").rows(),
            without_flow.get_table("regions").select("pop_14", "pop_15_64", "pop_65").rows(),
        )
        self.assertEqual(
            with_flow.get_table("regions").select("pop_14", "pop_15_64", "pop_65").row(0),
            (10, 99, 20),
        )

    def test_demographic_formulas_match_one_year_cohort_transitions(self):
        state = GameState(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [1],
                        "owner": ["AAA"],
                        "pop_14": [15_000],
                        "pop_15_64": [35_000],
                        "pop_65": [10_000],
                    }
                ),
                "countries": pl.DataFrame(
                    {
                        "id": ["AAA"],
                        "fertility_rate": [2.0],
                        "life_expectancy": [50.0],
                    }
                ),
            }
        )

        PopulationSystem()._apply_tfr_growth(state, days_passed=365.25)

        self.assertEqual(
            state.get_table("regions").select("pop_14", "pop_15_64", "pop_65").row(0),
            (14_500, 35_300, 10_500),
        )

    def test_large_elapsed_time_never_moves_more_than_a_cohort_or_creates_negative_people(self):
        state = self._state()

        PopulationSystem()._apply_tfr_growth(state, days_passed=365.25 * 100.0)

        for column in ("pop_14", "pop_15_64", "pop_65"):
            self.assertGreaterEqual(state.get_table("regions").item(0, column), 0)

    def test_country_demographic_changes_invalidate_cached_region_parameters(self):
        state = GameState(
            tables={
                "regions": pl.DataFrame({
                    "id": [1],
                    "owner": ["AAA"],
                    "pop_14": [0],
                    "pop_15_64": [100_000],
                    "pop_65": [0],
                }),
                "countries": pl.DataFrame({
                    "id": ["AAA"],
                    "fertility_rate": [2.0],
                    "life_expectancy": [67.0],
                }),
            }
        )
        system = PopulationSystem()

        system._apply_tfr_growth(state, days_passed=365.25)
        children_after_baseline = state.get_table("regions").item(0, "pop_14")
        state.update_table("countries", state.get_table("countries").with_columns(
            pl.lit(4.0).alias("fertility_rate")
        ))
        system._apply_tfr_growth(state, days_passed=365.25)

        self.assertGreater(
            state.get_table("regions").item(0, "pop_14"),
            children_after_baseline,
        )

    def test_region_ownership_changes_invalidate_cached_parameters(self):
        def make_state():
            return GameState(
                tables={
                    "regions": pl.DataFrame({
                        "id": [1],
                        "owner": ["AAA"],
                        "pop_14": [0],
                        "pop_15_64": [100_000],
                        "pop_65": [0],
                    }),
                    "countries": pl.DataFrame({
                        "id": ["AAA", "BBB"],
                        "fertility_rate": [2.0, 4.0],
                        "life_expectancy": [67.0, 67.0],
                    }),
                }
            )

        changed_owner = make_state()
        unchanged_owner = make_state()
        changed_system = PopulationSystem()
        unchanged_system = PopulationSystem()
        for state, system in (
            (changed_owner, changed_system),
            (unchanged_owner, unchanged_system),
        ):
            system._apply_tfr_growth(state, days_passed=365.25)

        changed_owner.update_table(
            "regions",
            changed_owner.get_table("regions").with_columns(pl.lit("BBB").alias("owner")),
        )
        changed_system._apply_tfr_growth(changed_owner, days_passed=365.25)
        unchanged_system._apply_tfr_growth(unchanged_owner, days_passed=365.25)

        self.assertGreater(
            changed_owner.get_table("regions").item(0, "pop_14"),
            unchanged_owner.get_table("regions").item(0, "pop_14"),
        )

    def test_game_speed_levels_and_leap_day_datetime_are_exact(self):
        system = TimeSystem()
        for level, minutes_per_second in system.MINUTES_PER_SEC.items():
            state = GameState()
            state.time.speed_level = level
            system.update(state, 1.0)
            self.assertEqual(state.time.total_minutes, int(minutes_per_second))

        state = GameState()
        leap_day_start = datetime(2004, 2, 28, 23, 45)
        state.time.total_minutes = int((leap_day_start - GAME_EPOCH).total_seconds() // 60)
        state.time.year = leap_day_start.year
        state.time.month = leap_day_start.month
        state.time.day = leap_day_start.day
        state.time.hour = leap_day_start.hour
        state.time.minute = leap_day_start.minute
        state.time.date_str = leap_day_start.strftime("%Y-%m-%d %H:%M")
        state.time.speed_level = 1

        system = TimeSystem()
        system.update(state, 0.5)

        self.assertEqual(state.time.date_str, "2004-02-29 00:00")
        self.assertEqual((state.time.year, state.time.month, state.time.day, state.time.hour, state.time.minute),
                         (2004, 2, 29, 0, 0))

    @staticmethod
    def _state():
        return GameState(
            tables={
                "regions": pl.DataFrame({
                    "id": [1, 2],
                    "owner": ["AAA", "AAA"],
                    "pop_14": [10, 0],
                    "pop_15_64": [100, 0],
                    "pop_65": [20, 0],
                    "health_capacity": [1.0, 1.0],
                }),
                "countries": pl.DataFrame({
                    "id": ["AAA"],
                    "fertility_rate": [2.7],
                    "life_expectancy": [67.0],
                    "economic_health": [1.0],
                }),
            },
            events=[EventRealSecond(game_seconds_passed=86_400.0, is_paused=False)],
        )


if __name__ == "__main__":
    unittest.main()
