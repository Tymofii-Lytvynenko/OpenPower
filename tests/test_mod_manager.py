import unittest
from pathlib import Path
from src.shared.config import GameConfig
from src.engine.mod_manager import ModManager

class TestModManager(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = GameConfig(self.project_root)
        self.mod_manager = ModManager(self.config)

    def test_discover_mods(self):
        mods = self.mod_manager._discover_mods()
        self.assertIn("base", mods)
        self.assertEqual(mods["base"].id, "base")

    def test_resolve_load_order(self):
        self.config.active_mods = ["base"]
        loaded = self.mod_manager.resolve_load_order()
        self.assertTrue(len(loaded) >= 1)
        self.assertEqual(loaded[0].id, "base")
        self.assertEqual(self.config.active_mods[0], "base")
