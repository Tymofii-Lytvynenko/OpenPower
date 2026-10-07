import unittest

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.demographics.migration_system import MigrationSystem
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import EventMigrationFlowResolved, EventNewDay
from src.shared.state import GameState


class TestMigrationSystem(unittest.TestCase):
    def test_month_boundary_creates_only_nonzero_supported_flow(self):
        state = self._state()
        state.update_table(
            "migration_flows",
            pl.DataFrame(schema=state.get_table("migration_flows").schema),
        )
        system = MigrationSystem()
        state.time.total_minutes = 1_440
        state.events = [EventNewDay(day=1, month=2, year=2001)]
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(
                pl.lit(1.0).alias("migration_pressure")
            ),
        )
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("transport_access"),
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("health_capacity"),
            ),
        )
        state.update_table(
            "migration_policies",
            state.get_table("migration_policies").with_columns(
                pl.lit(1.0).alias("entry_rate"),
                pl.lit(1.0).alias("exit_rate"),
                pl.lit(1.0).alias("family_reunification_rate"),
            ),
        )

        system.update(state, 0.1)

        flow = state.get_table("migration_flows").filter(pl.col("status") == "pending")
        self.assertEqual(flow.height, 1)
        row = flow.row(0, named=True)
        self.assertEqual((row["origin_region_id"], row["destination_region_id"]), (1, 2))
        self.assertGreater(row["population_count"], 0)
        self.assertEqual(sum(row[field] for field in ("dependent_count", "working_age_count", "elderly_count")), row["population_count"])
        self.assertEqual(row["transition_rule"], "finish_authorized")

    def test_unauthorized_policy_action_is_inspectable_and_has_no_effect(self):
        state = self._state()
        system = MigrationSystem()
        state.time.total_minutes = 100
        state.current_actions = [
            ActionUpdateMigrationPolicy("unrelated-player", "AAA", "restricted", "closed")
        ]

        system.update(state, 0.1)

        policy = state.get_table("migration_policies").row(0, named=True)
        result = state.get_table("migration_policy_transitions").filter(
            pl.col("status") == "rejected"
        ).row(0, named=True)
        self.assertEqual(policy["migration_policy"], "open")
        self.assertEqual(policy["border_policy"], "open")
        self.assertEqual(result["reason_code"], "authority_denied")

    def test_invalid_policy_values_and_postures_are_rejected_with_reasons(self):
        state = self._state()
        state.current_actions = [
            ActionUpdateMigrationPolicy(
                "AAA", "AAA", "open", "open", entry_rate=float("nan")
            ),
            ActionUpdateMigrationPolicy("AAA", "AAA", "unsupported", "open"),
        ]

        MigrationSystem().update(state, 0.1)

        results = state.get_table("migration_policy_transitions").filter(
            pl.col("status") == "rejected"
        ).sort("id")
        self.assertEqual(set(results["reason_code"].to_list()), {
            "invalid_policy_value",
            "invalid_policy_posture",
        })
        self.assertEqual(state.get_table("migration_policies")["migration_policy"].to_list(), ["open"])

    def test_future_policy_transition_preserves_current_policy_and_authorized_flow(self):
        state = self._state()
        system = MigrationSystem()
        state.time.total_minutes = 100
        state.current_actions = [
            ActionUpdateMigrationPolicy(
                "AAA",
                "AAA",
                "restricted",
                "closed",
                entry_rate=0.0,
                effective_at_minute=150,
            )
        ]

        system.update(state, 0.1)

        active = state.get_table("migration_policies").row(0, named=True)
        scheduled = state.get_table("migration_policy_transitions").row(0, named=True)
        self.assertEqual(active["migration_policy"], "open")
        self.assertEqual(active["border_policy"], "open")
        self.assertEqual(scheduled["status"], "scheduled")
        self.assertEqual(scheduled["effective_at_minute"], 150)

        state.current_actions = []
        state.time.total_minutes = 150
        system.update(state, 0.1)

        active = state.get_table("migration_policies").row(0, named=True)
        self.assertEqual(active["migration_policy"], "restricted")
        self.assertEqual(active["border_policy"], "closed")
        self.assertEqual(active["entry_rate"], 0.0)
        self.assertEqual(active["exit_rate"], 0.5)
        self.assertEqual(state.get_table("migration_policy_transitions")["status"].to_list(), ["applied"])

        state.time.total_minutes = 200
        system.update(state, 0.1)

        flow = state.get_table("migration_flows").row(0, named=True)
        regions = state.get_table("regions").sort("id")
        self.assertEqual(flow["status"], "completed")
        self.assertEqual(flow["completed_at_minute"], 200)
        self.assertEqual(flow["reason_code"], "completed")
        self.assertEqual(regions.select("pop_14", "pop_15_64", "pop_65").row(0), (18, 72, 10))
        self.assertEqual(regions.select("pop_14", "pop_15_64", "pop_65").row(1), (2, 8, 0))
        self.assertEqual(
            sum(sum(row) for row in regions.select("pop_14", "pop_15_64", "pop_65").rows()),
            110,
        )
        self.assertTrue(
            any(isinstance(event, EventMigrationFlowResolved) for event in state.events)
        )

    def test_pending_flow_does_not_change_population_before_completion(self):
        state = self._state()
        system = MigrationSystem()
        state.time.total_minutes = 199

        system.update(state, 0.1)

        self.assertEqual(
            state.get_table("regions").sort("id").select("pop_14", "pop_15_64", "pop_65").rows(),
            [(20, 80, 10), (0, 0, 0)],
        )
        self.assertEqual(state.get_table("migration_flows")["status"].to_list(), ["pending"])

    def test_destination_capacity_rejection_is_visible_without_zero_value_event(self):
        state = self._state()
        state.update_table(
            "migration_flows",
            pl.DataFrame(schema=state.get_table("migration_flows").schema),
        )
        system = MigrationSystem()
        state.time.total_minutes = 1_440
        state.events = [EventNewDay(day=1, month=2, year=2001)]
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(
                pl.lit(1.0).alias("migration_pressure")
            ),
        )
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("transport_access"),
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("health_capacity"),
                pl.when(pl.col("id") == 2).then(0).otherwise(pl.col("housing_capacity")).alias("housing_capacity"),
            ),
        )

        system.update(state, 0.1)

        rejected = state.get_table("migration_flows").filter(pl.col("status") == "rejected")
        self.assertEqual(rejected.height, 1)
        self.assertEqual(rejected["reason_code"][0], "no_destination_capacity")
        self.assertFalse(any(isinstance(event, EventMigrationFlowResolved) for event in state.events))

    def test_capacity_change_redirects_authorized_flow_to_accessible_neighbor(self):
        state = self._state()
        regions = state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2).then(0).otherwise(pl.col("housing_capacity")).alias("housing_capacity"),
            pl.when(pl.col("id") == 2).then(0).otherwise(pl.col("employment_capacity")).alias("employment_capacity"),
            pl.when(pl.col("id") == 2).then(0).otherwise(pl.col("service_capacity")).alias("service_capacity"),
            pl.when(pl.col("id") == 2).then(0).otherwise(pl.col("transport_capacity")).alias("transport_capacity"),
        )
        alternate = pl.DataFrame([{
            "id": 3,
            "owner": "AAA",
            "pop_14": 0,
            "pop_15_64": 0,
            "pop_65": 0,
            "transport_access": 0.8,
            "health_capacity": 0.8,
            "housing_capacity": 100,
            "employment_capacity": 100,
            "service_capacity": 100,
            "transport_capacity": 100,
        }], schema=regions.schema, strict=False)
        state.update_table("regions", pl.concat([regions, alternate], how="vertical_relaxed"))
        adjacency = state.get_table("region_adjacency")
        state.update_table(
            "region_adjacency",
            pl.concat([
                adjacency,
                pl.DataFrame({"region_id": [1], "neighbor_region_id": [3]}, schema=adjacency.schema),
            ], how="vertical_relaxed"),
        )
        original_population = sum(
            sum(row)
            for row in state.get_table("regions").select("pop_14", "pop_15_64", "pop_65").rows()
        )
        state.time.total_minutes = 200

        MigrationSystem().update(state, 0.1)

        flows = state.get_table("migration_flows").sort("id").to_dicts()
        original = next(row for row in flows if row["id"] == "flow-1")
        follow_up = next(row for row in flows if row["id"] != "flow-1")
        self.assertEqual(original["status"], "redirected")
        self.assertEqual(original["reason_code"], "redirected_capacity")
        self.assertEqual(follow_up["status"], "pending")
        self.assertEqual(follow_up["destination_region_id"], 3)
        self.assertEqual(follow_up["population_count"], 10)
        self.assertEqual(follow_up["reason_code"], "redirected_capacity")
        self.assertIn('"redirected_to_region_id":3', original["reason_factors_json"])
        self.assertEqual(
            sum(
                sum(row)
                for row in state.get_table("regions").select("pop_14", "pop_15_64", "pop_65").rows()
            ),
            original_population,
        )
        self.assertTrue(any(
            isinstance(event, EventMigrationFlowResolved) and event.status == "redirected"
            for event in state.events
        ))

    def test_due_flows_resolve_in_order_without_overdrawing_source_or_capacity(self):
        state = self._state()
        regions = state.get_table("regions")
        third_region = pl.DataFrame([{
            "id": 3,
            "owner": "AAA",
            "pop_14": 0,
            "pop_15_64": 0,
            "pop_65": 0,
            "transport_access": 0.8,
            "health_capacity": 0.8,
            "housing_capacity": 60,
            "employment_capacity": 60,
            "service_capacity": 60,
            "transport_capacity": 60,
        }], schema=regions.schema, strict=False)
        regions = pl.concat([regions, third_region], how="vertical_relaxed").with_columns(
            pl.when(pl.col("id") == 1).then(100).otherwise(pl.col("pop_15_64")).alias("pop_15_64"),
            pl.when(pl.col("id") == 1).then(0).otherwise(pl.col("pop_14")).alias("pop_14"),
            pl.when(pl.col("id") == 1).then(0).otherwise(pl.col("pop_65")).alias("pop_65"),
            pl.when(pl.col("id") == 2).then(60).otherwise(pl.col("housing_capacity")).alias("housing_capacity"),
            pl.when(pl.col("id") == 2).then(60).otherwise(pl.col("employment_capacity")).alias("employment_capacity"),
            pl.when(pl.col("id") == 2).then(60).otherwise(pl.col("service_capacity")).alias("service_capacity"),
            pl.when(pl.col("id") == 2).then(60).otherwise(pl.col("transport_capacity")).alias("transport_capacity"),
        )
        state.update_table("regions", regions)
        common = {
            "origin_region_id": 1,
            "origin_country_id": "AAA",
            "dependent_count": 0,
            "working_age_count": 60,
            "elderly_count": 0,
            "population_count": 60,
            "reason_code": "eligible_domestic",
            "reason_factors_json": "{}",
            "created_at_minute": 0,
            "authorized_at_minute": 0,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": "pending",
        }
        state.update_table("migration_flows", pl.DataFrame([
            {
                **common,
                "id": "a-earlier",
                "destination_region_id": 2,
                "destination_country_id": "AAA",
                "expected_completion_at_minute": 100,
            },
            {
                **common,
                "id": "b-later",
                "destination_region_id": 3,
                "destination_country_id": "AAA",
                "expected_completion_at_minute": 200,
            },
        ], schema=state.get_table("migration_flows").schema, strict=False))
        state.time.total_minutes = 200

        MigrationSystem().update(state, 0.1)

        flows = state.get_table("migration_flows").sort("id").to_dicts()
        regions = state.get_table("regions").sort("id")
        self.assertEqual([row["status"] for row in flows], ["completed", "completed"])
        self.assertEqual([row["population_count"] for row in flows], [40, 60])
        self.assertEqual(flows[0]["reason_code"], "source_cohort_limit")
        self.assertEqual(regions["pop_15_64"].to_list(), [0, 40, 60])
        self.assertEqual(sum(regions["pop_15_64"].to_list()), 100)

    @staticmethod
    def _state():
        registry = build_base_schema_registry()
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["AAA"]}),
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["AAA", "AAA"],
                "pop_14": [20, 0],
                "pop_15_64": [80, 0],
                "pop_65": [10, 0],
                "transport_access": [0.7, 0.8],
                "health_capacity": [0.7, 0.8],
                "housing_capacity": [150, 50],
                "employment_capacity": [150, 50],
                "service_capacity": [150, 50],
                "transport_capacity": [150, 50],
            }),
            "region_adjacency": pl.DataFrame({
                "region_id": [1], "neighbor_region_id": [2],
            }),
            "migration_policies": pl.DataFrame([{
                "country_id": "AAA",
                "migration_policy": "open",
                "border_policy": "open",
                "entry_rate": 0.5,
                "exit_rate": 0.5,
                "asylum_rate": 0.25,
                "family_reunification_rate": 0.5,
                "skilled_worker_preference": 0.0,
                "enforcement_strength": 0.5,
                "effective_at_minute": 0,
                "updated_at_minute": 0,
                "source": "scenario",
            }]),
            "migration_flows": pl.DataFrame([{
                "id": "flow-1",
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
                "created_at_minute": 100,
                "authorized_at_minute": 100,
                "expected_completion_at_minute": 200,
                "completed_at_minute": 0,
                "transition_rule": "finish_authorized",
                "status": "pending",
            }]),
        })
        registry.ensure_state(state)
        for table_name, schema in (
            ("countries_relations", {"source": pl.Utf8, "target": pl.Utf8, "value": pl.Float64}),
            ("countries_wars", {"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}),
            ("treaty_effects", {"treaty_id": pl.Utf8, "country_id": pl.Utf8, "effect": pl.Utf8, "value": pl.Float64, "detail": pl.Utf8}),
            ("regional_infrastructure", {"region_id": pl.Int32, "category": pl.Utf8, "capacity": pl.Float64}),
            ("domestic_production", {"country_id": pl.Utf8, "domestic_production": pl.Float64}),
        ):
            state.update_table(table_name, pl.DataFrame(schema=schema))
        return state


if __name__ == "__main__":
    unittest.main()
