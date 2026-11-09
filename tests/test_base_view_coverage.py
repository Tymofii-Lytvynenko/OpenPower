from types import SimpleNamespace
from unittest.mock import Mock

import arcade
import pytest

from src.client.views.base_view import BaseImGuiView
from src.client.views.imgui_input_router import ImGuiInputRouter


def _view(*, imgui=..., nav=..., settings=...):
    view = BaseImGuiView.__new__(BaseImGuiView)
    view._imgui_input_router = ImGuiInputRouter(
        arcade.MOUSE_BUTTON_RIGHT,
        arcade.MOUSE_BUTTON_MIDDLE,
    )
    window = SimpleNamespace()
    if imgui is not ...:
        window.imgui = imgui
    if nav is not ...:
        window.nav = nav
    if settings is not ...:
        window.settings = settings
    view.window = window
    return view


def _install_game_handlers(view):
    names = (
        "on_game_mouse_motion",
        "on_game_resize",
        "on_game_update",
        "on_game_mouse_press",
        "on_game_mouse_release",
        "on_game_mouse_drag",
        "on_game_mouse_scroll",
        "on_game_key_press",
        "on_game_key_release",
        "on_game_text",
    )
    for name in names:
        setattr(view, name, Mock())


def test_init_creates_input_router_after_initializing_arcade_view(monkeypatch):
    arcade_init = Mock()
    monkeypatch.setattr(arcade.View, "__init__", arcade_init)

    view = BaseImGuiView()

    arcade_init.assert_called_once_with()
    assert isinstance(view._imgui_input_router, ImGuiInputRouter)


def test_window_services_are_exposed_and_missing_services_raise_clear_errors():
    imgui, nav = Mock(), Mock()
    view = _view(imgui=imgui, nav=nav)

    assert view.imgui is imgui
    assert view.nav is nav

    with pytest.raises(AttributeError, match="ImGuiService not found on Window"):
        _view().imgui
    with pytest.raises(AttributeError, match="NavigationService not found on Window"):
        _view().nav


def test_deprecated_setup_and_default_game_hooks_are_no_ops():
    view = _view(imgui=Mock())

    assert view.setup_imgui() is None
    callbacks = (
        (view.on_game_mouse_motion, (1, 2, 3, 4)),
        (view.on_game_resize, (800, 600)),
        (view.on_game_update, (0.25,)),
        (view.on_game_mouse_press, (1, 2, 3, 4)),
        (view.on_game_mouse_release, (1, 2, 3, 4)),
        (view.on_game_mouse_drag, (1, 2, 3, 4, 5, 6)),
        (view.on_game_mouse_scroll, (1, 2, 3, 4)),
        (view.on_game_key_press, (5, 6)),
        (view.on_game_key_release, (5, 6)),
        (view.on_game_text, ("x",)),
    )

    assert [callback(*args) for callback, args in callbacks] == [None] * len(callbacks)


def test_resize_update_and_pointer_events_forward_to_imgui_and_game_handlers():
    imgui = Mock()
    for name in (
        "on_mouse_press",
        "on_mouse_release",
        "on_mouse_drag",
        "on_mouse_scroll",
    ):
        getattr(imgui, name).return_value = False
    view = _view(imgui=imgui)
    _install_game_handlers(view)

    view.on_resize(800, 600)
    view.on_update(0.25)
    view.on_mouse_press(1, 2, arcade.MOUSE_BUTTON_LEFT, 7)
    view.on_mouse_motion(3, 4, 5, 6)
    view.on_mouse_release(7, 8, arcade.MOUSE_BUTTON_LEFT, 9)
    view.on_mouse_drag(10, 11, 12, 13, arcade.MOUSE_BUTTON_LEFT, 14)
    view.on_mouse_scroll(15, 16, 0.5, -1)

    view.on_game_resize.assert_called_once_with(800, 600)
    view.on_game_update.assert_called_once_with(0.25)
    view.on_game_mouse_press.assert_called_once_with(1, 2, arcade.MOUSE_BUTTON_LEFT, 7)
    imgui.on_mouse_motion.assert_called_once_with(3, 4, 5, 6)
    view.on_game_mouse_motion.assert_called_once_with(3, 4, 5, 6)
    view.on_game_mouse_release.assert_called_once_with(7, 8, arcade.MOUSE_BUTTON_LEFT, 9)
    view.on_game_mouse_drag.assert_called_once_with(
        10, 11, 12, 13, arcade.MOUSE_BUTTON_LEFT, 14
    )
    view.on_game_mouse_scroll.assert_called_once_with(15, 16, 0.5, -1)


def test_key_press_prioritizes_global_fullscreen_shortcut_and_respects_capture():
    imgui = Mock()
    settings = SimpleNamespace(toggle_fullscreen=Mock())
    view = _view(imgui=imgui, settings=settings)
    _install_game_handlers(view)

    imgui.on_key_press.return_value = True
    view.on_key_press(arcade.key.F11, 0)
    settings.toggle_fullscreen.assert_called_once_with(view.window)
    view.on_game_key_press.assert_not_called()

    imgui.on_key_press.return_value = True
    view.on_key_press(arcade.key.A, 1)
    view.on_game_key_press.assert_not_called()

    imgui.on_key_press.return_value = False
    view.on_key_press(arcade.key.B, 2)
    view.on_game_key_press.assert_called_once_with(arcade.key.B, 2)


def test_f11_without_settings_falls_through_and_release_and_text_respect_capture():
    imgui = Mock()
    view = _view(imgui=imgui)
    _install_game_handlers(view)

    imgui.on_key_press.return_value = False
    view.on_key_press(arcade.key.F11, 0)
    view.on_game_key_press.assert_called_once_with(arcade.key.F11, 0)

    imgui.on_key_release.return_value = False
    imgui.on_text.return_value = False
    view.on_key_release(arcade.key.C, 3)
    view.on_text("hello")
    view.on_game_key_release.assert_called_once_with(arcade.key.C, 3)
    view.on_game_text.assert_called_once_with("hello")

    imgui.on_key_release.return_value = True
    imgui.on_text.return_value = True
    view.on_key_release(arcade.key.D, 4)
    view.on_text("captured")
    assert view.on_game_key_release.call_count == 1
    assert view.on_game_text.call_count == 1
