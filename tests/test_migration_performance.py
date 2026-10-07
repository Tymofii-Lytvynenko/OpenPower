from __future__ import annotations

import os
from time import perf_counter

import polars as pl
import pytest

from modules.base.schema import build_base_schema_registry
from modules.base.systems.demographics.migration_system import MigrationSystem
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("RUN_MIGRATION_BENCHMARKS") != "1",
    reason="Set RUN_MIGRATION_BENCHMARKS=1 to run the controlled flow scale benchmark.",
)
def test_due_flow_processing_scales_with_due_rows_in_large_pending_table():
    pending_count = 10_000
    due_count = 100
    now = 1_440
    state = GameState(tables={
        "countries": pl.DataFrame({"id": ["AAA"]}),
        "regions": pl.DataFrame({
            "id": [1, 2],
            "owner": ["AAA", "AAA"],
            "pop_14": [0, 0],
            "pop_15_64": [1_000_000, 0],
            "pop_65": [0, 0],
            "housing_capacity": [1_000_000, 1_000_000],
            "employment_capacity": [1_000_000, 1_000_000],
            "service_capacity": [1_000_000, 1_000_000],
            "transport_capacity": [1_000_000, 1_000_000],
            "transport_access": [1.0, 1.0],
        }),
    })
    build_base_schema_registry().ensure_state(state)
    flow_schema = state.get_table("migration_flows").schema
    flows = pl.DataFrame([
        {
            "id": f"flow-{index:05d}",
            "origin_region_id": 1,
            "destination_region_id": 2,
            "origin_country_id": "AAA",
            "destination_country_id": "AAA",
            "dependent_count": 0,
            "working_age_count": 1,
            "elderly_count": 0,
            "population_count": 1,
            "reason_code": "eligible_domestic",
            "reason_factors_json": "{}",
            "created_at_minute": 0,
            "authorized_at_minute": 0,
            "expected_completion_at_minute": now if index < due_count else now + 10_000,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": "pending",
        }
        for index in range(pending_count)
    ], schema=flow_schema, strict=False)
    state.update_table("migration_flows", flows)

    system = MigrationSystem()
    started = perf_counter()
    completed = system._complete_due_flows(state, now)
    elapsed = perf_counter() - started

    resulting = state.get_table("migration_flows")
    assert len(completed) == due_count
    assert resulting.filter(pl.col("status") == "completed").height == due_count
    future_flows = resulting.filter(pl.col("expected_completion_at_minute") > now)
    assert future_flows.height == pending_count - due_count
    assert future_flows.filter(
        (pl.col("expected_completion_at_minute") > now) & (pl.col("status") != "pending")
    ).is_empty()
    assert state.get_table("regions").sort("id")["pop_15_64"].to_list() == [999_900, 100]
    print(
        f"migration benchmark: {pending_count:,} pending flows, {due_count:,} due; {elapsed:.3f}s"
    )
    assert elapsed < 0.25, f"Processing {due_count:,} due flows took {elapsed:.3f}s"
