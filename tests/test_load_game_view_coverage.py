from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import arcade

import src.client.views.load_game_view as load_game_view_module
from src.client.views.base_view import BaseImGuiView


def test_load_game_view_wires_dialog_callbacks_and_draw_lifecycle(monkeypatch):
    config = object()
    session = object()
    nav = Mock()
    window = SimpleNamespace(imgui=Mock(), session=session, nav=nav)
    monkeypatch.setattr(
        BaseImGuiView,
        "__init__",
        lambda self: setattr(self, "window", window),
    )

    composer = Mock()
    message_dialog = Mock()
    save_dialog = Mock()
    monkeypatch.setattr(load_game_view_module, "UIComposer", Mock(return_value=composer))
    monkeypatch.setattr(
        load_game_view_module,
        "GenericMessageDialog",
        Mock(return_value=message_dialog),
    )
    save_dialog_factory = Mock(return_value=save_dialog)
    monkeypatch.setattr(load_game_view_module, "SaveGameDialog", save_dialog_factory)

    view = load_game_view_module.LoadGameView(config)

    save_dialog.toggle.assert_called_once_with("load")
    save_dialog_factory.call_args.args[2]("autosave")
    nav.load_saved_game.assert_called_once_with(config, "autosave")
    save_dialog_factory.call_args.kwargs["on_close"]()
    nav.show_main_menu.assert_called_once_with(session, config)

    view.window.imgui = None
    view.setup_imgui = Mock()
    view.on_show_view()
    assert view.window.background_color == arcade.color.BLACK
    view.setup_imgui.assert_called_once_with()

    view.window.imgui = Mock()
    view.on_show_view()
    view.setup_imgui.assert_called_once_with()

    view.clear = Mock()
    view.on_draw()
    view.clear.assert_called_once_with()
    view.window.imgui.new_frame.assert_called_once_with()
    composer.setup_frame.assert_called_once_with()
    save_dialog.render.assert_called_once_with()
    message_dialog.render.assert_called_once_with()
    view.window.imgui.render.assert_called_once_with()
