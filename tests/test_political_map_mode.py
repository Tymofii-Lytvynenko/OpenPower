import unittest

import polars as pl

from src.client.utils.color_generator import generate_political_colors
from src.client.visualization.map_modes.political_mode import PoliticalMapMode
from src.shared.state import GameState


class TestPoliticalMapMode(unittest.TestCase):
    def test_name_and_missing_region_authority_fall_back_to_empty_colors(self):
        mode = PoliticalMapMode()

        self.assertEqual(mode.name, "Political")
        self.assertEqual(mode.calculate_colors(GameState()), {})
        self.assertEqual(
            mode.calculate_colors(GameState(tables={"regions": pl.DataFrame({"id": [1]})})),
            {},
        )

    def test_owner_fallback_and_controller_only_rows_are_colored(self):
        mode = PoliticalMapMode()
        owner_state = GameState(
            tables={"regions": pl.DataFrame({"id": [1], "owner": ["UKR"]})}
        )
        controller_only_state = GameState(
            tables={"regions": pl.DataFrame({"id": [2], "controller": ["POL"]})}
        )

        owner_color = mode.calculate_colors(owner_state)
        controller_color = mode.calculate_colors(controller_only_state)

        self.assertEqual(owner_color[1], generate_political_colors(["UKR"])["UKR"])
        self.assertEqual(
            controller_color[2],
            generate_political_colors(["POL"])["POL"],
        )

    def test_null_owner_tags_receive_black_without_hashing(self):
        self.assertEqual(
            generate_political_colors(["", "None"]),
            {"": (0, 0, 0), "None": (0, 0, 0)},
        )

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
