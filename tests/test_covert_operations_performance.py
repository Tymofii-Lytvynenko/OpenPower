from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from src.shared.state import GameState


def _large_pending_state(cell_count: int = 5_000, mission_count: int = 1_000) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["OWNER", "TARGET"],
                    "gdp": [1_000.0, 1_000.0],
                    "money_reserves": [1_000.0, 1_000.0],
                }
            ),
            "regions": pl.DataFrame(
                {"id": [1, 2], "owner": ["OWNER", "TARGET"]}
            ),
        }
    )
    ensure_base_tables(state)

    cell_template = state.get_table("covert_cells")
    cells = [
        {
            "id": f"cell-{index:05d}",
            "country_id": "OWNER",
            "target_country_id": "TARGET",
            "status": "preparing" if index < mission_count else "active",
            "location_country_id": "TARGET",
            "assignment": "espionage",
            "upkeep": 0.0,
        }
        for index in range(cell_count)
    ]
    state.update_table(
        "covert_cells", pl.DataFrame(cells, schema=cell_template.schema, strict=False)
    )

    mission_template = state.get_table("covert_missions")
    missions = [
        {
            "id": f"mission-{index:05d}",
            "cell_id": f"cell-{index:05d}",
            "owner_country_id": "OWNER",
            "target_country_id": "TARGET",
            "mission_type": "civilian_espionage",
            "status": "preparation",
            "preparation_required": 60.0,
            "created_at_minute": 0,
            "resolves_at_minute": 60,
        }
        for index in range(mission_count)
    ]
    state.update_table(
        "covert_missions", pl.DataFrame(missions, schema=mission_template.schema, strict=False)
    )
    return state


@pytest.mark.skipif(
    os.environ.get("RUN_COVERT_BENCHMARKS") != "1",
    reason="Set RUN_COVERT_BENCHMARKS=1 to run the controlled 5,000-cell benchmark.",
)
def test_pending_mission_update_stays_below_half_second() -> None:
    state = _large_pending_state()
    system = CovertOperationsSystem()
    system.update(state, 0.0)

    samples = []
    for _ in range(5):
        started = time.perf_counter()
        system.update(state, 0.0)
        samples.append(time.perf_counter() - started)

    median_ms = statistics.median(samples) * 1_000.0
    print(f"covert update median={median_ms:.2f}ms samples={[round(value * 1_000.0, 2) for value in samples]}")
    assert median_ms < 500.0, "SC-007: covert update exceeds the 500 ms gate"
