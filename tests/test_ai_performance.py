from __future__ import annotations

import os
import platform
import sys
from statistics import median
from time import perf_counter

import polars as pl
import pytest

from modules.base.systems.world.ai.budget_policy import BudgetSurvivalPolicy
from modules.base.systems.world.ai.military_policies import MilitaryROIPolicy
from src.core.ai_framework import AITableContext, DeclarativeAIFramework

AI_FRAMEWORK_TARGET_MS = 2.0


def build_ai_benchmark_context(country_count: int = 220) -> AITableContext:
    countries = pl.DataFrame(
        {
            "id": [f"C{index:03d}" for index in range(country_count)],
            "is_playable": [True] * country_count,
            "gdp": [1_000_000_000.0] * country_count,
            "human_dev": [0.5] * country_count,
            "military_count": [0] * country_count,
            "trait_threat_perception": [1.0] * country_count,
            "money_reserves": [100.0] * (country_count // 2)
            + [10_000_000.0] * (country_count - country_count // 2),
            "total_annual_revenue": [100_000.0] * (country_count // 2)
            + [200_000.0] * (country_count - country_count // 2),
            "total_annual_expense": [1_000_000.0] * (country_count // 2)
            + [100_000.0] * (country_count - country_count // 2),
        }
    )
    return AITableContext(
        tables={"countries": countries},
        day_ordinal=0,
        total_minutes=0,
        date_text="2001-01-01 00:00",
    )


@pytest.mark.skipif(
    os.environ.get("RUN_AI_BENCHMARKS") != "1",
    reason="Set RUN_AI_BENCHMARKS=1 to run the 220-country AI scorer benchmark.",
)
def test_budget_and_military_roi_score_two_hundred_twenty_countries_under_two_milliseconds() -> None:
    country_count = 220
    context = build_ai_benchmark_context(country_count)
    budget = BudgetSurvivalPolicy()
    roi = MilitaryROIPolicy()
    budget.cadence_days = 1
    roi.cadence_days = 1
    state_lf = pl.concat(
        [budget.build_candidates(context), roi.build_candidates(context)],
        how="diagonal_relaxed",
    )

    state_lf.collect()
    samples = []
    decisions = None
    for _ in range(5):
        started = perf_counter()
        decisions = state_lf.collect()
        samples.append(perf_counter() - started)
    elapsed = median(samples)

    assert decisions is not None
    assert decisions.filter(pl.col("policy_id") == "budget_survival").height == country_count // 2
    assert decisions.filter(pl.col("policy_id") == "military_roi").height == country_count - country_count // 2
    print(
        f"AI benchmark: {country_count:,} countries, financial + military ROI; "
        f"median {elapsed * 1_000:.2f} ms, {pl.thread_pool_size()} Polars thread(s), "
        f"Python {sys.version.split()[0]} on {platform.platform()}"
    )
    assert elapsed < 0.002, f"AI evaluation took {elapsed * 1_000:.2f} ms"


@pytest.mark.skipif(
    os.environ.get("RUN_AI_BENCHMARKS") != "1",
    reason="Set RUN_AI_BENCHMARKS=1 to run the complete 220-country AI framework benchmark.",
)
def test_framework_ranking_and_action_resolution_for_two_hundred_twenty_countries() -> None:
    assert os.environ.get("POLARS_MAX_THREADS") == "1", (
        "The controlled AI benchmark pins one Polars worker thread; set POLARS_MAX_THREADS=1 "
        "before starting Python."
    )
    assert pl.thread_pool_size() == 1

    country_count = 220
    budget = BudgetSurvivalPolicy()
    roi = MilitaryROIPolicy()
    budget.cadence_days = 1
    roi.cadence_days = 1
    framework = DeclarativeAIFramework(budget, roi)
    context = build_ai_benchmark_context(country_count)

    warmup = framework.evaluate(context)
    assert len(warmup.actions) == country_count
    samples = []
    evaluation = warmup
    for _ in range(11):
        started = perf_counter()
        evaluation = framework.evaluate(context)
        samples.append(perf_counter() - started)

    elapsed = median(samples)
    assert evaluation.decisions.height == country_count
    assert len(evaluation.actions) == country_count
    assert evaluation.skipped_policies == ()
    print(
        f"AI framework benchmark: {country_count:,} countries, {len(evaluation.actions):,} actions; "
        f"median {elapsed * 1_000:.2f} ms, {pl.thread_pool_size()} Polars thread(s), "
        f"Python {sys.version.split()[0]} on {platform.platform()}; "
        f"framework target {'met' if elapsed * 1_000 < AI_FRAMEWORK_TARGET_MS else 'missed'} "
        f"({AI_FRAMEWORK_TARGET_MS:.2f} ms)"
    )
