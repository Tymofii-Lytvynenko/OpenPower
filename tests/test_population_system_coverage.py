import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import polars as pl

from modules.base.systems.demographics.population_system import PopulationSystem
from src.shared.events import EventRealSecond
from src.shared.state import GameState


class PopulationSystemCoverageTest(unittest.TestCase):
    def test_contract_and_paused_or_empty_events_do_not_update_population(self) -> None:
        state = self._state()
        original_regions = state.get_table("regions")
        system = PopulationSystem()
        state.events = [
            EventRealSecond(game_seconds_passed=86_400.0, is_paused=True),
            EventRealSecond(game_seconds_passed=0.0, is_paused=False),
        ]

        self.assertEqual(system.id, "base.population")
        self.assertEqual(system.dependencies, ["base.time"])
        system.update(state, 1.0)

        self.assertTrue(state.get_table("regions").equals(original_regions))

    def test_missing_demographic_columns_are_defaulted_with_deduplicated_warnings(self) -> None:
        state = GameState(
            tables={
                "regions": pl.DataFrame({"id": [1], "owner": ["AAA"]}),
                "countries": pl.DataFrame({"id": ["AAA"]}),
            }
        )
        system = PopulationSystem()
        output = StringIO()

        with redirect_stdout(output):
            system._apply_tfr_growth(state, days_passed=1.0)
            system._apply_tfr_growth(state, days_passed=1.0)

        warnings = output.getvalue().splitlines()
        self.assertEqual(len(warnings), 4)
        for column in ("pop_14", "pop_15_64", "pop_65"):
            self.assertEqual(state.get_table("regions")[column].to_list(), [0])
        self.assertIsNone(state.get_table("regions").item(0, "birth_rate_per_1000"))
        self.assertEqual(state.get_table("countries").item(0, "death_rate_per_1000"), 10.0)
        self.assertEqual(
            {"fertility_rate", "life_expectancy", "economic_health"}.intersection(
                state.get_table("countries").columns
            ),
            set(),
        )

    def test_compatibility_path_matches_fast_path(self) -> None:
        fast_state = self._state()
        fallback_state = self._state()
        PopulationSystem()._apply_tfr_growth(fast_state, days_passed=365.25)
        with patch(
            "modules.base.systems.demographics.population_system.calculate_population_growth",
            return_value=None,
        ):
            PopulationSystem()._apply_tfr_growth(fallback_state, days_passed=365.25)

        fast = fast_state.get_table("regions")
        fallback = fallback_state.get_table("regions")
        self.assertEqual(
            fast.select("pop_14", "pop_15_64", "pop_65").rows(),
            fallback.select("pop_14", "pop_15_64", "pop_65").rows(),
        )
        self.assertAlmostEqual(
            fast.item(0, "birth_rate_per_1000"), fallback.item(0, "birth_rate_per_1000")
        )
        self.assertIn("health_capacity", fallback.columns)

    def test_parameter_cache_reuses_values_for_replaced_aligned_regions(self) -> None:
        state = self._state()
        system = PopulationSystem()
        regions = state.get_table("regions")
        countries = state.get_table("countries")

        original = system._get_region_parameters(state, regions, countries)
        replacement = regions.clone()
        reused = system._get_region_parameters(state, replacement, countries)

        self.assertIs(original[0], reused[0])
        self.assertIs(system._parameter_cache[5], replacement)

    @staticmethod
    def _state() -> GameState:
        return GameState(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [1],
                        "owner": ["AAA"],
                        "pop_14": [15_000],
                        "pop_15_64": [35_000],
                        "pop_65": [10_000],
                        "health_capacity": [1.0],
                    }
                ),
                "countries": pl.DataFrame(
                    {
                        "id": ["AAA"],
                        "fertility_rate": [2.0],
                        "life_expectancy": [50.0],
                        "economic_health": [1.0],
                    }
                ),
            }
        )


if __name__ == "__main__":
    unittest.main()
