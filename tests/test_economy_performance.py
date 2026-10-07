from __future__ import annotations

import os
from statistics import median
from time import perf_counter

import polars as pl
import pytest

from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.economy.trade_system import TradeSystem
from src.shared.economy_meta import RESOURCE_MAPPING
from src.shared.events import EventRealSecond
from src.shared.state import GameState


def build_economy_benchmark_state(country_count: int = 220) -> GameState:
    country_ids = [f"C{index:03d}" for index in range(country_count)]
    resources = tuple(RESOURCE_MAPPING)
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": country_ids,
                    "gdp": [100_000_000.0] * country_count,
                    "gdp_per_capita": [10_000.0] * country_count,
                    "poverty_rate": [0.2] * country_count,
                    "human_dev": [0.8] * country_count,
                    "real_income_index": [1.0] * country_count,
                    "economic_trade_modifier": [1.0] * country_count,
                    "economic_policy_modifier": [1.0] * country_count,
                    "internal_tax_rate": [0.2] * country_count,
                    "industrial_growth_rate": [0.025] * country_count,
                    "personal_income_tax_rate": [0.2] * country_count,
                    "money_reserves": [1_000_000.0] * country_count,
                    "corruption_index": [0.0] * country_count,
                    "military_count": [0] * country_count,
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": list(range(1, country_count + 1)),
                    "owner": country_ids,
                    "pop_14": [2_000] * country_count,
                    "pop_15_64": [7_000] * country_count,
                    "pop_65": [1_000] * country_count,
                }
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": [country for country in country_ids for _ in resources],
                    "game_resource_id": [resource for _ in country_ids for resource in resources],
                    "domestic_production": [100.0] * (country_count * len(resources)),
                    "is_gov_controlled": [False] * (country_count * len(resources)),
                    "is_legal": [True] * (country_count * len(resources)),
                    "tax_rate": [0.05] * (country_count * len(resources)),
                }
            ),
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": [country for country in country_ids for _ in resources],
                    "game_resource_id": [resource for _ in country_ids for resource in resources],
                    "consumption_usd": [80.0] * (country_count * len(resources)),
                }
            ),
        }
    )
    state.events = [EventRealSecond(game_seconds_passed=1.0, is_paused=False)]
    return state


@pytest.mark.skipif(
    os.environ.get("RUN_ECONOMY_BENCHMARKS") != "1",
    reason="Set RUN_ECONOMY_BENCHMARKS=1 to run the controlled 220-country economy benchmark.",
)
def test_full_economy_tick_for_two_hundred_twenty_countries_under_five_milliseconds():
    country_count = 220
    resources = tuple(RESOURCE_MAPPING)
    state = build_economy_benchmark_state(country_count)
    systems = (TradeSystem(), InternalEconomySystem(), BudgetSystem())

    for system in systems:
        system.update(state, 0.0)

    samples = {system.id: [] for system in systems}
    for _ in range(5):
        for system in systems:
            started = perf_counter()
            system.update(state, 0.0)
            samples[system.id].append(perf_counter() - started)

    measured = sum(median(system_samples) for system_samples in samples.values())
    print(
        f"economy benchmark: {country_count:,} countries, "
        f"{country_count * len(resources):,} resource rows; "
        + ", ".join(
            f"{system_id} {median(system_samples) * 1_000:.2f} ms"
            for system_id, system_samples in samples.items()
        )
        + f"; combined {measured * 1_000:.2f} ms"
    )
    assert measured < 0.005, (
        f"Full economy tick for {country_count:,} countries took "
        f"{measured * 1_000:.2f} ms"
    )
