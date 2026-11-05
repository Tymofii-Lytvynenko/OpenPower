from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.gml_layout import active_gml_layout, get_gml_layout


_GML_TEMPLATE = "History_Tooltip_Window"
_MARKER_SIZE = 7.0
_MARKER_INFO_OFFSET_Y = 16.0


@dataclass(frozen=True, slots=True)
class HistoryEventMarker:
    test_id: str
    x: float
    y: float
    text: str


class HistoryTooltipWindow:
    """Render an OpenPower history event in the source GML marker tooltip."""

    def __init__(self) -> None:
        self._text = ""
        self._marker_position: tuple[float, float] | None = None
        self._parent_origin = (0.0, 0.0)
        self._parent_size = (0.0, 0.0)

    def update_hover(
        self,
        markers: Sequence[HistoryEventMarker],
        hovered_test_id: str | None,
        *,
        parent_origin: tuple[float, float],
        parent_size: tuple[float, float],
    ) -> None:
        self._parent_origin = parent_origin
        self._parent_size = parent_size
        hovered = next((marker for marker in markers if marker.test_id == hovered_test_id), None)
        if hovered is not None:
            self._text = hovered.text
            self._marker_position = (hovered.x, hovered.y)
            return

        if not self._text or self._marker_position is None:
            self.hide()
            return

        mouse = imgui.get_mouse_pos()
        width, height = self._window_size()
        x, y = self._tooltip_position(width, height)
        if not (x <= mouse.x <= x + width and y <= mouse.y <= y + height):
            self.hide()

    def hide(self) -> None:
        self._text = ""
        self._marker_position = None

    def render(self) -> bool:
        if not self._text or self._marker_position is None:
            return False

        width, height = self._window_size()
        x, y = self._tooltip_position(width, height)
        flags = (
            imgui.WindowFlags_.no_title_bar
            | imgui.WindowFlags_.no_resize
            | imgui.WindowFlags_.no_move
            | imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.no_saved_settings
            | imgui.WindowFlags_.no_scrollbar
            | imgui.WindowFlags_.no_scroll_with_mouse
        )
        with WindowManager.window(
            "##history_event_tooltip",
            x=x,
            y=y,
            w=width,
            h=height,
            closable=False,
            flags=flags,
            test_id="history.tooltip",
            gml_template=_GML_TEMPLATE,
            size_override=(width, height),
            follow_position=True,
            padding=(0.0, 0.0),
        ) as opened:
            if not opened:
                return False
            session = active_gml_layout()
            component = session.layout.component(f"{_GML_TEMPLATE}/txtText") if session else None
            font_size = component.font_size if component and component.font_size else 9.0
            style = imgui.get_style()
            scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
            imgui.push_font(None, float(font_size) / scale)
            try:
                imgui.text_wrapped(
                    self._text,
                    gml_id=f"{_GML_TEMPLATE}/txtText",
                    test_id="history.tooltip.text",
                )
            finally:
                imgui.pop_font()
        return True

    def _window_size(self) -> tuple[float, float]:
        parent_width, parent_height = self._parent_size
        layout = get_gml_layout(_GML_TEMPLATE)
        component = layout.component(f"{_GML_TEMPLATE}/txtText")
        font_size = component.font_size if component and component.font_size else 9.0
        style = imgui.get_style()
        scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
        imgui.push_font(None, float(font_size) / scale)
        try:
            text_size = imgui.calc_text_size(
                self._text,
                wrap_width=max(1.0, parent_width - 8.0),
            )
        finally:
            imgui.pop_font()
        width = min(parent_width, float(text_size.x) + 8.0)
        height = min(parent_height, float(text_size.y) + 8.0)
        return max(8.0, width), max(8.0, height)

    def _tooltip_position(self, width: float, height: float) -> tuple[float, float]:
        if self._marker_position is None:
            return self._parent_origin
        marker_x, marker_y = self._marker_position
        parent_x, parent_y = self._parent_origin
        parent_width, parent_height = self._parent_size
        x = marker_x - parent_x
        y = marker_y - parent_y

        if y + _MARKER_INFO_OFFSET_Y + height < parent_height:
            y += _MARKER_INFO_OFFSET_Y
        else:
            y -= _MARKER_INFO_OFFSET_Y + height - _MARKER_SIZE
        if x + width > parent_width:
            x = parent_width - width

        x = max(0.0, x)
        y = max(0.0, min(y, parent_height - height))
        return parent_x + x, parent_y + y
