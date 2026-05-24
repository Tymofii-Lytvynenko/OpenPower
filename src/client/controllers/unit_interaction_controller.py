from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Optional

import arcade

from src.client.renderers.map_renderer import MapRenderer
from src.client.renderers.unit_projection import ProjectedUnit
from src.client.renderers.unit_renderer import UnitDragPreview, UnitRenderer
from src.client.services.network_client_service import NetworkClient
from src.shared.actions import ActionMoveUnit


class UnitInteractionController:
    """Handles unit hover, selection, and drag-to-move input."""

    def __init__(
        self,
        unit_renderer: UnitRenderer,
        map_renderer: MapRenderer,
        net_client: NetworkClient,
        on_unit_double_click: Callable[[str], None] | None = None,
    ):
        self._unit_renderer = unit_renderer
        self._map_renderer = map_renderer
        self._net = net_client
        self._on_unit_double_click = on_unit_double_click

        self.selected_unit_id: Optional[str] = None
        self.hovered_unit_id: Optional[str] = None

        self._dragging_unit: Optional[ProjectedUnit] = None
        self._press_x = 0.0
        self._press_y = 0.0
        self._mouse_x = 0.0
        self._mouse_y = 0.0
        self._drag_threshold = 6.0
        self._double_click_interval_seconds = 0.35
        self._double_click_distance = 9.0
        self._last_click_unit_id: Optional[str] = None
        self._last_click_time = 0.0
        self._last_click_x = 0.0
        self._last_click_y = 0.0

    @property
    def drag_preview(self) -> Optional[UnitDragPreview]:
        if self._dragging_unit is None:
            return None

        return UnitDragPreview(
            unit_id=self._dragging_unit.unit_id,
            owner=self._dragging_unit.owner,
            origin_x=self._dragging_unit.screen_x,
            origin_y=self._dragging_unit.screen_y,
            mouse_x=self._mouse_x,
            mouse_y=self._mouse_y,
        )

    def on_mouse_motion(self, x: float, y: float) -> None:
        self._mouse_x = x
        self._mouse_y = y
        if self._dragging_unit is not None:
            return

        unit = self._unit_renderer.get_unit_at(x, y)
        self.hovered_unit_id = unit.unit_id if unit else None

    def on_mouse_press(self, x: float, y: float, button: int) -> bool:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return False

        unit = self._unit_renderer.get_unit_at(x, y)
        if unit is None:
            self.hovered_unit_id = None
            return False

        self.selected_unit_id = unit.unit_id
        self.hovered_unit_id = unit.unit_id
        self._dragging_unit = unit
        self._press_x = x
        self._press_y = y
        self._mouse_x = x
        self._mouse_y = y
        return True

    def on_mouse_drag(self, x: float, y: float, button_mask: int) -> bool:
        if self._dragging_unit is None or not (button_mask & arcade.MOUSE_BUTTON_LEFT):
            return False

        self._mouse_x = x
        self._mouse_y = y
        return True

    def on_mouse_release(self, x: float, y: float, button: int) -> bool:
        if button != arcade.MOUSE_BUTTON_LEFT or self._dragging_unit is None:
            return False

        drag_distance_sq = (x - self._press_x) ** 2 + (y - self._press_y) ** 2
        dragged_far_enough = drag_distance_sq >= self._drag_threshold * self._drag_threshold
        unit = self._dragging_unit
        self._dragging_unit = None
        self._mouse_x = x
        self._mouse_y = y

        if not dragged_far_enough:
            self._handle_click(unit, x, y)
            return True

        self._last_click_unit_id = None
        self._last_click_time = 0.0

        target_region_id = self._map_renderer.get_region_id_at_screen_pos(x, y)
        if target_region_id <= 0:
            return True

        target_geo = self._map_renderer.get_geo_at_screen_pos(x, y)
        if target_geo is None:
            return True

        self._net.send_action(
            ActionMoveUnit(
                player_id=self._net.player_id,
                unit_id=unit.unit_id,
                target_region_id=target_region_id,
                target_latitude=target_geo.latitude,
                target_longitude=target_geo.longitude,
            )
        )
        return True

    def _handle_click(self, unit: ProjectedUnit, x: float, y: float) -> None:
        now = perf_counter()
        distance_sq = (x - self._last_click_x) ** 2 + (y - self._last_click_y) ** 2
        same_spot = distance_sq <= self._double_click_distance * self._double_click_distance
        same_unit = self._last_click_unit_id == unit.unit_id
        within_interval = (now - self._last_click_time) <= self._double_click_interval_seconds

        if same_unit and same_spot and within_interval:
            self._last_click_unit_id = None
            self._last_click_time = 0.0
            if self._on_unit_double_click is not None:
                self._on_unit_double_click(unit.unit_id)
            return

        self._last_click_unit_id = unit.unit_id
        self._last_click_time = now
        self._last_click_x = x
        self._last_click_y = y
