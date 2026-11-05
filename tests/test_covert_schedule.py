from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.covert_schedule import (
    UpdateScheduleServices,
    update_schedule,
)
from src.shared.events import EventRealSecond


class _ScheduleState:
    def __init__(self, *, cells, missions, events=(), paused=False):
        self.tables = {
            "covert_cells": cells,
            "covert_cell_routes": pl.DataFrame(),
            "covert_missions": missions,
            "covert_findings": pl.DataFrame(),
            "covert_incidents": pl.DataFrame(),
        }
        self.time = SimpleNamespace(total_minutes=42, is_paused=paused)
        self.events = list(events)
        self.current_actions = []

    def get_table(self, name):
        return self.tables[name]


def _services():
    return UpdateScheduleServices(finite_number=lambda value: float(value or 0.0))


def test_schedule_runs_training_for_elapsed_unpaused_time():
    state = _ScheduleState(
        cells=pl.DataFrame({"status": ["training"]}),
        missions=pl.DataFrame(schema={"status": pl.Utf8}),
        events=[EventRealSecond(game_seconds_passed=172800, is_paused=False)],
    )

    assert update_schedule(state, services=_services()) == (42, 2.0, False)


def test_schedule_ignores_paused_idle_updates():
    state = _ScheduleState(
        cells=pl.DataFrame({"status": ["active"]}),
        missions=pl.DataFrame(schema={"status": pl.Utf8}),
        events=[EventRealSecond(game_seconds_passed=3600, is_paused=True)],
        paused=True,
    )

    assert update_schedule(state, services=_services()) is None


def test_schedule_runs_mission_when_its_execution_boundary_is_due():
    state = _ScheduleState(
        cells=pl.DataFrame(schema={"status": pl.Utf8}),
        missions=pl.DataFrame(
            {
                "status": ["executing"],
                "cleanup_until_minute": [0],
                "resolves_at_minute": [42],
            }
        ),
    )

    assert update_schedule(state, services=_services()) == (42, 0.0, False)
