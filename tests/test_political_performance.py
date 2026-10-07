from __future__ import annotations

from statistics import median
from time import perf_counter

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.state import GameState


def test_unchanged_political_lifecycle_for_ten_thousand_countries_stays_below_half_second():
    country_count = 10_000
    country_ids = [f"C{index:05d}" for index in range(country_count)]
    state = GameState(tables={"countries": pl.DataFrame({"id": country_ids})})
    ensure_base_tables(state)
    system = PoliticalLifecycleSystem()

    system.update(state, 0.0)
    system.update(state, 0.0)
    stable_revisions = dict(state.table_revisions)

    samples = []
    for _ in range(3):
        started = perf_counter()
        system.update(state, 0.0)
        samples.append(perf_counter() - started)
        assert state.table_revisions == stable_revisions

    measured = median(samples)
    print(
        f"political lifecycle benchmark: {country_count:,} unchanged countries; "
        f"median {measured:.3f}s over {len(samples)} runs"
    )
    assert measured < 0.5, f"10k unchanged political lifecycle took {measured:.3f}s"
