from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import active_telemetry
from src.client.ui.core.window_placement import (
    ResolvedWindowPlacement,
    WindowPlacement,
    WindowPlacementPolicy,
    WindowPlacementRequest,
)
from src.client.ui.layouts.gml_layout import GMLWindowLayout, resolve_gml_layout


@dataclass(frozen=True, slots=True)
class WindowRequest:
    title: str
    x: float
    y: float
    w: float
    h: float
    closable: bool
    flags: Any
    test_id: str | None
    gml_template: str | None
    padding: tuple[float, float] | None
    follow_position: bool
    size_override: tuple[float, float] | None
    horizontal_anchor: Literal["left", "right"]
    horizontal_margin: float
    fit_layout_width: bool
    avoid_overlaps: bool
    placement_margin: float
    bottom_clearance: float
    top_clearance: float


@dataclass(frozen=True, slots=True)
class WindowSetup:
    layout: GMLWindowLayout | None
    window_key: str
    viewport_width: float
    viewport_height: float
    live_placement: bool


class WindowSetupPolicy:
    """Resolve a window's layout, viewport placement, and initial ImGui geometry."""

    def __init__(self, placement_policy: WindowPlacementPolicy) -> None:
        self._placement_policy = placement_policy
        self._waiting_for_viewport: set[str] = set()

    def prepare(
        self,
        request: WindowRequest,
        *,
        placements: Mapping[str, WindowPlacement],
        frame_placements: Mapping[str, WindowPlacement],
    ) -> WindowSetup:
        layout, width, height = self._resolve_layout_and_size(request)
        telemetry = active_telemetry()
        viewport_width, viewport_height = self._resolve_viewport_size(telemetry)
        window_key = self._window_key(request)
        live_placement = telemetry is None or not telemetry.pin_windows
        previous = self._previous_placement(request, window_key, live_placement, placements)
        occupied = self._occupied_placements(request, window_key, frame_placements)
        resolved = self._resolve_placement(
            request,
            layout,
            (width, height),
            (viewport_width, viewport_height),
            previous,
            occupied,
        )
        self._schedule_geometry(
            request,
            telemetry,
            window_key,
            (viewport_width, viewport_height),
            resolved,
            has_layout=layout is not None,
        )
        return WindowSetup(
            layout=layout,
            window_key=window_key,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            live_placement=live_placement,
        )

    @staticmethod
    def _resolve_layout_and_size(
        request: WindowRequest,
    ) -> tuple[GMLWindowLayout | None, float, float]:
        layout = resolve_gml_layout(
            request.gml_template,
            test_id=request.test_id,
            title=request.title,
        )
        width, height = request.w, request.h
        if layout is not None:
            width, height = float(layout.width), float(layout.height)
        if request.size_override is not None:
            width, height = request.size_override
        return layout, width, height

    @staticmethod
    def _resolve_viewport_size(telemetry: Any) -> tuple[float, float]:
        if telemetry is not None:
            return telemetry.viewport_size
        viewport = imgui.get_io().display_size
        if viewport.x <= 0 or viewport.y <= 0:
            viewport = imgui.get_main_viewport().size
        return viewport.x, viewport.y

    @staticmethod
    def _window_key(request: WindowRequest) -> str:
        return request.test_id or request.title.split("###", 1)[0].strip()

    @staticmethod
    def _previous_placement(
        request: WindowRequest,
        window_key: str,
        live_placement: bool,
        placements: Mapping[str, WindowPlacement],
    ) -> WindowPlacement | None:
        if not live_placement or request.follow_position:
            return None
        return placements.get(window_key)

    @staticmethod
    def _occupied_placements(
        request: WindowRequest,
        window_key: str,
        frame_placements: Mapping[str, WindowPlacement],
    ) -> tuple[WindowPlacement, ...]:
        if not request.avoid_overlaps:
            return ()
        return tuple(
            placement
            for key, placement in frame_placements.items()
            if key != window_key
        )

    def _resolve_placement(
        self,
        request: WindowRequest,
        layout: GMLWindowLayout | None,
        size: tuple[float, float],
        viewport_size: tuple[float, float],
        previous: WindowPlacement | None,
        occupied: tuple[WindowPlacement, ...],
    ) -> ResolvedWindowPlacement:
        return self._placement_policy.resolve(
            WindowPlacementRequest(
                requested_position=(request.x, request.y),
                requested_size=size,
                viewport_size=viewport_size,
                previous=previous,
                occupied=occupied,
                avoid_overlaps=request.avoid_overlaps,
                horizontal_anchor=request.horizontal_anchor,
                horizontal_margin=request.horizontal_margin,
                fixed_size=layout is not None or request.size_override is not None,
                placement_margin=request.placement_margin,
                top_clearance=request.top_clearance,
                bottom_clearance=request.bottom_clearance,
            )
        )

    def _schedule_geometry(
        self,
        request: WindowRequest,
        telemetry: Any,
        window_key: str,
        viewport_size: tuple[float, float],
        placement: ResolvedWindowPlacement,
        *,
        has_layout: bool,
    ) -> None:
        x, y, width, height = placement.x, placement.y, placement.width, placement.height
        position_condition = self._position_condition(telemetry, request, window_key)
        if placement.viewport_changed:
            # A saved absolute coordinate can leave an anchored panel beyond a resized client area.
            position_condition = imgui.Cond_.always
        viewport_width, viewport_height = viewport_size
        # Authored panels must stay reachable on smaller viewports; overflowing content remains scrollable.
        if viewport_width > 0 and viewport_height > 0:
            width, height = min(width, viewport_width), min(height, viewport_height)
            x = max(0, min(x, viewport_width - width))
            y = max(0, min(y, viewport_height - height))
            if window_key in self._waiting_for_viewport:
                # ImGui may create the window before its first valid viewport size arrives.
                position_condition = imgui.Cond_.always
                self._waiting_for_viewport.discard(window_key)
        else:
            self._waiting_for_viewport.add(window_key)
        imgui.set_next_window_pos((x, y), position_condition)
        size_condition = (
            imgui.Cond_.always
            if has_layout or placement.viewport_changed
            else imgui.Cond_.first_use_ever
        )
        imgui.set_next_window_size((width, height), size_condition)

    @staticmethod
    def _position_condition(telemetry: Any, request: WindowRequest, window_key: str) -> Any:
        if request.follow_position or request.avoid_overlaps:
            return imgui.Cond_.always
        if telemetry is not None and telemetry.pin_windows:
            if window_key not in telemetry.movable_window_ids:
                return imgui.Cond_.always
        return imgui.Cond_.first_use_ever
