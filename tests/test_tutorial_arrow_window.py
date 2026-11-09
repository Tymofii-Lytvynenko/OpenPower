from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.tutorial_arrow_window as arrow_module
from src.client.ui.components.tutorial_arrow_window import (
    TutorialArrowWindow,
    resolve_tutorial_arrow_geometry,
)
from src.client.ui.core.ui_anchor_registry import UIAnchor


def test_tutorial_arrow_points_to_the_target_top_center() -> None:
    geometry = resolve_tutorial_arrow_geometry(
        UIAnchor(100.0, 120.0, 80.0, 24.0),
        (0.0, 0.0),
        (1280.0, 720.0),
    )

    assert geometry is not None
    assert geometry.window_x == 115.0
    assert geometry.window_y == 70.0
    assert geometry.target_x - geometry.window_x == 25.0
    assert geometry.target_y - geometry.window_y == 50.0


def test_tutorial_arrow_stays_inside_the_viewport_near_its_edges() -> None:
    geometry = resolve_tutorial_arrow_geometry(
        UIAnchor(0.0, 18.0, 20.0, 20.0),
        (5.0, 10.0),
        (100.0, 80.0),
    )

    assert geometry is not None
    assert geometry.window_x == 5.0
    assert geometry.window_y == 10.0
    assert geometry.target_x - geometry.window_x == 5.0
    assert geometry.target_y - geometry.window_y == 8.0


def test_tutorial_arrow_geometry_rejects_viewports_without_vertical_space() -> None:
    target = UIAnchor(100.0, 120.0, 80.0, 24.0)

    assert resolve_tutorial_arrow_geometry(target, (0.0, 0.0), (49.0, 720.0)) is None
    assert resolve_tutorial_arrow_geometry(target, (0.0, 0.0), (1280.0, 0.0)) is None
    assert resolve_tutorial_arrow_geometry(
        UIAnchor(100.0, 7.0, 80.0, 24.0),
        (0.0, 0.0),
        (1280.0, 720.0),
    ) is None


def _install_render_doubles(monkeypatch, *, window_open: bool, viewport_size=(1280.0, 720.0)):
    draw = SimpleNamespace(
        add_rect_filled=Mock(),
        add_triangle_filled=Mock(),
    )
    imgui = SimpleNamespace(
        get_main_viewport=Mock(
            return_value=SimpleNamespace(
                pos=SimpleNamespace(x=0.0, y=0.0),
                size=SimpleNamespace(x=viewport_size[0], y=viewport_size[1]),
            )
        ),
        WindowFlags_=SimpleNamespace(
            no_decoration=1,
            no_inputs=2,
            no_focus_on_appearing=4,
            no_bring_to_front_on_focus=8,
            no_background=16,
            no_saved_settings=32,
        ),
        get_foreground_draw_list=Mock(return_value=draw),
        get_color_u32=Mock(side_effect=[101, 202]),
    )
    window = Mock(side_effect=lambda *_args, **_kwargs: nullcontext(window_open))
    monkeypatch.setattr(arrow_module, "imgui", imgui)
    monkeypatch.setattr(
        arrow_module,
        "WindowManager",
        SimpleNamespace(window=window),
    )
    return imgui, window, draw


def test_render_skips_window_when_geometry_is_unavailable(monkeypatch) -> None:
    imgui, window, _draw = _install_render_doubles(
        monkeypatch,
        window_open=True,
        viewport_size=(40.0, 720.0),
    )

    TutorialArrowWindow().render(UIAnchor(100.0, 120.0, 80.0, 24.0))

    imgui.get_main_viewport.assert_called_once()
    window.assert_not_called()
    imgui.get_foreground_draw_list.assert_not_called()


def test_render_stops_when_the_window_manager_closes_the_overlay(monkeypatch) -> None:
    imgui, window, _draw = _install_render_doubles(monkeypatch, window_open=False)

    TutorialArrowWindow().render(UIAnchor(100.0, 120.0, 80.0, 24.0))

    window.assert_called_once()
    assert window.call_args.args[0] == "##TutorialArrow"
    assert window.call_args.kwargs["flags"] == 63
    imgui.get_foreground_draw_list.assert_not_called()


def test_render_draws_the_pointer_on_the_foreground_list(monkeypatch) -> None:
    imgui, window, draw = _install_render_doubles(monkeypatch, window_open=True)

    TutorialArrowWindow().render(UIAnchor(100.0, 120.0, 80.0, 24.0))

    window.assert_called_once_with(
        "##TutorialArrow",
        x=115.0,
        y=70.0,
        w=50.0,
        h=50.0,
        closable=False,
        flags=63,
        test_id="game.tutorial.arrow",
        gml_template="Tutorial_Arrow_Window",
        size_override=(50.0, 50.0),
        padding=(0.0, 0.0),
        follow_position=True,
    )
    imgui.get_foreground_draw_list.assert_called_once_with()
    assert imgui.get_color_u32.call_count == 2
    assert draw.add_rect_filled.call_count == 2
    assert draw.add_triangle_filled.call_count == 2
    assert draw.add_rect_filled.call_args_list[0].args == (
        (135.0, 72.0),
        (145.0, 104.0),
        101,
    )
    assert draw.add_triangle_filled.call_args_list[-1].args == (
        (140.0, 116.0),
        (128.75, 102.0),
        (151.25, 102.0),
        202,
    )
