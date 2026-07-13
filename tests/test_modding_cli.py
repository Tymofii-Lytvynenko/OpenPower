import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from main import main


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestModdingCli(unittest.TestCase):
    def setUp(self):
        self.project_root = PROJECT_ROOT / ".temp" / f"modding-cli-{uuid4().hex}"
        self.project_root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.project_root, ignore_errors=True)

    def test_create_scaffolds_a_minimal_mod_without_loading_the_gui(self):
        exit_code = main(
            [
                "mod",
                "create",
                "weather_pack",
                "--name",
                "Weather Pack",
                "--project-root",
                str(self.project_root),
            ]
        )

        self.assertEqual(exit_code, 0)
        mod_root = self.project_root / "modules" / "weather_pack"
        self.assertTrue((mod_root / "mod.toml").exists())
        self.assertTrue((mod_root / "registration.py").exists())
        systems_source = (mod_root / "systems.py").read_text(encoding="utf-8")
        compile(systems_source, str(mod_root / "systems.py"), "exec")
        self.assertIn('return "weather_pack.main"', systems_source)
        self.assertIn('return ["base.time"]', systems_source)

        self.assertEqual(
            main(
                [
                    "mod",
                    "create",
                    "weather_pack",
                    "--project-root",
                    str(self.project_root),
                ]
            ),
            2,
        )

    def test_create_rejects_non_importable_mod_ids(self):
        exit_code = main(
            [
                "mod",
                "create",
                "../unsafe",
                "--project-root",
                str(self.project_root),
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse((self.project_root / "unsafe").exists())


if __name__ == "__main__":
    unittest.main()
