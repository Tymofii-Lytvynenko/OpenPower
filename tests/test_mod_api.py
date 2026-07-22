import unittest
from functools import partial

import polars as pl

from src.engine.simulator import Engine
from src.shared.migrations import SaveMigration
from src.shared.mod_api import feature, mod
from src.shared.schema import ColumnSpec, TableSchema
from src.shared.state import GameState
from src.shared.system_interfaces import SystemAccess
from src.shared.system_state import SYSTEM_STATE_HELPER


class SimpleSystem:
    access = SystemAccess()

    @property
    def id(self) -> str:
        return "test.simple"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return None


class ConfiguredSystem:
    access = SystemAccess()
    runtime_state_contract = {"_system_id": SYSTEM_STATE_HELPER}

    def __init__(self, system_id: str):
        self._system_id = system_id

    @property
    def id(self) -> str:
        return self._system_id

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return None


def migrate_feature(meta, tables) -> None:
    meta["feature_migrated"] = True


class TestModApi(unittest.TestCase):
    def test_mod_accepts_classes_instances_factories_and_feature_packs(self):
        feature_schema = TableSchema(
            name="feature_table",
            columns={"id": ColumnSpec(pl.Int64, 0)},
            key_columns=("id",),
            owner="test-feature",
        )
        feature_migration = SaveMigration(1, 2, migrate_feature, owner="test-feature")
        economy = feature(
            partial(ConfiguredSystem, "test.feature"),
            schemas=(feature_schema,),
            migrations=(feature_migration,),
            name="economy",
        )

        contribution = mod(
            SimpleSystem,
            ConfiguredSystem("test.instance"),
            partial(ConfiguredSystem, "test.factory"),
            features=(economy,),
        )

        engine = Engine()
        engine.register_systems(contribution.systems)

        self.assertEqual(
            [system.id for system in contribution.systems],
            ["test.simple", "test.instance", "test.factory", "test.feature"],
        )
        self.assertEqual(contribution.table_schemas, (feature_schema,))
        self.assertEqual(contribution.save_migrations, (feature_migration,))

        single_feature = mod(features=economy)
        self.assertEqual(single_feature.systems[0].id, "test.feature")

    def test_mod_reports_invalid_specs_at_declaration_time(self):
        with self.assertRaisesRegex(TypeError, "zero-argument factory"):
            mod(ConfiguredSystem)

        with self.assertRaisesRegex(TypeError, "does not implement the ISystem contract"):
            mod(lambda: object())

        with self.assertRaisesRegex(TypeError, "features must contain ModFeature"):
            mod(features=(object(),))


if __name__ == "__main__":
    unittest.main()
