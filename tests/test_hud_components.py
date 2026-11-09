from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.context_menu import ContextMenu
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused


def test_panel_shortcut_uses_normal_close_path_for_dirty_panels():
    from src.client.ui.components.hud.panel_shortcuts import consume_panel_shortcuts
    manager = Mock()
    manager.is_visible.return_value = True
    native = Mock()
    native.get_io.return_value = SimpleNamespace(want_text_input=False, key_ctrl=False,
                                                 key_alt=False, key_super=False)
    native.is_popup_open.return_value = False
    native.is_key_pressed.side_effect = lambda key, repeat: key == native.Key.b
    with patch("src.client.ui.components.hud.panel_shortcuts.imgui", native), \
         patch("src.client.ui.components.hud.panel_shortcuts.WindowManager.request_close") as close:
        consume_panel_shortcuts(manager)
    close.assert_called_once_with("budget.panel")
    manager.set_visible.assert_not_called()


def test_panel_shortcuts_do_not_intercept_text_entry():
    from src.client.ui.components.hud.panel_shortcuts import consume_panel_shortcuts
    manager, native = Mock(), Mock()
    native.get_io.return_value = SimpleNamespace(want_text_input=True)
    with patch("src.client.ui.components.hud.panel_shortcuts.imgui", native):
        consume_panel_shortcuts(manager)
    native.is_key_pressed.assert_not_called()
    manager.set_visible.assert_not_called()


def test_panel_shortcuts_do_not_intercept_an_open_popup():
    from src.client.ui.components.hud.panel_shortcuts import consume_panel_shortcuts

    manager, native = Mock(), Mock()
    native.get_io.return_value = SimpleNamespace(
        want_text_input=False, key_ctrl=False, key_alt=False, key_super=False
    )
    native.is_popup_open.return_value = True

    with patch("src.client.ui.components.hud.panel_shortcuts.imgui", native):
        consume_panel_shortcuts(manager)

    native.is_key_pressed.assert_not_called()
    manager.is_visible.assert_not_called()
    manager.set_visible.assert_not_called()


def test_panel_shortcut_opens_hidden_panel_through_the_manager():
    from src.client.ui.components.hud.panel_shortcuts import consume_panel_shortcuts

    manager, native = Mock(), Mock()
    manager.is_visible.return_value = False
    native.get_io.return_value = SimpleNamespace(
        want_text_input=False, key_ctrl=False, key_alt=False, key_super=False
    )
    native.is_popup_open.return_value = False
    native.is_key_pressed.side_effect = lambda key, repeat: key == native.Key.l

    with patch("src.client.ui.components.hud.panel_shortcuts.imgui", native):
        consume_panel_shortcuts(manager)

    manager.is_visible.assert_called_once_with("UNIT_LIST")
    manager.set_visible.assert_called_once_with("UNIT_LIST", True)


def test_map_diplomacy_requires_a_real_country_counterpart():
    import polars as pl
    menu = object.__new__(ContextMenu)
    menu._target_id = 1
    menu._state = SimpleNamespace(tables={
        "regions": pl.DataFrame([{"id": 1, "owner": "None", "controller": "None"}]),
        "countries": pl.DataFrame([{"id": "POL"}]),
    })
    assert menu._target_country() == ""
    menu._state.tables["regions"] = pl.DataFrame([{"id": 1, "owner": "POL", "controller": "POL"}])
    assert menu._target_country() == "POL"


def test_system_bar_shortcut_callbacks_keep_navigation_and_network_actions_passive() -> None:
    help_callback = Mock()
    net_client = Mock()
    session = object()
    config = object()
    net_client.session = session
    nav_service = SimpleNamespace(
        window=SimpleNamespace(game_config=config),
        show_load_game_screen=Mock(),
        show_main_menu=Mock(),
    )
    objectives_callback = Mock()
    bar = SystemBar(open_help_cb=help_callback, open_objectives_cb=objectives_callback)

    bar._safe_call(help_callback)
    bar._safe_call(objectives_callback)
    bar._show_save(net_client)
    bar._show_load(nav_service, net_client)
    bar._show_menu(nav_service, net_client)

    help_callback.assert_called_once_with()
    objectives_callback.assert_called_once_with()
    net_client.request_save.assert_called_once_with()
    nav_service.show_load_game_screen.assert_called_once_with(config)
    nav_service.show_main_menu.assert_called_once_with(session, config)


def test_central_bar_sends_pause_and_speed_intents_without_mutating_snapshot() -> None:
    bar = object.__new__(CentralBar)
    state = SimpleNamespace(time=SimpleNamespace(speed_level=1, is_paused=False))
    net_client = Mock()
    ui = Mock()
    ui.rect.return_value = SimpleNamespace(width=92.0, height=22.0)
    ui.button_at.side_effect = lambda slot, label, *args, **kwargs: label == "3"
    with patch("src.client.ui.components.hud.central_bar.imgui"):
        bar._draw_speed_controls(state, net_client, ui)

    assert net_client.send_action.call_args_list[0].args[0] == ActionSetPaused("local", False)
    assert net_client.send_action.call_args_list[1].args[0] == ActionSetGameSpeed("local", 3)
    assert state.time.speed_level == 1
    assert state.time.is_paused is False


def test_central_bar_pause_control_sends_opposite_pause_intent() -> None:
    bar = object.__new__(CentralBar)
    state = SimpleNamespace(time=SimpleNamespace(speed_level=2, is_paused=True))
    net_client = Mock()
    ui = Mock()
    ui.rect.return_value = SimpleNamespace(width=92.0, height=22.0)
    ui.button_at.side_effect = lambda slot, label, *args, **kwargs: label == "||"
    with patch("src.client.ui.components.hud.central_bar.imgui"):
        bar._draw_speed_controls(state, net_client, ui)

    net_client.send_action.assert_called_once_with(ActionSetPaused("local", False))
    assert state.time.is_paused is True


def test_toggle_bar_dispatches_panel_visibility_through_manager() -> None:
    entry = SimpleNamespace(id="MILITARY", icon="unit", color=(1, 1, 1, 1), visible=False)
    manager = Mock()
    manager.get_entries.return_value = [entry]
    bar = ToggleBar(manager)

    with (
        patch("src.client.ui.components.hud.toggle_bar.imgui") as imgui,
        patch("src.client.ui.components.hud.toggle_bar.Prims.icon_toggle", return_value=True),
    ):
        imgui.begin.return_value = True
        imgui.get_main_viewport.return_value = SimpleNamespace(
            pos=SimpleNamespace(x=0.0, y=0.0),
            size=SimpleNamespace(x=1280.0, y=720.0),
        )
        imgui.get_style.return_value = SimpleNamespace(window_padding=SimpleNamespace(x=14.0, y=14.0))
        bar.render()

    manager.toggle.assert_called_once_with("MILITARY")


def test_toggle_bar_returns_early_when_no_entries_have_icons() -> None:
    manager = Mock()
    manager.get_entries.return_value = [
        SimpleNamespace(id="MILITARY", icon=None, color=(1, 1, 1, 1), visible=False)
    ]
    bar = ToggleBar(manager)

    with patch("src.client.ui.components.hud.toggle_bar.imgui") as imgui:
        bar.render()

    imgui.get_style.assert_not_called()


def test_toggle_bar_places_multiple_icons_on_one_row() -> None:
    entries = [
        SimpleNamespace(id="POL", icon="politics", color=(1, 1, 1, 1), visible=False),
        SimpleNamespace(id="MILITARY", icon="unit", color=(1, 1, 1, 1), visible=False),
    ]
    manager = Mock()
    manager.get_entries.return_value = entries
    bar = ToggleBar(manager)

    with (
        patch("src.client.ui.components.hud.toggle_bar.imgui") as imgui,
        patch("src.client.ui.components.hud.toggle_bar.Prims.icon_toggle", return_value=False),
    ):
        imgui.begin.return_value = True
        imgui.get_main_viewport.return_value = SimpleNamespace(
            pos=SimpleNamespace(x=0.0, y=0.0),
            size=SimpleNamespace(x=1280.0, y=720.0),
        )
        imgui.get_style.return_value = SimpleNamespace(
            window_padding=SimpleNamespace(x=14.0, y=14.0)
        )
        bar.render()

    imgui.same_line.assert_called_once_with(0, 10)


def test_toggle_bar_uses_clear_compact_viewport_strip() -> None:
    entry = SimpleNamespace(id="POL", icon="politics", color=(1, 1, 1, 1), visible=False)
    manager = Mock()
    manager.get_entries.return_value = [entry]
    bar = ToggleBar(manager)

    with (
        patch("src.client.ui.components.hud.toggle_bar.imgui") as imgui,
        patch("src.client.ui.components.hud.toggle_bar.Prims.icon_toggle", return_value=False),
    ):
        imgui.begin.return_value = True
        imgui.get_main_viewport.return_value = SimpleNamespace(
            pos=SimpleNamespace(x=0.0, y=0.0),
            size=SimpleNamespace(x=800.0, y=600.0),
        )
        imgui.get_style.return_value = SimpleNamespace(window_padding=SimpleNamespace(x=14.0, y=14.0))
        bar.render()

    imgui.ImVec2.assert_any_call(24.0, 40.0)
    imgui.push_style_var.assert_called_once()
    imgui.pop_style_var.assert_called_once()


def test_context_menu_move_action_uses_injected_callback() -> None:
    move_callback = Mock()
    composer = Mock()
    composer.draw_menu_item.side_effect = lambda label, *args, **kwargs: label == "Move"
    composer.begin_menu.return_value = False
    panels = Mock()
    panels.get_entries.return_value = []
    viewport = Mock()
    menu = ContextMenu(
        composer,
        panels,
        viewport,
        has_selected_units=lambda: True,
        on_move_selected_units=move_callback,
    )
    menu.show(42)

    with patch("src.client.ui.components.hud.context_menu.imgui"):
        menu.render()

    move_callback.assert_called_once_with()
    composer.begin_popup.assert_called_once_with("global_map_context")
    composer.end_popup.assert_called_once_with()
