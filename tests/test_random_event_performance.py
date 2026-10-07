from __future__ import annotations

from time import perf_counter

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.state import GameState


def test_due_lifecycle_updates_ten_thousand_instances_and_one_hundred_thousand_effects_under_one_second():
    state = GameState()
    build_base_schema_registry().ensure_state(state)
    now = 1_440
    instance_count = 10_000
    effects_per_instance = 10
    event_ids = [f"perf-event-{index:05d}" for index in range(instance_count)]
    instance_rows = [
        {
            "id": event_id,
            "event_type": "epidemic",
            "label": "Performance event",
            "category": "health",
            "target_scope": "region",
            "region_id": 1,
            "country_id": "AAA",
            "seed": index + 1,
            "triggered_at_minute": 0,
            "starts_at_minute": 0,
            "expires_at_minute": now,
            "severity": 0.5,
            "status": "active",
            "response_id": "",
            "response_country_id": "",
            "effects_json": "[]",
            "response_options_json": "[]",
            "recovery_state_json": "{}",
            "reason": "benchmark fixture",
            "next_update_at_minute": now,
        }
        for index, event_id in enumerate(event_ids)
    ]
    instance_schema = state.get_table("random_event_instances").schema
    state.update_table(
        "random_event_instances",
        pl.DataFrame(instance_rows, schema=instance_schema, strict=False),
    )
    effect_rows = [
        {
            "id": f"{event_id}:effect:{effect_index}",
            "event_id": event_id,
            "category": "health",
            "subject_type": "country",
            "subject_id": "AAA",
            "magnitude": -0.01,
            "unit": "index",
            "application_mode": "recurring",
            "starts_at_minute": 0,
            "expires_at_minute": now,
            "last_applied_at_minute": 0,
            "status": "active",
            "mitigation_pending": False,
            "recovery_state_json": "{}",
        }
        for event_id in event_ids
        for effect_index in range(effects_per_instance)
    ]
    effect_schema = state.get_table("random_event_effects").schema
    state.update_table(
        "random_event_effects",
        pl.DataFrame(effect_rows, schema=effect_schema, strict=False),
    )
    state.globals["random_event_state_version"] = 1
    state.time.total_minutes = now

    started = perf_counter()
    RandomEventsSystem().update(state, 0.0)
    elapsed = perf_counter() - started

    assert state.get_table("random_event_instances").filter(pl.col("status") == "resolved").height == instance_count
    assert state.get_table("random_event_effects").filter(pl.col("status") == "resolved").height == instance_count * effects_per_instance
    assert elapsed < 1.0, f"10k/100k lifecycle processing took {elapsed:.3f}s"
