from __future__ import annotations

import ast
from pathlib import Path
import unittest


class EngagementLayerBoundaryTests(unittest.TestCase):
    def test_shared_layer_has_no_engagement_mechanism_module(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        self.assertFalse((workspace / "src" / "shared" / "engagement.py").exists())

    def test_military_policy_does_not_import_engagement_geometry_into_shared(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        shared_root = workspace / "src" / "shared"
        forbidden = {"src.core.map.engagement_geometry", "modules.base.systems.military.war_policy"}
        for path in shared_root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            }
            self.assertTrue(
                imports.isdisjoint(forbidden),
                f"shared contract {path.name} imports gameplay engagement policy",
            )


if __name__ == "__main__":
    unittest.main()
