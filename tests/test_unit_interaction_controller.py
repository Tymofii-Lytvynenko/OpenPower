from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import arcade

from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.renderers.unit_projection import ProjectedUnit
from src.client.views.game_view import GameView
from src.shared.actions import (
    ActionAttackUnit,
    ActionDispatchUnitDeployment,
    ActionMoveUnit,
    ActionSetUnitReadiness,
)


def _unit(unit_id: str, screen_x: float, screen_y: float, owner: str = "AAA") -> ProjectedUnit:
    return ProjectedUnit(
        unit_id=unit_id,
        owner=owner,
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


class _MapRendererWithoutGeo(_MapRenderer):
    def get_geo_at_screen_pos(self, x: float, y: float) -> None:
        return None


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


def test_shift_click_adds_units_and_plain_click_keeps_a_multiselection() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("AAA-2", 100.0, 110.0),
    ])
    controller = UnitInteractionController(renderer, _MapRenderer(), _NetworkClient())
    assert controller.select_unit_by_id("AAA-1")

    assert controller.on_mouse_press(100.0, 110.0, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_SHIFT)
    assert controller.on_mouse_release(100.0, 110.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}

    assert controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.on_mouse_release(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}
    assert controller.selected_unit_id == "AAA-1"


def test_control_click_toggles_a_selected_unit_off_after_click_release() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("AAA-2", 100.0, 110.0),
    ])
    controller = UnitInteractionController(renderer, _MapRenderer(), _NetworkClient())
    assert controller.select_units_in_rect(0.0, 0.0, 150.0, 150.0)
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}

    assert controller.on_mouse_press(100.0, 110.0, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_CTRL)
    assert controller.on_mouse_release(100.0, 110.0, arcade.MOUSE_BUTTON_LEFT)

    assert controller.selected_unit_ids == {"AAA-1"}
    assert controller.selected_unit_id == "AAA-1"


def test_shift_and_control_box_selection_union_and_toggle_existing_units() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 30.0, 30.0),
        _unit("AAA-2", 80.0, 80.0),
        _unit("AAA-3", 130.0, 130.0),
    ])
    controller = UnitInteractionController(renderer, _MapRenderer(), _NetworkClient())
    assert controller.select_unit_by_id("AAA-1")

    assert controller.select_units_in_rect(
        60.0, 60.0, 100.0, 100.0, modifiers=arcade.key.MOD_SHIFT
    )
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}
    assert controller.select_units_in_rect(
        60.0, 60.0, 150.0, 150.0, modifiers=arcade.key.MOD_CTRL
    )
    assert controller.selected_unit_ids == {"AAA-1", "AAA-3"}


def test_box_selection_excludes_visible_foreign_units_when_policy_is_supplied() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 40.0, 40.0),
        _unit("BBB-1", 80.0, 80.0, owner="BBB"),
    ])
    controller = UnitInteractionController(
        renderer,
        _MapRenderer(),
        _NetworkClient(),
        can_box_select_unit=lambda unit: unit.owner == "AAA",
    )

    assert controller.select_units_in_rect(0.0, 0.0, 120.0, 120.0)

    assert controller.selected_unit_ids == {"AAA-1"}


def test_move_targeting_keeps_mode_after_invalid_click_then_dispatches_move() -> None:
    renderer = _UnitRenderer([_unit("AAA-1", 50.0, 60.0)])
    map_renderer = _MapRenderer()
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, map_renderer, network)
    assert controller.select_unit_by_id("AAA-1")

    assert controller.begin_move_order_targeting()
    map_renderer.target_region_id = 0
    assert controller.resolve_order_target_click(200.0, 220.0)
    assert controller.pending_order_mode == "move"
    assert network.actions == []

    map_renderer.target_region_id = 9
    assert controller.resolve_order_target_click(200.0, 220.0)
    assert controller.pending_order_mode is None
    assert network.actions == [
        ActionMoveUnit(
            player_id="player-1",
            unit_id="AAA-1",
            target_region_id=9,
            target_latitude=12.5,
            target_longitude=-34.25,
        )
    ]


def test_attack_move_targeting_dispatches_move_to_clicked_map_destination() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("BBB-1", 120.0, 130.0, owner="BBB"),
    ])
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, _MapRenderer(), network)
    assert controller.select_unit_by_id("AAA-1")

    assert controller.begin_attack_move_targeting()
    assert controller.resolve_order_target_click(120.0, 130.0)

    assert controller.pending_order_mode is None
    assert network.actions == [
        ActionMoveUnit(
            player_id="player-1",
            unit_id="AAA-1",
            target_region_id=9,
            target_latitude=12.5,
            target_longitude=-34.25,
        )
    ]


def test_direct_attack_command_still_targets_a_specific_hostile_unit() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("BBB-1", 120.0, 130.0, owner="BBB"),
    ])
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, _MapRenderer(), network)
    assert controller.select_unit_by_id("AAA-1")

    assert controller.attack_selected_units("BBB-1")

    assert network.actions == [
        ActionAttackUnit(
            player_id="player-1",
            attacker_unit_id="AAA-1",
            defender_unit_id="BBB-1",
        )
    ]


def test_attack_move_targeting_keeps_mode_when_map_destination_is_invalid() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("AAA-2", 120.0, 130.0),
    ])
    network = _NetworkClient()
    map_renderer = _MapRenderer()
    controller = UnitInteractionController(renderer, map_renderer, network)
    assert controller.select_unit_by_id("AAA-1")

    assert controller.begin_attack_move_targeting()
    map_renderer.target_region_id = 0
    assert controller.resolve_order_target_click(120.0, 130.0)

    assert controller.pending_order_mode == "attack_move"
    assert network.actions == []
    assert controller.cancel_order_targeting()
    assert controller.pending_order_mode is None


def test_escape_cancels_pending_order_targeting_in_game_view() -> None:
    controller = UnitInteractionController(
        _UnitRenderer([_unit("AAA-1", 50.0, 60.0)]),
        _MapRenderer(),
        _NetworkClient(),
    )
    assert controller.select_unit_by_id("AAA-1")
    assert controller.begin_move_order_targeting()
    view = GameView.__new__(GameView)
    view.unit_interactions = controller

    view.on_game_key_press(arcade.key.ESCAPE, 0)

    assert controller.pending_order_mode is None


def test_right_click_cancels_pending_order_targeting_in_game_view() -> None:
    controller = UnitInteractionController(
        _UnitRenderer([_unit("AAA-1", 50.0, 60.0)]),
        _MapRenderer(),
        _NetworkClient(),
    )
    assert controller.select_unit_by_id("AAA-1")
    assert controller.begin_attack_move_targeting()
    view = GameView.__new__(GameView)
    view.unit_interactions = controller

    view.on_game_mouse_press(200.0, 220.0, arcade.MOUSE_BUTTON_RIGHT, 0)

    assert controller.pending_order_mode is None
    assert view._right_drag_start_pos is None


def test_reserve_deployment_drag_dispatches_only_for_a_valid_map_drop() -> None:
    for region_id, drop_over_ui, expected_count in (
        (9, False, 2),
        (0, False, 0),
        (9, True, 0),
    ):
        with patch.object(GameView, "imgui", new_callable=PropertyMock) as imgui_property:
            imgui_property.return_value = SimpleNamespace(on_mouse_release=lambda *_args: None)
            view = GameView.__new__(GameView)
            network = _NetworkClient()
            map_renderer = _MapRenderer()
            map_renderer.target_region_id = region_id
            view.net = network
            view.renderer = map_renderer
            view._deployment_drop_over_ui = drop_over_ui
            view._deployment_drag_unit_ids = ()

            view._start_deployment_drag(["AAA-1", "AAA-2", "AAA-1"])
            view.on_mouse_release(200.0, 220.0, arcade.MOUSE_BUTTON_LEFT, 0)

            assert len(network.actions) == expected_count
            assert network.actions == [
                ActionDispatchUnitDeployment(
                    player_id="player-1",
                    unit_id=unit_id,
                    destination_region_id=region_id,
                    quantity=0,
                )
                for unit_id in ("AAA-1", "AAA-2")[:expected_count]
            ]
            assert view._deployment_drag_unit_ids == ()


def test_order_targeting_and_move_callback_handle_empty_and_rejected_requests() -> None:
    unit = _unit("AAA-1", 50.0, 60.0)
    renderer = _UnitRenderer([unit])
    network = _NetworkClient()
    requests = []
    outcomes = iter((False, True))
    map_renderer = _MapRenderer()
    controller = UnitInteractionController(
        renderer,
        map_renderer,
        network,
        on_move_requested=lambda *args: (requests.append(args), next(outcomes))[1],
    )

    assert controller.drag_preview is None
    assert not controller.has_selection()
    assert not controller.begin_move_order_targeting()
    assert not controller.begin_attack_move_targeting()
    assert not controller.cancel_order_targeting()
    assert not controller.resolve_order_target_click(100.0, 100.0)
    assert controller.get_unit_at(50.0, 60.0) is unit
    assert controller.get_unit_by_id("AAA-1") is unit
    assert not controller.select_unit_by_id("missing")
    assert not controller.move_selected_units_to_screen_pos(100.0, 100.0)

    assert controller.select_unit_by_id("AAA-1")
    assert controller.has_selection()
    assert not controller.move_selected_units_to_screen_pos(100.0, 100.0)
    assert controller.move_selected_units_to_screen_pos(100.0, 100.0)
    assert len(requests) == 2
    assert network.actions == []


def test_hover_and_mouse_events_ignore_invalid_buttons_and_empty_space() -> None:
    controller = UnitInteractionController(
        _UnitRenderer([_unit("AAA-1", 50.0, 60.0)]),
        _MapRenderer(),
        _NetworkClient(),
    )

    assert controller.drag_preview is None
    assert not controller.on_mouse_drag(80.0, 90.0, 0)
    assert not controller.on_mouse_release(80.0, 90.0, arcade.MOUSE_BUTTON_LEFT)
    assert not controller.on_mouse_release(80.0, 90.0, arcade.MOUSE_BUTTON_RIGHT)
    controller.on_mouse_motion(50.0, 60.0)
    assert controller.hovered_unit_id == "AAA-1"
    assert not controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_RIGHT)
    assert not controller.on_mouse_press(500.0, 500.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.hovered_unit_id is None

    assert controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
    controller.on_mouse_motion(100.0, 110.0)
    assert controller.hovered_unit_id == "AAA-1"
    assert not controller.on_mouse_drag(100.0, 110.0, arcade.MOUSE_BUTTON_RIGHT)
    assert not controller.on_mouse_release(100.0, 110.0, arcade.MOUSE_BUTTON_RIGHT)
    assert controller.on_mouse_release(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)


def test_double_click_invokes_the_optional_unit_callback() -> None:
    callbacks = []
    controller = UnitInteractionController(
        _UnitRenderer([_unit("AAA-1", 50.0, 60.0)]),
        _MapRenderer(),
        _NetworkClient(),
        on_unit_double_click=callbacks.append,
    )

    with patch(
        "src.client.controllers.unit_interaction_controller.perf_counter",
        side_effect=(1.0, 1.1),
    ):
        for _ in range(2):
            assert controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
            assert controller.on_mouse_release(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)

    assert callbacks == ["AAA-1"]


def test_focus_and_box_selection_handle_missing_units_and_empty_results() -> None:
    first = _unit("AAA-1", 40.0, 40.0)
    second = _unit("AAA-2", 80.0, 80.0)
    renderer = _UnitRenderer([first, second])
    controller = UnitInteractionController(renderer, _MapRenderer(), _NetworkClient())

    assert not controller.focus_context_unit("missing")
    assert controller.select_units_in_rect(20.0, 20.0, 100.0, 100.0)
    assert controller.focus_context_unit("AAA-2")
    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}
    renderer.billboards = [first]
    assert not controller.focus_context_unit("AAA-2")
    assert controller.focus_context_unit("AAA-1")

    controller.selected_unit_id = "AAA-2"
    assert controller.select_units_in_rect(35.0, 35.0, 45.0, 45.0)
    assert controller.selected_unit_ids == {"AAA-1"}
    assert controller.selected_unit_id == "AAA-1"
    renderer.billboards = []
    assert not controller.select_units_in_rect(0.0, 0.0, 100.0, 100.0)
    assert not controller.has_selection()


def test_attack_readiness_and_invalid_drag_drop_paths() -> None:
    units = [_unit("AAA-1", 50.0, 60.0), _unit("AAA-2", 100.0, 110.0)]
    network = _NetworkClient()
    controller = UnitInteractionController(_UnitRenderer(units), _MapRenderer(), network)

    assert not controller.attack_selected_units("missing")
    assert controller.select_unit_by_id("AAA-1")
    assert not controller.attack_selected_units("AAA-2")
    controller.clear_selection()
    assert not controller.set_selected_units_readiness("fortified")
    controller.selected_unit_ids = {"AAA-2", "AAA-1"}
    assert controller.set_selected_units_readiness("fortified")
    assert network.actions == [
        ActionSetUnitReadiness(
            player_id="player-1", unit_id=unit_id, target_status="fortified"
        )
        for unit_id in ("AAA-1", "AAA-2")
    ]

    for map_renderer in (_MapRenderer(), _MapRendererWithoutGeo()):
        if isinstance(map_renderer, _MapRendererWithoutGeo):
            map_renderer.target_region_id = 9
        else:
            map_renderer.target_region_id = 0
        drop_controller = UnitInteractionController(
            _UnitRenderer([_unit("AAA-1", 50.0, 60.0)]),
            map_renderer,
            _NetworkClient(),
        )
        if isinstance(map_renderer, _MapRendererWithoutGeo):
            assert drop_controller.select_unit_by_id("AAA-1")
            assert not drop_controller.move_selected_units_to_screen_pos(100.0, 100.0)
        assert drop_controller.on_mouse_press(50.0, 60.0, arcade.MOUSE_BUTTON_LEFT)
        assert drop_controller.on_mouse_release(100.0, 100.0, arcade.MOUSE_BUTTON_LEFT)


def test_dragging_cancels_a_pending_control_deselect_and_moves_the_selection() -> None:
    renderer = _UnitRenderer([
        _unit("AAA-1", 50.0, 60.0),
        _unit("AAA-2", 100.0, 110.0),
    ])
    network = _NetworkClient()
    controller = UnitInteractionController(renderer, _MapRenderer(), network)
    assert controller.select_units_in_rect(0.0, 0.0, 150.0, 150.0)

    assert controller.on_mouse_press(
        100.0, 110.0, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_CTRL
    )
    assert controller.on_mouse_drag(160.0, 180.0, arcade.MOUSE_BUTTON_LEFT)
    assert controller.on_mouse_release(160.0, 180.0, arcade.MOUSE_BUTTON_LEFT)

    assert controller.selected_unit_ids == {"AAA-1", "AAA-2"}
    assert [action.unit_id for action in network.actions] == ["AAA-1", "AAA-2"]
