"""Shared readiness, pending-order, and feedback workflows for unit commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState


UNIT_PENDING_ORDER_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "unit_id": pl.Utf8,
    "player_id": pl.Utf8,
    "order_type": pl.Utf8,
    "target_region_id": pl.Int32,
    "target_latitude": pl.Float64,
    "target_longitude": pl.Float64,
    "target_unit_id": pl.Utf8,
    "via_region_ids": pl.List(pl.Int32),
    "created_at_minute": pl.Int64,
    "status": pl.Utf8,
}

UNIT_ORDER_FEEDBACK_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "unit_id": pl.Utf8,
    "owner_country_id": pl.Utf8,
    "order_type": pl.Utf8,
    "status": pl.Utf8,
    "reason": pl.Utf8,
    "created_at_minute": pl.Int64,
}


@dataclass(frozen=True)
class UnitOrderFeedbackEntry:
    unit_id: str
    owner: str
    order_type: str
    status: str
    reason: str
    current_minute: int


class _ReadinessPreparer(Protocol):
    def prepare_order(self, state: GameState, unit_id: str) -> bool: ...


class UnitOrderWorkflowService:
    """Own shared command readiness, queuing, and feedback state changes."""

    def __init__(self, readiness_preparer: _ReadinessPreparer) -> None:
        self._readiness_preparer = readiness_preparer

    def record_feedback(
        self,
        rows: list[dict[str, Any]],
        unit_id: str,
        owner: str,
        order_type: str,
        status: str,
        reason: str,
        current_minute: int,
    ) -> None:
        rows.append({
            "id": f"{unit_id}-{current_minute}-{len(rows) + 1}",
            "unit_id": unit_id,
            "owner_country_id": owner,
            "order_type": order_type,
            "status": status,
            "reason": reason,
            "created_at_minute": current_minute,
        })
        if len(rows) > 500:
            del rows[:-500]

    def record_feedback_entry(
        self,
        rows: list[dict[str, Any]],
        entry: UnitOrderFeedbackEntry,
    ) -> None:
        self.record_feedback(
            rows,
            entry.unit_id,
            entry.owner,
            entry.order_type,
            entry.status,
            entry.reason,
            entry.current_minute,
        )

    def write_feedback(self, state: GameState, rows: list[dict[str, Any]]) -> None:
        frame = (
            pl.DataFrame(rows, schema=UNIT_ORDER_FEEDBACK_SCHEMA)
            if rows
            else pl.DataFrame(schema=UNIT_ORDER_FEEDBACK_SCHEMA)
        )
        current = state.tables.get("unit_order_feedback")
        if current is None or not current.equals(frame):
            state.update_table("unit_order_feedback", frame)

    def release_fortified_for_order(
        self,
        state: GameState,
        unit: dict[str, Any],
    ) -> bool:
        unit_id = str(unit.get("id") or "")
        if str(unit.get("readiness_status") or "").strip().lower() != "fortified":
            return False
        if self._unit_is_transitioning(state, unit_id):
            return False
        if not self._readiness_preparer.prepare_order(state, unit_id):
            return False
        unit["readiness_status"] = "ready"
        unit["readiness_progress"] = 0.0
        unit["readiness_transition_id"] = ""
        unit["readiness_eta_minute"] = 0
        return True

    def unit_is_transitioning(self, state: GameState, unit_id: str) -> bool:
        transitions = state.tables.get("unit_readiness_transitions")
        return (
            transitions is not None
            and not transitions.is_empty()
            and "unit_id" in transitions.columns
            and transitions.filter(pl.col("unit_id") == unit_id).height > 0
        )

    def queue_move(self, state: GameState, action: ActionMoveUnit) -> str:
        pending = self.ensure_pending_table(state.tables.get("unit_pending_orders"))
        rows = [
            row
            for row in pending.to_dicts()
            if str(row.get("unit_id") or "") != str(action.unit_id)
        ]
        order_id = f"pending-{action.unit_id}-move-{state.time.total_minutes}"
        rows.append({
            "id": order_id,
            "unit_id": str(action.unit_id),
            "player_id": str(action.player_id),
            "order_type": "move",
            "target_region_id": int(action.target_region_id),
            "target_latitude": float(action.target_latitude or 0.0),
            "target_longitude": float(action.target_longitude or 0.0),
            "target_unit_id": "",
            "via_region_ids": list(action.via_region_ids),
            "created_at_minute": int(state.time.total_minutes),
            "status": "queued",
        })
        state.update_table(
            "unit_pending_orders",
            pl.DataFrame(rows, schema=UNIT_PENDING_ORDER_SCHEMA),
        )
        self.attach_pending_to_transition(state, action.unit_id, order_id)
        return order_id

    def queue_attack(self, state: GameState, action: ActionAttackUnit) -> str:
        pending = self.ensure_pending_table(state.tables.get("unit_pending_orders"))
        rows = [
            row
            for row in pending.to_dicts()
            if str(row.get("unit_id") or "") != str(action.attacker_unit_id)
        ]
        order_id = f"pending-{action.attacker_unit_id}-attack-{state.time.total_minutes}"
        rows.append({
            "id": order_id,
            "unit_id": str(action.attacker_unit_id),
            "player_id": str(action.player_id),
            "order_type": "attack",
            "target_region_id": 0,
            "target_latitude": 0.0,
            "target_longitude": 0.0,
            "target_unit_id": str(action.defender_unit_id),
            "via_region_ids": [],
            "created_at_minute": int(state.time.total_minutes),
            "status": "queued",
        })
        state.update_table(
            "unit_pending_orders",
            pl.DataFrame(rows, schema=UNIT_PENDING_ORDER_SCHEMA),
        )
        self.attach_pending_to_transition(state, action.attacker_unit_id, order_id)
        return order_id

    def ensure_pending_table(self, pending: pl.DataFrame | None) -> pl.DataFrame:
        if pending is None:
            return pl.DataFrame(schema=UNIT_PENDING_ORDER_SCHEMA)
        for column, dtype in UNIT_PENDING_ORDER_SCHEMA.items():
            if column not in pending.columns:
                default: Any = (
                    []
                    if dtype == pl.List(pl.Int32)
                    else 0 if dtype in (pl.Int32, pl.Int64, pl.Float64) else ""
                )
                pending = pending.with_columns(pl.lit(default).cast(dtype).alias(column))
        return pending.select([
            pl.col(column).cast(dtype)
            for column, dtype in UNIT_PENDING_ORDER_SCHEMA.items()
        ])

    def attach_pending_to_transition(
        self,
        state: GameState,
        unit_id: str,
        order_id: str,
    ) -> None:
        transitions = state.tables.get("unit_readiness_transitions")
        if transitions is None or transitions.is_empty() or "unit_id" not in transitions.columns:
            return
        rows = transitions.to_dicts()
        for row in rows:
            if str(row.get("unit_id") or "") == str(unit_id):
                row["pending_order_id"] = order_id
        state.update_table(
            "unit_readiness_transitions",
            pl.DataFrame(rows, schema=transitions.schema),
        )
