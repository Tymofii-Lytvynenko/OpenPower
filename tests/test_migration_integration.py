from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import (
    DomainGameEvent,
    EventMigrationFlowCreated,
    EventMigrationFlowResolved,
    EventMigrationPolicyUpdated,
    EventMigrationSignalUpdated,
    EventNewDay,
    EventRealSecond,
)
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.config import GameConfig
from src.shared.state import GameState


class TestMigrationContracts(unittest.TestCase):
    def test_bootstrap_seeds_default_policy_without_rewriting_legacy_law(self):
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["AAA", "BBB"]}),
            "country_governments": pl.DataFrame({"country_id": ["AAA"]}),
            "country_laws": pl.DataFrame({
                "country_id": ["AAA"],
                "law_id": ["migration_policy"],
                "group_name": ["Borders"],
                "title": ["Migration Policy"],
                "status": ["Legacy status"],
                "value": ["Legacy value"],
                "notes": ["Preserve this row."],
            }),
        })
        build_base_schema_registry().ensure_state(state)

        BootstrapSystem().update(state, 0.1)

        self.assertEqual(state.get_table("migration_policies")["country_id"].to_list(), ["AAA", "BBB"])
        policy = state.get_table("migration_policies").filter(pl.col("country_id") == "AAA").row(0, named=True)
        self.assertEqual(policy["migration_policy"], "managed")
        self.assertEqual(policy["border_policy"], "managed")
        self.assertEqual(state.get_table("country_laws")["value"].to_list(), ["Legacy value"])

    def test_politics_consumes_migration_pressure_once_and_records_law_review_signal(self):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["AAA"],
                "gvt_approval": [60.0],
                "gvt_stability": [60.0],
                "human_dev": [0.5],
                "gvt_corruption": [0.1],
            }),
            "country_laws": pl.DataFrame({
                "country_id": ["AAA"],
                "law_id": ["border_policy"],
                "group_name": ["Borders"],
                "title": ["Border Policy"],
                "status": ["Managed"],
                "value": ["Managed"],
                "notes": ["Existing law record."],
            }),
            "migration_signals": pl.DataFrame({
                "country_id": ["AAA"],
                "gross_inflow": [20],
                "gross_outflow": [0],
                "net_flow": [20],
                "working_age_delta": [12],
                "service_pressure": [0.8],
                "political_pressure": [0.7],
                "law_pressure": [0.5],
                "window_start_minute": [0],
                "updated_at_minute": [100],
                "politics_consumed_at_minute": [0],
                "economy_consumed_at_minute": [0],
            }),
        })
        build_base_schema_registry().ensure_state(state)
        state.time.total_minutes = 7 * 24 * 60
        state.time.day = 8
        state.events = [EventNewDay(day=8, month=1, year=2001)]
        system = PoliticsSystem()

        system.update(state, 0.1)

        approval_after = state.get_table("countries")["gvt_approval"][0]
        self.assertLess(approval_after, 60.0)
        signal = state.get_table("migration_signals").row(0, named=True)
        self.assertEqual(signal["politics_consumed_at_minute"], 100)
        law = state.get_table("country_laws").filter(
            pl.col("law_id") == "migration_pressure"
        ).row(0, named=True)
        self.assertEqual(law["status"], "Under pressure")
        self.assertEqual(
            state.get_table("country_laws").filter(pl.col("law_id") == "border_policy")["notes"][0],
            "Existing law record.",
        )

        system.update(state, 0.1)

        self.assertEqual(state.get_table("countries")["gvt_approval"][0], approval_after)

    def test_legacy_migration_policy_action_constructor_is_compatible(self):
        action = ActionUpdateMigrationPolicy("player-a", "AAA", "managed", "open")

        self.assertEqual(action.player_id, "player-a")
        self.assertEqual(action.country_tag, "AAA")
        self.assertEqual(action.migration_policy, "managed")
        self.assertEqual(action.border_policy, "open")
        self.assertIsNone(action.entry_rate)
        self.assertIsNone(action.effective_at_minute)

    def test_policy_action_exposes_optional_effective_controls(self):
        action = ActionUpdateMigrationPolicy(
            "player-a",
            "AAA",
            "open",
            "open",
            entry_rate=0.9,
            exit_rate=0.8,
            asylum_rate=0.7,
            family_reunification_rate=0.6,
            skilled_worker_preference=0.5,
            enforcement_strength=0.4,
            effective_at_minute=123,
        )

        self.assertEqual(action.entry_rate, 0.9)
        self.assertEqual(action.exit_rate, 0.8)
        self.assertEqual(action.asylum_rate, 0.7)
        self.assertEqual(action.family_reunification_rate, 0.6)
        self.assertEqual(action.skilled_worker_preference, 0.5)
        self.assertEqual(action.enforcement_strength, 0.4)
        self.assertEqual(action.effective_at_minute, 123)

    def test_migration_events_are_durable_domain_events_with_stable_payloads(self):
        events = (
            EventMigrationFlowCreated("flow-1", 1, 2, 10, "eligible_domestic", 20),
            EventMigrationFlowResolved("flow-1", "completed", 10, "completed", 30),
            EventMigrationPolicyUpdated("AAA", 40, "player", 20),
            EventMigrationSignalUpdated("AAA", 0.25, 0.1, 10, 30),
        )

        self.assertTrue(all(isinstance(event, DomainGameEvent) for event in events))
        self.assertEqual(
            asdict(events[0]),
            {
                "flow_id": "flow-1",
                "origin_region_id": 1,
                "destination_region_id": 2,
                "population_count": 10,
                "reason_code": "eligible_domestic",
                "at_minute": 20,
            },
        )
        self.assertEqual(asdict(events[1])["status"], "completed")
        self.assertEqual(asdict(events[2])["effective_at_minute"], 40)
        self.assertEqual(asdict(events[3])["net_flow"], 10)

    def test_completed_cohorts_reach_labor_gdp_per_capita_and_service_pressure(self):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["AAA", "BBB"],
                "gdp": [1_000.0, 1_000.0],
                "economic_previous_gdp": [1_000.0, 1_000.0],
                "money_reserves": [2_000.0, 2_000.0],
                "total_annual_revenue": [500.0, 500.0],
                "total_annual_expense": [400.0, 400.0],
                "human_dev": [0.7, 0.7],
                "poverty_rate": [0.2, 0.2],
                "employment_rate": [0.8, 0.8],
                "unemployment_rate": [0.2, 0.2],
                "minimum_wage": [100.0, 100.0],
                "economic_previous_minimum_wage": [100.0, 100.0],
                "gvt_approval": [50.0, 50.0],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["AAA", "BBB"],
                "pop_14": [0, 0],
                "pop_15_64": [1_000, 1_000],
                "pop_65": [0, 0],
                "housing_capacity": [2_000, 2_000],
                "employment_capacity": [2_000, 2_000],
                "service_capacity": [2_500, 2_500],
                "transport_capacity": [2_000, 2_000],
                "transport_access": [1.0, 1.0],
                "health_capacity": [1.0, 1.0],
            }),
        })
        build_base_schema_registry().ensure_state(state)
        state.time.total_minutes = 1_440
        state.update_table("migration_flows", pl.DataFrame([{
            "id": "cross-border-1",
            "origin_region_id": 1,
            "destination_region_id": 2,
            "origin_country_id": "AAA",
            "destination_country_id": "BBB",
            "dependent_count": 0,
            "working_age_count": 100,
            "elderly_count": 0,
            "population_count": 100,
            "reason_code": "eligible_mobility_agreement",
            "reason_factors_json": "{}",
            "created_at_minute": 1_000,
            "authorized_at_minute": 1_000,
            "expected_completion_at_minute": 1_440,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": "pending",
        }], schema=state.get_table("migration_flows").schema, strict=False))
        state.update_table("domestic_production", pl.DataFrame({
            "country_id": ["AAA", "BBB"],
            "game_resource_id": ["steel", "steel"],
            "domestic_production": [1_000.0, 1_000.0],
            "is_legal": [True, True],
            "is_gov_controlled": [False, False],
            "tax_rate": [0.0, 0.0],
        }))

        state.events = [EventNewDay(day=2, month=1, year=2001)]
        MigrationSystem().update(state, 0.1)
        self.assertGreater(state.get_table("migration_signals").height, 0)
        self.assertEqual(state.get_table("migration_signals")["country_id"].to_list(), ["AAA", "BBB"])
        state.events = [EventRealSecond(game_seconds_passed=1.0, is_paused=False)]
        EconomicHealthSystem().update(state, 1.0)
        self.assertEqual(state.get_table("migration_signals").height, 2)
        self.assertEqual(state.get_table("migration_signals")["country_id"].to_list(), ["AAA", "BBB"])
        InternalEconomySystem()._process_economy(state, 0.0)

        countries = state.get_table("countries").sort("id")
        regions = state.get_table("regions").sort("id")
        signals = state.get_table("migration_signals").sort("country_id")
        completed_flow = state.get_table("migration_flows").row(0, named=True)
        self.assertEqual(completed_flow["status"], "completed", completed_flow)
        self.assertEqual(regions["pop_15_64"].to_list(), [900, 1_100])
        self.assertEqual(countries["labor_supply"].to_list(), [900.0, 1_100.0])
        self.assertGreater(countries.filter(pl.col("id") == "AAA")["gdp_per_capita"][0], 1.0)
        self.assertLess(countries.filter(pl.col("id") == "BBB")["gdp_per_capita"][0], 1.0)
        self.assertGreater(signals.filter(pl.col("country_id") == "BBB")["service_pressure"][0], 0.0)
        self.assertEqual(signals.filter(pl.col("country_id") == "BBB")["gross_inflow"][0], 100)
        self.assertEqual(signals.filter(pl.col("country_id") == "BBB")["net_flow"][0], 100)
        self.assertLessEqual(signals.filter(pl.col("country_id") == "BBB")["political_pressure"][0], 1.0)
        self.assertEqual(
            signals.filter(pl.col("country_id") == "BBB")["economy_consumed_at_minute"][0],
            1_440,
        )

    def test_migration_cohorts_reweight_existing_country_service_projection(self):
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["AAA"]}),
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["AAA", "AAA"],
                "population": [1_000, 1_000],
                "pop_14": [0, 0],
                "pop_15_64": [1_000, 1_000],
                "pop_65": [0, 0],
                "housing_capacity": [2_000, 2_000],
                "employment_capacity": [2_000, 2_000],
                "service_capacity": [2_000, 2_000],
                "transport_capacity": [2_000, 2_000],
                "transport_access": [1.0, 1.0],
            }),
        })
        build_base_schema_registry().ensure_state(state)
        profiles = pl.DataFrame({
            "region_id": [1, 2],
            "category": ["utilities", "utilities"],
            "condition": [1.0, 1.0],
            "capacity": [1.0, 0.0],
        })
        infrastructure = InfrastructureSystem()
        infrastructure._materialize_read_models_from_frames(state, profiles)
        index_before = state.get_table("countries").item(0, "public_service_index")
        state.time.total_minutes = 100
        state.update_table("migration_flows", pl.DataFrame([{
            "id": "service-weight-flow",
            "origin_region_id": 1,
            "destination_region_id": 2,
            "origin_country_id": "AAA",
            "destination_country_id": "AAA",
            "dependent_count": 0,
            "working_age_count": 100,
            "elderly_count": 0,
            "population_count": 100,
            "reason_code": "eligible_domestic",
            "reason_factors_json": "{}",
            "created_at_minute": 0,
            "authorized_at_minute": 0,
            "expected_completion_at_minute": 100,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": "pending",
        }], schema=state.get_table("migration_flows").schema, strict=False))

        MigrationSystem().update(state, 0.0)
        infrastructure._materialize_read_models_from_frames(state, profiles)

        index_after = state.get_table("countries").item(0, "public_service_index")
        regions = state.get_table("regions").sort("id")
        self.assertEqual(regions["pop_15_64"].to_list(), [900, 1_100])
        self.assertEqual([InfrastructureSystem._regional_weight(row) for row in regions.to_dicts()], [900.0, 1_100.0])
        self.assertEqual(index_before, 0.5)
        self.assertAlmostEqual(index_after, 0.45)

    def test_pending_flow_and_signal_watermarks_survive_snapshot_and_save_load(self):
        state = self._pending_flow_state()
        signal = state.get_table("migration_signals").row(0, named=True)
        self.assertEqual(signal["economy_consumed_at_minute"], 90)

        snapshot = GameState.from_ipc(state.to_ipc())
        self.assertEqual(snapshot.get_table("migration_flows").item(0, "status"), "pending")
        self.assertEqual(snapshot.get_table("migration_flows").item(0, "population_count"), 10)
        self.assertEqual(snapshot.get_table("migration_signals").item(0, "economy_consumed_at_minute"), 90)
        self.assertEqual(
            sum(snapshot.get_table("regions").select("pop_14", "pop_15_64", "pop_65").sum().row(0)),
            100,
        )

        with tempfile.TemporaryDirectory() as save_root:
            config = GameConfig(Path(save_root))
            self.assertTrue(SaveWriter(config).save_game(state, "migration-roundtrip"))
            loaded = DataLoader(config, schema_registry=build_base_schema_registry()).load_save("migration-roundtrip")
            self.assertTrue(loaded.get_table("migration_flows").equals(state.get_table("migration_flows")))
            self.assertTrue(loaded.get_table("migration_signals").equals(state.get_table("migration_signals")))
            self.assertTrue(loaded.get_table("regions").equals(state.get_table("regions")))

    def test_three_identical_ordered_runs_replay_the_same_migration_trace(self):
        def replay():
            state = self._pending_flow_state()
            system = MigrationSystem()
            state.current_actions = [ActionUpdateMigrationPolicy(
                "AAA", "AAA", "restricted", "closed", effective_at_minute=200
            )]
            state.time.total_minutes = 100
            system.update(state, 0.0)
            state.current_actions = []
            state.time.total_minutes = 200
            system.update(state, 0.0)
            return (
                state.get_table("migration_flows").sort("id"),
                state.get_table("migration_policies").sort("country_id"),
                state.get_table("migration_signals").sort("country_id"),
                state.get_table("regions").sort("id").select("pop_14", "pop_15_64", "pop_65"),
                tuple(asdict(event) for event in state.events),
            )

        traces = [replay() for _ in range(3)]
        for trace in traces[1:]:
            for expected, actual in zip(traces[0][:-1], trace[:-1]):
                self.assertTrue(expected.equals(actual))
            self.assertEqual(traces[0][-1], trace[-1])

    @staticmethod
    def _pending_flow_state():
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["AAA"]}),
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["AAA", "AAA"],
                "pop_14": [20, 0],
                "pop_15_64": [80, 0],
                "pop_65": [0, 0],
                "housing_capacity": [200, 200],
                "employment_capacity": [200, 200],
                "service_capacity": [200, 200],
                "transport_capacity": [200, 200],
                "transport_access": [1.0, 1.0],
            }),
        })
        build_base_schema_registry().ensure_state(state)
        state.update_table("migration_flows", pl.DataFrame([{
            "id": "pending-roundtrip",
            "origin_region_id": 1,
            "destination_region_id": 2,
            "origin_country_id": "AAA",
            "destination_country_id": "AAA",
            "dependent_count": 2,
            "working_age_count": 8,
            "elderly_count": 0,
            "population_count": 10,
            "reason_code": "eligible_domestic",
            "reason_factors_json": "{}",
            "created_at_minute": 80,
            "authorized_at_minute": 80,
            "expected_completion_at_minute": 200,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": "pending",
        }], schema=state.get_table("migration_flows").schema, strict=False))
        state.update_table("migration_signals", pl.DataFrame([{
            "country_id": "AAA",
            "gross_inflow": 0,
            "gross_outflow": 0,
            "net_flow": 0,
            "working_age_delta": 0,
            "service_pressure": 0.0,
            "political_pressure": 0.0,
            "law_pressure": 0.0,
            "window_start_minute": 0,
            "updated_at_minute": 90,
            "politics_consumed_at_minute": 90,
            "economy_consumed_at_minute": 90,
        }], schema=state.get_table("migration_signals").schema, strict=False))
        state.time.total_minutes = 100
        return state


if __name__ == "__main__":
    unittest.main()
