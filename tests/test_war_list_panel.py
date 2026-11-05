from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.client.ui.panels.military.war_list_panel import WarListPanel


class WarListPanelFlagTests(unittest.TestCase):
    def test_draw_flag_delegates_country_tag_to_flag_renderer(self):
        panel = object.__new__(WarListPanel)
        panel._flag_renderer = Mock()

        panel._draw_flag("USA")

        panel._flag_renderer.draw_flag.assert_called_once_with("USA", 20.0, 14.0)

    def test_draw_flag_uses_empty_tag_for_missing_country(self):
        panel = object.__new__(WarListPanel)
        panel._flag_renderer = Mock()

        panel._draw_flag(None)

        panel._flag_renderer.draw_flag.assert_called_once_with("", 20.0, 14.0)


class WarListPanelCoalitionTests(unittest.TestCase):
    def test_side_allies_excludes_the_separately_displayed_leader(self):
        allies = WarListPanel._side_allies(
            {"side_a": ["USA", "FRA", "GER"]},
            "side_a",
            "usa",
        )

        self.assertEqual(allies, ["FRA", "GER"])

    def test_side_allies_ignores_empty_tags_and_normalizes_case(self):
        allies = WarListPanel._side_allies(
            {"side_b": [None, "gbr", "  ", "FRA"]},
            "side_b",
            "USA",
        )

        self.assertEqual(allies, ["GBR", "FRA"])


if __name__ == "__main__":
    unittest.main()
