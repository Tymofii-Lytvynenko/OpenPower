from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import arcade
import pytest

from src.client.views import main_menu_view as menu_view_module


class FakeCamera:
    instances: list["FakeCamera"] = []

    def __init__(self, distance: float) -> None:
        self.distance = distance
        self.yaw = 0.0
        self.look_at_pixel_fraction = Mock()
        self.drag = Mock()
        self.zoom_scroll = Mock()
        self.instances.append(self)


class FakeMapRenderer:
    instances: list["FakeMapRenderer"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.camera = kwargs["camera"]
        self.set_overlay_style = Mock()
        self.draw = Mock()
        self.instances.append(self)


class FakeMenuContent:
    instances: list["FakeMenuContent"] = []

    def __init__(self, ui, settings_content, actions) -> None:
        self.ui = ui
        self.settings_content = settings_content
        self.actions = actions
        self.render = Mock()
        self.instances.append(self)


def install_view_dependencies(
    monkeypatch,
    *,
    tmp_path: Path,
    data_dirs: list[Path],
    shared_renderer=None,
):
    FakeCamera.instances.clear()
    FakeMapRenderer.instances.clear()
    FakeMenuContent.instances.clear()

    nav = SimpleNamespace(show_new_game_screen=Mock(), show_load_game_screen=Mock())
    context = SimpleNamespace(
        DEPTH_TEST=1,
        BLEND=2,
        scissor="old-scissor",
        viewport=None,
        enable_only=Mock(),
    )
    window = SimpleNamespace(
        settings=object(),
        shared_renderer=shared_renderer,
        nav=nav,
        imgui=SimpleNamespace(new_frame=Mock(), render=Mock()),
        ctx=context,
        background_color=None,
        get_size=Mock(return_value=(640, 480)),
    )
    session = SimpleNamespace(map_data=SimpleNamespace(width=1440, height=720))
    config = SimpleNamespace(
        project_root=tmp_path / "project",
        get_data_dirs=lambda: data_dirs,
        get_asset_path=lambda relative_path: tmp_path / "assets" / relative_path,
    )
    ui = SimpleNamespace(setup_frame=Mock())
    settings_content = object()
    actions = object()
    theme = object()

    monkeypatch.setattr(
        menu_view_module.BaseImGuiView,
        "__init__",
        lambda view: setattr(view, "window", window),
    )
    monkeypatch.setattr(menu_view_module, "UIComposer", lambda _theme: ui)
    monkeypatch.setattr(
        menu_view_module,
        "GameSettingsContent",
        Mock(return_value=settings_content),
    )
    monkeypatch.setattr(menu_view_module, "MainMenuContent", FakeMenuContent)
    build_actions = Mock(return_value=actions)
    monkeypatch.setattr(menu_view_module, "build_main_menu_actions", build_actions)
    monkeypatch.setattr(menu_view_module, "GAMETHEME", theme)
    monkeypatch.setattr(menu_view_module, "CameraController", FakeCamera)
    monkeypatch.setattr(menu_view_module, "MapRenderer", FakeMapRenderer)
    return window, session, config, ui, settings_content, actions, build_actions


def test_constructor_builds_renderer_from_first_available_mod_map(monkeypatch, tmp_path) -> None:
    mod_root = tmp_path / "mod"
    region_image = mod_root / "regions" / "regions.png"
    region_image.parent.mkdir(parents=True)
    region_image.touch()
    window, session, config, ui, settings, actions, build_actions = install_view_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        data_dirs=[mod_root, tmp_path / "other-mod"],
    )

    view = menu_view_module.MainMenuView(session, config)

    camera = FakeCamera.instances[0]
    renderer = FakeMapRenderer.instances[0]
    assert camera.distance == 2.3
    camera.look_at_pixel_fraction.assert_called_once_with(0.75, 0.30, 1440, 720)
    assert renderer.kwargs["map_img_path"] == region_image
    assert renderer.kwargs["terrain_img_path"] == tmp_path / "assets" / "map/terrain.png"
    assert window.shared_renderer is renderer
    renderer.set_overlay_style.assert_called_once_with(enabled=False, opacity=0.0)
    menu_view_module.GameSettingsContent.assert_called_once_with(window.settings, window, staged=True)
    assert FakeMenuContent.instances[0].ui is ui
    assert FakeMenuContent.instances[0].settings_content is settings
    assert FakeMenuContent.instances[0].actions is actions

    new_game, load_game, exit_game = build_actions.call_args.args
    new_game()
    load_game()
    window.nav.show_new_game_screen.assert_called_once_with(session, config)
    window.nav.show_load_game_screen.assert_called_once_with(config)
    assert callable(exit_game)
    assert view.renderer is renderer


def test_constructor_uses_base_map_fallback_when_no_mod_map_exists(monkeypatch, tmp_path) -> None:
    window, session, config, _ui, _settings, _actions, _build_actions = install_view_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        data_dirs=[tmp_path / "empty-mod"],
    )

    menu_view_module.MainMenuView(session, config)

    assert FakeMapRenderer.instances[0].kwargs["map_img_path"] == (
        config.project_root / "modules" / "base" / "data" / "regions" / "regions.png"
    )
    assert window.shared_renderer is FakeMapRenderer.instances[0]


def test_constructor_reuses_existing_renderer_and_camera(monkeypatch, tmp_path) -> None:
    renderer = SimpleNamespace(
        camera=object(),
        set_overlay_style=Mock(),
        draw=Mock(),
    )
    window, session, config, _ui, _settings, _actions, _build_actions = install_view_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        data_dirs=[],
        shared_renderer=renderer,
    )

    view = menu_view_module.MainMenuView(session, config)

    assert view.cam_ctrl is renderer.camera
    assert view.renderer is renderer
    assert window.shared_renderer is renderer
    assert FakeCamera.instances == []
    assert FakeMapRenderer.instances == []
    renderer.set_overlay_style.assert_called_once_with(enabled=False, opacity=0.0)


def test_view_draw_lifecycle_and_input_events(monkeypatch, tmp_path) -> None:
    renderer = SimpleNamespace(camera=FakeCamera(2.3), set_overlay_style=Mock(), draw=Mock())
    window, session, config, ui, _settings, _actions, _build_actions = install_view_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        data_dirs=[],
        shared_renderer=renderer,
    )
    view = menu_view_module.MainMenuView(session, config)
    view.clear = Mock()

    view.on_show_view()
    view.on_game_update(2.0)
    view.on_draw()
    view._render_menu_window()
    view.on_game_mouse_drag(1, 2, 3, 4, arcade.MOUSE_BUTTON_LEFT, 0)
    view.on_game_mouse_drag(1, 2, 3, 4, arcade.MOUSE_BUTTON_RIGHT, 0)
    view.on_game_mouse_scroll(1, 2, 0, -2)

    assert window.background_color == (15, 15, 20, 255)
    assert renderer.camera.yaw == pytest.approx(0.1)
    view.clear.assert_called_once_with()
    window.imgui.new_frame.assert_called_once_with()
    ui.setup_frame.assert_called_once_with()
    assert window.ctx.scissor is None
    assert window.ctx.viewport == (0, 0, 640, 480)
    window.ctx.enable_only.assert_called_once_with(window.ctx.DEPTH_TEST, window.ctx.BLEND)
    renderer.draw.assert_called_once_with()
    window.imgui.render.assert_called_once_with()
    assert FakeMenuContent.instances[0].render.call_count == 2
    renderer.camera.drag.assert_called_once_with(3, 4)
    renderer.camera.zoom_scroll.assert_called_once_with(-2)


def test_exit_to_desktop_exits_arcade_and_process(monkeypatch, tmp_path) -> None:
    _window, session, config, _ui, _settings, _actions, _build_actions = install_view_dependencies(
        monkeypatch,
        tmp_path=tmp_path,
        data_dirs=[],
        shared_renderer=SimpleNamespace(camera=object(), set_overlay_style=Mock()),
    )
    view = menu_view_module.MainMenuView(session, config)
    arcade_exit = Mock()
    process_exit = Mock(side_effect=SystemExit(0))
    monkeypatch.setattr(menu_view_module.arcade, "exit", arcade_exit)
    monkeypatch.setattr(menu_view_module.sys, "exit", process_exit)

    with pytest.raises(SystemExit):
        view._exit_to_desktop()

    arcade_exit.assert_called_once_with()
    process_exit.assert_called_once_with()
