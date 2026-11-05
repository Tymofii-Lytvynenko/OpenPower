"""Create and progress deployment orders independently from phase orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import polars as pl

from src.shared.actions import ActionDispatchUnitDeployment, ActionMoveUnit
from src.shared.state import GameState
from modules.base.systems.military.unit_order_workflow import UnitOrderFeedbackEntry


class _UnitFactory(Protocol):
    def next_id(
        self,
        unit_rows: list[dict[str, Any]],
        country_tag: str,
        unit_type: str,
    ) -> str: ...


class _UnitOrderWorkflow(Protocol):
    def record_feedback_entry(
        self,
        rows: list[dict[str, Any]],
        entry: UnitOrderFeedbackEntry,
    ) -> None: ...

    def write_feedback(self, state: GameState, rows: list[dict[str, Any]]) -> None: ...


@dataclass
class _DeploymentActionBatch:
    state: GameState
    current_minute: int
    unit_rows: list[dict[str, Any]]
    deployment_table: pl.DataFrame
    deployments: list[dict[str, Any]]
    units_by_id: dict[str, dict[str, Any]]
    deployments_by_unit: dict[str, dict[str, Any]]
    regions: pl.DataFrame | None
    moves: list[ActionMoveUnit] = field(default_factory=list)
    seen_unit_ids: set[str] = field(default_factory=set)
    feedback: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DeploymentOrderSpec:
    production_order_id: str
    unit_id: str
    country_id: str
    quantity: int
    source_region_id: int
    created_at_minute: int


class MilitaryDeploymentService:
    """Own deployment dispatch validation and deployment lifecycle projection."""

    def __init__(
        self,
        unit_factory: _UnitFactory,
        unit_order_workflow: _UnitOrderWorkflow,
        authorization_policy: Callable[[GameState, str, str], bool],
        units_from_rows: Callable[[list[dict[str, Any]]], pl.DataFrame],
    ) -> None:
        self._unit_factory = unit_factory
        self._unit_order_workflow = unit_order_workflow
        self._authorization_policy = authorization_policy
        self._units_from_rows = units_from_rows

    def process_actions(
        self,
        state: GameState,
        units: pl.DataFrame,
    ) -> tuple[pl.DataFrame, list[ActionMoveUnit]]:
        actions = self._deployment_actions(state)
        if not actions:
            return units, []

        batch = self._create_action_batch(state, units)
        if batch is None:
            return units, []

        for action in actions:
            self._process_action(action, batch)
        self._persist_action_batch(batch)
        return self._units_from_rows(batch.unit_rows), batch.moves

    def _deployment_actions(self, state: GameState) -> list[ActionDispatchUnitDeployment]:
        return [
            action
            for action in state.current_actions
            if isinstance(action, ActionDispatchUnitDeployment)
        ]

    def _create_action_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
    ) -> _DeploymentActionBatch | None:
        deployment_table = state.tables.get("unit_deployment_orders")
        if units.is_empty() or deployment_table is None:
            return None

        deployment_rows = deployment_table.to_dicts()
        unit_rows = units.to_dicts()
        feedback_table = state.tables.get("unit_order_feedback")
        batch = _DeploymentActionBatch(
            state=state,
            current_minute=int(state.time.total_minutes),
            unit_rows=unit_rows,
            deployment_table=deployment_table,
            deployments=deployment_rows,
            units_by_id={str(row.get("id") or ""): row for row in unit_rows},
            deployments_by_unit={
                str(row.get("unit_id") or ""): row for row in deployment_rows
            },
            regions=state.tables.get("regions"),
            feedback=[] if feedback_table is None else feedback_table.to_dicts(),
        )
        return batch

    def _persist_action_batch(self, batch: _DeploymentActionBatch) -> None:
        if batch.deployments != batch.deployment_table.to_dicts():
            batch.state.update_table(
                "unit_deployment_orders",
                pl.DataFrame(batch.deployments, schema=batch.deployment_table.schema),
            )
        self._unit_order_workflow.write_feedback(batch.state, batch.feedback)

    def create_order_record(
        self,
        spec: DeploymentOrderSpec,
        existing_deployments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "id": self.next_deployment_id(spec.production_order_id, existing_deployments),
            "unit_id": spec.unit_id,
            "country_id": spec.country_id,
            "production_order_id": spec.production_order_id,
            "quantity": spec.quantity,
            "source_region_id": spec.source_region_id,
            "destination_region_id": 0,
            "route_region_ids": [],
            "route_index": 0,
            "status": "queued",
            "created_at_minute": int(spec.created_at_minute),
            "estimated_arrival_at_minute": 0,
            "blocking_reason": "Select a valid deployment region and dispatch this group.",
        }

    def next_deployment_id(
        self,
        production_order_id: str,
        deployments: list[dict[str, Any]],
    ) -> str:
        existing = {str(row.get("id") or "") for row in deployments}
        index = 1
        identifier = f"deployment-{production_order_id}-{index:03d}"
        while identifier in existing:
            index += 1
            identifier = f"deployment-{production_order_id}-{index:03d}"
        return identifier

    def refresh_state(self, state: GameState, units: pl.DataFrame) -> None:
        deployments_table = state.tables.get("unit_deployment_orders")
        if deployments_table is None or deployments_table.is_empty():
            return

        unit_rows = units.to_dicts()
        units_by_id = {str(row.get("id") or ""): row for row in unit_rows}
        routes_table = state.tables.get("unit_movement_routes")
        routes = (
            {}
            if routes_table is None
            else {
                str(row.get("unit_id") or ""): row
                for row in routes_table.to_dicts()
            }
        )
        deployments = deployments_table.to_dicts()
        for deployment in deployments:
            self._refresh_deployment(deployment, units_by_id, routes)

        frame = pl.DataFrame(deployments, schema=deployments_table.schema)
        if not frame.equals(deployments_table):
            state.update_table("unit_deployment_orders", frame)
        self._refresh_completed_production_orders(state, deployments)

    def _process_action(
        self,
        action: ActionDispatchUnitDeployment,
        batch: _DeploymentActionBatch,
    ) -> None:
        unit_id = self._string_value(action.unit_id)
        unit = batch.units_by_id.get(unit_id)
        deployment = batch.deployments_by_unit.get(unit_id)
        if unit is None or deployment is None:
            self._record_rejection(
                batch,
                UnitOrderFeedbackEntry(
                    unit_id=unit_id,
                    owner="",
                    order_type="deployment",
                    status="rejected",
                    reason="No deployment-queued group matches this unit.",
                    current_minute=batch.current_minute,
                ),
            )
            return
        if unit_id in batch.seen_unit_ids:
            self._record_rejection(
                batch,
                UnitOrderFeedbackEntry(
                    unit_id=unit_id,
                    owner=self._string_value(unit.get("owner")).strip().upper(),
                    order_type="deployment",
                    status="rejected",
                    reason="A unit group can receive only one deployment order per update.",
                    current_minute=batch.current_minute,
                ),
            )
            return

        batch.seen_unit_ids.add(unit_id)
        owner = self._string_value(unit.get("owner")).strip().upper()
        rejection_reason = self._action_rejection_reason(
            action,
            unit,
            owner,
            batch,
        )
        if rejection_reason:
            self._record_rejection(
                batch,
                UnitOrderFeedbackEntry(
                    unit_id=unit_id,
                    owner=owner,
                    order_type="deployment",
                    status="rejected",
                    reason=rejection_reason,
                    current_minute=batch.current_minute,
                ),
            )
            return

        self._dispatch_group(action, unit, deployment, owner, batch)

    def _dispatch_group(
        self,
        action: ActionDispatchUnitDeployment,
        unit: dict[str, Any],
        deployment: dict[str, Any],
        owner: str,
        batch: _DeploymentActionBatch,
    ) -> None:
        available = max(0, self._integer_value(unit.get("strength")))
        requested = self._requested_quantity(action, available)
        dispatched_id = self._string_value(action.unit_id)
        if requested < available:
            dispatched_id = self._split_deployment_group(
                unit,
                deployment,
                requested,
                owner,
                batch,
            )
            deployment = batch.deployments_by_unit[dispatched_id]

        destination_id = self._integer_value(action.destination_region_id)
        deployment["destination_region_id"] = destination_id
        deployment["status"] = "dispatching"
        deployment["blocking_reason"] = ""
        batch.moves.append(
            ActionMoveUnit(self._string_value(action.player_id, owner), dispatched_id, destination_id)
        )

    def _action_rejection_reason(
        self,
        action: ActionDispatchUnitDeployment,
        unit: dict[str, Any],
        owner: str,
        batch: _DeploymentActionBatch,
    ) -> str:
        if not self._authorization_policy(
            batch.state,
            self._string_value(action.player_id),
            owner,
        ):
            return "The issuer does not control this deployment group."
        if self._string_value(unit.get("unit_lifecycle")) not in {
            "deployment_queued",
            "deployment_blocked",
        }:
            return "The unit is not waiting for deployment or route recovery."

        target_id = self._integer_value(action.destination_region_id)
        if not self._destination_is_valid(batch.regions, target_id):
            return "The deployment destination is invalid."

        available = max(0, self._integer_value(unit.get("strength")))
        if not self._quantity_is_valid(self._requested_quantity(action, available), available):
            return "The deployment quantity must be between one and the available group strength."
        return ""

    def _destination_is_valid(
        self,
        regions: pl.DataFrame | None,
        target_id: int,
    ) -> bool:
        if target_id <= 0 or regions is None:
            return False
        return not regions.filter(pl.col("id") == target_id).is_empty()

    def _requested_quantity(
        self,
        action: ActionDispatchUnitDeployment,
        available: int,
    ) -> int:
        requested = self._integer_value(action.quantity)
        return available if requested <= 0 else requested

    def _quantity_is_valid(self, requested: int, available: int) -> bool:
        return requested > 0 and requested <= available

    def _string_value(self, value: Any, fallback: str = "") -> str:
        return str(value or fallback)

    def _integer_value(self, value: Any) -> int:
        return int(value or 0)

    def _split_deployment_group(
        self,
        unit: dict[str, Any],
        deployment: dict[str, Any],
        requested: int,
        owner: str,
        batch: _DeploymentActionBatch,
    ) -> str:
        available = max(0, self._integer_value(unit.get("strength")))
        available_equipment = max(
            0,
            self._integer_value(unit.get("equipment_quantity")),
        )
        dispatched_equipment = min(
            available_equipment,
            int(round(available_equipment * requested / available)),
        )
        unit["strength"] = available - requested
        unit["equipment_quantity"] = available_equipment - dispatched_equipment
        deployment["quantity"] = available - requested

        clone = dict(unit)
        dispatched_id = self._unit_factory.next_id(
            batch.unit_rows,
            owner,
            self._string_value(unit.get("unit_type")),
        )
        clone.update(
            id=dispatched_id,
            strength=requested,
            equipment_quantity=dispatched_equipment,
            unit_lifecycle="deployment_queued",
        )
        batch.unit_rows.append(clone)
        batch.units_by_id[dispatched_id] = clone

        split_deployment = dict(deployment)
        split_deployment.update(
            id=self.next_deployment_id(
                self._string_value(deployment.get("production_order_id")),
                batch.deployments,
            ),
            unit_id=dispatched_id,
            quantity=requested,
            destination_region_id=0,
            route_region_ids=[],
            route_index=0,
            status="queued",
            estimated_arrival_at_minute=0,
            blocking_reason="Select a valid deployment region and dispatch this group.",
        )
        batch.deployments.append(split_deployment)
        batch.deployments_by_unit[dispatched_id] = split_deployment
        return dispatched_id

    def _record_rejection(
        self,
        batch: _DeploymentActionBatch,
        entry: UnitOrderFeedbackEntry,
    ) -> None:
        self._unit_order_workflow.record_feedback_entry(batch.feedback, entry)

    def _refresh_deployment(
        self,
        deployment: dict[str, Any],
        units_by_id: dict[str, dict[str, Any]],
        routes: dict[str, dict[str, Any]],
    ) -> None:
        unit_id = self._string_value(deployment.get("unit_id"))
        unit = units_by_id.get(unit_id)
        if unit is None:
            if self._string_value(deployment.get("status")) not in {
                "delivered",
                "cancelled",
                "failed",
                "disbanded",
            }:
                deployment.update(
                    status="blocked",
                    blocking_reason="The deployed group no longer exists.",
                )
            return

        route = routes.get(unit_id)
        if route is not None:
            self._copy_route_state(deployment, unit, route)
        status_update = self._status_update(
            self._string_value(unit.get("unit_lifecycle")),
            route,
        )
        if status_update is not None:
            deployment.update(status=status_update[0], blocking_reason=status_update[1])

    def _copy_route_state(
        self,
        deployment: dict[str, Any],
        unit: dict[str, Any],
        route: dict[str, Any],
    ) -> None:
        deployment["route_region_ids"] = list(route.get("route_region_ids") or [])
        deployment["route_index"] = max(0, self._integer_value(route.get("route_index")))
        deployment["destination_region_id"] = max(
            0,
            self._integer_value(route.get("destination_region_id")),
        )
        deployment["estimated_arrival_at_minute"] = max(
            0,
            self._integer_value(unit.get("arrival_at_minute")),
        )

    def _status_update(
        self,
        lifecycle: str,
        route: dict[str, Any] | None,
    ) -> tuple[str, str] | None:
        if lifecycle == "available":
            return "delivered", ""
        if lifecycle in {"deployment_transit", "in_transit"}:
            return "in_transit", ""
        if lifecycle in {"deployment_blocked", "route_blocked"}:
            reason = str(
                (route or {}).get("rejection_reason")
                or "The deployment route needs a new order."
            )
            return "blocked", reason
        if lifecycle == "deployment_queued":
            return "queued", "Select a valid deployment region and dispatch this group."
        return None

    def _refresh_completed_production_orders(
        self,
        state: GameState,
        deployments: list[dict[str, Any]],
    ) -> None:
        production_table = state.tables.get("production_orders")
        if production_table is None or production_table.is_empty():
            return

        production_rows = production_table.to_dicts()
        deployments_by_order: dict[str, list[dict[str, Any]]] = {}
        for deployment in deployments:
            order_id = str(deployment.get("production_order_id") or "")
            deployments_by_order.setdefault(order_id, []).append(deployment)

        changed = False
        for order in production_rows:
            if not self._has_fully_delivered(order, deployments_by_order):
                continue
            order["status"] = "delivered"
            order["blocking_reason"] = (
                "All produced groups arrived at their assigned deployment regions."
            )
            changed = True

        if changed:
            state.update_table(
                "production_orders",
                pl.DataFrame(production_rows, schema=production_table.schema),
            )

    def _has_fully_delivered(
        self,
        order: dict[str, Any],
        deployments_by_order: dict[str, list[dict[str, Any]]],
    ) -> bool:
        if self._string_value(order.get("status")) != "awaiting_deployment":
            return False
        related = deployments_by_order.get(self._string_value(order.get("id")), [])
        return bool(related) and all(
            self._string_value(item.get("status")) == "delivered"
            for item in related
        )
