from types import SimpleNamespace
from unittest.mock import Mock

import src.client.views.server_boot_view as boot_view_module
from src.client.views.server_boot_view import ServerBootView


def test_constructor_composes_theme_and_keeps_config(monkeypatch):
    base_imgui = object()
    base_window = SimpleNamespace(imgui=base_imgui)

    def initialize_base(view):
        view.window = base_window

    monkeypatch.setattr(boot_view_module.BaseImGuiView, "__init__", initialize_base)
    composer = Mock()
    composer_factory = Mock(return_value=composer)
    theme = object()
    monkeypatch.setattr(boot_view_module, "UIComposer", composer_factory)
    monkeypatch.setattr(boot_view_module, "GAMETHEME", theme)
    config = object()

    view = ServerBootView(config)

    assert view.config is config
    assert view.window is base_window
    assert view.imgui is base_imgui
    composer_factory.assert_called_once_with(theme)
    assert view.ui is composer


def test_show_and_update_delegate_to_window_and_imgui():
    view = ServerBootView.__new__(ServerBootView)
    view.window = SimpleNamespace(imgui=Mock())

    view.on_show_view()
    view.on_game_update(0.25)

    assert view.window.background_color == (10, 10, 10, 255)
    view.imgui.update_time.assert_called_once_with(0.25)


def test_draw_renders_error_progress_defaults_and_closed_panel(monkeypatch):
    imgui = Mock()
    monkeypatch.setattr(boot_view_module, "imgui", imgui)
    view = ServerBootView.__new__(ServerBootView)
    view.clear = Mock()
    imgui_service = Mock()
    view.window = SimpleNamespace(imgui=imgui_service)
    view.ui = Mock()
    view.ui.begin_centered_panel.side_effect = [True, True, False]
    view.window = SimpleNamespace(
        imgui=imgui_service,
        boot_progress="0.4",
        boot_status=17,
        boot_error=RuntimeError("server failed"),
        get_size=Mock(return_value=(1024, 768)),
    )

    view.on_draw()
    view.window = SimpleNamespace(
        imgui=imgui_service,
        get_size=Mock(return_value=(800, 600)),
    )
    view.on_draw()
    view.on_draw()

    assert view.ui.begin_centered_panel.call_args_list[0].args == (
        "Server Boot", 1024, 768,
    )
    assert view.ui.begin_centered_panel.call_args_list[1].args == (
        "Server Boot", 800, 600,
    )
    assert view.ui.draw_progress_bar.call_args_list[0].args == (0.4, "17")
    assert view.ui.draw_progress_bar.call_args_list[1].args == (
        0.0, "Starting engine...",
    )
    imgui.text_colored.assert_called_once_with(
        boot_view_module.GAMETHEME.colors.error,
        "server failed",
    )
    imgui.text_disabled.assert_called_once_with("Starting simulation process...")
    assert view.ui.end_panel.call_count == 2
    assert imgui_service.render.call_count == 3
    assert view.clear.call_count == 3
