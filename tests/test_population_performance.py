from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.demographics.population_system import PopulationSystem
from src.shared.state import GameState


def _build_state(region_count: int) -> GameState:
    country_count = 200
    regions = pl.DataFrame({
        "id": list(range(1, region_count + 1)),
        "owner": [f"C{index % country_count:03d}" for index in range(region_count)],
        "pop_14": [10_000] * region_count,
        "pop_15_64": [50_000] * region_count,
        "pop_65": [8_000] * region_count,
        "health_capacity": [0.8] * region_count,
    })
    countries = pl.DataFrame({
        "id": [f"C{index:03d}" for index in range(country_count)],
        "fertility_rate": [2.1] * country_count,
        "life_expectancy": [72.0] * country_count,
        "economic_health": [0.9] * country_count,
    })
    state = GameState(tables={"regions": regions, "countries": countries})
    ensure_base_tables(state)
    return state


@pytest.mark.skipif(
    os.environ.get("RUN_POPULATION_BENCHMARKS") != "1",
    reason="Set RUN_POPULATION_BENCHMARKS=1 to run the 10,000-region population benchmark.",
)
def test_population_update_for_ten_thousand_regions_stays_under_two_milliseconds() -> None:
    state = _build_state(10_000)
    system = PopulationSystem()

    for _ in range(5):
        system._apply_tfr_growth(state, days_passed=1.0)

    samples_ms = []
    for _ in range(31):
        started_at = time.perf_counter()
        system._apply_tfr_growth(state, days_passed=1.0)
        samples_ms.append((time.perf_counter() - started_at) * 1_000.0)

    median_ms = statistics.median(samples_ms)
    print(
        f"10,000-region population tick median: {median_ms:.3f} ms "
        f"(Polars threads: {pl.thread_pool_size()})"
    )
    assert median_ms < 2.0, f"10,000-region population tick median was {median_ms:.3f} ms"
