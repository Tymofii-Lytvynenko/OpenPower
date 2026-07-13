import unittest
from pathlib import Path

import polars as pl

from src.engine.mod_manager import ModManager
from src.server.io.migrations import CORE_SAVE_MIGRATIONS
from src.shared.config import GameConfig
from src.shared.migrations import MigrationRegistry
from src.shared.schema import ColumnSpec, TableSchema, WorldSchemaRegistry
from src.shared.state import GameState


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSchemaModMigrations(unittest.TestCase):
    def test_schema_registry_normalizes_defaults_types_and_extra_columns(self):
        registry = WorldSchemaRegistry(
            (
                TableSchema(
                    name="sample",
                    columns={
                        "id": ColumnSpec(pl.Int64, 0),
                        "enabled": ColumnSpec(pl.Boolean, True),
                    },
                    key_columns=("id",),
                    owner="test",
                ),
            )
        )

        normalized = registry.normalize(
            "sample",
            pl.DataFrame({"id": [1], "extra": ["kept"]}, schema={"id": pl.Int32, "extra": pl.Utf8}),
        )
        self.assertEqual(normalized.schema["id"], pl.Int64)
        self.assertEqual(normalized["enabled"].to_list(), [True])
        self.assertEqual(normalized["extra"].to_list(), ["kept"])

        duplicate_state = GameState(
            tables={
                "sample": pl.DataFrame(
                    {"id": [1, 1], "enabled": [True, False]},
                    schema={"id": pl.Int64, "enabled": pl.Boolean},
                )
            }
        )
        self.assertIn(
            "duplicate_key",
            {issue.code for issue in registry.validate_state(duplicate_state)},
        )

        with self.assertRaisesRegex(RuntimeError, "Schema conflict"):
            registry.register(
                TableSchema(
                    name="sample",
                    columns={"id": ColumnSpec(pl.Utf8, "")},
                    owner="conflicting-mod",
                )
            )

    def test_core_save_migration_initializes_runtime_contracts(self):
        meta = {"version": 1}
        MigrationRegistry(CORE_SAVE_MIGRATIONS).migrate(meta, {})

        self.assertEqual(meta["version"], 2)
        self.assertIn("determinism", meta)
        self.assertIn("journal", meta)
        self.assertEqual(meta["schema_versions"], {})

    def test_base_module_contributes_systems_schemas_and_api_version(self):
        manager = ModManager(GameConfig(PROJECT_ROOT))
        manifests = manager.resolve_load_order()
        runtime = manager.load_runtime()

        self.assertEqual(manifests[0].api_version, 1)
        self.assertEqual(len(runtime.systems), 15)
        self.assertIn("countries", runtime.schemas.table_names)
        self.assertIn("pending_treaties", runtime.schemas.table_names)


if __name__ == "__main__":
    unittest.main()
