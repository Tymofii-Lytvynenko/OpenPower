import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from src.shared.config import GameConfig


class TestGameConfig(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = GameConfig(self.project_root)
        self.temp_root = self.project_root / ".temp"
        self.temp_root.mkdir(exist_ok=True)

    def test_active_mods_default(self):
        self.assertIn("base", self.config.active_mods)

    def test_get_data_dirs(self):
        dirs = self.config.get_data_dirs()
        self.assertTrue(len(dirs) >= 1)
        for data_dir in dirs:
            self.assertTrue(data_dir.exists())

    def test_get_asset_path(self):
        path = self.config.get_asset_path("map/terrain.png")
        self.assertTrue(path.exists())

    def test_resolves_dependency_load_order_from_mods_json(self):
        project_root = self.temp_root / f"config-test-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_mod(project_root, "base", [])
            self._write_mod(project_root, "expansion", ["base"])
            (project_root / "mods.json").write_text(
                '{\n  "active_mods": ["expansion"]\n}\n',
                encoding="utf-8",
            )

            config = GameConfig(project_root)

            self.assertEqual(config.requested_mods, ["expansion"])
            self.assertEqual(config.active_mods, ["base", "expansion"])
            self.assertEqual(
                config.get_data_dirs(),
                [
                    project_root / "modules" / "base" / "data",
                    project_root / "modules" / "expansion" / "data",
                ],
            )
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def _write_mod(self, project_root: Path, mod_id: str, dependencies: list[str]) -> None:
        mod_root = project_root / "modules" / mod_id
        (mod_root / "data").mkdir(parents=True, exist_ok=True)
        dependencies_literal = ", ".join(f'"{dependency}"' for dependency in dependencies)
        (mod_root / "mod.toml").write_text(
            "\n".join(
                [
                    f'id = "{mod_id}"',
                    f'name = "{mod_id}"',
                    'version = "0.0.1"',
                    f"dependencies = [{dependencies_literal}]",
                    "",
                ]
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
