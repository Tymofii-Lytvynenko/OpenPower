from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.context_menu import ContextMenu
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused


def test_system_bar_callbacks_are_composed_and_keep_network_actions_passive() -> None:
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
    summary = SimpleNamespace(active_objectives=2, unread_messages=3, unread_news=4)
    bar = SystemBar(open_help_cb=help_callback)

    actions = {action.id: action for action in bar._build_actions(net_client, nav_service, summary)}
    assert actions["objectives"].badge == 2
    assert actions["mail"].badge == 3
    assert actions["news"].badge == 4

    actions["help"].callback()
    actions["save"].callback()
    actions["load"].callback()
    actions["menu"].callback()

    help_callback.assert_called_once_with()
    net_client.request_save.assert_called_once_with()
    nav_service.show_load_game_screen.assert_called_once_with(config)
    nav_service.show_main_menu.assert_called_once_with(session, config)


def test_central_bar_sends_pause_and_speed_intents_without_mutating_snapshot() -> None:
    bar = object.__new__(CentralBar)
    state = SimpleNamespace(time=SimpleNamespace(speed_level=1, is_paused=False))
    net_client = Mock()
    metrics = SimpleNamespace(
        tab_height=18.0,
        speed_button_width=24.0,
        item_gap=4.0,
        lcd_width=180.0,
        control_height=42.0,
    )

    with patch("src.client.ui.components.hud.central_bar.imgui") as imgui:
        imgui.button.side_effect = lambda label, size: label == "3"
        bar._draw_speed_controls(state, net_client, metrics)

    assert net_client.send_action.call_args_list[0].args[0] == ActionSetPaused("local", False)
    assert net_client.send_action.call_args_list[1].args[0] == ActionSetGameSpeed("local", 3)
    assert state.time.speed_level == 1
    assert state.time.is_paused is False


def test_central_bar_pause_control_sends_opposite_pause_intent() -> None:
    bar = object.__new__(CentralBar)
    state = SimpleNamespace(time=SimpleNamespace(speed_level=2, is_paused=True))
    net_client = Mock()
    metrics = SimpleNamespace(
        tab_height=18.0,
        speed_button_width=24.0,
        item_gap=4.0,
        lcd_width=180.0,
        control_height=42.0,
    )

    with patch("src.client.ui.components.hud.central_bar.imgui") as imgui:
        imgui.button.side_effect = lambda label, size: label == "||"
        bar._draw_speed_controls(state, net_client, metrics)

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
        bar.render()

    manager.toggle.assert_called_once_with("MILITARY")


def test_context_menu_move_action_uses_injected_callback() -> None:
    move_callback = Mock()
    composer = Mock()
    composer.draw_menu_item.side_effect = lambda label, *args: label == "Move"
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
