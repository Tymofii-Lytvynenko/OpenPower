"""Server-side lifecycle for unit readiness postures."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.politics.political_effect_policy import aggregate_political_effects
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
        reads=frozenset({"units", TRANSITIONS_TABLE, PENDING_TABLE, "political_effects"}),
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
        updated_units, updated_transitions = self._advance_transitions(state, units, transitions, now)
        self._update_table_if_changed(state, UNITS_TABLE, updated_units)
        self._update_table_if_changed(state, TRANSITIONS_TABLE, updated_transitions)

    def _advance_transitions(
        self,
        state: GameState,
        units: pl.DataFrame,
        transitions: pl.DataFrame,
        now: int,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        if units.is_empty():
            return units, transitions

        unit_keys = units.select(pl.col("id").alias("unit_key"))
        matched = transitions.join(unit_keys, left_on="unit_id", right_on="unit_key", how="semi")
        orphaned = transitions.join(unit_keys, left_on="unit_id", right_on="unit_key", how="anti")
        due = matched.filter(pl.col("completes_at_minute").fill_null(now) <= now).join(
            units.select(
                pl.col("id").alias("due_unit_id"),
                pl.col("owner").alias("due_owner"),
            ),
            left_on="unit_id",
            right_on="due_unit_id",
            how="left",
        )
        completed = due.to_dicts()
        next_transitions: list[dict[str, Any]] = []
        completed_ids = due.select("id").unique()

        for transition in completed:
            unit_id = str(transition.get("unit_id") or "")
            transition_id = str(transition.get("id") or "")
            staged = str(transition.get("stage") or "") == "parked_to_fortified"
            target = READINESS_READY if staged else self._policy.normalize(transition.get("target_status"))
            pending_order_id = str(transition.get("pending_order_id") or "")
            state.events.append(
                EventUnitReadinessCompleted(
                    unit_id=unit_id,
                    transition_id=transition_id,
                    status=target,
                    completed_at_minute=now,
                    released_order_id="" if staged else pending_order_id,
                )
            )
            if staged:
                next_transition = self._new_transition(
                    unit_id,
                    READINESS_READY,
                    READINESS_FORTIFIED,
                    "ready_to_fortified",
                    now,
                    self._transition_duration_for_owner(
                        state,
                        str(transition.get("due_owner") or ""),
                        self._policy.READY_TO_FORTIFIED_MINUTES,
                    ),
                )
                # Preserve the pending order through both stages so completion can release it.
                next_transition["pending_order_id"] = pending_order_id
                next_transitions.append(next_transition)
            else:
                self._release_pending_order(state, unit_id, pending_order_id)

        active = matched.join(completed_ids, on="id", how="anti")
        if next_transitions:
            active = pl.concat(
                [
                    active,
                    pl.DataFrame(next_transitions, schema=TRANSITION_SCHEMA),
                ],
                how="vertical",
            )
        active = active.with_columns(
            ((pl.lit(now) - pl.col("started_at_minute").fill_null(now))
             / (pl.col("completes_at_minute").fill_null(now) - pl.col("started_at_minute").fill_null(now)).clip(lower_bound=1))
            .clip(lower_bound=0.0, upper_bound=1.0)
            .alias("progress")
        )

        unit_transitions = active.select(
            pl.col("unit_id").alias("_readiness_unit_id"),
            pl.col("from_status").alias("_readiness_from_status"),
            pl.col("id").alias("_readiness_transition_id"),
            pl.col("completes_at_minute").alias("_readiness_eta"),
            pl.col("progress").alias("_readiness_progress"),
        )
        completed_units = due.filter(pl.col("stage") != "parked_to_fortified").select(
            pl.col("unit_id").alias("_completed_unit_id"),
            pl.col("target_status").alias("_completed_status"),
        )
        completed_units = completed_units.with_columns(
            pl.col("_completed_status").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_lowercase()
        ).with_columns(
            pl.when(pl.col("_completed_status").is_in(list(READINESS_STATUSES)))
            .then(pl.col("_completed_status"))
            .otherwise(pl.lit(READINESS_READY))
            .alias("_completed_status")
        )
        updated_units = (
            units.join(unit_transitions, left_on="id", right_on="_readiness_unit_id", how="left")
            .join(completed_units, left_on="id", right_on="_completed_unit_id", how="left")
            .with_columns(
                pl.col("readiness_status").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_lowercase()
                .alias("_normalized_original_status"),
                pl.col("_readiness_from_status").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_lowercase()
                .alias("_normalized_transition_status"),
            )
            .with_columns(
                pl.when(pl.col("_readiness_transition_id").is_not_null())
                .then(
                    pl.when(pl.col("_normalized_transition_status").is_in(list(READINESS_STATUSES)))
                    .then(pl.col("_normalized_transition_status"))
                    .otherwise(pl.lit(READINESS_READY))
                )
                .when(pl.col("_completed_status").is_not_null())
                .then(pl.col("_completed_status"))
                .otherwise(
                    pl.when(pl.col("_normalized_original_status").is_in(list(READINESS_STATUSES)))
                    .then(pl.col("_normalized_original_status"))
                    .otherwise(pl.lit(READINESS_READY))
                )
                .alias("readiness_status"),
                pl.when(pl.col("_readiness_transition_id").is_null())
                .then(pl.when(pl.col("_completed_status").is_not_null()).then(pl.lit(1.0)).otherwise(pl.lit(0.0)))
                .otherwise(pl.col("_readiness_progress"))
                .alias("readiness_progress"),
                pl.col("_readiness_transition_id").fill_null("").alias("readiness_transition_id"),
                pl.col("_readiness_eta").fill_null(0).alias("readiness_eta_minute"),
            )
            .drop(
                "_readiness_from_status",
                "_readiness_transition_id",
                "_readiness_eta",
                "_readiness_progress",
                "_completed_status",
                "_normalized_original_status",
                "_normalized_transition_status",
            )
        )
        updated_transitions = pl.concat([active, orphaned], how="vertical") if not orphaned.is_empty() else active
        return updated_units, updated_transitions.select(list(TRANSITION_SCHEMA))

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
        unit_rows = units.filter(pl.col("id") == unit_key).head(1).to_dicts()
        unit = unit_rows[0] if unit_rows else None
        if unit is None:
            return False

        current = self._policy.normalize(unit.get("readiness_status"))
        existing = transitions.filter(pl.col("unit_id") == unit_key).head(1).to_dicts()
        if current == READINESS_READY and not existing:
            return True

        if existing:
            existing_target = self._policy.normalize(existing[0].get("target_status"))
            if current == READINESS_PARKED and existing_target == READINESS_READY:
                if pending_order_id:
                    updated = transitions.with_columns(
                        pl.when(pl.col("unit_id") == unit_key)
                        .then(pl.lit(str(pending_order_id)))
                        .otherwise(pl.col("pending_order_id"))
                        .alias("pending_order_id")
                    )
                    state.update_table(TRANSITIONS_TABLE, updated)
                return False
            # A movement/attack order supersedes a pending fortification or a
            # stale transition target, but only after the order was validated.
            self.cancel_transition_for_unit(state, unit_key, "order_posture_release")
            units = self._ensure_units(state.tables.get(UNITS_TABLE))
            unit_rows = units.filter(pl.col("id") == unit_key).head(1).to_dicts()
            if not unit_rows:
                return False
            unit = unit_rows[0]
            current = self._policy.normalize(unit.get("readiness_status"))

        if current == READINESS_FORTIFIED:
            state.update_table(
                UNITS_TABLE,
                self._set_unit_fields(units, unit_key, {
                    "readiness_status": READINESS_READY,
                    "readiness_progress": 0.0,
                    "readiness_transition_id": "",
                    "readiness_eta_minute": 0,
                }),
            )
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
        updated_transitions = pl.concat(
            [
                transitions.filter(pl.col("unit_id") != unit_key),
                pl.DataFrame([transition_row], schema=TRANSITION_SCHEMA),
            ],
            how="vertical",
        )
        state.update_table(
            UNITS_TABLE,
            self._set_unit_fields(units, unit_key, {
                "readiness_status": current,
                "readiness_progress": 0.0,
                "readiness_transition_id": transition_row["id"],
                "readiness_eta_minute": transition_row["completes_at_minute"],
            }),
        )
        state.update_table(TRANSITIONS_TABLE, updated_transitions)
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
        unit_key = str(unit_id)
        canceled = transitions.filter(pl.col("unit_id") == unit_key).head(1).to_dicts()
        if not canceled:
            return
        remaining = transitions.filter(pl.col("unit_id") != unit_key)
        units = self._ensure_units(state.tables.get(UNITS_TABLE))
        unit_rows = units.filter(pl.col("id") == unit_key).head(1).to_dicts()
        now = int(state.time.total_minutes)
        if unit_rows:
            status = self._policy.normalize(unit_rows[0].get("readiness_status"))
            state.events.append(
                EventUnitReadinessCanceled(
                    unit_id=unit_key,
                    transition_id=str(canceled[0].get("id") or ""),
                    status=status,
                    canceled_at_minute=now,
                    reason=reason,
                )
            )
            units = self._set_unit_fields(units, unit_key, {
                "readiness_transition_id": "",
                "readiness_progress": 0.0,
                "readiness_eta_minute": 0,
            })
            state.update_table(UNITS_TABLE, units)
        state.update_table(TRANSITIONS_TABLE, remaining)
        pending = state.tables.get(PENDING_TABLE)
        if pending is not None and not pending.is_empty() and "unit_id" in pending.columns:
            state.update_table(PENDING_TABLE, pending.filter(pl.col("unit_id") != str(unit_id)))

    def _request_transition(self, state: GameState, units: pl.DataFrame, transitions: pl.DataFrame, action: ActionSetUnitReadiness, now: int) -> None:
        if str(action.target_status or "").strip().lower() not in READINESS_STATUSES:
            return
        unit_key = str(action.unit_id)
        unit_rows = units.filter(pl.col("id") == unit_key).head(1).to_dicts()
        unit = unit_rows[0] if unit_rows else None
        actor_id = str(action.player_id or "").strip()
        owner_id = str(unit.get("owner") or "").strip() if unit is not None else ""
        if unit is None or (
            actor_id not in {owner_id, "server", "local_player", "local_admin"}
            and actor_id.casefold() != owner_id.casefold()
        ):
            return
        current = self._policy.normalize(unit.get("readiness_status"))
        target = self._policy.normalize(action.target_status)
        existing = transitions.filter(pl.col("unit_id") == unit_key).head(1).to_dicts()
        if existing and self._policy.normalize(existing[0].get("target_status")) == target:
            return
        if existing:
            self.cancel_transition_for_unit(state, unit_key, "replaced")
        transition = self._policy.transition(current, target)
        if transition is None:
            state.update_table(UNITS_TABLE, self._set_unit_fields(units, unit_key, {
                "readiness_status": current,
                "readiness_progress": 0.0,
                "readiness_transition_id": "",
                "readiness_eta_minute": 0,
            }))
            return
        duration = self._transition_duration_for_owner(state, owner_id, transition.duration_minutes)
        if duration <= 0:
            state.update_table(UNITS_TABLE, self._set_unit_fields(units, unit_key, {
                "readiness_status": target,
                "readiness_progress": 1.0,
                "readiness_transition_id": "",
                "readiness_eta_minute": 0,
            }))
            state.events.append(EventUnitReadinessCompleted(str(action.unit_id), f"readiness-{action.unit_id}-{now}", target, now))
            return

        transition_row = self._new_transition(
            str(action.unit_id), current, target, transition.stage, now, duration
        )
        updated_transitions = pl.concat(
            [
                transitions.filter(pl.col("unit_id") != unit_key),
                pl.DataFrame([transition_row], schema=TRANSITION_SCHEMA),
            ],
            how="vertical",
        )
        state.update_table(UNITS_TABLE, self._set_unit_fields(units, unit_key, {
            "readiness_status": current,
            "readiness_progress": 0.0,
            "readiness_transition_id": transition_row["id"],
            "readiness_eta_minute": transition_row["completes_at_minute"],
        }))
        state.update_table(TRANSITIONS_TABLE, updated_transitions)
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

    @staticmethod
    def _transition_duration_for_owner(state: GameState, owner_id: str, base_duration: int) -> int:
        if base_duration <= 0:
            return max(0, int(base_duration))
        effect = aggregate_political_effects(
            state.tables.get("political_effects"),
            int(state.time.total_minutes),
            domain="readiness",
            effect="transition_duration_modifier",
        ).get(str(owner_id or "").strip().upper(), 0.0)
        duration_factor = min(1.5, max(0.5, 1.0 + effect))
        return max(1, round(int(base_duration) * duration_factor))

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True

    @staticmethod
    def _set_unit_fields(
        units: pl.DataFrame,
        unit_id: str,
        values: dict[str, Any],
    ) -> pl.DataFrame:
        return units.with_columns(
            [
                pl.when(pl.col("id") == unit_id)
                .then(pl.lit(value).cast(units.schema[column], strict=False))
                .otherwise(pl.col(column))
                .alias(column)
                for column, value in values.items()
            ]
        )

    def _release_pending_order(self, state: GameState, unit_id: str, pending_order_id: str) -> None:
        pending = state.tables.get(PENDING_TABLE)
        if pending is None or pending.is_empty() or not {"unit_id", "status"}.issubset(pending.columns):
            return
        indexed = pending.with_row_index("_pending_row_order")
        selected = indexed.filter(
            (pl.col("unit_id").cast(pl.Utf8) == unit_id)
            & pl.col("status").cast(pl.Utf8).fill_null("").replace("", "queued").eq("queued")
        ).head(1)
        if selected.is_empty():
            return
        row_order = int(selected.get_column("_pending_row_order")[0])
        released = selected.drop("_pending_row_order").to_dicts()[0]
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
        remaining = indexed.filter(pl.col("_pending_row_order") != row_order).drop("_pending_row_order")
        state.update_table(PENDING_TABLE, remaining)

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

def cancel_readiness_for_contact(state: GameState, unit_ids: list[str], reason: str = "combat_contact") -> None:
    """Cancel transitions for units that entered contact before completion."""
    helper = ReadinessSystem()
    for unit_id in sorted({str(value) for value in unit_ids if value}):
        helper.cancel_transition_for_unit(state, unit_id, reason)
