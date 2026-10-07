from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    os.environ.get("RUN_MOD_STARTUP_BENCHMARKS") != "1",
    reason="Set RUN_MOD_STARTUP_BENCHMARKS=1 to measure cold mod/system startup.",
)
def test_mod_scan_import_and_system_graph_resolve_under_five_hundred_milliseconds() -> None:
    script = """
import time
from pathlib import Path
from src.engine.mod_manager import ModManager
from src.engine.simulator import Engine
from src.shared.config import GameConfig

manager = ModManager(GameConfig(Path.cwd()))
started = time.perf_counter()
manager.resolve_load_order()
runtime = manager.load_runtime()
engine = Engine()
engine.register_systems(runtime.systems)
engine._rebuild_execution_order()
print(f\"STARTUP_RESULT={(time.perf_counter() - started) * 1000.0:.3f}\")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    match = re.search(r"STARTUP_RESULT=(\d+\.\d+)", result.stdout)
    assert match is not None, result.stdout

    startup_ms = float(match.group(1))
    print(f"Cold mod and system graph startup: {startup_ms:.3f} ms")
    assert startup_ms < 500.0, f"Startup took {startup_ms:.3f} ms"
