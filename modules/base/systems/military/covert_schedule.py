"""Decide whether the covert subsystem has work for the current tick."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl

from src.shared.actions import (
    ActionCancelCovertMission,
    ActionCreateCovertCell,
    ActionExecuteCovertMission,
    ActionRetargetCovertCell,
    ActionRetireCovertCell,
    ActionSetCovertCellActivity,
    ActionSetCovertCellAssignment,
    ActionStartCovertMission,
    ActionTrainCovertCell,
)
from src.shared.events import EventNewDay, EventRealSecond, EventUnitReadinessStarted


_REQUIRED_TABLES = frozenset(
    {
        "covert_cells",
        "covert_cell_routes",
        "covert_missions",
        "covert_findings",
        "covert_incidents",
    }
)
_COVERT_ACTION_TYPES = (
    ActionCreateCovertCell,
    ActionExecuteCovertMission,
    ActionRetargetCovertCell,
    ActionSetCovertCellActivity,
    ActionCancelCovertMission,
    ActionTrainCovertCell,
    ActionStartCovertMission,
    ActionSetCovertCellAssignment,
    ActionRetireCovertCell,
)


@dataclass(frozen=True, slots=True)
class UpdateScheduleServices:
    finite_number: Callable[[Any], float]


def update_schedule(
    state: Any, *, services: UpdateScheduleServices
) -> tuple[int, float, bool] | None:
    if not _REQUIRED_TABLES.issubset(state.tables):
        return None

    cells_frame = state.get_table("covert_cells")
    missions_frame = state.get_table("covert_missions")
    now = int(state.time.total_minutes)
    elapsed_days = sum(
        max(0.0, services.finite_number(event.game_seconds_passed)) / 86400.0
        for event in state.events
        if isinstance(event, EventRealSecond) and not event.is_paused
    )
    upkeep_boundary = not state.time.is_paused and any(
        isinstance(event, EventNewDay) for event in state.events
    )
    has_actions = any(
        isinstance(action, _COVERT_ACTION_TYPES) for action in state.current_actions
    )
    has_cell_motion = _has_status(cells_frame, {"transit", "transit_blocked"})
    has_training = _has_status(cells_frame, {"training"}) and (
        elapsed_days > 0.0 or _has_due_training(cells_frame, now)
    )
    has_preparation = _has_status(missions_frame, {"preparation"})
    has_due_mission = _has_due_missions(missions_frame, now)
    has_mobilization = any(
        isinstance(event, EventUnitReadinessStarted) for event in state.events
    )
    has_active_upkeep = upkeep_boundary and _has_status(
        cells_frame, {"active", "idle"}
    )
    if not any(
        (
            has_actions,
            has_cell_motion,
            has_training,
            has_preparation,
            has_due_mission,
            has_mobilization,
            has_active_upkeep,
        )
    ):
        return None
    return now, elapsed_days, upkeep_boundary


def _has_status(frame: pl.DataFrame, statuses: set[str]) -> bool:
    return "status" in frame.columns and not frame.filter(
        pl.col("status").is_in(statuses)
    ).is_empty()


def _has_due_missions(missions: pl.DataFrame, now: int) -> bool:
    if missions.is_empty() or not {
        "status",
        "cleanup_until_minute",
        "resolves_at_minute",
    }.issubset(missions.columns):
        return False
    status = pl.col("status").cast(pl.Utf8).fill_null("")
    cleanup_due = (status == "cleanup") & (
        pl.col("cleanup_until_minute").fill_null(0) <= now
    )
    execution_due = (status == "executing") & (
        pl.col("resolves_at_minute").fill_null(0) <= now
    )
    return not missions.filter(cleanup_due | execution_due).is_empty()


def _has_due_training(cells: pl.DataFrame, now: int) -> bool:
    if cells.is_empty() or not {
        "status",
        "training_completes_at_minute",
    }.issubset(cells.columns):
        return False
    status = pl.col("status").cast(pl.Utf8).fill_null("")
    due = (status == "training") & (
        pl.col("training_completes_at_minute")
        .cast(pl.Int64, strict=False)
        .fill_null(0)
        <= now
    )
    return not cells.filter(due).is_empty()
