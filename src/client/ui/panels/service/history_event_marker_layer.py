from __future__ import annotations

from typing import Any

from src.client.ui.components.shared.history_tooltip_window import (
    HistoryEventMarker,
    HistoryTooltipWindow,
)
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.theme import GAMETHEME


_MARKER_SIZE = 7.0
_MARKER_MERGE_DISTANCE = _MARKER_SIZE + 1.0
_MAX_EVENTS_PER_MARKER = 4


class HistoryEventMarkerLayer:
    """Draw OpenPower history events and keep their GML tooltip in sync."""

    def __init__(self) -> None:
        self._tooltip = HistoryTooltipWindow()

    def draw(
        self,
        events: list[dict[str, Any]],
        *,
        chart_rect: tuple[float, float, float, float],
        start_minute: int,
        end_minute: int,
        parent_origin: tuple[float, float],
        parent_size: tuple[float, float],
    ) -> None:
        markers = self._markers(events, chart_rect, start_minute, end_minute)
        draw_list = imgui.get_window_draw_list()
        hovered_test_id = None
        for marker in markers:
            minimum = (marker.x, marker.y)
            maximum = (marker.x + _MARKER_SIZE, marker.y + _MARKER_SIZE)
            draw_list.add_rect_filled(
                minimum,
                maximum,
                imgui.get_color_u32(GAMETHEME.colors.warning),
            )
            draw_list.add_rect(
                minimum,
                maximum,
                imgui.get_color_u32((0.06, 0.07, 0.08, 1.0)),
                0.0,
                flags=0,
                thickness=1.0,
            )
            imgui.set_cursor_screen_pos(minimum)
            imgui.dummy((_MARKER_SIZE, _MARKER_SIZE), test_id=marker.test_id)
            mouse = imgui.get_mouse_pos()
            if marker.x <= mouse.x <= maximum[0] and marker.y <= mouse.y <= maximum[1]:
                hovered_test_id = marker.test_id
                draw_list.add_rect(
                    minimum,
                    maximum,
                    imgui.get_color_u32(GAMETHEME.colors.text_main),
                    0.0,
                    flags=0,
                    thickness=1.0,
                )

        self._tooltip.update_hover(
            markers,
            hovered_test_id,
            parent_origin=parent_origin,
            parent_size=parent_size,
        )

    def render_tooltip(self) -> bool:
        return self._tooltip.render()

    def hide(self) -> None:
        self._tooltip.hide()

    @classmethod
    def _markers(
        cls,
        events: list[dict[str, Any]],
        chart_rect: tuple[float, float, float, float],
        start_minute: int,
        end_minute: int,
    ) -> list[HistoryEventMarker]:
        x, y, width, height = chart_rect
        plot_left = x + 5.0
        plot_width = max(1.0, width - 10.0)
        minute_span = max(1, int(end_minute) - int(start_minute))
        marker_y = y + height - _MARKER_SIZE
        groups: list[dict[str, Any]] = []

        for event in events:
            minute = int(event.get("game_minute") or 0)
            if minute < start_minute or minute > end_minute:
                continue
            fraction = max(0.0, min(1.0, (minute - start_minute) / minute_span))
            center_x = plot_left + plot_width * fraction
            if groups and center_x - groups[-1]["last_x"] <= _MARKER_MERGE_DISTANCE:
                group = groups[-1]
                group["events"].append(event)
                group["last_x"] = center_x
                count = len(group["events"])
                group["center_x"] = (group["center_x"] * (count - 1) + center_x) / count
            else:
                groups.append({"events": [event], "center_x": center_x, "last_x": center_x})

        return [
            HistoryEventMarker(
                test_id=f"history.event_marker.{index}",
                x=float(group["center_x"]) - _MARKER_SIZE / 2.0,
                y=marker_y,
                text=cls._marker_text(group["events"]),
            )
            for index, group in enumerate(groups)
        ]

    @staticmethod
    def _marker_text(events: list[dict[str, Any]]) -> str:
        lines = []
        for event in events[:_MAX_EVENTS_PER_MARKER]:
            title = str(event.get("title") or event.get("event_type") or "Recorded event").strip()
            minute = int(event.get("game_minute") or 0)
            lines.append(f"{title} · minute {minute:,}")
            cause_type = str(event.get("cause_source_type") or "").strip()
            cause_id = str(event.get("cause_source_id") or "").strip()
            if cause_type or cause_id:
                lines.append(f"Cause: {cause_type} {cause_id}".strip())
        if len(events) > _MAX_EVENTS_PER_MARKER:
            lines.append(f"{len(events) - _MAX_EVENTS_PER_MARKER} more events at this time")
        return "\n".join(lines)
