from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from src.client.visualization.map_modes.empire_mode import EmpireMapMode
from src.shared.state import GameState


def _build_state(region_count: int) -> GameState:
    country_tags = [f"C{index:03d}" for index in range(200)]
    country_tags[0] = "USA"
    treaty_members = ["USA", *country_tags[1:80]]
    enemy_members = country_tags[80:100]
    regions = pl.DataFrame({
        "id": list(range(1, region_count + 1)),
        "owner": [country_tags[index % len(country_tags)] for index in range(region_count)],
        "controller": [country_tags[index % len(country_tags)] for index in range(region_count)],
    })
    return GameState(tables={
        "regions": regions,
        "countries_treaties": pl.DataFrame({
            "type": ["military_alliance"],
            "members": [treaty_members],
            "status": ["active"],
        }),
        "countries_wars": pl.DataFrame({
            "side_a": [["USA"]],
            "side_b": [enemy_members],
            "status": ["active"],
        }),
    })


@pytest.mark.skipif(
    os.environ.get("RUN_EMPIRE_MAP_BENCHMARKS") != "1",
    reason="Set RUN_EMPIRE_MAP_BENCHMARKS=1 to run the full-region Empire color benchmark.",
)
def test_empire_focus_recalculates_all_region_colors_under_two_milliseconds() -> None:
    state = _build_state(4_559)
    mode = EmpireMapMode()
    focus_tags = ("USA", "C001")
    for index in range(5):
        mode.set_selected_country(focus_tags[index % len(focus_tags)])
        mode.calculate_colors(state)

    samples_ms = []
    for index in range(31):
        mode.set_selected_country(focus_tags[index % len(focus_tags)])
        started_at = time.perf_counter()
        mode.calculate_colors(state)
        samples_ms.append((time.perf_counter() - started_at) * 1_000.0)

    median_ms = statistics.median(samples_ms)
    print(f"4,559-region Empire map color median: {median_ms:.3f} ms")
    assert median_ms < 2.0, f"Empire map color recalculation median was {median_ms:.3f} ms"
