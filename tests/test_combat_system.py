import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from src.shared.events import EventBattleEnded, EventBattleStarted, EventNewHour
from src.shared.state import GameState


class TestCombatSystem(unittest.TestCase):
    def setUp(self):
        self.system = CombatSystem()

    def test_hostile_units_create_active_battle(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 120, "current_region_id": 1, "is_moving": False},
                {"id": "can-1", "owner": "CAN", "strength": 110, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )

        self.system.update(state, 0.1)

        battles = state.get_table("battles")
        battle_units = state.get_table("battle_units")
        regions = state.get_table("regions")

        self.assertEqual(len(battles), 1)
        self.assertEqual(len(battle_units), 2)
        self.assertEqual(battles["status"][0], "active")
        self.assertEqual(regions["controller"][0], "CAN")
        self.assertTrue(any(isinstance(event, EventBattleStarted) for event in state.events))
        self.assertFalse(any(isinstance(event, EventBattleEnded) for event in state.events))

    def test_hourly_resolution_occupies_region_for_victor(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 240, "current_region_id": 1, "is_moving": False},
                {"id": "can-1", "owner": "CAN", "strength": 60, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )
        state.events.append(EventNewHour(hour=1, total_minutes=60))

        self.system.update(state, 0.1)

        battles = state.get_table("battles")
        units = state.get_table("units")
        regions = state.get_table("regions")
        countries = state.get_table("countries")

        self.assertEqual(len(battles), 0)
        self.assertEqual(len(units), 1)
        self.assertEqual(units["owner"][0], "USA")
        self.assertEqual(regions["controller"][0], "USA")
        self.assertEqual(countries.filter(pl.col("id") == "USA")["military_count"][0], units["strength"][0])
        self.assertEqual(countries.filter(pl.col("id") == "CAN")["military_count"][0], 0)
        self.assertTrue(any(isinstance(event, EventBattleStarted) for event in state.events))
        self.assertTrue(any(isinstance(event, EventBattleEnded) for event in state.events))

    def test_undefended_enemy_region_becomes_occupied(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 80, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )

        self.system.update(state, 0.1)

        regions = state.get_table("regions")
        self.assertEqual(regions["owner"][0], "CAN")
        self.assertEqual(regions["controller"][0], "USA")
        self.assertEqual(len(state.get_table("battles")), 0)

    def test_no_occupation_without_active_war(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 80, "current_region_id": 1, "is_moving": False},
            ],
            wars=[],
        )

        self.system.update(state, 0.1)

        self.assertEqual(state.get_table("regions")["controller"][0], "CAN")
        self.assertEqual(len(state.get_table("battles")), 0)

    def _build_state(self, units: list[dict], wars: list[dict]) -> GameState:
        tables = {
            "countries": pl.DataFrame(
                {
                    "id": ["USA", "CAN"],
                    "military_count": [240, 120],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["CAN"],
                    "controller": ["CAN"],
                }
            ),
            "units": pl.DataFrame(units),
            "countries_wars": pl.DataFrame(wars) if wars else pl.DataFrame(schema={"side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8)}),
        }
        return GameState(tables=tables)


if __name__ == "__main__":
    unittest.main()
