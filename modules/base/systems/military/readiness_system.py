"""Server-side lifecycle for unit readiness postures."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.military.readiness_policy import (
    READINESS_FORTIFIED,
    READINESS_PARKED,
    READINESS_READY,
    READINESS_STATUSES,
    ReadinessPolicy,
)
from src.shared.actions import ActionSetUnitReadiness
from src.shared.actions import ActionMoveUnit
from src.shared.events import (
    EventUnitReadinessCanceled,
    EventUnitReadinessCompleted,
    EventUnitReadinessStarted,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER


TRANSITIONS_TABLE = "unit_readiness_transitions"
PENDING_TABLE = "unit_pending_orders"
UNITS_TABLE = "units"

TRANSITION_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "unit_id": pl.Utf8,
    "from_status": pl.Utf8,
    "target_status": pl.Utf8,
    "stage": pl.Utf8,
    "started_at_minute": pl.Int64,
    "completes_at_minute": pl.Int64,
    "progress": pl.Float64,
    "pending_order_id": pl.Utf8,
}

PENDING_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8, "unit_id": pl.Utf8, "player_id": pl.Utf8,
    "order_type": pl.Utf8, "target_region_id": pl.Int32,
    "target_latitude": pl.Float64, "target_longitude": pl.Float64,
    "target_unit_id": pl.Utf8, "via_region_ids": pl.List(pl.Int32),
    "created_at_minute": pl.Int64, "status": pl.Utf8,
}


class ReadinessSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({"units", TRANSITIONS_TABLE, PENDING_TABLE}),
        writes=frozenset({"units", TRANSITIONS_TABLE, PENDING_TABLE}),
        handles=frozenset({ActionSetUnitReadiness}),
        # A lower numeric phase guarantees readiness advances before movement
        # when both systems are registered, while keeping MilitarySystem usable
        # in minimal test compositions that do not include this optional system.
        phase=SystemPhase.MILITARY - 1,
    )
    runtime_state_contract = {"_policy": SYSTEM_STATE_HELPER}

    def __init__(self) -> None:
        self._policy = ReadinessPolicy()

    @property
    def id(self) -> str:
        return "base.readiness"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        units = self._ensure_units(state.tables.get(UNITS_TABLE))
        transitions = self._ensure_transitions(state.tables.get(TRANSITIONS_TABLE))
        now = int(state.time.total_minutes)

        # Commands are processed before due transitions. This gives an explicit
        # replacement command the same-tick precedence expected by the UI.
        for action in state.current_actions:
            if not isinstance(action, ActionSetUnitReadiness):
                continue
            self._request_transition(state, units, transitions, action, now)

        # A request may have materialized or replaced a transition table row.
        # Reload it before advancing progress so the command is visible in the
        # same server tick and is not overwritten by the stale local frame.
        transitions = self._ensure_transitions(state.tables.get(TRANSITIONS_TABLE))
        units = self._ensure_units(state.tables.get(UNITS_TABLE))

        units_rows = units.to_dicts()
        transition_rows = transitions.to_dicts()
        by_unit = {str(row.get("unit_id") or ""): row for row in transition_rows}
        for unit in units_rows:
            unit_id = str(unit.get("id") or "")
            transition = by_unit.get(unit_id)
            if transition is None:
                unit["readiness_progress"] = 0.0
                unit["readiness_transition_id"] = ""
                unit["readiness_eta_minute"] = 0
                unit["readiness_status"] = self._policy.normalize(unit.get("readiness_status"))
                continue

            if now >= int(transition.get("completes_at_minute") or now):
                requested_target = self._policy.normalize(transition.get("target_status"))
                staged = str(transition.get("stage") or "") == "parked_to_fortified"
                target = READINESS_READY if staged else requested_target
                unit["readiness_status"] = target
                unit["readiness_progress"] = 1.0
                unit["readiness_transition_id"] = ""
                unit["readiness_eta_minute"] = 0
                released_order_id = "" if staged else str(transition.get("pending_order_id") or "")
                state.events.append(
                    EventUnitReadinessCompleted(
                        unit_id=unit_id,
                        transition_id=str(transition.get("id") or ""),
                        status=target,
                        completed_at_minute=now,
                        released_order_id=released_order_id,
                    )
                )
                transition_rows = [row for row in transition_rows if row is not transition]
                # A two-stage parked -> fortified transition is represented as
                # one user-visible request but two deterministic stages.
                if staged:
                    next_transition = self._new_transition(
                        unit_id,
                        READINESS_READY,
                        READINESS_FORTIFIED,
                        "ready_to_fortified",
                        now,
                        self._policy.READY_TO_FORTIFIED_MINUTES,
                    )
                    # Keep the order attached to the request until the final
                    # stage completes; otherwise a staged readiness order can
                    # strand its pending movement or attack.
                    next_transition["pending_order_id"] = str(transition.get("pending_order_id") or "")
                    unit["readiness_status"] = READINESS_READY
                    unit["readiness_progress"] = 0.0
                    unit["readiness_transition_id"] = next_transition["id"]
                    unit["readiness_eta_minute"] = next_transition["completes_at_minute"]
                    transition_rows.append(next_transition)
                    by_unit[unit_id] = next_transition
                else:
                    self._release_pending_order(state, unit_id, str(transition.get("pending_order_id") or ""))
                    by_unit.pop(unit_id, None)
                continue

            started_at = transition.get("started_at_minute")
            completes_at = transition.get("completes_at_minute")
            unit["readiness_status"] = self._policy.normalize(transition.get("from_status"))
            unit["readiness_progress"] = self._policy.progress(
                int(started_at if started_at is not None else now),
                int(completes_at if completes_at is not None else now),
                now,
            )
            transition["progress"] = unit["readiness_progress"]
            unit["readiness_transition_id"] = str(transition.get("id") or "")
            unit["readiness_eta_minute"] = int(completes_at if completes_at is not None else 0)

        self._update_table_if_changed(
            state,
            UNITS_TABLE,
            self._frame_from_rows(units.schema, units_rows),
        )
        self._update_table_if_changed(
            state,
            TRANSITIONS_TABLE,
            self._frame_from_rows(TRANSITION_SCHEMA, transition_rows),
        )

    def prepare_order(self, state: GameState, unit_id: str, pending_order_id: str = "") -> bool:
        """Prepare a validated order and report whether it may execute now.

        Orders are validated by the military system before this method is
        called. This method only reconciles posture: parked units start or
        join a transition to ready, while fortified units are released
        immediately. A ready unit with a pending fortification transition is
        released as well so the latest valid order is not delayed by an older
        posture request.
        """
        units = self._ensure_units(state.tables.get(UNITS_TABLE))
        transitions = self._ensure_transitions(state.tables.get(TRANSITIONS_TABLE))
        unit_key = str(unit_id)
        rows = units.to_dicts()
        unit = next((row for row in rows if str(row.get("id") or "") == unit_key), None)
        if unit is None:
            return False

        current = self._policy.normalize(unit.get("readiness_status"))
        existing = [
            row
            for row in transitions.to_dicts()
            if str(row.get("unit_id") or "") == unit_key
        ]
        if current == READINESS_READY and not existing:
            return True

        if existing:
            existing_target = self._policy.normalize(existing[0].get("target_status"))
            if current == READINESS_PARKED and existing_target == READINESS_READY:
                if pending_order_id:
                    updated_rows = [
                        {
                            **row,
                            "pending_order_id": str(pending_order_id),
                        }
                        if str(row.get("unit_id") or "") == unit_key
                        else row
                        for row in transitions.to_dicts()
                    ]
                    state.update_table(
                        TRANSITIONS_TABLE,
                        self._frame_from_rows(TRANSITION_SCHEMA, updated_rows),
                    )
                return False
            # A movement/attack order supersedes a pending fortification or a
            # stale transition target, but only after the order was validated.
            self.cancel_transition_for_unit(state, unit_key, "order_posture_release")
            units = self._ensure_units(state.tables.get(UNITS_TABLE))
            rows = units.to_dicts()
            unit = next(row for row in rows if str(row.get("id") or "") == unit_key)
            current = self._policy.normalize(unit.get("readiness_status"))

        if current == READINESS_FORTIFIED:
            unit["readiness_status"] = READINESS_READY
            unit["readiness_progress"] = 0.0
            unit["readiness_transition_id"] = ""
            unit["readiness_eta_minute"] = 0
            state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, rows))
            return True

        transition = self._policy.transition(current, READINESS_READY)
        if transition is None:
            return True
        now = int(state.time.total_minutes)
        transition_row = self._new_transition(
            unit_key,
            current,
            READINESS_READY,
            transition.stage,
            now,
            transition.duration_minutes,
        )
        transition_row["pending_order_id"] = str(pending_order_id or "")
        updated_rows = [
            row
            for row in transitions.to_dicts()
            if str(row.get("unit_id") or "") != unit_key
        ]
        updated_rows.append(transition_row)
        unit["readiness_status"] = current
        unit["readiness_progress"] = 0.0
        unit["readiness_transition_id"] = transition_row["id"]
        unit["readiness_eta_minute"] = transition_row["completes_at_minute"]
        state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, rows))
        state.update_table(TRANSITIONS_TABLE, self._frame_from_rows(TRANSITION_SCHEMA, updated_rows))
        state.events.append(
            EventUnitReadinessStarted(
                unit_id=unit_key,
                transition_id=transition_row["id"],
                from_status=current,
                target_status=READINESS_READY,
                stage=transition.stage,
                started_at_minute=now,
                completes_at_minute=transition_row["completes_at_minute"],
            )
        )
        return False

    def cancel_transition_for_unit(self, state: GameState, unit_id: str, reason: str) -> None:
        transitions = self._ensure_transitions(state.tables.get(TRANSITIONS_TABLE))
        rows = transitions.to_dicts()
        canceled = [row for row in rows if str(row.get("unit_id") or "") == str(unit_id)]
        if not canceled:
            return
        remaining = [row for row in rows if str(row.get("unit_id") or "") != str(unit_id)]
        units = self._ensure_units(state.tables.get(UNITS_TABLE)).to_dicts()
        now = int(state.time.total_minutes)
        for unit in units:
            if str(unit.get("id") or "") != str(unit_id):
                continue
            status = self._policy.normalize(unit.get("readiness_status"))
            unit["readiness_transition_id"] = ""
            unit["readiness_progress"] = 0.0
            unit["readiness_eta_minute"] = 0
            state.events.append(
                EventUnitReadinessCanceled(
                    unit_id=str(unit_id),
                    transition_id=str(canceled[0].get("id") or ""),
                    status=status,
                    canceled_at_minute=now,
                    reason=reason,
                )
            )
        state.update_table(UNITS_TABLE, self._frame_from_rows(self._ensure_units(state.tables.get(UNITS_TABLE)).schema, units))
        state.update_table(TRANSITIONS_TABLE, self._frame_from_rows(TRANSITION_SCHEMA, remaining))
        pending = state.tables.get(PENDING_TABLE)
        if pending is not None and not pending.is_empty() and "unit_id" in pending.columns:
            state.update_table(PENDING_TABLE, pending.filter(pl.col("unit_id") != str(unit_id)))

    def _request_transition(self, state: GameState, units: pl.DataFrame, transitions: pl.DataFrame, action: ActionSetUnitReadiness, now: int) -> None:
        if str(action.target_status or "").strip().lower() not in READINESS_STATUSES:
            return
        rows = units.to_dicts()
        unit = next((row for row in rows if str(row.get("id") or "") == str(action.unit_id)), None)
        actor_id = str(action.player_id or "").strip()
        owner_id = str(unit.get("owner") or "").strip() if unit is not None else ""
        if unit is None or (
            actor_id not in {owner_id, "server", "local_player", "local_admin"}
            and actor_id.casefold() != owner_id.casefold()
        ):
            return
        current = self._policy.normalize(unit.get("readiness_status"))
        target = self._policy.normalize(action.target_status)
        existing = [row for row in transitions.to_dicts() if str(row.get("unit_id") or "") == str(action.unit_id)]
        if existing and self._policy.normalize(existing[0].get("target_status")) == target:
            return
        if existing:
            self.cancel_transition_for_unit(state, action.unit_id, "replaced")
        transition = self._policy.transition(current, target)
        if transition is None:
            unit["readiness_status"] = current
            unit["readiness_progress"] = 0.0
            unit["readiness_transition_id"] = ""
            unit["readiness_eta_minute"] = 0
            state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, rows))
            return
        if transition.duration_minutes <= 0:
            unit["readiness_status"] = target
            unit["readiness_progress"] = 1.0
            unit["readiness_transition_id"] = ""
            unit["readiness_eta_minute"] = 0
            state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, rows))
            state.events.append(EventUnitReadinessCompleted(str(action.unit_id), f"readiness-{action.unit_id}-{now}", target, now))
            return

        transition_row = self._new_transition(
            str(action.unit_id), current, target, transition.stage, now, transition.duration_minutes
        )
        updated_rows = [row for row in transitions.to_dicts() if str(row.get("unit_id") or "") != str(action.unit_id)]
        updated_rows.append(transition_row)
        unit["readiness_status"] = current
        unit["readiness_progress"] = 0.0
        unit["readiness_transition_id"] = transition_row["id"]
        unit["readiness_eta_minute"] = transition_row["completes_at_minute"]
        state.update_table(UNITS_TABLE, self._frame_from_rows(units.schema, rows))
        state.update_table(TRANSITIONS_TABLE, self._frame_from_rows(TRANSITION_SCHEMA, updated_rows))
        state.events.append(
            EventUnitReadinessStarted(
                unit_id=str(action.unit_id),
                transition_id=transition_row["id"],
                from_status=current,
                target_status=target,
                stage=transition.stage,
                started_at_minute=now,
                completes_at_minute=transition_row["completes_at_minute"],
            )
        )

    def _new_transition(self, unit_id: str, source: str, target: str, stage: str, now: int, duration: int) -> dict[str, Any]:
        transition_id = f"readiness-{unit_id}-{now}-{stage}"
        return {
            "id": transition_id,
            "unit_id": unit_id,
            "from_status": source,
            "target_status": target,
            "stage": stage,
            "started_at_minute": now,
            "completes_at_minute": now + max(0, int(duration)),
            "progress": 0.0,
            "pending_order_id": "",
        }

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True

    def _release_pending_order(self, state: GameState, unit_id: str, pending_order_id: str) -> None:
        pending = state.tables.get(PENDING_TABLE)
        if pending is None or pending.is_empty():
            return
        rows = pending.to_dicts()
        released = next((row for row in rows if str(row.get("unit_id") or "") == unit_id and str(row.get("status") or "queued") == "queued"), None)
        if released is None:
            return
        order_type = str(released.get("order_type") or "")
        player_id = str(released.get("player_id") or "server")
        if order_type == "move":
            state.current_actions.append(ActionMoveUnit(
                player_id, unit_id, int(released.get("target_region_id") or 0),
                float(released.get("target_latitude") or 0.0), float(released.get("target_longitude") or 0.0),
                list(released.get("via_region_ids") or []),
            ))
        elif order_type == "attack":
            from src.shared.actions import ActionAttackUnit
            state.current_actions.append(ActionAttackUnit(player_id, unit_id, str(released.get("target_unit_id") or "")))
        remaining = [row for row in rows if row is not released]
        state.update_table(PENDING_TABLE, self._frame_from_rows(PENDING_SCHEMA, remaining))

    def _ensure_units(self, units: pl.DataFrame | None) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8, "owner": pl.Utf8, "strength": pl.Int64,
            "readiness_status": pl.Utf8, "readiness_transition_id": pl.Utf8,
            "readiness_progress": pl.Float64, "readiness_eta_minute": pl.Int64,
        }
        if units is None:
            return pl.DataFrame(schema=schema)
        for column, dtype in schema.items():
            if column not in units.columns:
                default: Any = 0 if dtype in (pl.Int64, pl.Float64) else ("ready" if column == "readiness_status" else "")
                if dtype == pl.Float64:
                    default = 0.0
                units = units.with_columns(pl.lit(default).cast(dtype).alias(column))
        return units.with_columns([
            pl.col("readiness_status").cast(pl.Utf8), pl.col("readiness_transition_id").cast(pl.Utf8),
            pl.col("readiness_progress").cast(pl.Float64), pl.col("readiness_eta_minute").cast(pl.Int64),
        ])

    def _ensure_transitions(self, transitions: pl.DataFrame | None) -> pl.DataFrame:
        if transitions is None:
            return pl.DataFrame(schema=TRANSITION_SCHEMA)
        for column, dtype in TRANSITION_SCHEMA.items():
            if column not in transitions.columns:
                default: Any = 0 if dtype in (pl.Int64, pl.Float64) else ""
                transitions = transitions.with_columns(pl.lit(default).cast(dtype).alias(column))
        return transitions.select([pl.col(column).cast(dtype) for column, dtype in TRANSITION_SCHEMA.items()])

    def _frame_from_rows(self, schema: dict[str, pl.DataType], rows: list[dict[str, Any]]) -> pl.DataFrame:
        return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def cancel_readiness_for_contact(state: GameState, unit_ids: list[str], reason: str = "combat_contact") -> None:
    """Cancel transitions for units that entered contact before completion."""
    helper = ReadinessSystem()
    for unit_id in sorted({str(value) for value in unit_ids if value}):
        helper.cancel_transition_for_unit(state, unit_id, reason)
