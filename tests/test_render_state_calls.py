import ast
import unittest
from pathlib import Path


class RenderStateCallTest(unittest.TestCase):
    def test_enable_only_receives_flags_as_separate_arguments(self) -> None:
        client_root = Path(__file__).parents[1] / "src" / "client"
        invalid_calls: list[str] = []

        for source_path in client_root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "enable_only" or len(node.args) != 1:
                    continue
                if isinstance(node.args[0], (ast.Tuple, ast.List, ast.Set)):
                    invalid_calls.append(f"{source_path}:{node.lineno}")

        self.assertEqual(invalid_calls, [])


if __name__ == "__main__":
    unittest.main()
