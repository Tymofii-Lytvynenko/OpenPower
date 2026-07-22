import os
import ast
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

    def assert_client_import(self, module_name, file_path):
        # Client cannot import src.server internals (except spawn_local_server)
        if "src.server" in module_name or "server" in module_name:
            # We only allow imports from src.server.launcher
            allowed = "src.server.launcher"
            if "src.server" in module_name and not module_name.startswith(allowed):
                self.fail(f"Layer Boundary Violation: Client file '{file_path}' imports forbidden server module '{module_name}'")

    def assert_module_import(self, module_name, file_path):
        # Gameplay modules depend only on shared contracts, never engine internals.
        if module_name.startswith("src.engine"):
            self.fail(
                f"Layer Boundary Violation: Module file '{file_path}' "
                f"imports forbidden engine module '{module_name}'"
            )
