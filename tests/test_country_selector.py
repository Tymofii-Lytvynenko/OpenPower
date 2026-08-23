import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from src.client.controllers.viewport_controller import ViewportController
from src.client.ui.components.hud import central_bar as central_bar_module
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.country_selector import (
    CountryOption,
    CountryStatus,
    country_options_from_state,
    resolve_country_status,
)
from src.client.ui.layouts import game_layout as game_layout_module
from src.client.ui.layouts.game_layout import GameLayout
from src.shared.state import GameState


class TestCountryOptions(unittest.TestCase):
    def test_normalizes_deduplicates_and_sorts_by_display_name(self) -> None:
        state = SimpleNamespace(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["UKR", "CAN", "CAN", None, "USA"],
                        "name": ["Ukraine", "Canada", "Duplicate", "Unknown", None],
                    }
                )
            }
        )

        self.assertEqual(
            country_options_from_state(state),
            (
                CountryOption("CAN", "Canada"),
                CountryOption("UKR", "Ukraine"),
                CountryOption("USA", "USA"),
            ),
        )

    def test_returns_empty_options_when_country_table_is_unavailable(self) -> None:
        self.assertEqual(country_options_from_state(SimpleNamespace(tables={})), ())
        self.assertEqual(country_options_from_state(None), ())

    def test_resolves_player_alliance_and_neutral_statuses(self) -> None:
        state = GameState(
            tables={
                "countries_treaties": pl.DataFrame(
                    {
                        "type": ["alliance"],
                        "members": [["UKR", "CAN"]],
                    }
                )
            }
        )

        self.assertIs(resolve_country_status(state, "UKR", "UKR"), CountryStatus.PLAYER)
        self.assertIs(resolve_country_status(state, "UKR", "CAN"), CountryStatus.ALLIANCE)
        self.assertIs(resolve_country_status(state, "UKR", "USA"), CountryStatus.NEUTRAL)


class TestGameLayoutCountrySwitch(unittest.TestCase):
    def test_applies_dropdown_choice_to_panels_and_viewport_in_same_frame(self) -> None:
        layout = GameLayout.__new__(GameLayout)
        layout.local_player_tag = "UKR"
        layout._cached_target_tag = "UKR"
        layout._last_selected_id = None
        layout.viewport_ctrl = MagicMock()
        layout.viewport_ctrl.focus_on_country.return_value = 7
        layout.net = MagicMock()
        layout.net.get_system_errors.return_value = []
        layout.feed_presenter = MagicMock()
        layout.feed_presenter.build_summary.side_effect = ["ukr-summary", "can-summary"]
        layout.system_bar = MagicMock()
        layout.central_bar = MagicMock()
        layout.central_bar.render.return_value = "CAN"
        layout.toggle_bar = MagicMock()
        layout.panel_manager = MagicMock()
        layout.context_menu = MagicMock()
        layout._render_fps = MagicMock()

        state = SimpleNamespace(tables={})
        with patch.object(game_layout_module.GAMETHEME, "apply"):
            layout.render(None, 60.0, MagicMock(), state=state)

        panel_context = layout.panel_manager.render_all.call_args.args[1]
        self.assertEqual(panel_context.target_tag, "CAN")
        self.assertFalse(panel_context.is_own_country)
        self.assertEqual(panel_context.selected_region_id, 7)
        self.assertEqual(layout._cached_target_tag, "CAN")
        layout.viewport_ctrl.focus_on_country.assert_called_once_with("CAN")


class TestCentralBarSizing(unittest.TestCase):
    def test_uses_content_width_without_empty_flexible_space(self) -> None:
        bar = CentralBar.__new__(CentralBar)
        metrics = SimpleNamespace(em=14.0, outer_padding=6.0, total_width=500.0)

        self.assertEqual(bar._bar_width(1920.0, metrics), 500.0)
        self.assertEqual(bar._bar_width(1280.0, metrics), 500.0)
        self.assertEqual(bar._bar_width(480.0, metrics), 468.0)

    def test_measured_controls_fit_two_line_clock_and_news_icon(self) -> None:
        bar = CentralBar.__new__(CentralBar)
        style = SimpleNamespace(frame_padding=SimpleNamespace(x=8.0, y=5.0))

        with patch.multiple(
            central_bar_module.imgui,
            get_font_size=MagicMock(return_value=14.0),
            get_style=MagicMock(return_value=style),
            get_text_line_height=MagicMock(return_value=14.0),
            calc_text_size=MagicMock(
                side_effect=lambda text: SimpleNamespace(x=len(text) * 7.0, y=14.0)
            ),
        ):
            metrics = bar._measure_layout(("2001/02/04", "03:32"))

        self.assertLess(metrics.total_width, 550.0)
        self.assertGreaterEqual(metrics.control_height, 28.0)
        self.assertGreater(metrics.ticker_button_size, 14.0)


class TestViewportCountrySwitch(unittest.TestCase):
    def test_focuses_and_highlights_country_as_a_country_map_click(self) -> None:
        controller = ViewportController.__new__(ViewportController)
        controller.selected_country_tag = None
        controller.current_mode_key = "political"
        controller.map_modes = {"empire": MagicMock()}
        controller.renderer = MagicMock(width=1000, height=500)
        controller.cam = MagicMock()
        controller.on_selection_change = MagicMock()
        controller.net = MagicMock()
        controller.net.get_state.return_value = SimpleNamespace(
            tables={
                "regions": pl.DataFrame(
                    {
                        "id": [11, 12, 20],
                        "controller": ["CAN", "CAN", "USA"],
                        "center_x": [100.0, 200.0, 700.0],
                        "center_y": [50.0, 100.0, 300.0],
                        "area_km2": [10.0, 30.0, 20.0],
                    }
                )
            }
        )

        focused_region_id = controller.focus_on_country(" CAN ")

        self.assertEqual(focused_region_id, 12)
        self.assertEqual(controller.selected_country_tag, "CAN")
        controller.map_modes["empire"].set_selected_country.assert_called_once_with("CAN")
        controller.renderer.set_highlight.assert_called_once_with([11, 12])
        controller.cam.look_at_pixel_coords.assert_called_once_with(150.0, 75.0, 1000, 500)
        controller.on_selection_change.assert_called_once_with(12)


if __name__ == "__main__":
    unittest.main()
