import unittest

import polars as pl

from src.client.visualization.map_modes.political_mode import PoliticalMapMode
from src.shared.state import GameState


class TestPoliticalMapMode(unittest.TestCase):
    def test_controller_column_takes_priority_over_owner(self):
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

        self.assertEqual(color_map[1], color_map[2])
        self.assertNotEqual(color_map[1], color_map[3])


if __name__ == "__main__":
    unittest.main()
