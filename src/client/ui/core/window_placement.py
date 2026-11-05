from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class WindowPlacement:
    viewport_width: float
    viewport_height: float
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class ResolvedWindowPlacement:
    x: float
    y: float
    width: float
    height: float
    viewport_changed: bool


@dataclass(frozen=True)
class WindowPlacementRequest:
    requested_position: tuple[float, float]
    requested_size: tuple[float, float]
    viewport_size: tuple[float, float]
    previous: WindowPlacement | None
    occupied: tuple[WindowPlacement, ...]
    avoid_overlaps: bool
    horizontal_anchor: Literal["left", "right"]
    horizontal_margin: float
    fixed_size: bool
    placement_margin: float
    top_clearance: float
    bottom_clearance: float


class WindowPlacementPolicy:
    """Resolve requested window geometry against prior and visible placements."""

    def resolve(self, request: WindowPlacementRequest) -> ResolvedWindowPlacement:
        x, y = request.requested_position
        preserved_placement = self._previous_placement_for_same_viewport(request)
        if preserved_placement is not None:
            x, y = preserved_placement.x, preserved_placement.y

        resolved = resolve_window_placement(
            (x, y),
            request.requested_size,
            request.viewport_size,
            request.previous,
            horizontal_anchor=request.horizontal_anchor,
            horizontal_margin=request.horizontal_margin,
            fixed_size=request.fixed_size,
        )
        if request.avoid_overlaps:
            x, y = resolve_non_overlapping_position(
                (resolved.x, resolved.y),
                (resolved.width, resolved.height),
                request.viewport_size,
                request.occupied,
                margin=request.placement_margin,
                top_clearance=request.top_clearance,
                bottom_clearance=request.bottom_clearance,
            )
            return ResolvedWindowPlacement(
                x,
                y,
                resolved.width,
                resolved.height,
                resolved.viewport_changed,
            )
        return resolved

    @staticmethod
    def _previous_placement_for_same_viewport(
        request: WindowPlacementRequest,
    ) -> WindowPlacement | None:
        if not request.avoid_overlaps:
            return None
        previous = request.previous
        if previous is None:
            return None
        if previous.viewport_width != request.viewport_size[0]:
            return None
        if previous.viewport_height != request.viewport_size[1]:
            return None
        return previous


def center_window(
    viewport_size: tuple[float, float], window_size: tuple[float, float]
) -> tuple[float, float]:
    """Return viewport-relative coordinates for the center of a window."""
    return (
        (viewport_size[0] - window_size[0]) / 2,
        (viewport_size[1] - window_size[1]) / 2,
    )


def resolve_window_placement(
    requested_position: tuple[float, float],
    requested_size: tuple[float, float],
    viewport_size: tuple[float, float],
    previous: WindowPlacement | None = None,
    *,
    horizontal_anchor: Literal["left", "right"] = "left",
    horizontal_margin: float = 0.0,
    fixed_size: bool = True,
) -> ResolvedWindowPlacement:
    """Keep a window reachable after a viewport resize without undoing user moves."""
    viewport_width, viewport_height = viewport_size
    width = min(requested_size[0], viewport_width) if viewport_width > 0 else requested_size[0]
    height = min(requested_size[1], viewport_height) if viewport_height > 0 else requested_size[1]
    x, y = requested_position
    viewport_changed = previous is not None and (
        previous.viewport_width != viewport_width or previous.viewport_height != viewport_height
    )

    if viewport_changed and previous is not None:
        x, y = previous.x, previous.y
        if not fixed_size:
            width = min(previous.width, viewport_width) if viewport_width > 0 else previous.width
            height = min(previous.height, viewport_height) if viewport_height > 0 else previous.height
        previous_right_gap = previous.viewport_width - (previous.x + previous.width)
        was_right_anchored = abs(previous_right_gap - horizontal_margin) <= 2.0
        if horizontal_anchor == "right" and was_right_anchored:
            x = viewport_width - width - horizontal_margin
    elif horizontal_anchor == "right":
        x = viewport_width - width - horizontal_margin

    if viewport_width > 0:
        x = max(0.0, min(x, viewport_width - width))
    if viewport_height > 0:
        y = max(0.0, min(y, viewport_height - height))

    return ResolvedWindowPlacement(x, y, width, height, viewport_changed)


def resolve_non_overlapping_position(
    requested_position: tuple[float, float],
    requested_size: tuple[float, float],
    viewport_size: tuple[float, float],
    occupied: tuple[WindowPlacement, ...] | list[WindowPlacement],
    *,
    margin: float = 8.0,
    top_clearance: float = 0.0,
    bottom_clearance: float = 0.0,
) -> tuple[float, float]:
    """Choose the closest position that avoids active windows and reserved HUD strips."""
    viewport_width, viewport_height = viewport_size
    width = min(requested_size[0], viewport_width) if viewport_width > 0 else requested_size[0]
    height = min(requested_size[1], viewport_height) if viewport_height > 0 else requested_size[1]
    max_x = max(0.0, viewport_width - width)
    max_y = max(0.0, viewport_height - height - bottom_clearance)
    min_y = min(max(0.0, top_clearance), max_y)
    requested_x, requested_y = requested_position

    def clamp(value: float, maximum: float) -> float:
        return max(0.0, min(value, maximum))

    def clamp_y(value: float) -> float:
        return max(min_y, min(value, max_y))

    xs = {clamp(requested_x, max_x), 0.0, max_x}
    ys = {clamp_y(requested_y), min_y, max_y}
    for window in occupied:
        xs.update((
            clamp(window.x - width - margin, max_x),
            clamp(window.x + window.width + margin, max_x),
            clamp(window.x, max_x),
            clamp(window.x + window.width - width, max_x),
        ))
        ys.update((
            clamp_y(window.y - height - margin),
            clamp_y(window.y + window.height + margin),
            clamp_y(window.y),
            clamp_y(window.y + window.height - height),
        ))

    def collision_cost(x: float, y: float) -> tuple[int, float]:
        count = 0
        area = 0.0
        for window in occupied:
            overlap_width = max(
                0.0,
                min(x + width, window.x + window.width + margin)
                - max(x, window.x - margin),
            )
            overlap_height = max(
                0.0,
                min(y + height, window.y + window.height + margin)
                - max(y, window.y - margin),
            )
            if overlap_width and overlap_height:
                count += 1
                area += overlap_width * overlap_height
        return count, area

    candidates = ((x, y) for x in xs for y in ys)
    x, y = min(
        candidates,
        key=lambda point: (
            *collision_cost(*point),
            abs(point[0] - requested_x) + abs(point[1] - requested_y),
            abs(point[1] - requested_y),
            point[1],
            point[0],
        ),
    )
    return x, y


def max_unoccupied_horizontal_width(
    viewport_width: float,
    occupied: tuple[WindowPlacement, ...] | list[WindowPlacement],
    *,
    margin: float = 8.0,
) -> float:
    """Return the widest horizontal strip clear of active windows and their margins."""
    if viewport_width <= 0:
        return 0.0

    intervals = sorted(
        (
            max(0.0, window.x - margin),
            min(viewport_width, window.x + window.width + margin),
        )
        for window in occupied
        if window.width > 0
    )
    widest_gap = 0.0
    right_edge = 0.0
    for left_edge, interval_right in intervals:
        widest_gap = max(widest_gap, left_edge - right_edge)
        right_edge = max(right_edge, interval_right)
    return max(widest_gap, viewport_width - right_edge)
