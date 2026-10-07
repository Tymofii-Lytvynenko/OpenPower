from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from modules.base.systems.military.military_system import UNIT_SCHEMA, MilitarySystem, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


def _build_state(unit_count: int, region_count: int, *, moving: bool) -> tuple[GameState, pl.DataFrame]:
    factory = UnitFactory()
    unit_rows = []
    country_count = 200
    for index in range(unit_count):
        owner = f"C{index % country_count:03d}"
        unit = factory.create(
            f"{owner}-infantry-{index:05d}", owner, "infantry", 100, 1,
            GeoCoordinate(0.0, 0.0), 0,
        )
        if moving:
            unit.update(
                is_moving=True,
                source_region_id=1,
                source_latitude=0.0,
                source_longitude=0.0,
                target_region_id=2,
                target_latitude=0.0,
                target_longitude=1.0,
                departed_at_minute=0,
                arrival_at_minute=10_080,
                movement_progress=0.0,
            )
        unit_rows.append(unit)

    units = pl.DataFrame(unit_rows, schema=UNIT_SCHEMA)
    region_owners = [f"C{index % country_count:03d}" for index in range(region_count)]
    regions = pl.DataFrame({
        "id": list(range(1, region_count + 1)),
        "owner": region_owners,
        "pop_15_64": [1_000] * region_count,
        "latitude": [0.0] * region_count,
        "longitude": [0.0] * region_count,
    })
    state = GameState(tables={
        "units": units,
        "regions": regions,
        "countries": pl.DataFrame({"id": [f"C{index:03d}" for index in range(country_count)]}),
    })
    return state, units


@pytest.mark.skipif(
    os.environ.get("RUN_MILITARY_MOVEMENT_BENCHMARKS") != "1",
    reason="Set RUN_MILITARY_MOVEMENT_BENCHMARKS=1 to run the 10,000-unit movement benchmark.",
)
@pytest.mark.parametrize("moving", [False, True], ids=["stationary", "in-transit"])
def test_movement_and_manpower_tick_stays_under_two_milliseconds(moving: bool) -> None:
    unit_count = 10_000
    region_count = 4_561
    state, units = _build_state(unit_count, region_count, moving=moving)
    system = MilitarySystem()
    current_minute = 1_000 if moving else 0

    for _ in range(3):
        system._update_unit_movements(state, units, current_minute)
        system._update_manpower(state)

    samples_ms = []
    for _ in range(15):
        started_at = time.perf_counter()
        system._update_unit_movements(state, units, current_minute)
        system._update_manpower(state)
        samples_ms.append((time.perf_counter() - started_at) * 1_000.0)

    median_ms = statistics.median(samples_ms)
    assert median_ms < 2.0, f"10,000-unit {('in-transit' if moving else 'stationary')} movement/manpower tick median was {median_ms:.3f} ms"
