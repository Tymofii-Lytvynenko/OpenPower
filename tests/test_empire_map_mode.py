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
