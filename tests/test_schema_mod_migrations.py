import unittest
from pathlib import Path

import polars as pl

from modules.base.schema import build_base_schema_registry
from src.engine.mod_manager import ModManager
from src.server.io.migrations import CORE_SAVE_MIGRATIONS
from src.server.state_migrations import migrate_political_state
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

    def test_schema_registry_reuses_already_normalized_frames(self):
        registry = WorldSchemaRegistry((
            TableSchema(
                name="sample",
                columns={
                    "id": ColumnSpec(pl.Int64, 0),
                    "enabled": ColumnSpec(pl.Boolean, True),
                },
                key_columns=("id",),
                owner="test",
            ),
        ))
        frame = pl.DataFrame({"id": [1], "enabled": [True], "extra": ["kept"]})

        normalized = registry.normalize("sample", frame)

        self.assertIs(normalized, frame)

    def test_core_save_migration_initializes_runtime_contracts(self):
        meta = {"version": 1}
        MigrationRegistry(CORE_SAVE_MIGRATIONS).migrate(meta, {})

        self.assertEqual(meta["version"], 2)
        self.assertIn("determinism", meta)
        self.assertIn("journal", meta)
        self.assertEqual(meta["schema_versions"], {})

    def test_economic_schema_normalizes_legacy_and_partial_contract_rows(self):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["A"],
                "gdp": [1_000.0],
                "money_reserves": [250.0],
                "scenario_note": ["preserved"],
            }),
            "debt_contracts": pl.DataFrame({
                "id": ["legacy-loan"],
                "principal_remaining": [75.0],
            }),
        })

        build_base_schema_registry().ensure_state(state)

        country = state.get_table("countries").row(0, named=True)
        contract = state.get_table("debt_contracts").row(0, named=True)
        self.assertEqual(country["gdp"], 1_000.0)
        self.assertEqual(country["money_reserves"], 250.0)
        self.assertEqual(country["scenario_note"], "preserved")
        self.assertEqual(country["inflation_rate"], 0.0)
        self.assertEqual(country["economic_health"], 1.0)
        self.assertEqual(contract["principal_remaining"], 75.0)
        self.assertEqual(contract["maturity_months"], 0)
        self.assertEqual(contract["status"], "pending")
        self.assertTrue(state.get_table("economic_policy_transitions").is_empty())
        self.assertTrue(state.get_table("debt_distress_cases").is_empty())
        self.assertTrue(state.get_table("economic_cause_records").is_empty())

    def test_migration_schema_initializes_empty_legacy_tables_without_changing_cohorts(self):
        regions = pl.DataFrame({
            "id": [11],
            "owner": ["A"],
            "pop_14": [4],
            "pop_15_64": [7],
            "pop_65": [2],
        })
        state = GameState(tables={"regions": regions})

        build_base_schema_registry().ensure_state(state)

        self.assertTrue(state.get_table("migration_policies").is_empty())
        self.assertTrue(state.get_table("migration_policy_transitions").is_empty())
        self.assertTrue(state.get_table("migration_flows").is_empty())
        self.assertTrue(state.get_table("migration_signals").is_empty())
        self.assertEqual(
            state.get_table("regions").select("pop_14", "pop_15_64", "pop_65").row(0),
            (4, 7, 2),
        )
        self.assertEqual(
            build_base_schema_registry().get("migration_flows").key_columns,
            ("id",),
        )
        self.assertEqual(
            build_base_schema_registry().get("migration_policy_transitions").key_columns,
            ("id",),
        )

    def test_political_state_migration_adds_contract_defaults_without_reseeding_or_ownership_changes(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame({"id": ["AAA"]}),
                "regions": pl.DataFrame({"id": [7], "owner": ["AAA"], "controller": ["AAA"]}),
                "country_governments": pl.DataFrame(
                    {"country_id": ["AAA"], "government_form_id": ["legacy form"]}
                ),
                "political_crises": pl.DataFrame(
                    {
                        "id": ["legacy-crisis"],
                        "country_id": ["AAA"],
                        "status": ["active"],
                        "legacy_marker": ["preserve"],
                    }
                ),
            }
        )
        owners_before = state.get_table("regions")["owner"].to_list()

        migrate_political_state(state)

        government = state.get_table("country_governments").row(0, named=True)
        crisis = state.get_table("political_crises").row(0, named=True)
        self.assertEqual(government["government_form_id"], "legacy form")
        self.assertEqual(government["ruling_party_id"], "")
        self.assertEqual(government["next_election_at_minute"], 0)
        self.assertEqual(crisis["id"], "legacy-crisis")
        self.assertEqual(crisis["status"], "active")
        self.assertEqual(crisis["legacy_marker"], "preserve")
        self.assertTrue(state.get_table("political_elections").is_empty())
        self.assertTrue(state.get_table("political_effects").is_empty())
        self.assertEqual(state.get_table("regions")["owner"].to_list(), owners_before)
        political_tables = {
            "country_governments",
            "government_form_rules",
            "political_parties",
            "country_laws",
            "law_transitions",
            "political_elections",
            "political_crises",
            "political_effects",
            "political_history",
        }
        self.assertTrue(political_tables.issubset(build_base_schema_registry().versions()))
        revisions = dict(state.table_revisions)
        migrate_political_state(state)
        self.assertEqual(state.table_revisions, revisions)

    def test_base_module_contributes_systems_schemas_and_api_version(self):
        manager = ModManager(GameConfig(PROJECT_ROOT))
        manifests = manager.resolve_load_order()
        runtime = manager.load_runtime()

        self.assertEqual(manifests[0].api_version, 1)
        system_ids = {system.id for system in runtime.systems}
        self.assertEqual(len(system_ids), 30)
        self.assertIn("base.economic_health", system_ids)
        self.assertIn("base.migration", system_ids)
        self.assertIn("base.recognition", system_ids)
        self.assertIn("base.political_lifecycle", system_ids)
        self.assertIn("base.campaign", system_ids)
        self.assertIn("base.campaign_setup", system_ids)
        self.assertIn("base.history", system_ids)
        self.assertIn("base.advanced_diplomacy", system_ids)
        self.assertIn("base.diplomatic_balance", system_ids)
        self.assertTrue({
            "base.battle_strategy",
            "base.military_capabilities",
            "base.military_programs",
            "base.covert_operations",
            "base.strategic_warfare",
            "base.foreign_orders",
            "base.infrastructure",
        }.issubset(system_ids))
        self.assertIn("countries", runtime.schemas.table_names)
        self.assertIn("pending_treaties", runtime.schemas.table_names)
        self.assertTrue({
            "history_indicator_definitions", "history_series_state", "history_snapshots", "history_events",
        }.issubset(runtime.schemas.table_names))
        self.assertTrue({
            "recognition_cases",
            "recognition_votes",
            "regional_recognition_status",
            "regional_production",
        }.issubset(runtime.schemas.table_names))
        self.assertIn("regional_infrastructure", runtime.schemas.table_names)
        self.assertIn("infrastructure_projects", runtime.schemas.table_names)
        self.assertIn("infrastructure_damage_records", runtime.schemas.table_names)
        self.assertTrue({
            "government_form_rules",
            "political_parties",
            "law_transitions",
            "political_elections",
            "political_crises",
            "political_effects",
            "political_history",
        }.issubset(runtime.schemas.table_names))
        self.assertTrue({
            "campaign_scenarios",
            "campaigns",
            "sphere_delegations",
            "advisor_recommendations",
        }.issubset(runtime.schemas.table_names))
        self.assertIn("objective_type", runtime.schemas.get("objectives").columns)


if __name__ == "__main__":
    unittest.main()
