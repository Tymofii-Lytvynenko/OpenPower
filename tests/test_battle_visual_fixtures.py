"""Small deterministic inputs shared by tactical battle visualization tests."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.client.controllers.camera_controller import CameraController
from src.client.services.client_game_clock import ClientGameClock
from src.shared.state import TimeData


def build_battle_row(index: int = 1, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"battle-{index:03d}",
        "region_id": index,
        "anchor_latitude": 0.0,
        "anchor_longitude": float(index - 1),
        "anchor_source": "region_center",
        "attacker_side": "USA",
        "defender_side": "CAN",
        "mode": "positional",
        "status": "active",
        "round": 0,
        "started_at_minute": 0,
        "concluded_at_minute": 0,
    }
    row.update(overrides)
    return row


def build_battle_frame(count: int = 1, **overrides: Any) -> pl.DataFrame:
    return pl.DataFrame([build_battle_row(index, **overrides) for index in range(1, count + 1)])


def build_region_row(region_id: int = 1, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": region_id,
        "latitude": 10.0 + region_id,
        "longitude": -20.0 + region_id,
        "owner": "CAN",
        "controller": "CAN",
    }
    row.update(overrides)
    return row


def build_region_frame(count: int = 1, **overrides: Any) -> pl.DataFrame:
    return pl.DataFrame([build_region_row(index, **overrides) for index in range(1, count + 1)])


def build_unit_row(unit_id: str = "unit-1", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": unit_id,
        "owner": "USA",
        "strength": 100,
        "current_region_id": 1,
        "latitude": 0.0,
        "longitude": 179.0,
        "is_moving": False,
    }
    row.update(overrides)
    return row


def build_unit_frame(count: int = 1, **overrides: Any) -> pl.DataFrame:
    return pl.DataFrame(
        [build_unit_row(f"unit-{index:03d}", **overrides) for index in range(1, count + 1)]
    )


def build_camera(**overrides: Any) -> CameraController:
    camera = CameraController()
    for name, value in overrides.items():
        setattr(camera, name, value)
    return camera


def build_presentation_clock(total_minutes: int = 0, *, paused: bool = True) -> ClientGameClock:
    clock = ClientGameClock()
    clock.sync(TimeData(total_minutes=total_minutes, is_paused=paused))
    return clock

