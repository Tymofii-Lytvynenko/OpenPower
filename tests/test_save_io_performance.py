from __future__ import annotations

import math
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

import pytest

from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig


def _percentile_95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def test_production_initial_state_save_and_load_gates() -> None:
    if os.environ.get("RUN_SAVE_IO_PERFORMANCE_CHECKS") != "1":
        pytest.skip("Set RUN_SAVE_IO_PERFORMANCE_CHECKS=1 to run the serialization benchmark.")

    project_root = Path(__file__).resolve().parent.parent
    production_config = GameConfig(project_root)
    with tempfile.TemporaryDirectory(prefix="openpower-save-io-") as temporary_root:
        config = GameConfig(Path(temporary_root))
        config.get_data_dirs = production_config.get_data_dirs
        config.get_asset_path = production_config.get_asset_path

        state = DataLoader(config).load_initial_state()
        table_rows = sum(table.height for table in state.tables.values())
        assert state.tables, "The production static-data fixture must contain tables."

        writer = SaveWriter(config)
        loader = DataLoader(config)
        save_samples_ms: list[float] = []
        load_samples_ms: list[float] = []
        sample_count = 9

        for _ in range(sample_count):
            started = time.perf_counter_ns()
            assert writer.save_game(state, "benchmark")
            save_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)

            started = time.perf_counter_ns()
            loaded_state = loader.load_save("benchmark")
            load_samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            assert set(loaded_state.tables) == set(state.tables)

        save_median = statistics.median(save_samples_ms)
        save_p95 = _percentile_95(save_samples_ms)
        load_median = statistics.median(load_samples_ms)
        load_p95 = _percentile_95(load_samples_ms)
        print(
            "SAVE_IO_PERFORMANCE "
            f"platform={platform.platform()} python={platform.python_version()} "
            f"tables={len(state.tables)} rows={table_rows} samples={sample_count} "
            f"save_median_ms={save_median:.3f} save_p95_ms={save_p95:.3f} "
            f"load_median_ms={load_median:.3f} load_p95_ms={load_p95:.3f}"
        )

        assert save_median < 300, f"Save median {save_median:.3f}ms exceeds 300ms."
        assert load_median < 500, f"Load median {load_median:.3f}ms exceeds 500ms."
