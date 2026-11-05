from unittest.mock import Mock

import arcade

from src.client.views.imgui_input_router import (
    ImGuiInputRouter,
    MouseButtonInput,
    MouseDragInput,
    MouseMotionInput,
    MouseScrollInput,
)


def _router() -> ImGuiInputRouter:
    return ImGuiInputRouter(
        arcade.MOUSE_BUTTON_RIGHT,
        arcade.MOUSE_BUTTON_MIDDLE,
    )


def test_captured_mouse_press_blocks_game_click_but_keeps_right_click_passthrough():
    router = _router()
    imgui = Mock()
    imgui.on_mouse_press.return_value = True
    game_handler = Mock()

    router.dispatch_mouse_press(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_LEFT, 0),
        game_handler,
    )
    router.dispatch_mouse_press(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_RIGHT, 0),
        game_handler,
    )

    assert imgui.on_mouse_press.call_count == 2
    game_handler.assert_called_once_with(10, 20, arcade.MOUSE_BUTTON_RIGHT, 0)


def test_captured_mouse_release_keeps_middle_button_passthrough():
    router = _router()
    imgui = Mock()
    imgui.on_mouse_release.return_value = True
    game_handler = Mock()

    router.dispatch_mouse_release(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_LEFT, 0),
        game_handler,
    )
    router.dispatch_mouse_release(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_MIDDLE, 0),
        game_handler,
    )

    assert imgui.on_mouse_release.call_count == 2
    game_handler.assert_called_once_with(10, 20, arcade.MOUSE_BUTTON_MIDDLE, 0)


def test_captured_drag_is_forwarded_only_when_right_or_middle_is_held():
    router = _router()
    imgui = Mock()
    imgui.on_mouse_drag.return_value = True
    game_handler = Mock()

    router.dispatch_mouse_drag(
        imgui,
        MouseDragInput(10, 20, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0),
        game_handler,
    )
    router.dispatch_mouse_drag(
        imgui,
        MouseDragInput(
            10,
            20,
            1,
            2,
            arcade.MOUSE_BUTTON_LEFT | arcade.MOUSE_BUTTON_RIGHT,
            0,
        ),
        game_handler,
    )

    game_handler.assert_called_once_with(
        10,
        20,
        1,
        2,
        arcade.MOUSE_BUTTON_LEFT | arcade.MOUSE_BUTTON_RIGHT,
        0,
    )


def test_mouse_motion_updates_imgui_before_always_forwarding_to_game():
    router = _router()
    calls = []
    imgui = Mock()
    imgui.on_mouse_motion.side_effect = lambda *_args: calls.append("imgui")
    game_handler = Mock(side_effect=lambda *_args: calls.append("game"))

    router.dispatch_mouse_motion(imgui, MouseMotionInput(10, 20, 1, 2), game_handler)

    assert calls == ["imgui", "game"]


def test_captured_scroll_text_and_key_release_do_not_reach_game():
    router = _router()
    imgui = Mock()
    imgui.on_mouse_scroll.return_value = True
    imgui.on_text.return_value = True
    imgui.on_key_release.return_value = True
    scroll_handler = Mock()
    text_handler = Mock()
    key_handler = Mock()

    router.dispatch_mouse_scroll(
        imgui,
        MouseScrollInput(10, 20, 0, 1),
        scroll_handler,
    )
    router.dispatch_text(imgui, "x", text_handler)
    router.dispatch_key_release(imgui, arcade.key.A, 0, key_handler)

    scroll_handler.assert_not_called()
    text_handler.assert_not_called()
    key_handler.assert_not_called()


def test_uncaptured_events_reach_game_handlers():
    router = _router()
    imgui = Mock()
    for event_name in (
        "on_mouse_press",
        "on_mouse_release",
        "on_mouse_drag",
        "on_mouse_scroll",
        "on_key_release",
        "on_text",
    ):
        getattr(imgui, event_name).return_value = False

    mouse_button_handler = Mock()
    mouse_drag_handler = Mock()
    mouse_scroll_handler = Mock()
    key_handler = Mock()
    text_handler = Mock()

    router.dispatch_mouse_press(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_LEFT, 0),
        mouse_button_handler,
    )
    router.dispatch_mouse_release(
        imgui,
        MouseButtonInput(10, 20, arcade.MOUSE_BUTTON_LEFT, 0),
        mouse_button_handler,
    )
    router.dispatch_mouse_drag(
        imgui,
        MouseDragInput(10, 20, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0),
        mouse_drag_handler,
    )
    router.dispatch_mouse_scroll(
        imgui,
        MouseScrollInput(10, 20, 0, 1),
        mouse_scroll_handler,
    )
    router.dispatch_key_release(imgui, arcade.key.A, 0, key_handler)
    router.dispatch_text(imgui, "x", text_handler)

    assert mouse_button_handler.call_count == 2
    mouse_drag_handler.assert_called_once_with(10, 20, 1, 2, arcade.MOUSE_BUTTON_LEFT, 0)
    mouse_scroll_handler.assert_called_once_with(10, 20, 0, 1)
    key_handler.assert_called_once_with(arcade.key.A, 0)
    text_handler.assert_called_once_with("x")


def test_key_press_capture_is_returned_for_global_shortcut_ordering():
    router = _router()
    imgui = Mock()
    imgui.on_key_press.return_value = True

    assert router.key_press_captured(imgui, arcade.key.F11, 0)
