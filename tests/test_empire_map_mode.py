from __future__ import annotations

import unittest

import polars as pl

from src.client.visualization.map_modes.empire_mode import EmpireMapMode
from src.shared.state import GameState


class EmpireMapModeOccupationTests(unittest.TestCase):
    def test_occupied_region_is_orange(self) -> None:
        state = self._state()

        colors = EmpireMapMode().calculate_colors(state)

        self.assertEqual(colors[1], EmpireMapMode.OCCUPIED)

    def test_pending_annexation_is_dark_green(self) -> None:
        state = self._state()
        state.update_table(
            "annexation_claims",
            pl.DataFrame(
                {
                    "region_id": [1],
                    "political_owner_id": ["CAN"],
                    "annexing_country_id": ["USA"],
                    "status": ["pending"],
                }
            ),
        )

        colors = EmpireMapMode().calculate_colors(state)

        self.assertEqual(colors[1], EmpireMapMode.ANNEXATION_PENDING)

    def test_completed_annexation_uses_occupier_relation_color(self) -> None:
        state = self._state()
        state.update_table(
            "regions",
            pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["USA"],
                    "controller": ["USA"],
                }
            ),
        )
        mode = EmpireMapMode()
        mode.set_selected_country("USA")

        colors = mode.calculate_colors(state)

        self.assertEqual(colors[1], EmpireMapMode.SELECTED)

    def test_overlapping_alliances_and_only_active_unsuspended_diplomacy_are_colored(self) -> None:
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [1, 2, 3, 4, 5, 6, 7],
                "owner": ["USA", "CAN", "GBR", "FRA", "MEX", "CHN", "JPN"],
                "controller": ["USA", "CAN", "GBR", "FRA", "MEX", "CHN", "JPN"],
            }),
            "countries_treaties": pl.DataFrame({
                "type": ["military_alliance", "defensive_alliance", "military_alliance", "military_alliance"],
                "members": [["USA", "CAN", "GBR", "MEX"], ["USA", "GBR"], ["USA", "NOR"], ["USA", "JPN"]],
                "suspended_members": [["MEX"], [], [], []],
                "status": ["active", "active", "terminated", "active"],
                "expires_at_minute": [0, 0, 0, 50],
            }),
            "countries_wars": pl.DataFrame({
                "side_a": [["USA"], ["USA"]],
                "side_b": [["FRA"], ["CHN"]],
                "status": ["active", "ended"],
            }),
        })
        state.time.total_minutes = 100
        mode = EmpireMapMode()
        mode.set_selected_country("USA")
        colors = mode.calculate_colors(state)

        self.assertEqual(colors[1], EmpireMapMode.SELECTED)
        self.assertEqual(colors[2], EmpireMapMode.ALLY)
        self.assertEqual(colors[3], EmpireMapMode.ALLY)
        self.assertEqual(colors[4], EmpireMapMode.ENEMY)
        self.assertEqual(colors[5], EmpireMapMode.NEUTRAL)
        self.assertEqual(colors[6], EmpireMapMode.NEUTRAL)
        self.assertEqual(colors[7], EmpireMapMode.NEUTRAL)

    def test_region_group_cache_invalidates_after_controller_change(self) -> None:
        state = self._state()
        mode = EmpireMapMode()
        mode.set_selected_country("USA")

        self.assertEqual(mode.calculate_colors(state)[1], EmpireMapMode.OCCUPIED)
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(pl.lit("CAN").alias("controller")),
        )

        self.assertEqual(mode.calculate_colors(state)[1], EmpireMapMode.NEUTRAL)

    def test_region_without_a_controller_uses_unknown_palette(self) -> None:
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [1],
                "owner": [None],
                "controller": [None],
            }),
        })

        self.assertEqual(
            EmpireMapMode().calculate_colors(state)[1],
            EmpireMapMode.UNKNOWN,
        )

    def _state(self) -> GameState:
        return GameState(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [1],
                        "owner": ["CAN"],
                        "controller": ["USA"],
                    }
                )
            }
        )


if __name__ == "__main__":
    unittest.main()
