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


class _MappingSystem(dict):
    access = SystemAccess()
    runtime_state_contract = {}

    @property
    def id(self) -> str:
        return str(self["system_id"])

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

    def _registration_manifest(self, parent: Path, name: str, api_version: int = 1):
        mod_dir = parent / name
        mod_dir.mkdir()
        (mod_dir / "registration.py").write_text("", encoding="utf-8")
        return ModManifest(
            name,
            name,
            "1.0",
            api_version=api_version,
            path=mod_dir,
        )

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

    def test_resolve_load_order_rejects_empty_module_discovery(self):
        with patch.object(self.mod_manager, "_discover_mods", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "No modules found"):
                self.mod_manager.resolve_load_order()

    def test_runtime_requires_resolved_mods_and_returns_cached_runtime(self):
        with self.assertRaisesRegex(RuntimeError, "resolve_load_order\(\) must run"):
            self.mod_manager.load_runtime()

        cached = object()
        self.mod_manager._runtime = cached
        self.assertIs(self.mod_manager.load_runtime(), cached)

    def test_runtime_rejects_api_mismatch_and_invalid_package_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = self._registration_manifest(Path(temp_dir), "api_mismatch", api_version=999)
            self.mod_manager.loaded_mods = [manifest]
            with patch("src.engine.mod_manager.importlib.import_module") as import_module:
                with self.assertRaisesRegex(RuntimeError, "targets API 999"):
                    self.mod_manager.load_runtime()
            import_module.assert_not_called()

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = self._registration_manifest(Path(temp_dir), "invalid-package")
            self.mod_manager.loaded_mods = [manifest]
            with self.assertRaisesRegex(RuntimeError, "valid Python identifier"):
                self.mod_manager.load_runtime()

    def test_runtime_adds_project_root_before_loading_registration(self):
        system = _RegisteredSystem("runtime.system")
        with tempfile.TemporaryDirectory() as temp_dir:
            self.mod_manager.loaded_mods = [
                self._registration_manifest(Path(temp_dir), "runtime")
            ]
            runtime_path: list[str] = []
            module = SimpleNamespace(contribute=lambda: mod(system))
            with patch("src.engine.mod_manager.sys.path", runtime_path):
                with patch(
                    "src.engine.mod_manager.importlib.import_module",
                    return_value=module,
                ):
                    runtime = self.mod_manager.load_runtime()

        self.assertIn(str(self.config.project_root), runtime_path)
        self.assertEqual(runtime.systems, (system,))

    def test_runtime_validates_contribution_types_and_legacy_return_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.mod_manager.loaded_mods = [
                self._registration_manifest(Path(temp_dir), "invalid_contribution")
            ]
            module = SimpleNamespace(contribute=lambda: object())
            with patch(
                "src.engine.mod_manager.importlib.import_module",
                return_value=module,
            ):
                with self.assertRaisesRegex(TypeError, "returned object"):
                    self.mod_manager.load_runtime()

        for name, registered, expected_system_id in (
            ("single_legacy", _RegisteredSystem("single.system"), "single.system"),
            ("mapping_legacy", _MappingSystem(system_id="mapping.system"), "mapping.system"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                self.mod_manager._runtime = None
                self.mod_manager.loaded_mods = [
                    self._registration_manifest(Path(temp_dir), name)
                ]
                module = SimpleNamespace(register=lambda: registered)
                with patch(
                    "src.engine.mod_manager.importlib.import_module",
                    return_value=module,
                ):
                    runtime = self.mod_manager.load_runtime()

                self.assertEqual(runtime.systems[0].id, expected_system_id)

    def test_runtime_rejects_duplicate_system_ids_from_one_module(self):
        system = _RegisteredSystem("duplicate.system")
        with tempfile.TemporaryDirectory() as temp_dir:
            self.mod_manager.loaded_mods = [
                self._registration_manifest(Path(temp_dir), "duplicate")
            ]
            module = SimpleNamespace(contribute=lambda: mod(system, system))
            with patch(
                "src.engine.mod_manager.importlib.import_module",
                return_value=module,
            ):
                with self.assertRaisesRegex(RuntimeError, "registers system id"):
                    self.mod_manager.load_runtime()

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

    def test_legacy_register_can_return_a_mod_contribution(self):
        system = _RegisteredSystem("contribution.system")
        with tempfile.TemporaryDirectory() as temp_dir:
            self.mod_manager.loaded_mods = [
                self._registration_manifest(Path(temp_dir), "contribution")
            ]
            module = SimpleNamespace(register=lambda: mod(system))
            with patch(
                "src.engine.mod_manager.importlib.import_module",
                return_value=module,
            ):
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

    def test_registration_file_without_entrypoint_warns_and_skips_module(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.mod_manager.loaded_mods = [
                self._registration_manifest(Path(temp_dir), "no_entrypoint")
            ]
            with patch(
                "src.engine.mod_manager.importlib.import_module",
                return_value=SimpleNamespace(),
            ):
                with self.assertLogs("src.engine.mod_manager", level="WARNING") as captured:
                    runtime = self.mod_manager.load_runtime()

        self.assertEqual(runtime.systems, ())
        self.assertIn("has no contribute() or register()", captured.output[0])

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
