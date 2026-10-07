from __future__ import annotations

import cProfile
import io
import json
import math
import os
import platform
import pstats
import statistics
import time

import polars as pl
import pytest

from modules.base.systems.military.capability_system import (
    _PROJECTION_SCHEMA,
    MilitaryCapabilitySystem,
)
from src.shared.state import GameState


_UNIT_COUNT = 50_000
_DESIGN_COUNT = 10_000
_CHANGED_COUNT = _UNIT_COUNT // 20
_SAMPLE_COUNT = 5


def _percentile_95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _benchmark_state() -> tuple[GameState, list[dict[str, object]]]:
    design_roles = ("infantry", "tanks", "fighters", "frigates")
    design_ids = [f"design-{index:05d}" for index in range(_DESIGN_COUNT)]
    role_by_design = [design_roles[index % len(design_roles)] for index in range(_DESIGN_COUNT)]
    domain_by_role = {
        "infantry": "land",
        "tanks": "land",
        "fighters": "air",
        "frigates": "naval",
    }
    design_frame = pl.DataFrame(
        {
            "id": design_ids,
            "class_name": role_by_design,
            "domain": [domain_by_role[role] for role in role_by_design],
            "branch": [domain_by_role[role] for role in role_by_design],
            "capabilities_json": [
                json.dumps({"speed": float(40 + index % 100), "armor": float(index % 80)})
                for index in range(_DESIGN_COUNT)
            ],
            "valid_targets_json": ['["infantry","armor"]'] * _DESIGN_COUNT,
            "vulnerabilities_json": ['["air"]'] * _DESIGN_COUNT,
        }
    )
    research_rows = [
        {
            "id": f"research-{country:03d}-{domain}",
            "country_id": f"C{country:03d}",
            "branch": domain,
            "research_level": country % 6,
        }
        for country in range(100)
        for domain in ("land", "air", "naval")
    ]
    units: list[dict[str, object]] = [
        {
            "id": f"unit-{index:05d}",
            "design_id": design_ids[index % _DESIGN_COUNT],
            "owner": f"C{index % 100:03d}",
            "unit_type": role_by_design[index % _DESIGN_COUNT],
            "unit_domain": domain_by_role[role_by_design[index % _DESIGN_COUNT]],
            "training_level": "Recruit",
        }
        for index in range(_UNIT_COUNT)
    ]
    state = GameState(tables={
        "unit_designs": design_frame,
        "research_tracks": pl.DataFrame(research_rows),
        "unit_capability_projections": pl.DataFrame(schema=_PROJECTION_SCHEMA),
    })
    state.globals["military_training_bonuses"] = {
        "Recruit": 0.0,
        "Regular": 0.05,
        "Veteran": 0.10,
        "Elite": 0.15,
    }
    state.globals["military_research_capability_bonuses"] = {
        "land": {"speed": {"per_level": 0.01, "max_bonus": 0.05}},
        "air": {"sensors": {"per_level": 0.02, "max_bonus": 0.1}},
    }
    state.time.total_minutes = 50_000
    return state, units


def _write_projection_rows(
    system: MilitaryCapabilitySystem,
    state: GameState,
    rows: list[dict[str, object]],
) -> None:
    system._write_if_changed(state, "unit_capability_projections", _PROJECTION_SCHEMA, rows)
    mark_written = getattr(system, "_mark_projection_cache_written", None)
    if mark_written is not None:
        mark_written(state)


def test_fifty_thousand_unit_projection_update_gate() -> None:
    if os.environ.get("RUN_MILITARY_CAPABILITY_PERFORMANCE_CHECKS") != "1":
        pytest.skip("Set RUN_MILITARY_CAPABILITY_PERFORMANCE_CHECKS=1 to run the scaling benchmark.")

    setup_started = time.perf_counter_ns()
    state, baseline_units = _benchmark_state()
    system = MilitaryCapabilitySystem()
    baseline_rows = system._build_projections(state, baseline_units, [])
    baseline_frame = pl.DataFrame(baseline_rows, schema=_PROJECTION_SCHEMA)
    state.update_table("unit_capability_projections", baseline_frame)
    mark_written = getattr(system, "_mark_projection_cache_written", None)
    if mark_written is not None:
        mark_written(state)
    setup_ms = (time.perf_counter_ns() - setup_started) / 1_000_000

    profiler = cProfile.Profile()
    profile_units = [dict(unit) for unit in baseline_units]
    for unit in profile_units[:_CHANGED_COUNT]:
        unit["training_level"] = "Regular"
    profiler.enable()
    profiled_rows = system._build_projections(state, profile_units, [])
    profiler.disable()
    assert len(profiled_rows) == _UNIT_COUNT
    profile_output = io.StringIO()
    pstats.Stats(profiler, stream=profile_output).sort_stats("cumtime").print_stats(12)
    print("CAPABILITY_PROJECTION_PROFILE (not timed samples)\n" + profile_output.getvalue())

    projection_samples_ms: list[float] = []
    write_samples_ms: list[float] = []
    changed_counts: list[int] = []
    for _ in range(_SAMPLE_COUNT):
        units = [dict(unit) for unit in baseline_units]
        state.update_table("unit_capability_projections", baseline_frame)
        warm_rows = system._build_projections(state, units, [])
        _write_projection_rows(system, state, warm_rows)
        for unit in units[:_CHANGED_COUNT]:
            unit["training_level"] = "Regular"

        started = time.perf_counter_ns()
        rows = system._build_projections(state, units, [])
        projection_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        changed_counts.append(sum(row["training_level"] == "Regular" for row in rows))

        started = time.perf_counter_ns()
        _write_projection_rows(system, state, rows)
        write_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)

    total_samples_ms = [projection + write for projection, write in zip(projection_samples_ms, write_samples_ms)]
    projection_median_ms = statistics.median(projection_samples_ms)
    projection_p95_ms = _percentile_95(projection_samples_ms)
    write_median_ms = statistics.median(write_samples_ms)
    write_p95_ms = _percentile_95(write_samples_ms)
    total_median_ms = statistics.median(total_samples_ms)
    total_p95_ms = _percentile_95(total_samples_ms)
    print(
        "CAPABILITY_PROJECTION_PERFORMANCE "
        f"platform={platform.platform()} units={_UNIT_COUNT} designs={_DESIGN_COUNT} "
        f"changed={_CHANGED_COUNT} changed_ratio={_CHANGED_COUNT / _UNIT_COUNT:.3f} "
        f"samples={_SAMPLE_COUNT} setup_ms={setup_ms:.3f} "
        f"projection_median_ms={projection_median_ms:.3f} projection_p95_ms={projection_p95_ms:.3f} "
        f"write_median_ms={write_median_ms:.3f} write_p95_ms={write_p95_ms:.3f} "
        f"total_median_ms={total_median_ms:.3f} total_p95_ms={total_p95_ms:.3f}"
    )

    assert changed_counts == [_CHANGED_COUNT] * _SAMPLE_COUNT
    assert total_median_ms < 1_000, f"Projection update median {total_median_ms:.3f}ms exceeds 1 second."
