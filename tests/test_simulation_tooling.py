import shutil
import unittest
from dataclasses import make_dataclass
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import polars as pl

from src.shared.actions import ActionSetGameSpeed, GameAction
from src.shared.state import GameState
from src.simulation.actions import build_action_registry
from src.simulation.comparison import DeterminismComparisonRunner
from src.simulation.fingerprint import state_fingerprint
from src.simulation.runner import SimulationRunConfig, SimulationRunReport


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSimulationTooling(unittest.TestCase):
    def setUp(self):
        self.output_dir = PROJECT_ROOT / ".temp" / f"simulation-tooling-{uuid4().hex}"

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_state_fingerprint_covers_all_persistent_state(self):
        left = GameState(tables={"sample": pl.DataFrame({"id": [1], "value": [2.0]})})
        right = GameState(tables={"sample": pl.DataFrame({"id": [1], "value": [2.0]})})

        self.assertEqual(state_fingerprint(left), state_fingerprint(right))

        right.globals["tick"] = 1
        self.assertNotEqual(state_fingerprint(left), state_fingerprint(right))

    def test_action_registry_keeps_qualified_names_when_short_names_collide(self):
        collision_action = make_dataclass(
            "ActionSetGameSpeed",
            [],
            bases=(GameAction,),
        )
        collision_action.__module__ = "modules.collision.actions"

        registry = build_action_registry([collision_action])

        self.assertNotIn("ActionSetGameSpeed", registry)
        self.assertIs(
            registry["src.shared.actions.ActionSetGameSpeed"],
            ActionSetGameSpeed,
        )
        self.assertIs(
            registry["modules.collision.actions.ActionSetGameSpeed"],
            collision_action,
        )

    def test_comparison_writes_a_machine_readable_report(self):
        config = SimulationRunConfig(
            project_root=PROJECT_ROOT,
            run_id="comparison-test",
            days=0,
            export_final_tables=False,
        )
        reports = [
            self._report("run-1", "same-fingerprint"),
            self._report("run-2", "same-fingerprint"),
        ]

        with patch(
            "src.simulation.comparison.HeadlessSimulationRunner.run",
            side_effect=reports,
        ):
            report = DeterminismComparisonRunner(
                config,
                runs=2,
                output_dir=self.output_dir,
            ).run()

        self.assertTrue(report.matched)
        self.assertTrue(report.report_path.exists())
        self.assertEqual(report.fingerprints, ("same-fingerprint", "same-fingerprint"))

    def _report(self, run_id: str, fingerprint: str) -> SimulationRunReport:
        run_dir = self.output_dir / run_id
        return SimulationRunReport(
            run_id=run_id,
            output_dir=run_dir,
            final_report_path=run_dir / "final_report.json",
            timeline_path=run_dir / "timeline.jsonl",
            snapshots_written=[],
            table_exports=[],
            failed=False,
            failure_reasons=[],
            issue_counts={},
            state_fingerprint=fingerprint,
            final_snapshot={},
        )


if __name__ == "__main__":
    unittest.main()
