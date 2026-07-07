import dataclasses
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import polars as pl

from src.engine.simulator import Engine
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_loader import SaveStateLoader
from src.server.io.save_writer import SaveWriter
from src.server.session import GameSession
from src.shared.actions import ActionBuildUnit, ActionCreateTreaty, ActionSaveGame, ActionUpdateBudget
from src.shared.config import GameConfig
from src.shared.events import EventSystemError
from src.shared.state import GameState, persistent_state_field_names
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
        state.system_state["base.time"] = {"real_sec_timer": 0.4, "last_event_total_minutes": 240}
        state.events.append(EventSystemError("test.system", "boom", "traceback"))

        writer = SaveWriter(config)
        self.assertTrue(writer.save_game(state, "slot_1"))

        meta_path = self.project_root / "user_data" / "saves" / "slot_1" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["globals"]["player_tag"], "UKR")
        self.assertEqual(meta["persistent_fields"], list(persistent_state_field_names()))
        self.assertEqual(meta["system_state"], {"base.time": {"real_sec_timer": 0.4, "last_event_total_minutes": 240}})
        self.assertNotIn("current_actions", meta)
        self.assertNotIn("events", meta)

        loaded = DataLoader(config).load_save("slot_1")
        self.assertEqual(loaded.globals["player_tag"], "UKR")
        self.assertEqual(loaded.system_state, {"base.time": {"real_sec_timer": 0.4, "last_event_total_minutes": 240}})
        self.assertEqual(loaded.current_actions, [])
        self.assertEqual(loaded.events, [])

    def test_real_session_save_roundtrip_preserves_all_persistent_state(self):
        config = GameConfig(PROJECT_ROOT)
        config.dev_mode = False
        save_name = f"roundtrip-audit-{uuid4().hex}"
        writer = SaveWriter(config)
        loader = DataLoader(config)
        compatibility_loader = SaveStateLoader(config)

        session = GameSession.create_headless(config, player_tag="UKR")
        session.state.time.speed_level = 5
        session.state.globals["game_speed"] = 5

        session.tick(0.6)
        session.receive_action(
            ActionUpdateBudget(
                player_id="audit",
                country_tag="UKR",
                allocations={
                    "personal_income_tax_rate": 0.31,
                    "budget_health_ratio": 0.62,
                    "budget_research_ratio": 0.18,
                },
            )
        )
        session.receive_action(ActionBuildUnit(player_id="audit", country_tag="UKR", unit_type="infantry", count=7))
        session.receive_action(
            ActionCreateTreaty(
                player_id="audit",
                source_country_tag="UKR",
                target_country_tag="POL",
                treaty_type="non_aggression",
                title="Audit corridor",
                terms="Roundtrip audit treaty payload.",
            )
        )
        session.tick(0.6)
        for _ in range(4):
            session.tick(0.6)

        session.state.globals["audit_marker"] = {
            "stage": "post-sim",
            "days_simulated": 6,
            "player_tag": "UKR",
        }
        session.state.events.append(EventSystemError("audit.system", "transient", "ignored"))
        session.state.current_actions.append(ActionSaveGame(player_id="audit", save_name=save_name))

        self.assertTrue(writer.save_game(session.state, save_name))

        save_dir = config.project_root / "user_data" / "saves" / save_name
        meta = json.loads((config.project_root / "user_data" / "saves" / save_name / "meta.json").read_text(encoding="utf-8"))
        self.assertTrue(save_dir.exists())
        self.assertEqual(meta["persistent_fields"], list(persistent_state_field_names()))
        self.assertEqual(meta["system_state"], session.state.system_state)
        self.assertTrue((save_dir / "meta.json").exists())
        table_files = sorted(path.stem for path in (save_dir / "tables").glob("*.parquet"))
        self.assertEqual(table_files, sorted(session.state.tables.keys()))

        loaded = loader.load_save(save_name)
        compatibility_loaded = compatibility_loader.load(save_name)

        self._assert_persistent_state_equal(session.state, loaded)
        self._assert_persistent_state_equal(session.state, compatibility_loaded)
        self.assertEqual(loaded.events, [])
        self.assertEqual(loaded.current_actions, [])
        self.assertEqual(compatibility_loaded.events, [])
        self.assertEqual(compatibility_loaded.current_actions, [])

        self.assertTrue(writer.delete_save(save_name))

    def _assert_persistent_state_equal(self, expected: GameState, actual: GameState) -> None:
        self.assertEqual(dataclasses.asdict(expected.time), dataclasses.asdict(actual.time))
        self.assertEqual(expected.globals, actual.globals)
        self.assertEqual(expected.system_state, actual.system_state)
        self.assertEqual(sorted(expected.tables.keys()), sorted(actual.tables.keys()))

        for table_name in sorted(expected.tables.keys()):
            expected_table = expected.tables[table_name]
            actual_table = actual.tables[table_name]
            with self.subTest(table=table_name):
                self.assertEqual(expected_table.schema, actual_table.schema)
                self.assertTrue(expected_table.equals(actual_table))


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