from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.covert_mission_resolution import (
    _coverage_band,
    _espionage_cell_count,
    _intelligence_output,
)


def test_espionage_cell_count_uses_precomputed_metrics_when_available():
    calls = []

    def metric_count(frame, **keys):
        calls.append((frame, keys))
        return 3

    counts = pl.DataFrame(
        {"country_id": ["USA"], "target_country_id": ["CAN"], "count": [3]}
    )

    count = _espionage_cell_count(
        [], "USA", "CAN", counts, SimpleNamespace(metric_count=metric_count)
    )

    assert count == 3
    assert calls == [
        (counts, {"country_id": "USA", "target_country_id": "CAN"})
    ]


def test_coverage_band_marks_single_and_dense_cell_networks():
    assert _coverage_band(1) == "limited"
    assert _coverage_band(4) == "dense"


def test_failed_mission_does_not_emit_intelligence_snapshot():
    result = _intelligence_output(
        None,
        {},
        {},
        "failure",
        None,
        None,
        None,
    )

    assert result == {}
