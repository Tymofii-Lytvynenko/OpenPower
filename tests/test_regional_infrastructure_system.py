from __future__ import annotations

import unittest
import copy
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionCancelInfrastructureProject, ActionInvestRegionalInfrastructure
from src.shared.config import GameConfig
from src.shared.events import EventRandomEventTriggered
from src.shared.state import GameState
from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


class RegionalInfrastructureSystemTest(unittest.TestCase):
    def test_elapsed_frame_path_matches_row_path_with_occupation_and_maintenance(self):
        from polars.testing import assert_frame_equal
        state = build_infrastructure_state()
        ensure_base_tables(state)
        state.update_table("countries", state.get_table("countries").with_columns(
            pl.lit(0.35).alias("budget_infra_ratio"), pl.lit(0.65).alias("budget_health_ratio"),
            pl.lit(0.2).alias("budget_telecom_ratio"),
        ))
        InfrastructureSystem().update(state, 0.0)
        state.time.total_minutes = 60
        state.update_table("occupations", pl.DataFrame({"region_id": [101], "occupation_status": ["active"]}))
        reference = copy.deepcopy(state)
        InfrastructureSystem().update(state, 0.1)
        with patch.object(InfrastructureSystem, "_can_refresh_read_models_without_mutable_rows", return_value=False):
            InfrastructureSystem().update(reference, 0.1)
        for name in ("regional_infrastructure", "regions", "countries"):
            assert_frame_equal(state.get_table(name), reference.get_table(name), check_exact=False, rel_tol=1e-12, abs_tol=1e-12)

    def test_scenario_category_is_seeded_and_survives_the_vectorized_refresh_path(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        state.globals["infrastructure_category_policies"] = {
            "airports": {
                "baseline": 0.1,
                "maximum": 0.8,
                "construction_cost_per_level": 200_000.0,
                "construction_minutes_per_level": 10_000,
                "maintenance_cost_per_level_month": 400.0,
                "annual_depreciation": 0.02,
            }
        }
        system = InfrastructureSystem()

        system.update(state, 0.0)
        before = state.get_table("regional_infrastructure").filter(
            pl.col("category") == "airports"
        )
        system.update(state, 0.0)

        after = state.get_table("regional_infrastructure").filter(
            pl.col("category") == "airports"
        )
        self.assertEqual(before.height, 3)
        self.assertEqual(after.to_dicts(), before.to_dicts())
        self.assertTrue((after["level"] == 0.1).all())

    def test_legacy_profiles_initialize_without_changing_existing_world_totals(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        original_countries = state.get_table("countries").select("id", "money_reserves", "gdp")
        original_regions = state.get_table("regions").select("id", "owner", "population")

        InfrastructureSystem().update(state, 0.0)

        profiles = state.get_table("regional_infrastructure")
        self.assertEqual(profiles.height, 12)
        self.assertEqual(
            state.get_table("countries").select("id", "money_reserves", "gdp").to_dicts(),
            original_countries.to_dicts(),
        )
        self.assertEqual(
            state.get_table("regions").select("id", "owner", "population").to_dicts(),
            original_regions.to_dicts(),
        )
        transport = profiles.filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        ).to_dicts()[0]
        self.assertAlmostEqual(transport["level"], 0.4)
        self.assertAlmostEqual(transport["condition"], 0.9)

    def test_duplicate_region_ids_do_not_multiply_on_repeated_projection_refreshes(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        regions = state.get_table("regions")
        duplicated_regions = pl.concat(
            [regions, regions.filter(pl.col("id") == 101)],
            how="vertical",
        )
        state.update_table("regions", duplicated_regions)
        expected_height = duplicated_regions.height
        expected_unique_ids = duplicated_regions["id"].n_unique()
        system = InfrastructureSystem()

        for minute in (0, 60, 120):
            state.time.total_minutes = minute
            system.update(state, 0.0)

            actual_regions = state.get_table("regions")
            self.assertEqual(actual_regions.height, expected_height)
            self.assertEqual(actual_regions["id"].n_unique(), expected_unique_ids)

    def test_investment_is_reserved_once_and_completes_on_game_time(self):
        state = self._prepared_state()
        initial_reserves = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]
        system = InfrastructureSystem()

        system.update(state, 0.0)

        project = state.get_table("infrastructure_projects").to_dicts()[0]
        reserved_reserves = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        self.assertEqual(project["status"], "in_progress")
        self.assertLess(reserved_reserves, initial_reserves)
        self.assertAlmostEqual(initial_reserves - reserved_reserves, project["cost_total"])

        state.current_actions = []
        state.time.total_minutes = project["started_at_minute"] + project["duration_minutes"]
        system.update(state, 0.0)

        completed = state.get_table("infrastructure_projects").to_dicts()[0]
        profile = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        ).to_dicts()[0]
        self.assertEqual(completed["status"], "completed")
        self.assertAlmostEqual(profile["level"], 0.6)

    def test_active_project_completion_matches_row_path_for_upgrades_and_repairs(self):
        from polars.testing import assert_frame_equal

        system = InfrastructureSystem()
        for project_type in ("upgrade", "repair"):
            with self.subTest(project_type=project_type):
                state = self._prepared_state()
                target_level = 0.6
                if project_type == "repair":
                    state.update_table(
                        "strategic_impacts",
                        pl.DataFrame(
                            [{"id": "damage-parity-1", "region_id": 101,
                              "category": "infrastructure", "severity": 0.5}],
                            schema=state.get_table("strategic_impacts").schema,
                        ),
                    )
                    system.update(state, 0.0)
                    target_level = state.get_table("infrastructure_damage_records")[
                        "restoration_ceiling"
                    ][0]

                state.current_actions = [
                    ActionInvestRegionalInfrastructure(
                        "player-1", "USA", 101, "transport", target_level
                    )
                ]
                system.update(state, 0.0)
                project = state.get_table("infrastructure_projects").to_dicts()[0]
                self.assertEqual(project["project_type"], project_type)
                state.current_actions = []
                if project_type == "repair":
                    state.update_table(
                        "strategic_impacts", state.get_table("strategic_impacts").head(0)
                    )
                state.time.total_minutes = project["started_at_minute"] + project[
                    "duration_minutes"
                ]
                reference = copy.deepcopy(state)

                system.update(state, 0.0)
                with patch.object(
                    InfrastructureSystem,
                    "_can_refresh_read_models_without_mutable_rows",
                    return_value=False,
                ):
                    system.update(reference, 0.0)

                for table_name in (
                    "regional_infrastructure",
                    "infrastructure_projects",
                    "infrastructure_damage_records",
                    "regions",
                    "countries",
                ):
                    assert_frame_equal(
                        state.get_table(table_name),
                        reference.get_table(table_name),
                        check_exact=False,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )

    def test_invalid_authority_and_project_conflict_do_not_debit_treasury(self):
        state = self._prepared_state()
        before = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        system = InfrastructureSystem()

        state.current_actions = [
            ActionInvestRegionalInfrastructure("unmapped-player", "USA", 101, "transport", 0.6)
        ]
        system.update(state, 0.0)
        after_unauthorized = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        self.assertEqual(after_unauthorized, before)

        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 202, "transport", 0.7)
        ]
        system.update(state, 0.0)
        after_foreign = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        self.assertEqual(after_foreign, before)

        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]
        system.update(state, 0.0)
        reserved = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.8)
        ]
        system.update(state, 0.0)
        self.assertEqual(
            state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0],
            reserved,
        )

    def test_insufficient_treasury_and_zero_budget_are_rejected_atomically(self):
        state = self._prepared_state()
        system = InfrastructureSystem()
        before_profile = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        ).row(0, named=True)
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(
                pl.when(pl.col("id") == "USA")
                .then(1.0).otherwise(pl.col("money_reserves")).alias("money_reserves")
            ),
        )
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]

        system.update(state, 0.0)

        self.assertTrue(state.get_table("infrastructure_projects").is_empty())
        self.assertEqual(
            state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0],
            1.0,
        )
        self.assertEqual(
            state.get_table("regional_infrastructure").filter(
                (pl.col("region_id") == 101) & (pl.col("category") == "transport")
            ).row(0, named=True),
            before_profile,
        )
        self.assertIn("insufficient", state.journal.command_results[-1]["reason"].lower())

        state.current_actions = []
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(
                pl.when(pl.col("id") == "USA")
                .then(100_000.0).otherwise(pl.col("money_reserves")).alias("money_reserves"),
                pl.when(pl.col("id") == "USA")
                .then(0.0).otherwise(pl.col("budget_infra_ratio")).alias("budget_infra_ratio"),
            ),
        )
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]
        system.update(state, 0.0)

        self.assertTrue(state.get_table("infrastructure_projects").is_empty())
        self.assertEqual(
            state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0],
            100_000.0,
        )

    def test_cancel_refunds_only_uncompleted_project_value(self):
        state = self._prepared_state()
        system = InfrastructureSystem()
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.8)
        ]
        system.update(state, 0.0)
        project = state.get_table("infrastructure_projects").to_dicts()[0]
        state.current_actions = []
        state.time.total_minutes = project["started_at_minute"] + project["duration_minutes"] // 2
        system.update(state, 0.0)
        before_cancel = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]

        state.current_actions = [ActionCancelInfrastructureProject("player-1", project["id"])]
        system.update(state, 0.0)

        updated = state.get_table("infrastructure_projects").filter(pl.col("id") == project["id"]).to_dicts()[0]
        after_cancel = state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0]
        self.assertEqual(updated["status"], "cancelled")
        self.assertGreater(after_cancel, before_cancel)
        self.assertLess(after_cancel - before_cancel, project["cost_total"])

    def test_project_pauses_when_control_is_lost_and_resumes_without_losing_progress(self):
        state = self._prepared_state()
        system = InfrastructureSystem()
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.8)
        ]
        system.update(state, 0.0)
        project = state.get_table("infrastructure_projects").to_dicts()[0]
        state.current_actions = []
        half_time = project["duration_minutes"] // 2
        state.time.total_minutes += half_time
        system.update(state, 0.0)
        progress_before_loss = state.get_table("infrastructure_projects")["progress"][0]
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 101).then(pl.lit("CAN")).otherwise(pl.col("owner")).alias("owner")
            ),
        )
        state.time.total_minutes += 30
        system.update(state, 0.0)
        paused = state.get_table("infrastructure_projects").to_dicts()[0]
        self.assertEqual(paused["status"], "paused")
        self.assertAlmostEqual(paused["progress"], progress_before_loss)

        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 101).then(pl.lit("USA")).otherwise(pl.col("owner")).alias("owner")
            ),
        )
        state.time.total_minutes += 30
        system.update(state, 0.0)
        resumed = state.get_table("infrastructure_projects").to_dicts()[0]
        self.assertEqual(resumed["status"], "in_progress")
        self.assertAlmostEqual(resumed["progress"], progress_before_loss)

    def test_maintenance_allocation_reduces_depreciation_and_repair_respects_damage_ceiling(self):
        fully_funded = self._prepared_state()
        unfunded = self._prepared_state()
        for state, allocation in ((fully_funded, 1.0), (unfunded, 0.0)):
            state.update_table(
                "countries",
                state.get_table("countries").with_columns(pl.lit(allocation).alias("budget_infra_ratio")),
            )
        year = 365 * 24 * 60
        fully_funded.time.total_minutes = year
        unfunded.time.total_minutes = year
        system = InfrastructureSystem()
        system.update(fully_funded, 0.0)
        system.update(unfunded, 0.0)
        funded_condition = fully_funded.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["condition"][0]
        unfunded_condition = unfunded.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["condition"][0]
        self.assertGreater(funded_condition, unfunded_condition)

        state = self._prepared_state()
        state.update_table(
            "strategic_impacts",
            pl.DataFrame(
                [{"id": "damage-repair-1", "region_id": 101, "category": "infrastructure", "severity": 0.5}],
                schema=state.get_table("strategic_impacts").schema,
            ),
        )
        system.update(state, 0.0)
        damaged_profile = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        ).to_dicts()[0]
        ceiling = state.get_table("infrastructure_damage_records")["restoration_ceiling"][0]
        repair_target = ceiling
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", repair_target)
        ]
        system.update(state, 0.0)
        project = state.get_table("infrastructure_projects").to_dicts()[0]
        state.current_actions = []
        state.time.total_minutes = project["duration_minutes"]
        system.update(state, 0.0)
        repaired = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["capacity"][0]
        self.assertGreater(repaired, damaged_profile["capacity"])
        self.assertLessEqual(repaired, ceiling)
        self.assertTrue(state.get_table("infrastructure_damage_records")["recovered"][0])

    def test_scenario_damage_response_and_occupation_wear_are_applied_deterministically(self):
        event_state = self._prepared_state()
        event_state.globals["infrastructure_category_policies"] = {
            "transport": {"damage_response": {"earthquake": 0.5}}
        }
        event_state.events.append(
            EventRandomEventTriggered("earthquake-1", "earthquake", 101, 0.4)
        )
        InfrastructureSystem().update(event_state, 0.0)
        damage = event_state.get_table("infrastructure_damage_records").filter(
            pl.col("category") == "transport"
        ).row(0, named=True)
        self.assertAlmostEqual(damage["severity"], 0.2)

        occupied = self._prepared_state()
        unoccupied = self._prepared_state()
        for state in (occupied, unoccupied):
            state.time.total_minutes = 365 * 24 * 60
        occupied.update_table(
            "occupations",
            pl.DataFrame(
                [{
                    "region_id": 101,
                    "controller_country_id": "CAN",
                    "occupation_status": "active",
                    "contested": False,
                }],
                schema=occupied.get_table("occupations").schema,
            ),
        )
        InfrastructureSystem().update(occupied, 0.0)
        InfrastructureSystem().update(unoccupied, 0.0)
        occupied_condition = occupied.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["condition"][0]
        unoccupied_condition = unoccupied.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["condition"][0]
        self.assertLess(occupied_condition, unoccupied_condition)

    def test_partial_legacy_tables_snapshot_and_save_load_preserve_infrastructure_state(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        state.update_table(
            "regional_infrastructure",
            pl.DataFrame({"region_id": [101], "category": ["transport"], "level": [0.5]}),
        )
        self.assertEqual(state.get_table("regional_infrastructure").schema["condition"], pl.Float64)
        self.assertEqual(state.get_table("infrastructure_projects").schema["status"], pl.Utf8)
        system = InfrastructureSystem()
        system.update(state, 0.0)
        state.update_table(
            "strategic_impacts",
            pl.DataFrame(
                [{"id": "saved-damage", "region_id": 101, "category": "infrastructure", "severity": 0.1}],
                schema=state.get_table("strategic_impacts").schema,
            ),
        )
        system.update(state, 0.0)
        state.current_actions = [
            ActionInvestRegionalInfrastructure("player-1", "USA", 101, "transport", 0.6)
        ]
        system.update(state, 0.0)
        state.current_actions = []

        snapshot = GameState.from_ipc(state.to_ipc())
        ensure_base_tables(snapshot)
        self.assertEqual(
            snapshot.get_table("infrastructure_projects").to_dicts(),
            state.get_table("infrastructure_projects").to_dicts(),
        )
        self.assertEqual(
            snapshot.get_table("infrastructure_damage_records").to_dicts(),
            state.get_table("infrastructure_damage_records").to_dicts(),
        )

        with TemporaryDirectory(prefix="openpower-infrastructure-") as root:
            config = GameConfig(Path(root))
            self.assertTrue(SaveWriter(config).save_game(state, "infrastructure-slot"))
            loaded = DataLoader(
                config,
                schema_registry=build_base_schema_registry(),
            ).load_save("infrastructure-slot")
            self.assertEqual(
                loaded.get_table("regional_infrastructure").to_dicts(),
                state.get_table("regional_infrastructure").to_dicts(),
            )
            self.assertEqual(
                loaded.get_table("infrastructure_projects").to_dicts(),
                state.get_table("infrastructure_projects").to_dicts(),
            )
            self.assertEqual(
                loaded.get_table("infrastructure_damage_records").to_dicts(),
                state.get_table("infrastructure_damage_records").to_dicts(),
            )
            self.assertEqual(
                loaded.globals["infrastructure_last_update_minute"],
                state.globals["infrastructure_last_update_minute"],
            )

    def test_stable_frame_refresh_preserves_weighted_outputs_and_clamps_corrupt_values(self):
        state = self._prepared_state()
        state.update_table(
            "regional_infrastructure",
            state.get_table("regional_infrastructure").with_columns(
                pl.when((pl.col("region_id") == 101) & (pl.col("category") == "transport"))
                .then(1.4).otherwise(pl.col("level")).alias("level"),
                pl.when((pl.col("region_id") == 101) & (pl.col("category") == "transport"))
                .then(-0.5).otherwise(pl.col("condition")).alias("condition"),
            ),
        )
        system = InfrastructureSystem()

        system.update(state, 0.0)

        transport = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        ).row(0, named=True)
        region = state.get_table("regions").filter(pl.col("id") == 101).row(0, named=True)
        country = state.get_table("countries").filter(pl.col("id") == "USA").row(0, named=True)
        self.assertEqual(transport["level"], 1.0)
        self.assertEqual(transport["condition"], 0.0)
        self.assertEqual(transport["capacity"], 0.0)
        self.assertEqual(region["transport_access"], 0.0)
        self.assertAlmostEqual(country["infrastructure_index"], 0.0)

    def _prepared_state(self) -> GameState:
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        state.current_actions = []
        return state


if __name__ == "__main__":
    unittest.main()
