import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from src.client.ui.core import theme
from src.client.ui.core.gml_tooltip import render_gml_tooltip, resolve_gml_tooltip_geometry


def test_gml_tooltip_sizes_short_text_and_sits_above_left_of_cursor():
    geometry = resolve_gml_tooltip_geometry(
        "help",
        lambda _text, _wrap_width: (20.0, 12.0),
        (100.0, 80.0),
    )

    assert (geometry.x, geometry.y, geometry.width, geometry.height) == (
        67.0,
        55.0,
        30.0,
        22.0,
    )


def test_gml_tooltip_widens_until_long_content_fits_below_the_frame_width():
    text = "x" * 180

    def measure(value: str, wrap_width: float) -> tuple[float, float]:
        natural_width = len(value) * 10.0
        lines = max(1, (int(natural_width) + int(wrap_width) - 1) // int(wrap_width))
        return min(natural_width, wrap_width), lines * 20.0

    geometry = resolve_gml_tooltip_geometry(text, measure, (700.0, 700.0))

    assert geometry.width == 250.0
    assert geometry.height == 170.0


def test_gml_tooltip_moves_below_and_right_when_above_left_position_is_negative():
    geometry = resolve_gml_tooltip_geometry(
        "long text",
        lambda _text, _wrap_width: (400.0, 12.0),
        (10.0, 5.0),
    )

    assert (geometry.x, geometry.y) == (20.0, 15.0)


@pytest.mark.parametrize("tooltip_open", [True, False])
def test_render_gml_tooltip_balances_imgui_scopes_for_open_and_closed_tooltips(
    monkeypatch,
    tooltip_open,
):
    api = SimpleNamespace(
        Cond_=SimpleNamespace(always=1),
        StyleVar_=SimpleNamespace(window_padding=2, window_border_size=3, window_rounding=4),
        Col_=SimpleNamespace(window_bg=5, border=6),
    )
    fake_package = ModuleType("imgui_bundle")
    fake_package.imgui = api
    monkeypatch.setitem(sys.modules, "imgui_bundle", fake_package)
    monkeypatch.setattr(
        theme,
        "GAMETHEME",
        SimpleNamespace(colors=SimpleNamespace(bg_popup=(0.1, 0.2, 0.3, 1.0))),
    )

    native_imgui = MagicMock()
    native_imgui.get_style.return_value = SimpleNamespace(
        font_scale_main=1.0,
        font_scale_dpi=1.0,
    )
    native_imgui.get_mouse_pos.return_value = SimpleNamespace(x=100.0, y=80.0)
    native_imgui.calc_text_size.return_value = SimpleNamespace(x=20.0, y=12.0)
    native_imgui.get_cursor_pos_x.return_value = 15.0
    native_imgui.begin_tooltip.return_value = tooltip_open

    render_gml_tooltip(native_imgui, "help")

    native_imgui.push_font.assert_called_once_with(None, 12.0)
    native_imgui.set_next_window_pos.assert_called_once_with((67.0, 55.0), api.Cond_.always)
    native_imgui.set_next_window_size.assert_called_once_with((30.0, 22.0), api.Cond_.always)
    assert native_imgui.push_style_var.call_args_list == [
        call(api.StyleVar_.window_padding, (5.0, 5.0)),
        call(api.StyleVar_.window_border_size, 1.0),
        call(api.StyleVar_.window_rounding, 0.0),
    ]
    native_imgui.push_style_color.assert_has_calls(
        [
            call(api.Col_.window_bg, (0.1, 0.2, 0.3, 1.0)),
            call(api.Col_.border, (0.3, 0.3, 0.3, 0.55)),
        ]
    )
    native_imgui.pop_style_color.assert_called_once_with(2)
    native_imgui.pop_style_var.assert_called_once_with(3)
    native_imgui.pop_font.assert_called_once_with()

    if tooltip_open:
        native_imgui.push_text_wrap_pos.assert_called_once_with(35.0)
        native_imgui.text_wrapped.assert_called_once_with("help")
        native_imgui.pop_text_wrap_pos.assert_called_once_with()
        native_imgui.end_tooltip.assert_called_once_with()
    else:
        native_imgui.push_text_wrap_pos.assert_not_called()
        native_imgui.text_wrapped.assert_not_called()
        native_imgui.end_tooltip.assert_not_called()
