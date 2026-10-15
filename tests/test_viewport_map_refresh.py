from __future__ import annotations

import unittest
from unittest.mock import Mock

import polars as pl

from src.client.controllers.viewport_controller import ViewportController
from src.client.visualization.map_modes.political_mode import PoliticalMapMode
from src.shared.state import GameState


class ViewportMapRefreshTests(unittest.TestCase):
    def _controller(self) -> ViewportController:
        controller = object.__new__(ViewportController)
        controller.current_mode_key = "political"
        controller.selected_country_tag = None
        controller.map_modes = {"political": PoliticalMapMode()}
        controller.renderer = Mock()
        controller.net = Mock()
        controller._map_layer_cache_key = None
        return controller

    def _state(self) -> GameState:
        return GameState(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [1],
                        "owner": ["CAN"],
                        "controller": ["CAN"],
                    }
                )
            }
        )

    def test_map_layer_refreshes_once_per_region_revision(self) -> None:
        controller = self._controller()
        state = self._state()

        self.assertTrue(controller.refresh_map_layer_if_stale(state))
        self.assertFalse(controller.refresh_map_layer_if_stale(state))
        self.assertEqual(controller.renderer.update_overlay.call_count, 1)

        state.update_table(
            "regions",
            pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["CAN"],
                    "controller": ["USA"],
                }
            ),
        )

        self.assertTrue(controller.refresh_map_layer_if_stale(state))
        self.assertEqual(controller.renderer.update_overlay.call_count, 2)

    def test_population_changes_do_not_rebuild_political_overlay(self) -> None:
        controller = self._controller()
        state = self._state()
        self.assertTrue(controller.refresh_map_layer_if_stale(state))
        state.update_table("regions", state.tables["regions"].with_columns(
            pl.lit(1000).alias("population")
        ))
        self.assertFalse(controller.refresh_map_layer_if_stale(state))
        self.assertFalse(controller.refresh_map_layer_if_stale(state))
        self.assertEqual(controller.renderer.update_overlay.call_count, 1)


if __name__ == "__main__":
    unittest.main()
