from __future__ import annotations

import os
from time import perf_counter
from types import SimpleNamespace

import polars as pl
import pytest

from src.client.services.history_query_service import HistoryQueryService


@pytest.mark.skipif(
    os.environ.get("RUN_HISTORY_BENCHMARKS") != "1",
    reason="Set RUN_HISTORY_BENCHMARKS=1 to run the 10-million-snapshot history benchmark.",
)
def test_history_ranking_for_ten_million_snapshots_under_half_second() -> None:
    snapshot_count = 10_000_000
    country_count = 200
    snapshots = (
        pl.DataFrame({"sequence": pl.int_range(0, snapshot_count, eager=True)})
        .with_columns(
            pl.lit("country").alias("subject_type"),
            (pl.col("sequence") % country_count).cast(pl.Utf8).alias("subject_id"),
            pl.lit("country.gdp").alias("indicator_id"),
            pl.col("sequence").cast(pl.Utf8).alias("id"),
            (pl.col("sequence") % country_count).cast(pl.Float64).alias("value"),
            pl.lit("USD/year").alias("unit"),
            (pl.col("sequence") // country_count).cast(pl.Int64).alias("game_minute"),
            pl.lit(0, dtype=pl.Int64).alias("tick"),
            pl.lit("complete").alias("completeness"),
        )
        .select(
            "id", "subject_type", "subject_id", "indicator_id", "value", "unit",
            "game_minute", "tick", "completeness",
        )
    )
    last_sample_sequences = [
        snapshot_count - country_count + subject
        for subject in range(country_count)
    ]
    series_state = pl.DataFrame(
        {
            "id": [f"country:{subject}:country.gdp" for subject in range(country_count)],
            "subject_type": ["country"] * country_count,
            "subject_id": [str(subject) for subject in range(country_count)],
            "indicator_id": ["country.gdp"] * country_count,
            "unit": ["USD/year"] * country_count,
            "latest_value": [float(subject) for subject in range(country_count)],
            "latest_snapshot_id": [str(sequence) for sequence in last_sample_sequences],
            "latest_source_boundary": ["interval"] * country_count,
            "latest_confidence": [1.0] * country_count,
            "latest_value_kind": ["authoritative"] * country_count,
            "last_sample_minute": [snapshot_count // country_count - 1] * country_count,
            "last_sample_tick": [0] * country_count,
            "sample_count": [snapshot_count // country_count] * country_count,
            "completeness": ["complete"] * country_count,
        }
    )
    state = SimpleNamespace(
        tables={"history_snapshots": snapshots, "history_series_state": series_state}
    )

    started = perf_counter()
    ranking = HistoryQueryService().rank(state, "country.gdp")
    elapsed = perf_counter() - started

    print(
        f"history benchmark: {snapshot_count:,} snapshots, {country_count} series; "
        f"ranking {elapsed * 1_000:.2f} ms"
    )
    assert ranking["evaluation_minute"] == snapshot_count // country_count - 1
    assert len(ranking["rows"]) == country_count
    assert ranking["rows"][0]["subject_id"] == str(country_count - 1)
    assert elapsed < 0.5, f"10-million-snapshot ranking took {elapsed * 1_000:.2f} ms"
