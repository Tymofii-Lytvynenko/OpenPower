import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from src.client.ui.components.hud import country_selector as country_selector_module
from src.client.controllers.viewport_controller import ViewportController
from src.client.ui.components.hud import central_bar as central_bar_module
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.country_selector import (
    CountryOption,
    CountrySelector,
    CountryStatus,
    country_status_label,
    country_options_from_state,
    resolve_country_status,
)
from src.client.ui.layouts import game_layout as game_layout_module
from src.client.ui.layouts.game_layout import GameLayout
from src.client.ui.components.shared.dirty_close_confirmation import SaveConfirmationPreferences
from src.shared.state import GameState


def _install_country_selector_imgui(*, viewport_y=0.0, window_open=True):
    native = MagicMock()
    native.is_popup_open.return_value = True
    native.get_font_size.return_value = 20.0
    native.get_text_line_height.return_value = 20.0
    native.get_main_viewport.return_value = SimpleNamespace(
        pos=SimpleNamespace(y=viewport_y)
    )
    native.begin_popup.return_value = window_open
    native.selectable.return_value = (False, False)
    native.is_item_clicked.return_value = False
    native.is_item_hovered.return_value = False
    return native


class TestCountryOptions(unittest.TestCase):
    def test_status_labels_fit_the_source_slot_and_keep_the_full_status_name_separate(self) -> None:
        self.assertEqual(country_status_label(CountryStatus.ALLIANCE), "ALLIED")
        self.assertEqual(country_status_label(CountryStatus.MILITARY_ACCESS), "ACCESS")

    def test_options_are_reused_until_country_table_changes(self) -> None:
        selector = CountrySelector(flag_renderer=MagicMock())
        state = GameState(tables={"countries": pl.DataFrame({
            "id": ["UKR"], "name": ["Ukraine"]
        })})
        first = selector.options(state)
        self.assertIs(selector.options(state), first)
        state.update_table("countries", pl.DataFrame({
            "id": ["UKR"], "name": ["Updated name"]
        }))
        self.assertEqual(selector.options(state), (CountryOption("UKR", "Updated name"),))

    def test_closed_popup_does_not_build_options(self) -> None:
        selector = CountrySelector(flag_renderer=MagicMock())
        with patch("src.client.ui.components.hud.country_selector.imgui.is_popup_open", return_value=False):
            with patch.object(selector, "options") as options:
                self.assertIsNone(selector.render(None, "UKR"))
                options.assert_not_called()

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

    def test_popup_renders_sized_rows_and_selects_country_by_row(self) -> None:
        native = _install_country_selector_imgui()
        native.selectable.side_effect = [(True, False), (False, False)]
        native.is_item_hovered.side_effect = [True, False]
        flags = MagicMock()
        selector = CountrySelector(flag_renderer=flags)
        state = SimpleNamespace(
            tables={
                "countries": pl.DataFrame(
                    {"id": ["UKR", "CAN"], "name": ["Ukraine", "Canada"]}
                )
            },
            table_revisions={"countries": 1},
        )

        with patch.object(country_selector_module, "imgui", native):
            selector.open((100.0, 300.0), 220.0)
            selected_tag = selector.render(state, "CAN")

        self.assertEqual(selected_tag, "CAN")

        native.open_popup.assert_called_once_with(CountrySelector.POPUP_ID)
        self.assertAlmostEqual(
            native.set_next_window_pos.call_args.args[0][1], 229.6
        )
        native.set_next_window_size.assert_called_once()
        self.assertEqual(flags.draw_flag.call_count, 2)
        native.set_item_default_focus.assert_called_once_with()
        native.set_tooltip.assert_called_once_with("CAN")
        native.close_current_popup.assert_called_once_with()
        native.pop_style_color.assert_called_once_with(5)
        native.pop_style_var.assert_called_once_with(4)

    def test_popup_renders_error_when_no_country_options_exist(self) -> None:
        native = _install_country_selector_imgui()
        selector = CountrySelector(flag_renderer=MagicMock())

        with patch.object(country_selector_module, "imgui", native):
            selected_tag = selector.render(SimpleNamespace(tables={}), "UKR")

        self.assertIsNone(selected_tag)

        native.text_colored.assert_called_once_with(
            country_selector_module.GAMETHEME.colors.error,
            "No country data loaded",
        )
        native.end_popup.assert_called_once_with()

    def test_clicking_a_flag_selects_its_country(self) -> None:
        native = _install_country_selector_imgui()
        native.is_item_clicked.return_value = True
        selector = CountrySelector(flag_renderer=MagicMock())
        state = SimpleNamespace(
            tables={"countries": pl.DataFrame({"id": ["UKR"], "name": ["Ukraine"]})}
        )

        with patch.object(country_selector_module, "imgui", native):
            selected_tag = selector.render(state, "CAN")

        self.assertEqual(selected_tag, "UKR")
        native.close_current_popup.assert_called_once_with()

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
        self.assertIs(resolve_country_status(state, " ukr ", "ukr"), CountryStatus.PLAYER)
        self.assertIs(resolve_country_status(state, "UKR", "CAN"), CountryStatus.ALLIANCE)
        self.assertIs(resolve_country_status(state, "UKR", "USA"), CountryStatus.NEUTRAL)

    def test_resolves_war_and_military_transit_statuses(self) -> None:
        state = GameState(
            tables={
                "countries_treaties": pl.DataFrame(
                    {
                        "id": ["transit"],
                        "type": ["military_trespassing_right"],
                        "side_a": [["UKR"]],
                        "side_b": [["POL"]],
                        "status": ["active"],
                    }
                ),
                "countries_wars": pl.DataFrame(
                    {
                        "id": ["war"],
                        "side_a": [["UKR"]],
                        "side_b": [["RUS"]],
                        "status": ["active"],
                    }
                ),
            }
        )

        self.assertIs(resolve_country_status(state, "UKR", "POL"), CountryStatus.MILITARY_ACCESS)
        self.assertIs(resolve_country_status(state, "UKR", "RUS"), CountryStatus.HOSTILE)

    def test_war_status_takes_precedence_over_an_active_alliance(self) -> None:
        state = GameState(
            tables={
                "countries_treaties": pl.DataFrame(
                    {"type": ["alliance"], "members": [["UKR", "CAN"]], "status": ["active"]}
                ),
                "countries_wars": pl.DataFrame(
                    {"side_a": [["UKR"]], "side_b": [["CAN"]], "status": ["active"]}
                ),
            }
        )

        self.assertIs(resolve_country_status(state, "UKR", "CAN"), CountryStatus.HOSTILE)

    def test_inactive_or_suspended_military_access_is_not_displayed(self) -> None:
        state = GameState(
            tables={
                "countries_treaties": pl.DataFrame(
                    {
                        "type": ["military_trespassing_right", "military_trespassing_right"],
                        "side_a": [["UKR"], ["UKR"]],
                        "side_b": [["POL"], ["ROM"]],
                        "suspended_members": [[], ["UKR"]],
                        "status": ["active", "active"],
                        "expires_at_minute": [10, 0],
                    }
                )
            }
        )
        state.time.total_minutes = 10

        self.assertIs(resolve_country_status(state, "UKR", "POL"), CountryStatus.NEUTRAL)
        self.assertIs(resolve_country_status(state, "UKR", "ROM"), CountryStatus.NEUTRAL)


class TestGameLayoutCountrySwitch(unittest.TestCase):
    def test_advisor_button_toggles_advisor_settings(self) -> None:
        panel_manager = MagicMock()
        with (
            patch.object(game_layout_module, "PanelManager", return_value=panel_manager),
            patch.object(game_layout_module, "build_game_panel_specs", return_value=[]),
            patch.object(game_layout_module, "CentralBar") as central_bar,
        ):
            GameLayout(MagicMock(), "UKR", MagicMock())

        central_bar.call_args.kwargs["open_ai_cb"]()
        panel_manager.toggle.assert_called_once_with("ADVISOR_SETTINGS")

    def test_applies_dropdown_choice_to_panels_and_viewport_in_same_frame(self) -> None:
        layout = GameLayout.__new__(GameLayout)
        layout.local_player_tag = "UKR"
        layout._cached_target_tag = "UKR"
        layout._last_selected_id = None
        layout._on_deployment_drag_start = None
        layout.save_confirmation_preferences = SaveConfirmationPreferences()
        layout.viewport_ctrl = MagicMock()
        layout.viewport_ctrl.focus_on_country.return_value = 7
        layout.net = MagicMock()
        layout.net.get_system_errors.return_value = []
        layout.message_dialog = MagicMock()
        layout.advisor_question_dialog = MagicMock()
        # This test bypasses composition to isolate same-frame country switching;
        # the other render ports still need their normal constructor contract.
        for name in (
            "autosave",
            "game_over_dialog",
            "advisor_recommendation_window",
            "command_feedback",
            "save_game_dialog",
            "battle_summary_dialog",
            "unit_order_feedback",
            "unit_reorganization",
            "covert_outcome_dialog",
            "dispatch_report_dialog",
            "battle_inspection",
            "unit_attack_confirmation",
            "thematic_map_legend",
            "mini_map",
            "tutorial_window",
        ):
            setattr(layout, name, MagicMock())
        layout.autosave.update.return_value = set()
        layout.game_over_dialog.is_game_over.return_value = False
        layout.feed_presenter = MagicMock()
        layout.feed_presenter.build_summary.side_effect = ["ukr-summary", "can-summary"]
        layout.system_bar = MagicMock()
        layout.central_bar = MagicMock()
        layout.central_bar.render.return_value = "CAN"
        layout.toggle_bar = MagicMock()
        layout.panel_manager = MagicMock()
        layout.context_menu = MagicMock()
        layout._render_fps = MagicMock()
        layout._render_game_menu = MagicMock()

        state = SimpleNamespace(tables={})
        with (patch.object(game_layout_module.GAMETHEME, "apply"),
              patch.object(game_layout_module, "consume_panel_shortcuts")):
            layout.render(None, 60.0, MagicMock(), state=state)

        panel_context = layout.panel_manager.render_all.call_args.args[1]
        self.assertEqual(panel_context.target_tag, "CAN")
        self.assertFalse(panel_context.is_own_country)
        self.assertEqual(panel_context.selected_region_id, 7)
        self.assertEqual(layout._cached_target_tag, "CAN")
        layout.viewport_ctrl.focus_on_country.assert_called_once_with("CAN")


class TestCentralBarSizing(unittest.TestCase):
    def test_source_bar_remains_centered_and_inside_supported_viewports(self) -> None:
        for width, height in ((800, 600), (1024, 768), (1280, 720), (1920, 1080)):
            bounds = central_bar_module.main_bar_bounds(width, height)
            self.assertEqual((bounds.width, bounds.height), (689.0, 96.0))
            self.assertEqual(bounds.x + bounds.width / 2.0, width / 2.0)
            self.assertLessEqual(bounds.y + bounds.height, height)

    def test_source_bar_respects_the_viewport_origin(self) -> None:
        bounds = central_bar_module.main_bar_bounds(1280, 720, 100, 200)
        self.assertEqual(bounds.x + bounds.width / 2.0, 740.0)
        self.assertEqual(bounds.y + bounds.height, 912.0)


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
