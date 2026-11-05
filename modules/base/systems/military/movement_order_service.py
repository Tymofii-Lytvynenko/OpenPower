"""Apply player and system-issued movement commands to military units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

import polars as pl

from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.movement_constants import NO_TARGET_REGION
from modules.base.systems.military.movement_order_policy import MilitaryMovementOrderPolicy
from modules.base.systems.military.naval_invasion_policy import NavalInvasionPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner, RegionRouteGraph, RoutePlan
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionMoveUnit
from src.shared.state import GameState


class _ReadinessPreparer(Protocol):
    def prepare_order(self, state: GameState, unit_id: str) -> bool: ...


class _UnitOrderWorkflow(Protocol):
    def release_fortified_for_order(self, state: GameState, unit: dict[str, Any]) -> bool: ...

    def queue_move(self, state: GameState, action: ActionMoveUnit) -> str: ...

    def record_feedback(
        self,
        rows: list[dict[str, Any]],
        unit_id: str,
        owner: str,
        order_type: str,
        status: str,
        reason: str,
        current_minute: int,
    ) -> None: ...

    def write_feedback(self, state: GameState, rows: list[dict[str, Any]]) -> None: ...


@dataclass
class _MovementOrderContext:
    state: GameState
    action_by_unit: dict[str, ActionMoveUnit]
    input_unit_rows: list[dict[str, Any]]
    result_rows: list[dict[str, Any]]
    current_minute: int
    region_locations: dict[int, GeoCoordinate]
    adjacency: pl.DataFrame | None
    prepared_graph: RegionRouteGraph
    region_by_id: dict[int, dict[str, Any]]
    route_table: pl.DataFrame | None
    route_rows: list[dict[str, Any]]
    route_by_unit: dict[str, dict[str, Any]]
    feedback_rows: list[dict[str, Any]]
    has_domain_metadata: bool
    capability_speed_by_unit: dict[str, float]


@dataclass(frozen=True)
class _PlannedMovement:
    action: ActionMoveUnit
    unit_id: str
    owner: str
    deployment_dispatch: bool
    source_region_id: int
    source_geo: GeoCoordinate
    target_region_id: int
    target_geo: GeoCoordinate
    unit_domain: str
    route_plan: RoutePlan
    segment_duration: Callable[[dict[str, Any], dict[str, Any]], int]


class MilitaryMoveOrderService:
    """Validate route requests and apply their movement and feedback changes."""

    def __init__(
        self,
        route_planner: MilitaryRoutePlanner,
        access_policy: MovementAccessPolicy,
        naval_invasion_policy: NavalInvasionPolicy,
        movement_order_policy: MilitaryMovementOrderPolicy,
        readiness_preparer: _ReadinessPreparer,
        unit_order_workflow: _UnitOrderWorkflow,
        units_from_rows: Callable[[list[dict[str, Any]]], pl.DataFrame],
        route_schema: dict[str, pl.DataType],
    ) -> None:
        self._route_planner = route_planner
        self._access_policy = access_policy
        self._naval_invasion_policy = naval_invasion_policy
        self._movement_order_policy = movement_order_policy
        self._readiness_preparer = readiness_preparer
        self._unit_order_workflow = unit_order_workflow
        self._units_from_rows = units_from_rows
        self._route_schema = route_schema

    def process(
        self,
        state: GameState,
        units: pl.DataFrame,
        additional_actions: Iterable[ActionMoveUnit] = (),
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> pl.DataFrame:
        actions = [action for action in state.current_actions if isinstance(action, ActionMoveUnit)]
        actions.extend(additional_actions)
        if not actions or units.is_empty() or "regions" not in state.tables:
            return units

        action_by_unit = {action.unit_id: action for action in actions}
        if not action_by_unit:
            return units

        context = self._build_context(state, units, action_by_unit, capability_speed_by_unit)
        for row in units.to_dicts():
            self._process_unit(context, row)
        self._publish_results(context)
        return self._units_from_rows(context.result_rows)

    def _build_context(
        self,
        state: GameState,
        units: pl.DataFrame,
        action_by_unit: dict[str, ActionMoveUnit],
        capability_speed_by_unit: dict[str, float] | None,
    ) -> _MovementOrderContext:
        regions = state.get_table("regions")
        region_locations = self._movement_order_policy.region_locations(regions)
        adjacency = state.tables.get("region_adjacency")
        prepared_graph = self._route_planner.prepare(regions, adjacency)
        route_table = state.tables.get("unit_movement_routes")
        route_rows = [] if route_table is None else route_table.to_dicts()
        feedback_table = state.tables.get("unit_order_feedback")
        feedback_rows = [] if feedback_table is None else feedback_table.to_dicts()
        region_by_id = prepared_graph.region_by_id
        return _MovementOrderContext(
            state=state,
            action_by_unit=action_by_unit,
            input_unit_rows=units.to_dicts(),
            result_rows=[],
            current_minute=int(state.time.total_minutes),
            region_locations=region_locations,
            adjacency=adjacency,
            prepared_graph=prepared_graph,
            region_by_id=region_by_id,
            route_table=route_table,
            route_rows=route_rows,
            route_by_unit={str(row.get("unit_id") or ""): row for row in route_rows},
            feedback_rows=feedback_rows,
            has_domain_metadata=self._movement_order_policy.has_domain_metadata(
                region_by_id.values()
            ),
            capability_speed_by_unit=capability_speed_by_unit or {},
        )

    def _process_unit(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
    ) -> None:
        action = context.action_by_unit.get(str(unit["id"]))
        if action is None:
            context.result_rows.append(unit)
            return

        route = self._plan_movement(context, unit, action)
        if route is None:
            return
        if self._complete_deployment_arrival(context, unit, route):
            return
        if self._handle_local_move(context, unit, route):
            return

        next_leg = self._next_leg(context, unit, route)
        if next_leg is None:
            return
        if not self._prepare_order_for_departure(context, unit, route):
            return
        if str(unit.get("engagement_mode") or "").lower() == "positional":
            unit["engagement_mode"] = "assault"
            self._record(context, route, "move", "accepted", "The unit escalated its existing contact instead of leaving the battle.")
            context.result_rows.append(unit)
            return
        self._start_route(context, unit, route, *next_leg)

    def _plan_movement(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        action: ActionMoveUnit,
    ) -> _PlannedMovement | None:
        unit_id = str(unit.get("id") or "")
        owner = str(unit.get("owner") or "").strip().upper()
        deployment_dispatch = str(unit.get("unit_lifecycle") or "") in {
            "deployment_queued",
            "deployment_blocked",
        }
        source_region_id = (
            int(unit.get("source_region_id") or 0)
            if deployment_dispatch
            else int(unit["current_region_id"])
        )
        target_region_id = int(action.target_region_id)
        target_region = context.region_by_id.get(target_region_id)
        if target_region is None:
            self._reject(context, unit, "move", "The destination region is invalid.")
            return None

        source_geo = self._movement_order_policy.source_geo_for_order(
            unit,
            deployment_dispatch,
        )
        target_geo = self._movement_order_policy.resolve_target_geo(
            action,
            target_region_id,
            context.region_locations,
        )
        if target_geo is None:
            self._reject(
                context,
                unit,
                "move",
                "The destination has no valid geographic location.",
            )
            return None

        if action.is_naval_invasion:
            valid_landing, landing_reason = self._naval_invasion_policy.validate(
                context.state,
                unit,
                target_region,
                context.input_unit_rows,
                (source_geo.latitude, source_geo.longitude),
            )
            if not valid_landing:
                self._reject(context, unit, "naval_invasion", landing_reason)
                return None

        unit_domain = self._movement_order_policy.domain_for_unit(unit)
        access_context = self._access_policy.for_country(context.state, owner)
        segment_duration = self._movement_order_policy.route_segment_cost_for_unit(
            context.region_locations,
            unit,
            context.state,
            context.capability_speed_by_unit.get(unit_id, 1.0),
            context.prepared_graph.edge_distance_km,
        )
        blocked_domains: list[int] = []

        def can_enter(region: dict[str, Any], final: bool) -> bool:
            domain_allowed, _ = self._movement_order_policy.domain_route_compatible(
                unit_domain,
                region,
                final,
                action.is_naval_invasion,
                context.region_by_id.values(),
                metadata_available=context.has_domain_metadata,
            )
            if not domain_allowed:
                blocked_domains.append(int(region.get("id") or 0))
                return False
            return access_context.can_station(region) if final else access_context.can_transit(region)

        route_plan = self._route_planner.plan(
            source_region_id,
            target_region_id,
            context.region_by_id.values(),
            context.adjacency,
            can_enter,
            segment_cost=segment_duration,
            explicit_waypoints=action.via_region_ids if action.via_region_ids else None,
            prepared_graph=context.prepared_graph,
        )
        if not route_plan.is_valid:
            reason = route_plan.rejection_reason
            if blocked_domains:
                reason = (
                    f"The route contains a region incompatible with the {unit_domain} domain "
                    f"(region {min(blocked_domains)})."
                )
            self._reject(context, unit, "move", reason)
            return None
        return _PlannedMovement(
            action=action,
            unit_id=unit_id,
            owner=owner,
            deployment_dispatch=deployment_dispatch,
            source_region_id=source_region_id,
            source_geo=source_geo,
            target_region_id=target_region_id,
            target_geo=target_geo,
            unit_domain=unit_domain,
            route_plan=route_plan,
            segment_duration=segment_duration,
        )

    def _complete_deployment_arrival(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        route: _PlannedMovement,
    ) -> bool:
        if not route.deployment_dispatch or len(route.route_plan.region_ids) >= 2:
            return False
        unit.update(
            current_region_id=route.target_region_id,
            latitude=route.target_geo.latitude,
            longitude=route.target_geo.longitude,
            source_region_id=route.target_region_id,
            source_latitude=route.target_geo.latitude,
            source_longitude=route.target_geo.longitude,
            target_region_id=NO_TARGET_REGION,
            target_latitude=route.target_geo.latitude,
            target_longitude=route.target_geo.longitude,
            unit_lifecycle="available",
            is_moving=False,
            movement_progress=0.0,
        )
        context.route_by_unit[route.unit_id] = {
            "unit_id": route.unit_id,
            "owner_country_id": route.owner,
            "source_region_id": route.source_region_id,
            "destination_region_id": route.target_region_id,
            "route_region_ids": list(route.route_plan.region_ids),
            "route_index": 0,
            "destination_latitude": route.target_geo.latitude,
            "destination_longitude": route.target_geo.longitude,
            "has_custom_destination": False,
            "is_naval_invasion": False,
            "status": "arrived",
            "rejection_reason": "",
            "updated_at_minute": context.current_minute,
        }
        self._record(
            context,
            route,
            "deployment",
            "arrived",
            "Deployment origin already matches the destination.",
        )
        context.result_rows.append(unit)
        return True

    def _handle_local_move(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        route: _PlannedMovement,
    ) -> bool:
        if len(route.route_plan.region_ids) >= 2:
            return False
        if str(unit.get("engagement_mode") or "").lower() == "positional":
            if not self._prepare_order_for_departure(context, unit, route):
                return True
            unit["engagement_mode"] = "assault"
            self._record(
                context,
                route,
                "move",
                "accepted",
                "The unit escalated its existing contact instead of leaving the battle.",
            )
        else:
            self._record(
                context,
                route,
                "move",
                "arrived",
                "The unit is already at the destination.",
            )
        context.result_rows.append(unit)
        return True

    def _next_leg(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        route: _PlannedMovement,
    ) -> tuple[list[int], int, GeoCoordinate] | None:
        path = list(route.route_plan.region_ids)
        next_region_id = path[1]
        next_geo = (
            route.target_geo
            if next_region_id == route.target_region_id
            else context.region_locations.get(next_region_id)
        )
        if next_geo is None:
            self._reject(
                context,
                unit,
                "move",
                "The route contains a region without valid coordinates.",
            )
            return None
        return path, next_region_id, next_geo

    def _prepare_order_for_departure(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        route: _PlannedMovement,
    ) -> bool:
        # Keep fortified units unchanged until every route check has succeeded.
        released_fortification = (
            False
            if route.deployment_dispatch
            else self._unit_order_workflow.release_fortified_for_order(
                context.state,
                unit,
            )
        )
        can_execute = (
            route.deployment_dispatch
            or released_fortification
            or self._readiness_preparer.prepare_order(context.state, route.unit_id)
        )
        if not can_execute:
            self._unit_order_workflow.queue_move(context.state, route.action)
            self._record(
                context,
                route,
                "move",
                "queued",
                "The move will begin when the readiness transition completes.",
            )
            context.result_rows.append(unit)
            return False
        if not route.deployment_dispatch:
            unit["readiness_status"] = "ready"
            unit["readiness_progress"] = 0.0
            unit["readiness_transition_id"] = ""
            unit["readiness_eta_minute"] = 0
        return True

    def _start_route(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        route: _PlannedMovement,
        path: list[int],
        next_region_id: int,
        next_geo: GeoCoordinate,
    ) -> None:
        duration = route.segment_duration(
            context.region_by_id[route.source_region_id],
            context.region_by_id[next_region_id],
        )
        unit["source_region_id"] = route.source_region_id
        unit["source_latitude"] = route.source_geo.latitude
        unit["source_longitude"] = route.source_geo.longitude
        unit["target_region_id"] = next_region_id
        unit["target_latitude"] = next_geo.latitude
        unit["target_longitude"] = next_geo.longitude
        unit["departed_at_minute"] = context.current_minute
        unit["arrival_at_minute"] = context.current_minute + duration
        unit["movement_progress"] = 0.0
        unit["is_moving"] = True
        if route.deployment_dispatch:
            unit["unit_lifecycle"] = "deployment_transit"
        context.route_by_unit[route.unit_id] = {
            "unit_id": route.unit_id,
            "owner_country_id": route.owner,
            "source_region_id": route.source_region_id,
            "destination_region_id": route.target_region_id,
            "route_region_ids": path,
            "route_index": 1,
            "destination_latitude": route.target_geo.latitude,
            "destination_longitude": route.target_geo.longitude,
            "has_custom_destination": (
                route.action.target_latitude is not None
                and route.action.target_longitude is not None
            ),
            "is_naval_invasion": bool(route.action.is_naval_invasion),
            "status": "in_transit",
            "rejection_reason": "",
            "updated_at_minute": context.current_minute,
        }
        self._record(context, route, "move", "accepted", "Route accepted.")
        context.result_rows.append(unit)

    def _reject(
        self,
        context: _MovementOrderContext,
        unit: dict[str, Any],
        order_type: str,
        reason: str,
    ) -> None:
        self._unit_order_workflow.record_feedback(
            context.feedback_rows,
            str(unit.get("id") or ""),
            str(unit.get("owner") or "").strip().upper(),
            order_type,
            "rejected",
            reason,
            context.current_minute,
        )
        context.result_rows.append(unit)

    def _record(
        self,
        context: _MovementOrderContext,
        route: _PlannedMovement,
        order_type: str,
        status: str,
        reason: str,
    ) -> None:
        self._unit_order_workflow.record_feedback(
            context.feedback_rows,
            route.unit_id,
            route.owner,
            order_type,
            status,
            reason,
            context.current_minute,
        )

    def _publish_results(self, context: _MovementOrderContext) -> None:
        routes_changed = (
            context.route_table is None
            or context.route_rows != list(context.route_by_unit.values())
        )
        if routes_changed:
            context.state.update_table(
                "unit_movement_routes",
                pl.DataFrame(list(context.route_by_unit.values()), schema=self._route_schema),
            )
        self._unit_order_workflow.write_feedback(context.state, context.feedback_rows)
