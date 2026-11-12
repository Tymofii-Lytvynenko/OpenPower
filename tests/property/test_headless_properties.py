import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from src.simulation.comparison import DeterminismComparisonRunner
from src.simulation.runner import SimulationRunConfig


@pytest.mark.slow
@settings(max_examples=2, deadline=None)
@given(st.integers(1, 100000))
def test_real_headless_runner_replays_with_identical_fingerprints(seed):
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='openpower-headless-') as directory:
        output = Path(directory)
        config = SimulationRunConfig(
            project_root=root, player_tag='UKR', output_dir=output,
            run_id='property', days=1, random_seed=seed,
            snapshot_interval_days=1, export_final_tables=False,
        )
        result = DeterminismComparisonRunner(config, output_dir=output).run()
        assert result.matched
        assert len(result.fingerprints) == 2
        assert result.fingerprints[0] == result.fingerprints[1]
