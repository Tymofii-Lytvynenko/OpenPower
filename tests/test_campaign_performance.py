from __future__ import annotations

import os
import time

import polars as pl
import pytest

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.campaign_system import CampaignSystem
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("OPENPOWER_PERFORMANCE_TESTS") != "1",
    reason="Set OPENPOWER_PERFORMANCE_TESTS=1 to run controlled performance gates.",
)
def test_campaign_evaluates_ten_thousand_objectives_and_five_thousand_advisor_signals() -> None:
    state = GameState(tables={
        "countries": pl.DataFrame({"id": ["USA"], "gdp": [1000.0], "population": [100.0]}),
    })
    registry = build_base_schema_registry()
    registry.capture_state(state)
    registry.ensure_state(state)
    scenario = state.get_table("campaign_scenarios")
    state.update_table("campaign_scenarios", pl.DataFrame([{
        "id": "performance", "title": "Performance gate", "sandbox_allowed": True,
        "enabled": True, "objectives_json": "[]", "win_conditions_json": "{}", "loss_conditions_json": "{}",
    }], schema=scenario.schema, strict=False))
    campaigns = state.get_table("campaigns")
    state.update_table("campaigns", pl.DataFrame([{
        "id": "campaign-performance", "scenario_id": "performance", "actor_country_id": "USA",
        "outcome": "ongoing", "started_at_minute": 0, "sandbox_allowed": True,
    }], schema=campaigns.schema, strict=False))
    state.update_table("research_tracks", pl.DataFrame([{
        "id": "usa-strategic", "country_id": "USA", "branch": "strategic", "research_level": 1,
    }], schema=state.get_table("research_tracks").schema, strict=False))
    state.update_table("objectives", pl.DataFrame([
        {
            "id": f"objective-{index:05d}", "campaign_id": "campaign-performance", "country_id": "USA",
            "actor_id": "USA", "objective_type": "research_level", "target_branch": "strategic",
            "target_value": 1.0, "current_value": 0.0, "progress": 0.0, "required": False,
            "status": "active", "reason": "Condition is not yet satisfied.", "comparison": "at_least",
            "last_evaluated_at_minute": 0, "deadline_at_minute": -1, "hold_started_at_minute": -1,
            "evidence_json": "[]",
        }
        for index in range(10_000)
    ], schema=state.get_table("objectives").schema, strict=False))
    state.update_table("messages", pl.DataFrame([
        {
            "id": f"message-{index:05d}", "country_id": "USA", "category": "economy",
            "subject": "Advisor signal", "body": "Review this signal.", "is_read": False,
        }
        for index in range(5_000)
    ], schema=state.get_table("messages").schema, strict=False))

    started = time.perf_counter()
    system = CampaignSystem()
    phase_times = {}
    for name, phase in (
        ("objectives", system._evaluate_objectives),
        ("outcomes", system._evaluate_campaign_outcomes),
        ("advisor", system._refresh_recommendations),
        ("rules", system._publish_active_rules),
    ):
        phase_started = time.perf_counter()
        phase(state)
        phase_times[name] = time.perf_counter() - phase_started
    elapsed = time.perf_counter() - started

    assert state.get_table("objectives").filter(pl.col("status") == "completed").height == 10_000
    assert state.get_table("advisor_recommendations").height == 5_000
    print(
        f"Campaign gate: 10,000 objectives and 5,000 advisor signals in {elapsed * 1000:.2f} ms "
        f"(phases: {', '.join(f'{name}={value * 1000:.2f} ms' for name, value in phase_times.items())})"
    )
    assert elapsed < 0.5, f"Campaign evaluation took {elapsed * 1000:.2f} ms"
