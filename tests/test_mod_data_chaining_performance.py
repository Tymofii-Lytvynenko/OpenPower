from __future__ import annotations

import os
import statistics
import time

import polars as pl
import pytest

from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig


def _write_mod_chain(project_root, mod_count: int = 25) -> list[str]:
    module_ids = ["base", *(f"layer_{index:02d}" for index in range(1, mod_count))]
    previous = ""
    for index, mod_id in enumerate(module_ids):
        module_dir = project_root / "modules" / mod_id
        world_dir = module_dir / "data" / "world"
        world_dir.mkdir(parents=True)
        dependencies = f'["{previous}"]' if previous else "[]"
        (module_dir / "mod.toml").write_text(
            "\n".join(
                [
                    f'id = "{mod_id}"',
                    f'name = "{mod_id}"',
                    'version = "0.1.0"',
                    "api_version = 1",
                    'min_engine_version = "0.1.0"',
                    f"dependencies = {dependencies}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (world_dir / "countries_treaties.toml").write_text(
            "\n".join(
                [
                    "[countries_treaties.SHARED.PARTNER]",
                    f"trust = {index}",
                    "",
                    f"[countries_treaties.UNIQUE{index:02d}.PARTNER{index:02d}]",
                    f"trust = {index}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        previous = mod_id

    (project_root / "mods.json").write_text(
        f'{{"active_mods": ["{module_ids[-1]}"]}}\n',
        encoding="utf-8",
    )
    return module_ids


@pytest.mark.skipif(
    os.environ.get("RUN_MOD_CHAIN_BENCHMARKS") != "1",
    reason="Set RUN_MOD_CHAIN_BENCHMARKS=1 to run the controlled 25-mod load benchmark.",
)
def test_twenty_five_mod_dependency_and_table_merge_under_one_and_a_half_seconds(tmp_path) -> None:
    expected_order = _write_mod_chain(tmp_path)

    def load_chain():
        config = GameConfig(tmp_path)
        tables = DataLoader(config)._load_world_tables()
        return config.active_mods, tables["countries_treaties"]

    load_chain()
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        active_mods, treaties = load_chain()
        samples.append(time.perf_counter() - started)
        assert active_mods == expected_order
        assert treaties.height == 26
        shared = treaties.filter(
            (pl.col("source") == "SHARED") & (pl.col("target") == "PARTNER")
        )
        assert shared["trust"][0] == 24

    median_ms = statistics.median(samples) * 1_000.0
    print(f"25-mod resolve+table-merge median={median_ms:.2f}ms samples={[round(value * 1_000.0, 2) for value in samples]}")
    assert median_ms < 1_500.0, "SC-001: 25-mod resolve and table merge exceeds 1.5 s"
