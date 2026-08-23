import unittest

import polars as pl

from src.client.utils.color_generator import generate_political_colors
from src.client.visualization.map_modes.political_mode import PoliticalMapMode
from src.shared.state import GameState


class TestPoliticalMapMode(unittest.TestCase):
    def test_occupied_region_mixes_owner_and_controller_colors_and_is_highlighted(self):
        state = GameState(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [1, 2, 3],
                        "owner": ["CAN", "USA", "CAN"],
                        "controller": ["USA", "USA", "CAN"],
                    }
                )
            }
        )

        color_map = PoliticalMapMode().calculate_colors(state)
        palette = generate_political_colors(["CAN", "USA"])
        expected_mixed = tuple(
            round((palette["CAN"][index] + palette["USA"][index]) / 2)
            for index in range(3)
        )

        self.assertEqual(color_map[1], (*expected_mixed, 255))
        self.assertEqual(color_map[2], palette["USA"])
        self.assertNotEqual(color_map[1], color_map[3])


if __name__ == "__main__":
    unittest.main()
