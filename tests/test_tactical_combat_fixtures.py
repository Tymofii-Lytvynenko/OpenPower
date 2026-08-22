"""Reusable deterministic fixtures for tactical combat focused tests."""

from __future__ import annotations

from dataclasses import asdict

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.events import EventNewHour
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


def canonical_tactical_result(state: GameState) -> dict:
    table_names = (
        "units",
        "battles",
        "battle_units",
        "battle_participants",
        "occupations",
        "regions",
    )
    return {
        "tables": {
            name: canonical_rows(state.tables[name])
            for name in table_names
            if name in state.tables
        },
        "events": [
            {"type": type(event).__name__, "payload": asdict(event)}
            for event in state.events
        ],
    }


def replay_fixture_state() -> GameState:
    factory = UnitFactory()
    attacker = factory.create("usa-1", "USA", "army", 120, 1, GeoCoordinate(0.0, 0.0), 0)
    defender = factory.create("can-1", "CAN", "army", 100, 1, GeoCoordinate(0.0, 0.0), 0)
    attacker["readiness_status"] = "ready"
    defender["readiness_status"] = "ready"
    return GameState(tables={
        "regions": pl.DataFrame({"id": [1], "owner": ["CAN"], "controller": ["CAN"], "latitude": [0.0], "longitude": [0.0]}),
        "units": pl.DataFrame([attacker, defender], schema=UNIT_SCHEMA),
        "countries_wars": pl.DataFrame({"id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}),
    })


def run_replay_fixture() -> dict:
    state = replay_fixture_state()
    combat = CombatSystem()
    combat.update(state, 0.0)
    state.time.total_minutes = 60
    state.events.append(EventNewHour(hour=1, total_minutes=60))
    combat.update(state, 0.0)
    return canonical_tactical_result(state)
