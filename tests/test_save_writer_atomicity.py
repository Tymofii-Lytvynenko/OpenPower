from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl

from src.core.saves import list_available_saves
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig
from src.shared.determinism import DeterminismState
from src.shared.events import JournalState
from src.shared.state import GameState, TimeData, persistent_state_field_names


def representative_persistent_state() -> GameState:
    """Build a compact fixture covering each persistent state representation."""
    return GameState(
        tables={"regions": pl.DataFrame({"id": [1, 2], "owner": ["AAA", None]})},
        time=TimeData(
            total_minutes=1234,
            year=2001,
            month=1,
            day=1,
            hour=20,
            minute=34,
            date_str="2001-01-01 20:34",
            speed_level=3,
            is_paused=True,
            _accumulator=0.25,
        ),
        globals={"tick": 47, "nested": {"campaign": "test"}},
        system_state={"economy": {"last_update": 1234, "reserve": 17.5}},
        determinism=DeterminismState(seed=41, rng_state=89, id_sequence=7),
        journal=JournalState(
            domain_events=[{"event_id": "evt-1", "tick": 47, "payload": {"value": 3}}],
            command_results=[{"command_id": "cmd-1", "status": "executed"}],
        ),
        events=[MagicMock(name="transient-event")],
        current_actions=[MagicMock(name="transient-action")],
    )


class TestSaveWriterAtomicity(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.save_root = self.project_root / "user_data" / "saves"
        self.save_root.mkdir(parents=True)
        self.writer = SaveWriter(GameConfig(self.project_root))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_serialization_failure_preserves_existing_slot(self) -> None:
        target = self.save_root / "slot"
        target.mkdir()
        marker = target / "previous-generation.txt"
        marker.write_text("still valid", encoding="utf-8")

        with patch.object(self.writer, "_write_state_to_disk", side_effect=OSError("disk full")):
            self.assertFalse(self.writer.save_game(representative_persistent_state(), "slot"))

        self.assertEqual(marker.read_text(encoding="utf-8"), "still valid")
        self.assertFalse(list(self.save_root.glob(".slot.tmp-*")))

    def test_staging_directory_failure_is_reported_without_raising(self) -> None:
        with patch("src.server.io.save_writer.tempfile.mkdtemp", side_effect=OSError("disk unavailable")):
            self.assertFalse(self.writer.save_game(GameState(), "slot"))

    def test_successful_replacement_installs_new_generation_and_cleans_backup(self) -> None:
        target = self.save_root / "slot"
        target.mkdir()
        (target / "generation.txt").write_text("old", encoding="utf-8")
        backup = self.save_root / ".slot.backup"

        def write_new_generation(state: GameState, path: Path) -> None:
            (path / "generation.txt").write_text("new", encoding="utf-8")

        with patch.object(self.writer, "_write_state_to_disk", side_effect=write_new_generation):
            self.assertTrue(self.writer.save_game(GameState(), "slot"))

        self.assertEqual((target / "generation.txt").read_text(encoding="utf-8"), "new")
        self.assertFalse(backup.exists())
        self.assertFalse(list(self.save_root.glob(".slot.tmp-*")))

    def test_commit_failure_rolls_back_previous_slot(self) -> None:
        target = self.save_root / "slot"
        backup = self.save_root / ".slot.backup"
        staged = self.save_root / ".slot.tmp-test"
        target.mkdir()
        staged.mkdir()
        (target / "generation.txt").write_text("old", encoding="utf-8")
        (staged / "generation.txt").write_text("new", encoding="utf-8")
        original_rename = Path.rename

        def fail_install(source: Path, destination: Path) -> Path:
            if source == staged:
                raise OSError("rename interrupted")
            return original_rename(source, destination)

        with patch.object(Path, "rename", fail_install):
            with self.assertRaisesRegex(OSError, "rename interrupted"):
                self.writer._commit_staged_save(staged, target, backup)

        self.assertEqual((target / "generation.txt").read_text(encoding="utf-8"), "old")
        self.assertFalse(backup.exists())

    def test_orphaned_backup_is_listed_and_loadable(self) -> None:
        backup = self.save_root / ".slot.backup"
        backup.mkdir()
        (backup / "meta.json").write_text(
            json.dumps({"version": 1, "timestamp": "2026-01-01T00:00:00", "globals": {"tick": 9}}),
            encoding="utf-8",
        )

        self.assertEqual(list_available_saves(GameConfig(self.project_root))[0]["name"], "slot")
        loaded = DataLoader(GameConfig(self.project_root)).load_save("slot")
        self.assertEqual(loaded.globals["tick"], 9)

    def test_load_and_delete_reject_path_traversal(self) -> None:
        loader = DataLoader(GameConfig(self.project_root))
        with self.assertRaises(ValueError):
            loader.load_save("../outside")
        self.assertFalse(self.writer.delete_save("../outside"))

    def test_save_rejects_noncanonical_names_without_creating_a_slot(self) -> None:
        self.assertFalse(self.writer.save_game(GameState(), "../outside"))
        self.assertEqual(list(self.save_root.iterdir()), [])

    def test_roundtrip_preserves_every_persistent_field_and_omits_transient_fields(self) -> None:
        state = representative_persistent_state()

        self.assertTrue(self.writer.save_game(state, "full-roundtrip"))
        loaded = DataLoader(GameConfig(self.project_root)).load_save("full-roundtrip")

        self.assertEqual(loaded.time, state.time)
        self.assertEqual(loaded.globals, state.globals)
        self.assertEqual(loaded.system_state, state.system_state)
        self.assertEqual(loaded.determinism, state.determinism)
        self.assertEqual(loaded.journal, state.journal)
        self.assertTrue(loaded.tables["regions"].equals(state.tables["regions"]))
        self.assertEqual(loaded.events, [])
        self.assertEqual(loaded.current_actions, [])

        metadata = json.loads((self.save_root / "full-roundtrip" / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["persistent_fields"], list(persistent_state_field_names()))
        self.assertNotIn("events", metadata)
        self.assertNotIn("current_actions", metadata)

    def test_legacy_and_future_save_versions_have_explicit_migration_behavior(self) -> None:
        legacy_dir = self.save_root / "legacy"
        legacy_dir.mkdir()
        (legacy_dir / "meta.json").write_text(
            json.dumps({"version": 1, "globals": {"tick": 11}}),
            encoding="utf-8",
        )

        loaded = DataLoader(GameConfig(self.project_root)).load_save("legacy")

        self.assertEqual(loaded.globals["tick"], 11)
        self.assertEqual(loaded.determinism, DeterminismState())
        self.assertEqual(loaded.journal, JournalState())

        future_dir = self.save_root / "future"
        future_dir.mkdir()
        (future_dir / "meta.json").write_text(
            json.dumps({"version": 999}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            DataLoader(GameConfig(self.project_root)).load_save("future")

    def test_corrupt_save_metadata_is_skipped_with_a_diagnostic(self) -> None:
        corrupt_slot = self.save_root / "corrupt"
        corrupt_slot.mkdir()
        (corrupt_slot / "meta.json").write_text("not json", encoding="utf-8")

        with self.assertLogs("src.core.saves", level="WARNING"):
            saves = list_available_saves(GameConfig(self.project_root))

        self.assertEqual(saves, [])

    def test_delete_removes_orphaned_backup_slot(self) -> None:
        backup = self.save_root / ".slot.backup"
        backup.mkdir()
        (backup / "meta.json").write_text("{}", encoding="utf-8")

        self.assertTrue(self.writer.delete_save("slot"))
        self.assertFalse(backup.exists())


if __name__ == "__main__":
    unittest.main()
