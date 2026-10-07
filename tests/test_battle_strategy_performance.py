from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("RUN_BATTLE_STRATEGY_BENCHMARKS") != "1",
    reason="Set RUN_BATTLE_STRATEGY_BENCHMARKS=1 to run the 10,000-posture/2,000-battle gate.",
)
def test_battle_strategy_due_work_scale_gate() -> None:
    posture_count = 10_000
    battle_count = 2_000
    due_count = 250
    state = GameState(tables={
        "regions": pl.DataFrame({
            "id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0],
        }),
        "units": pl.DataFrame(schema=UNIT_SCHEMA),
        "battles": pl.DataFrame([{
            "id": f"battle-{index:05d}", "region_id": 1, "status": "active",
        } for index in range(battle_count)], schema={
            "id": pl.Utf8, "region_id": pl.Int32, "status": pl.Utf8,
        }),
    })
    ensure_base_tables(state)
    units = []
    postures = []
    factory = UnitFactory()
    for index in range(posture_count):
        unit_id = f"unit-{index:05d}"
        units.append(factory.create(
            unit_id, "USA", "infantry", 100, 1, GeoCoordinate(10.0, 20.0), 0,
        ))
        due = index < due_count
        postures.append({
            "unit_id": unit_id,
            "battle_id": f"battle-{index % battle_count:05d}",
            "country_id": "USA",
            "strategy": "reorganize" if due else "hold",
            "issuer_player_id": "USA",
            "effective_at_minute": 0,
            "expires_at_minute": 100 if due else 0,
            "reason": "Benchmark due work" if due else "",
            "attack_modifier": 1.0,
            "defense_modifier": 1.0,
            "casualty_modifier": 1.0,
            "status": "reorganizing" if due else "active",
        })
    units_frame = pl.DataFrame(units, schema=UNIT_SCHEMA)
    posture_frame = pl.DataFrame(postures, schema=state.get_table("battle_force_postures").schema)
    system = BattleStrategySystem()
    state.time.total_minutes = 100
    samples_ms: list[float] = []

    for sample_index in range(8):
        state.update_table("units", units_frame)
        state.update_table("battle_force_postures", posture_frame)
        started_at = time.perf_counter()
        system.update(state, 0.0)
        elapsed_ms = (time.perf_counter() - started_at) * 1_000.0
        if sample_index >= 3:
            samples_ms.append(elapsed_ms)

    median_ms = statistics.median(samples_ms)
    print(
        f"battle strategy: {posture_count:,} postures + {battle_count:,} battles "
        f"({due_count:,} due); median={median_ms:.2f}ms "
        f"samples={[round(value, 2) for value in samples_ms]}"
    )
    assert median_ms < 500.0, "SC-007: battle-strategy due-work gate exceeds 500 ms"
