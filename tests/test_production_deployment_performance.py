from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("RUN_PRODUCTION_DEPLOYMENT_BENCHMARKS") != "1",
    reason="Set RUN_PRODUCTION_DEPLOYMENT_BENCHMARKS=1 to run the 50,000-order/100,000-route gate.",
)
def test_production_and_transit_scale_gate() -> None:
    order_count = 50_000
    transit_count = 100_000
    due_count = 1_000
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["AAA"], "gdp": [1_100_000.0], "economic_health": [1.0],
        }),
        "regions": pl.DataFrame({
            "id": [1, 2], "owner": ["AAA", "AAA"],
            "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
        }),
    })
    ensure_base_tables(state)
    order_schema = state.get_table("production_orders").schema
    orders = pl.DataFrame(
        [{
            "id": f"order-{index:05d}", "country_id": "AAA", "design_id": "design-aaa",
            "quantity": 1, "priority": index % 5 + 1, "status": "queued",
            "progress": 0.0, "unit_cost": 1_000.0, "work_required": 1_000.0,
            "remaining_work": 1_000.0, "assigned_capacity": 0.0,
        } for index in range(order_count)],
        schema=order_schema,
        strict=False,
    )
    state.update_table("production_orders", orders)

    units = pl.DataFrame({
        "id": [f"unit-{index:06d}" for index in range(transit_count)],
        "owner": ["AAA"] * transit_count,
        "unit_type": ["infantry"] * transit_count,
        "current_region_id": [0] * transit_count,
        "latitude": [0.0] * transit_count,
        "longitude": [0.0] * transit_count,
        "source_region_id": [1] * transit_count,
        "source_latitude": [0.0] * transit_count,
        "source_longitude": [0.0] * transit_count,
        "target_region_id": [2] * transit_count,
        "target_latitude": [0.0] * transit_count,
        "target_longitude": [1.0] * transit_count,
        "departed_at_minute": [0] * transit_count,
        "arrival_at_minute": [30] * due_count + [10_000] * (transit_count - due_count),
        "movement_progress": [0.0] * transit_count,
        "is_moving": [True] * transit_count,
        "training_facility_id": [""] * transit_count,
        "training_location_region_id": [0] * transit_count,
        "combat_defense_modifier": [1.0] * transit_count,
        "cohesion": [1.0] * transit_count,
        "reorganization_until_minute": [0] * transit_count,
        "unit_lifecycle": ["in_transit"] * transit_count,
    })
    movement_system = MilitarySystem()
    units = movement_system._normalize_units_table(units, state)
    route_schema = state.get_table("unit_movement_routes").schema
    routes = pl.DataFrame(
        [{
            "unit_id": f"unit-{index:06d}", "owner_country_id": "AAA",
            "source_region_id": 1, "destination_region_id": 2,
            "route_region_ids": [1, 2], "route_index": 1,
            "status": "in_transit", "updated_at_minute": 0,
        } for index in range(transit_count)],
        schema=route_schema,
        strict=False,
    )
    state.update_table("units", units)
    state.update_table("unit_movement_routes", routes)

    production_system = ResearchProgramSystem()
    samples_ms: list[float] = []
    production_samples_ms: list[float] = []
    movement_samples_ms: list[float] = []
    for sample_index in range(8):
        state.update_table("production_orders", orders)
        state.update_table("unit_movement_routes", routes)
        production_started_at = time.perf_counter()
        production_system._advance_production(state, 1.0 / 365.25)
        production_elapsed_ms = (time.perf_counter() - production_started_at) * 1_000.0
        movement_started_at = time.perf_counter()
        movement_system._update_unit_movements(state, units, 60)
        movement_elapsed_ms = (time.perf_counter() - movement_started_at) * 1_000.0
        elapsed_ms = production_elapsed_ms + movement_elapsed_ms
        if sample_index >= 3:
            samples_ms.append(elapsed_ms)
            production_samples_ms.append(production_elapsed_ms)
            movement_samples_ms.append(movement_elapsed_ms)

    median_ms = statistics.median(samples_ms)
    print(
        f"production/deployment: {order_count:,} orders + {transit_count:,} transit records "
        f"({due_count:,} due); median={median_ms:.2f}ms "
        f"samples={[round(value, 2) for value in samples_ms]}; "
        f"production_median={statistics.median(production_samples_ms):.2f}ms "
        f"movement_median={statistics.median(movement_samples_ms):.2f}ms"
    )
    assert median_ms < 1_000.0, "SC-007: production/deployment scale gate exceeds 1 second"
