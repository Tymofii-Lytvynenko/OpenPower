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


if __name__ == "__main__":
    unittest.main()
