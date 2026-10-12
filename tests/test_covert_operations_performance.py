from __future__ import annotations

import os
import statistics
import time
from unittest.mock import patch

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.military.military_system import MovementDurationPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from src.shared.actions import ActionCreateCovertCell
from src.shared.state import GameState


def test_multiple_routes_share_one_index_and_next_update_sees_map_changes() -> None:
    region_count = 64
    regions = pl.DataFrame({
        "id": list(range(1, region_count + 1)),
        "owner": ["USA"] * (region_count - 1) + ["CAN"],
        "latitude": [0.0] * region_count,
        "longitude": [index * 0.1 for index in range(region_count)],
    })
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["USA", "CAN"], "gdp": [1000.0, 1000.0],
            "money_reserves": [1000.0, 1000.0],
        }),
        "regions": regions,
    })
    ensure_base_tables(state)
    state.update_table("region_adjacency", pl.DataFrame({
        "region_id": list(range(1, region_count)),
        "neighbor_region_id": list(range(2, region_count + 1)),
    }))
    state.current_actions = [
        ActionCreateCovertCell("USA", "USA", "CAN", "First"),
        ActionCreateCovertCell("USA", "USA", "CAN", "Second"),
    ]
    system = CovertOperationsSystem()
    original = MovementDurationPolicy.region_locations
    original_graph = MilitaryRoutePlanner._adjacency
    policy = MovementDurationPolicy()
    locations = original(policy, regions)
    expected_minutes = sum(
        policy.estimate_between(locations[left], locations[left + 1])
        for left in range(1, region_count)
    )

    with (
        patch.object(MovementDurationPolicy, "region_locations", autospec=True, side_effect=original) as build_index,
        patch.object(MilitaryRoutePlanner, "_adjacency", autospec=True, side_effect=original_graph) as build_graph,
    ):
        system.update(state, 0.0)
        assert build_index.call_count == 0
        assert build_graph.call_count == 1
        cells = state.get_table("covert_cells").to_dicts()
        assert len(cells) == 2
        assert all(cell["available_at_minute"] == expected_minutes for cell in cells)
        routes = state.get_table("covert_cell_routes").to_dicts()
        assert all(route["route_region_ids"] == list(range(1, region_count + 1)) for route in routes)
        assert all(route["arrival_at_minute"] == policy.estimate_between(locations[1], locations[2]) for route in routes)

        state.current_actions = []
        system.update(state, 0.0)
        assert build_index.call_count == 0
        assert build_graph.call_count == 1

        changed_regions = regions.with_columns((pl.col("longitude") * 5).alias("longitude"))
        state.update_table("regions", changed_regions)
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "CAN", "Changed map")]
        system.update(state, 0.0)
        assert build_index.call_count == 0
        assert build_graph.call_count == 2
        changed_locations = original(policy, changed_regions)
        changed_minutes = sum(
            policy.estimate_between(changed_locations[left], changed_locations[left + 1])
            for left in range(1, region_count)
        )
        assert changed_minutes != expected_minutes
        assert state.get_table("covert_cells").to_dicts()[-1]["available_at_minute"] == changed_minutes


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
