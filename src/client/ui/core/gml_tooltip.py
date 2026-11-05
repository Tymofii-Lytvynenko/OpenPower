"""Render hover help using the source game's transient tooltip frame geometry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class GMLTooltipGeometry:
    x: float
    y: float
    width: float
    height: float


def resolve_gml_tooltip_geometry(
    text: str,
    measure_text: Callable[[str, float], tuple[float, float]],
    cursor_position: tuple[float, float],
) -> GMLTooltipGeometry:
    """Apply Tooltip_Window's auto-size and above-left cursor placement rules."""
    initial_content_width = 190.0
    measured_width, measured_height = measure_text(text, initial_content_width)
    width = measured_width + 10.0 if measured_width < initial_content_width else 200.0
    height = measured_height + 10.0

    while height > width:
        width += 50.0
        _, measured_height = measure_text(text, width - 10.0)
        height = measured_height + 10.0

    mouse_x, mouse_y = cursor_position
    x = mouse_x - width - 3.0
    y = mouse_y - height - 3.0
    if x < 0:
        x = mouse_x + 10.0
    if y < 0:
        y = mouse_y + 10.0

    return GMLTooltipGeometry(x, y, width, height)


def render_gml_tooltip(native_imgui, text: str) -> None:
    """Draw one ImGui tooltip with the GML Tooltip_Window frame and placement."""
    from imgui_bundle import imgui as imgui_api

    from src.client.ui.core.theme import GAMETHEME

    style = native_imgui.get_style()
    scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
    native_imgui.push_font(None, 12.0 / scale)
    try:
        def measure(value: str, wrap_width: float) -> tuple[float, float]:
            size = native_imgui.calc_text_size(value, wrap_width=wrap_width)
            return float(size.x), float(size.y)

        mouse = native_imgui.get_mouse_pos()
        geometry = resolve_gml_tooltip_geometry(
            text,
            measure,
            (float(mouse.x), float(mouse.y)),
        )
        native_imgui.set_next_window_pos(
            (geometry.x, geometry.y), imgui_api.Cond_.always
        )
        native_imgui.set_next_window_size(
            (geometry.width, geometry.height), imgui_api.Cond_.always
        )
        native_imgui.push_style_var(imgui_api.StyleVar_.window_padding, (5.0, 5.0))
        native_imgui.push_style_var(imgui_api.StyleVar_.window_border_size, 1.0)
        native_imgui.push_style_var(imgui_api.StyleVar_.window_rounding, 0.0)
        native_imgui.push_style_color(imgui_api.Col_.window_bg, GAMETHEME.colors.bg_popup)
        native_imgui.push_style_color(imgui_api.Col_.border, (0.3, 0.3, 0.3, 0.55))
        try:
            if not native_imgui.begin_tooltip():
                return
            try:
                native_imgui.push_text_wrap_pos(
                    native_imgui.get_cursor_pos_x() + max(1.0, geometry.width - 10.0)
                )
                try:
                    native_imgui.text_wrapped(text)
                finally:
                    native_imgui.pop_text_wrap_pos()
            finally:
                native_imgui.end_tooltip()
        finally:
            native_imgui.pop_style_color(2)
            native_imgui.pop_style_var(3)
    finally:
        native_imgui.pop_font()
