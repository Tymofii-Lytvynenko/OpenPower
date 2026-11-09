from types import SimpleNamespace

import polars as pl
import pytest

import modules.base.systems.military.covert_mission_control as mission_control
from modules.base.systems.military.covert_mission_control import (
    control_prepared_mission,
)
from src.shared.actions import ActionCancelCovertMission, ActionExecuteCovertMission


def _state(duration=1, now=100):
    journal = []
    return SimpleNamespace(
        tables={
            "countries": pl.DataFrame({"id": ["CAN"]}),
            "regions": pl.DataFrame({"owner": ["CAN"]}),
        },
        globals={"covert_execution_minutes": duration},
        time=SimpleNamespace(total_minutes=now),
        journal=SimpleNamespace(append_command_result=journal.append),
    )


def _ready_records():
    mission = {
        "id": "mission-1",
        "cell_id": "cell-1",
        "owner_country_id": "USA",
        "target_country_id": "CAN",
        "status": "ready",
    }
    cell = {
        "id": "cell-1",
        "country_id": "USA",
        "status": "ready",
        "communications_ready": True,
        "location_country_id": "CAN",
        "target_country_id": "CAN",
    }
    return cell, mission


@pytest.fixture
def controlled_country(monkeypatch):
    monkeypatch.setattr(mission_control, "player_controls_country", lambda *_: True)


def test_cancel_rejects_missions_outside_preparation_or_ready(controlled_country):
    state = _state()
    cell, mission = _ready_records()
    mission["status"] = "executing"

    reason = control_prepared_mission(
        state,
        [cell],
        [mission],
        ActionCancelCovertMission("USA", "mission-1"),
    )

    assert reason == "Only a preparing or ready mission can be cancelled."


def test_execute_rejects_invalid_configured_duration(controlled_country):
    state = _state(duration="not-a-number")
    cell, mission = _ready_records()

    reason = control_prepared_mission(
        state,
        [cell],
        [mission],
        ActionExecuteCovertMission("USA", "mission-1"),
    )

    assert reason == "The configured mission execution duration is invalid."


def test_execute_rejects_resolution_time_overflow(controlled_country):
    state = _state(duration=2, now=9_223_372_036_854_775_806)
    cell, mission = _ready_records()

    reason = control_prepared_mission(
        state,
        [cell],
        [mission],
        ActionExecuteCovertMission("USA", "mission-1"),
    )

    assert reason == "The mission execution date exceeds the supported range."
