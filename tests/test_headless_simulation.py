import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import polars as pl

from src.engine.simulator import Engine
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.server.session import GameSession
from src.shared.actions import ActionSaveGame
from src.shared.config import GameConfig
from src.shared.events import EventSystemError
from src.shared.state import GameState
from src.simulation.runner import HeadlessSimulationRunner, SimulationRunConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSaveLifecycleForSimulation(unittest.TestCase):
    def setUp(self):
        self.project_root = PROJECT_ROOT / ".temp" / f"simulation-save-{uuid4().hex}"
        self.project_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_session_player_tag_is_stored_in_state_globals(self):
        config = GameConfig(self.project_root)
        session = GameSession(config, None, None, Engine(dev_mode=False), None, GameState(), player_tag="UKR")

        self.assertEqual(session.player_tag, "UKR")
        self.assertEqual(session.state.globals["player_tag"], "UKR")

    def test_save_preserves_player_tag_and_drops_transient_tick_data(self):
        config = GameConfig(self.project_root)
        state = GameState()
        state.globals["player_tag"] = "UKR"
        state.update_table("countries", pl.DataFrame({"id": ["UKR"], "name": ["Ukraine"]}))
        state.current_actions.append(ActionSaveGame(player_id="tester", save_name="slot_1"))
        state.events.append(EventSystemError("test.system", "boom", "traceback"))

        writer = SaveWriter(config)
        self.assertTrue(writer.save_game(state, "slot_1"))

        meta_path = self.project_root / "user_data" / "saves" / "slot_1" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["globals"]["player_tag"], "UKR")
        self.assertNotIn("current_actions", meta)
        self.assertNotIn("events", meta)

        loaded = DataLoader(config).load_save("slot_1")
        self.assertEqual(loaded.globals["player_tag"], "UKR")
        self.assertEqual(loaded.current_actions, [])
        self.assertEqual(loaded.events, [])


class TestHeadlessSimulationRunner(unittest.TestCase):
    def setUp(self):
        self.output_dir = PROJECT_ROOT / ".temp" / f"simulation-run-{uuid4().hex}"

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_runner_writes_timeline_snapshots_and_keeps_player_tag(self):
        config = SimulationRunConfig(
            project_root=PROJECT_ROOT,
            player_tag="UKR",
            output_dir=self.output_dir,
            days=2,
            snapshot_interval_days=1,
            table_sample_limit=2,
            export_final_tables=False,
            fail_on_system_errors=False,
        )

        report = HeadlessSimulationRunner(config).run()

        self.assertFalse(report.failed)
        self.assertTrue(report.timeline_path.exists())
        self.assertTrue(report.final_report_path.exists())
        self.assertEqual(report.final_snapshot["player"]["tag"], "UKR")
        self.assertIsNotNone(report.final_snapshot["player"]["country"])
        self.assertGreaterEqual(len(report.snapshots_written), 3)

        timeline_lines = report.timeline_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(timeline_lines), 3)
        final_report = json.loads(report.final_report_path.read_text(encoding="utf-8"))
        self.assertEqual(final_report["final_snapshot"]["player"]["tag"], "UKR")


if __name__ == "__main__":
    unittest.main()