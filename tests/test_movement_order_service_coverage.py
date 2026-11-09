from types import SimpleNamespace
from unittest.mock import Mock

from modules.base.systems.military.movement_order_service import MilitaryMoveOrderService


def _route(*, region_ids=(1, 2), target_region_id=2):
    return SimpleNamespace(
        action=object(),
        unit_id="unit-1",
        owner="USA",
        deployment_dispatch=False,
        target_region_id=target_region_id,
        target_geo=SimpleNamespace(latitude=1.0, longitude=2.0),
        route_plan=SimpleNamespace(region_ids=list(region_ids)),
    )


def test_process_unit_stops_when_the_next_route_leg_has_no_coordinates():
    service = object.__new__(MilitaryMoveOrderService)
    route = _route()
    service._plan_movement = Mock(return_value=route)
    service._complete_deployment_arrival = Mock(return_value=False)
    service._handle_local_move = Mock(return_value=False)
    service._next_leg = Mock(return_value=None)
    service._prepare_order_for_departure = Mock()
    service._start_route = Mock()
    context = SimpleNamespace(
        action_by_unit={"unit-1": object()},
        result_rows=[],
    )

    service._process_unit(context, {"id": "unit-1"})

    assert context.result_rows == []
    service._prepare_order_for_departure.assert_not_called()
    service._start_route.assert_not_called()


def test_process_unit_escalates_positional_contact_after_route_validation():
    service = object.__new__(MilitaryMoveOrderService)
    route = _route()
    service._plan_movement = Mock(return_value=route)
    service._complete_deployment_arrival = Mock(return_value=False)
    service._handle_local_move = Mock(return_value=False)
    service._next_leg = Mock(return_value=([1, 2], 2, route.target_geo))
    service._prepare_order_for_departure = Mock(return_value=True)
    service._record = Mock()
    service._start_route = Mock()
    context = SimpleNamespace(
        action_by_unit={"unit-1": object()},
        result_rows=[],
        current_minute=10,
    )
    unit = {"id": "unit-1", "engagement_mode": "positional"}

    service._process_unit(context, unit)

    assert unit["engagement_mode"] == "assault"
    assert context.result_rows == [unit]
    service._record.assert_called_once_with(
        context,
        route,
        "move",
        "accepted",
        "The unit escalated its existing contact instead of leaving the battle.",
    )
    service._start_route.assert_not_called()


def test_plan_movement_rejects_missing_destination_coordinates():
    service = object.__new__(MilitaryMoveOrderService)
    service._movement_order_policy = SimpleNamespace(
        source_geo_for_order=lambda *_args: SimpleNamespace(latitude=0.0, longitude=0.0),
        resolve_target_geo=lambda *_args: None,
    )
    service._reject = Mock()
    context = SimpleNamespace(
        region_by_id={2: {"id": 2}},
        region_locations={},
    )
    unit = {"id": "unit-1", "owner": "USA", "current_region_id": 1}
    action = SimpleNamespace(target_region_id=2)

    assert service._plan_movement(context, unit, action) is None
    service._reject.assert_called_once_with(
        context,
        unit,
        "move",
        "The destination has no valid geographic location.",
    )


def test_plan_movement_rejects_invalid_naval_landing():
    service = object.__new__(MilitaryMoveOrderService)
    service._movement_order_policy = SimpleNamespace(
        source_geo_for_order=lambda *_args: SimpleNamespace(latitude=0.0, longitude=0.0),
        resolve_target_geo=lambda *_args: SimpleNamespace(latitude=1.0, longitude=2.0),
    )
    service._naval_invasion_policy = SimpleNamespace(
        validate=Mock(return_value=(False, "Landing zone is unavailable."))
    )
    service._reject = Mock()
    context = SimpleNamespace(
        region_by_id={2: {"id": 2}},
        region_locations={},
        state=object(),
        input_unit_rows=[],
    )
    unit = {"id": "unit-1", "owner": "USA", "current_region_id": 1}
    action = SimpleNamespace(target_region_id=2, is_naval_invasion=True)

    assert service._plan_movement(context, unit, action) is None
    service._naval_invasion_policy.validate.assert_called_once()
    service._reject.assert_called_once_with(
        context, unit, "naval_invasion", "Landing zone is unavailable."
    )


def test_plan_movement_reports_blocked_domain_from_route_planner():
    class RoutePlanner:
        def plan(self, *_args, **_kwargs):
            can_enter = _args[4]
            assert not can_enter({"id": 7}, True)
            return SimpleNamespace(is_valid=False, rejection_reason="No valid route.")

    movement_policy = SimpleNamespace(
        source_geo_for_order=lambda *_args: SimpleNamespace(latitude=0.0, longitude=0.0),
        resolve_target_geo=lambda *_args: SimpleNamespace(latitude=1.0, longitude=2.0),
        domain_for_unit=lambda _unit: "land",
        route_segment_cost_for_unit=lambda *_args: 1.0,
        domain_route_compatible=lambda *_args, **_kwargs: (False, "incompatible"),
    )
    service = object.__new__(MilitaryMoveOrderService)
    service._movement_order_policy = movement_policy
    service._access_policy = SimpleNamespace(for_country=lambda *_args: object())
    service._route_planner = RoutePlanner()
    service._reject = Mock()
    context = SimpleNamespace(
        region_by_id={2: {"id": 2}},
        region_locations={1: SimpleNamespace(latitude=0.0, longitude=0.0)},
        state=object(),
        capability_speed_by_unit={},
        prepared_graph=SimpleNamespace(edge_distance_km={}),
        adjacency=None,
        has_domain_metadata=True,
    )
    unit = {"id": "unit-1", "owner": "USA", "current_region_id": 1}
    action = SimpleNamespace(
        target_region_id=2,
        is_naval_invasion=False,
        via_region_ids=[],
    )

    assert service._plan_movement(context, unit, action) is None
    service._reject.assert_called_once_with(
        context,
        unit,
        "move",
        "The route contains a region incompatible with the land domain (region 7).",
    )


def test_local_move_records_arrival_and_preserves_failed_positional_order():
    service = object.__new__(MilitaryMoveOrderService)
    route = _route(region_ids=(1,))
    context = SimpleNamespace(result_rows=[])
    service._record = Mock()

    assert service._handle_local_move(context, {"id": "unit-1"}, route)
    service._record.assert_called_once_with(
        context,
        route,
        "move",
        "arrived",
        "The unit is already at the destination.",
    )
    assert context.result_rows == [{"id": "unit-1"}]

    positional_context = SimpleNamespace(result_rows=[])
    service._prepare_order_for_departure = Mock(return_value=False)
    assert service._handle_local_move(
        positional_context,
        {"id": "unit-2", "engagement_mode": "positional"},
        route,
    )
    assert positional_context.result_rows == []
    service._prepare_order_for_departure.assert_called_once()


def test_next_leg_rejects_intermediate_region_without_coordinates():
    service = object.__new__(MilitaryMoveOrderService)
    service._reject = Mock()
    context = SimpleNamespace(region_locations={})
    unit = {"id": "unit-1"}
    route = _route(region_ids=(1, 7, 2), target_region_id=2)

    assert service._next_leg(context, unit, route) is None
    service._reject.assert_called_once_with(
        context,
        unit,
        "move",
        "The route contains a region without valid coordinates.",
    )
