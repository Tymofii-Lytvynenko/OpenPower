import os
import ast
import os
import unittest
from pathlib import Path

class TestLayerBoundaries(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent

    def test_client_imports(self):
        client_dir = self.project_root / "src" / "client"
        for root, dirs, files in os.walk(client_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=file_path)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                self.assert_client_import(alias.name, file_path)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                self.assert_client_import(node.module, file_path)

    def test_module_imports(self):
        modules_dir = self.project_root / "modules"
        for root, dirs, files in os.walk(modules_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=file_path)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                self.assert_module_import(alias.name, file_path)
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                self.assert_module_import(node.module, file_path)

    def test_migration_feature_keeps_simulation_and_presentation_layers_separate(self):
        simulation_files = [
            self.project_root / "modules/base/systems/demographics/migration_policy.py",
            self.project_root / "modules/base/systems/demographics/migration_system.py",
        ]
        presentation_files = [
            self.project_root / "src/client/ui/panels/migration_presenter.py",
            self.project_root / "src/client/ui/panels/migration_panel.py",
        ]
        for path in [*simulation_files, *presentation_files]:
            self.assertTrue(path.is_file(), f"Migration layer module is missing: {path}")

        for path in simulation_files:
            modules = self._imported_modules(path)
            self.assertFalse(
                any(name.startswith(("src.client", "src.server")) for name in modules),
                f"Gameplay module imports a forbidden layer: {path}",
            )

        for path in presentation_files:
            modules = self._imported_modules(path)
            self.assertFalse(
                any(name.startswith("modules.") for name in modules),
                f"Client module imports gameplay implementation: {path}",
            )

    @staticmethod
    def _imported_modules(path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules

    def assert_client_import(self, module_name, file_path):
        if module_name.startswith("src.server"):
            self.fail(
                f"Layer Boundary Violation: Client file '{file_path}' "
                f"imports server implementation '{module_name}'"
            )

    def assert_module_import(self, module_name, file_path):
        # Gameplay modules depend only on shared contracts, never engine internals.
        if module_name.startswith("src.engine"):
            self.fail(
                f"Layer Boundary Violation: Module file '{file_path}' "
                f"imports forbidden engine module '{module_name}'"
            )
