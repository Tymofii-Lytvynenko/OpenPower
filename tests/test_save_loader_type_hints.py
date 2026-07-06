from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from src.server.io.data_load_manager import DataLoader
from src.shared.state import GameState


class TestSaveLoaderTypeHints(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parent.parent / ".temp" / f"save-loader-{uuid4().hex}"
        self.project_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_load_save_resolves_game_state_forward_references(self):
        save_dir = self.project_root / "user_data" / "saves" / "quicksave"
        save_dir.mkdir(parents=True, exist_ok=True)

        loader = DataLoader(SimpleNamespace(project_root=self.project_root))
        state = loader.load_save("quicksave")

        self.assertIsInstance(state, GameState)
        self.assertEqual(state.tables, {})
        self.assertEqual(state.globals["tick"], 0)


if __name__ == "__main__":
    unittest.main()