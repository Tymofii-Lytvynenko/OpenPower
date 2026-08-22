"""Reusable deterministic fixtures for tactical combat focused tests."""

from __future__ import annotations

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


def tactical_state(
    units: list[dict],
    wars: list[dict] | None = None,
    treaties: list[dict] | None = None,
    *,
    region_id: int = 1,
    owner: str = "CAN",
) -> GameState:
    return GameState(tables={
        "regions": pl.DataFrame({"id": [region_id], "owner": [owner], "controller": [owner], "latitude": [0.0], "longitude": [0.0]}),
        "units": pl.DataFrame(units, schema=UNIT_SCHEMA),
        "countries_wars": pl.DataFrame(wars or [{"id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active"}]),
        "countries_treaties": pl.DataFrame(treaties or [], schema={"id": pl.Utf8, "type": pl.Utf8, "status": pl.Utf8, "members": pl.List(pl.Utf8), "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8)}),
    })


def unit(unit_id: str, owner: str, strength: int = 100, region_id: int = 1) -> dict:
    return UnitFactory().create(unit_id, owner, "army", strength, region_id, GeoCoordinate(0.0, 0.0), 0)


def canonical_rows(frame: pl.DataFrame) -> list[dict]:
    return sorted(frame.to_dicts(), key=lambda row: tuple(str(value) for value in row.values()))
