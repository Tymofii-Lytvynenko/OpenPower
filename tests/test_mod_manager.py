import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.shared.config import GameConfig
from src.engine.mod_manager import ModManager
from src.shared.mod_api import mod
from src.shared.mods import ModManifest, validate_engine_compatibility
from src.shared.system_interfaces import SystemAccess


class _RegisteredSystem:
    access = SystemAccess()
    runtime_state_contract = {}

    def __init__(self, system_id: str):
        self._system_id = system_id

    @property
    def id(self) -> str:
        return self._system_id

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state, delta_time: float) -> None:
        return None

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

    def test_resolve_load_order_expands_transitive_dependencies(self):
        available = {
            "base": ModManifest("base", "Base", "1.0"),
            "shared": ModManifest("shared", "Shared", "1.0", dependencies=["base"]),
            "ui": ModManifest("ui", "UI", "1.0", dependencies=["shared"]),
        }
        self.config.active_mods = ["ui"]

        ordered = self.mod_manager._sort_mods(available)

        self.assertEqual([manifest.id for manifest in ordered], ["base", "shared", "ui"])

    def test_resolve_load_order_reports_missing_and_cyclic_dependencies(self):
        missing_dependency = {
            "ui": ModManifest("ui", "UI", "1.0", dependencies=["missing"]),
        }
        cyclic_dependencies = {
            "first": ModManifest("first", "First", "1.0", dependencies=["second"]),
            "second": ModManifest("second", "Second", "1.0", dependencies=["first"]),
        }

        self.config.active_mods = ["ui"]
        with self.assertRaisesRegex(RuntimeError, "Missing dependency"):
            self.mod_manager._sort_mods(missing_dependency)
        self.config.active_mods = ["first"]
        with self.assertRaisesRegex(RuntimeError, "Circular dependency"):
            self.mod_manager._sort_mods(cyclic_dependencies)

    def test_engine_compatibility_bounds_are_validated_before_registration_loading(self):
        compatible = ModManifest(
            "compatible", "Compatible", "1.0", min_engine_version="0.1.0", max_engine_version="0.2.0"
        )
        validate_engine_compatibility(compatible, "0.1.0")

        too_new = ModManifest("too_new", "Too New", "1.0", min_engine_version="0.2.0")
        with self.assertRaisesRegex(RuntimeError, "requires engine >= 0.2.0"):
            validate_engine_compatibility(too_new, "0.1.0")

        too_old = ModManifest("too_old", "Too Old", "1.0", max_engine_version="0.0.9")
        with self.assertRaisesRegex(RuntimeError, "supports engine <= 0.0.9"):
            validate_engine_compatibility(too_old, "0.1.0")

    def test_invalid_engine_version_metadata_is_descriptive(self):
        manifest = ModManifest("broken", "Broken", "1.0", min_engine_version="vNext")
        with self.assertRaisesRegex(RuntimeError, "Invalid min_engine_version"):
            validate_engine_compatibility(manifest, "0.1.0")

    def test_runtime_rejects_incompatible_mod_before_importing_registration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mod_dir = Path(temp_dir) / "too_new"
            mod_dir.mkdir()
            (mod_dir / "registration.py").write_text("", encoding="utf-8")
            self.mod_manager.loaded_mods = [
                ModManifest(
                    "too_new", "Too New", "1.0", path=mod_dir,
                    min_engine_version="0.2.0",
                )
            ]
            with patch("src.engine.mod_manager.importlib.import_module") as import_module:
                with self.assertRaisesRegex(RuntimeError, "requires engine >= 0.2.0"):
                    self.mod_manager.load_runtime()

        import_module.assert_not_called()

    def test_legacy_register_entrypoint_loads_system_instances(self):
        system = _RegisteredSystem("legacy.system")
        with tempfile.TemporaryDirectory() as temp_dir:
            mod_dir = Path(temp_dir) / "legacy"
            mod_dir.mkdir()
            (mod_dir / "registration.py").write_text("", encoding="utf-8")
            self.mod_manager.loaded_mods = [
                ModManifest("legacy", "Legacy", "1.0", path=mod_dir)
            ]
            module = SimpleNamespace(register=lambda: [system])
            with patch("src.engine.mod_manager.importlib.import_module", return_value=module):
                runtime = self.mod_manager.load_runtime()

        self.assertEqual(runtime.systems, (system,))

    def test_missing_registration_entrypoint_warns_and_skips_module(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mod_dir = Path(temp_dir) / "empty"
            mod_dir.mkdir()
            self.mod_manager.loaded_mods = [
                ModManifest("empty", "Empty", "1.0", path=mod_dir)
            ]

            with self.assertLogs("src.engine.mod_manager", level="WARNING") as captured:
                runtime = self.mod_manager.load_runtime()

        self.assertEqual(runtime.systems, ())
        self.assertIn("registration.py", captured.output[0])

    def test_missing_registration_file_warns_and_skips_module(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mod_dir = Path(temp_dir) / "unregistered"
            mod_dir.mkdir()
            self.mod_manager.loaded_mods = [
                ModManifest("unregistered", "Unregistered", "1.0", path=mod_dir)
            ]

            with self.assertLogs("src.engine.mod_manager", level="WARNING") as captured:
                runtime = self.mod_manager.load_runtime()

        self.assertEqual(runtime.systems, ())
        self.assertIn("no registration.py", captured.output[0])

    def test_legacy_register_rejects_a_missing_contribution_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mod_dir = Path(temp_dir) / "invalid"
            mod_dir.mkdir()
            (mod_dir / "registration.py").write_text("", encoding="utf-8")
            self.mod_manager.loaded_mods = [
                ModManifest("invalid", "Invalid", "1.0", path=mod_dir)
            ]
            module = SimpleNamespace(register=lambda: None)

            with patch("src.engine.mod_manager.importlib.import_module", return_value=module):
                with self.assertRaisesRegex(TypeError, "must return a system"):
                    self.mod_manager.load_runtime()

    def test_higher_load_order_overrides_a_system_id_with_warning(self):
        base_system = _RegisteredSystem("shared.system")
        expansion_system = _RegisteredSystem("shared.system")
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir) / "base"
            expansion_dir = Path(temp_dir) / "expansion"
            base_dir.mkdir()
            expansion_dir.mkdir()
            for mod_dir in (base_dir, expansion_dir):
                (mod_dir / "registration.py").write_text("", encoding="utf-8")
            self.mod_manager.loaded_mods = [
                ModManifest("base", "Base", "1.0", path=base_dir),
                ModManifest("expansion", "Expansion", "1.0", path=expansion_dir),
            ]
            modules = [
                SimpleNamespace(contribute=lambda: mod(base_system)),
                SimpleNamespace(contribute=lambda: mod(expansion_system)),
            ]
            with patch(
                "src.engine.mod_manager.importlib.import_module",
                side_effect=modules,
            ), self.assertLogs("src.engine.mod_manager", level="WARNING") as captured:
                runtime = self.mod_manager.load_runtime()

        self.assertEqual(runtime.systems, (expansion_system,))
        self.assertIn("overrides system", captured.output[0])
