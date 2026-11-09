from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import polars as pl

from src.client.views import editor_view as editor_module
from src.client.views.editor_view import EditorView


def test_editor_view_initialization_composes_camera_renderer_and_controllers(monkeypatch) -> None:
    imgui = Mock()
    window = SimpleNamespace(imgui=imgui)
    camera = Mock()
    renderer = Mock()
    layout = Mock()
    world_camera = Mock()
    viewport = Mock()
    net_client = Mock()

    def initialize_base(view):
        view.window = window

    monkeypatch.setattr(editor_module.BaseImGuiView, "__init__", initialize_base)
    monkeypatch.setattr(editor_module, "CameraController", Mock(return_value=camera))
    monkeypatch.setattr(editor_module, "MapRenderer", Mock(return_value=renderer))
    monkeypatch.setattr(editor_module, "EditorLayout", Mock(return_value=layout))
    monkeypatch.setattr(editor_module.arcade, "Camera2D", Mock(return_value=world_camera))
    viewport_type = Mock(return_value=viewport)
    monkeypatch.setattr(editor_module, "ViewportController", viewport_type)
    context = SimpleNamespace(
        net_client=net_client,
        map_path=Path("regions.png"),
        terrain_path=Path("terrain.png"),
        map_data=object(),
    )

    view = EditorView(context, object())

    assert view.net is net_client
    assert view.imgui is imgui
    assert view.cam_ctrl is camera
    assert view.renderer is renderer
    assert view.layout is layout
    assert view.world_cam is world_camera
    assert view.viewport_ctrl is viewport
    assert view.selected_region_id is None
    view.on_selection_changed(0xAA0000)
    assert view.selected_region_id == 0xAA0000
    viewport_type.assert_called_once()
    assert viewport_type.call_args.kwargs["on_selection_change"].__self__ is view


def test_editor_view_refreshes_overlay_only_when_region_owners_exist(monkeypatch) -> None:
    view = object.__new__(EditorView)
    view.net = Mock()
    view.renderer = Mock()

    view.net.get_state.return_value = SimpleNamespace(tables={})
    view._refresh_political_data()
    view.net.get_state.return_value = SimpleNamespace(
        tables={"regions": pl.DataFrame({"id": [1]})},
        get_table=Mock(return_value=pl.DataFrame({"id": [1]})),
    )
    view._refresh_political_data()
    view.renderer.update_overlay.assert_not_called()

    region_data = pl.DataFrame({"id": [1, 2, 3], "owner": ["USA", "CAN", "USA"]})
    view.net.get_state.return_value = SimpleNamespace(
        tables={"regions": region_data},
        get_table=Mock(return_value=region_data),
    )
    colors = {"USA": (1, 2, 3), "CAN": (4, 5, 6)}
    with patch.object(editor_module, "generate_political_colors", return_value=colors) as color_factory:
        view._refresh_political_data()

    color_factory.assert_called_once()
    assert set(color_factory.call_args.args[0]) == {"USA", "CAN"}
    view.renderer.update_overlay.assert_called_once_with(colors)


def test_editor_view_draws_both_overlay_modes_and_delegates_window_input() -> None:
    view = object.__new__(EditorView)
    view.clear = Mock()
    imgui = SimpleNamespace(new_frame=Mock(), io=SimpleNamespace(framerate=60), render=Mock())
    view.window = SimpleNamespace(imgui=imgui, use=Mock())
    view.world_cam = Mock()
    view.renderer = Mock()
    view.layout = Mock()
    view.viewport_ctrl = Mock()
    view.net = Mock()

    for mode, expected_enabled in (("terrain", False), ("political", True)):
        view.layout.get_current_render_mode.return_value = mode
        view.on_draw()
        assert view.renderer.set_overlay_style.call_args.kwargs == {
            "enabled": expected_enabled,
            "opacity": 0.90,
        }

    view.on_game_resize(1280, 720)
    view.world_cam.match_window.assert_called_once_with()
    view.on_game_mouse_press(1, 2, 3, 4)
    view.viewport_ctrl.on_mouse_press.assert_called_once_with(1, 2, 3)
    view.on_game_mouse_release(5, 6, 7, 8)
    view.viewport_ctrl.on_mouse_release.assert_called_once_with(5, 6, 7)
    view.on_game_mouse_drag(9, 10, 11, 12, 13, 14)
    view.viewport_ctrl.on_mouse_drag.assert_called_once_with(9, 10, 11, 12, 13)
    view.on_game_mouse_scroll(15, 16, 17, 18)
    view.viewport_ctrl.on_mouse_scroll.assert_called_once_with(15, 16, 17, 18)

    view.on_game_key_press(editor_module.arcade.key.S, editor_module.arcade.key.MOD_CTRL)
    view.net.request_save.assert_called_once_with()
    view.on_game_key_press(editor_module.arcade.key.S, 0)
    view.net.request_save.assert_called_once_with()


def test_editor_view_show_sets_black_background_and_refreshes_data() -> None:
    view = object.__new__(EditorView)
    view.window = SimpleNamespace(background_color=None)
    view._refresh_political_data = Mock()

    view.on_show_view()

    assert view.window.background_color == editor_module.arcade.color.BLACK
    view._refresh_political_data.assert_called_once_with()
