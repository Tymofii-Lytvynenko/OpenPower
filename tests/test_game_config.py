import unittest
from pathlib import Path
from src.shared.config import GameConfig

class TestGameConfig(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = GameConfig(self.project_root)

    def test_active_mods_default(self):
        self.assertIn("base", self.config.active_mods)

    def test_get_data_dirs(self):
        dirs = self.config.get_data_dirs()
        self.assertTrue(len(dirs) >= 1)
        for d in dirs:
            self.assertTrue(d.exists())

    def test_get_asset_path(self):
        # Verify it finds the terrain map asset correctly
        path = self.config.get_asset_path("map/terrain.png")
        self.assertTrue(path.exists())
