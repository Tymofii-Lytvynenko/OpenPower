from __future__ import annotations

from types import SimpleNamespace

import arcade

from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.renderers.unit_projection import ProjectedUnit
from src.shared.actions import ActionMoveUnit


def _unit(unit_id: str, screen_x: float, screen_y: float) -> ProjectedUnit:
    return ProjectedUnit(
        unit_id=unit_id,
        owner="AAA",
        unit_type="infantry",
        strength=100,
        current_region_id=1,
        target_region_id=0,
        screen_x=screen_x,
        screen_y=screen_y,
        distance_to_camera=0.0,
        width=20.0,
        height=12.0,
        movement_progress=0.0,
        is_moving=False,
    )


class _UnitRenderer:
    def __init__(self, units: list[ProjectedUnit]) -> None:
        self.billboards = units

    def get_unit_at(self, x: float, y: float) -> ProjectedUnit | None:
        return next((unit for unit in reversed(self.billboards) if unit.contains(x, y)), None)

    def get_unit(self, unit_id: str) -> ProjectedUnit | None:
        return next((unit for unit in self.billboards if unit.unit_id == unit_id), None)


class _MapRenderer:
    def __init__(self) -> None:
        self.target_region_id = 9

    def get_region_id_at_screen_pos(self, x: float, y: float) -> int:
        return self.target_region_id

    def get_geo_at_screen_pos(self, x: float, y: float) -> SimpleNamespace:
        return SimpleNamespace(latitude=12.5, longitude=-34.25)


class _NetworkClient:
    player_id = "player-1"

    def __init__(self) -> None:
        self.actions = []

    def send_action(self, action) -> None:
        self.actions.append(action)


def test_dragging_selected_unit_shows_preview_and_dispatches_move_action() -> None:
    renderer = _UnitRenderer([_unit("AAA-1", 50.0, 60.0)])
    map_renderer = _MapRenderer()
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, map_renderer, network)

    assert controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.on_mouse_drag(160.0, 180.0, arcade.MOUSE_BUTTON_LEFT)
    preview = controller.drag_preview
    assert preview is not None
    assert (preview.origin_x, preview.origin_y, preview.mouse_x, preview.mouse_y) == (
        50.0,
        60.0,
        160.0,
        180.0,
    )

    assert controller.on_mouse_release(160.0, 180.0, arcade.MOUSE_BUTTON_LEFT)

    assert network.actions == [
        ActionMoveUnit(
            player_id="player-1",
            unit_id="AAA-1",
            target_region_id=9,
            target_latitude=12.5,
            target_longitude=-34.25,
        )
    ]


def test_box_selection_moves_units_in_stable_id_order_and_ignores_invalid_targets() -> None:
    renderer = _UnitRenderer(
        [
            _unit("AAA-2", 40.0, 40.0),
            _unit("AAA-1", 50.0, 50.0),
            _unit("AAA-outside", 200.0, 200.0),
        ]
    )
    map_renderer = _MapRenderer()
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, map_renderer, network)

    assert controller.select_units_in_rect(0.0, 0.0, 100.0, 100.0)
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}
    assert controller.move_selected_units_to_screen_pos(300.0, 300.0)
    assert [action.unit_id for action in network.actions] == ["AAA-1", "AAA-2"]
    assert all(isinstance(action, ActionMoveUnit) for action in network.actions)

    network.actions.clear()
    map_renderer.target_region_id = 0
    assert not controller.move_selected_units_to_screen_pos(300.0, 300.0)
    assert network.actions == []
