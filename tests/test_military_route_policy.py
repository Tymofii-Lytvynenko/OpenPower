from __future__ import annotations

import unittest
from unittest.mock import patch

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, MilitarySystem, UnitFactory
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionDispatchUnitDeployment, ActionMoveUnit
from src.shared.state import GameState


class MilitaryRoutePlannerTest(unittest.TestCase):
    def test_prepared_graph_rechecks_access_and_preserves_cost_tie_breaking(self) -> None:
        regions = [{"id": value} for value in range(1, 5)]
        edges = [
            {"region_id": 1, "neighbor_region_id": 2},
            {"region_id": 2, "neighbor_region_id": 4},
            {"region_id": 1, "neighbor_region_id": 3},
            {"region_id": 3, "neighbor_region_id": 4},
        ]
        planner = MilitaryRoutePlanner()
        with patch.object(planner, "_adjacency", wraps=planner._adjacency) as build_graph:
            graph = planner.prepare(regions, edges)
            for blocked in (None, 2, 3):
                allowed = lambda region, _final: region["id"] != blocked
                plan = planner.plan(1, 4, regions, edges, allowed, prepared_graph=graph)
                assert plan.region_ids == ((1, 3, 4) if blocked == 2 else (1, 2, 4))
                assert plan.travel_cost == 2.0
            manual = planner.plan(
                1, 4, regions, edges, lambda region, _final: region["id"] != 2,
                explicit_waypoints=[2], prepared_graph=graph,
            )
            assert not manual.is_valid
            assert build_graph.call_count == 1

    def test_finds_least_cost_route_and_breaks_ties_by_region_id(self) -> None:
        regions = [{"id": value} for value in range(1, 5)]
        edges = [
            {"region_id": 1, "neighbor_region_id": 2},
            {"region_id": 2, "neighbor_region_id": 4},
            {"region_id": 1, "neighbor_region_id": 3},
            {"region_id": 3, "neighbor_region_id": 4},
        ]
        costs = {(1, 2): 1.0, (2, 4): 1.0, (1, 3): 1.0, (3, 4): 1.0}
        plan = MilitaryRoutePlanner().plan(
            1, 4, regions, edges, lambda _region, _final: True,
            segment_cost=lambda left, right: costs[(left["id"], right["id"])],
        )

        self.assertEqual(plan.region_ids, (1, 2, 4))
        self.assertEqual(plan.travel_cost, 2.0)

    def test_rejects_transit_through_inaccessible_region_and_non_adjacent_manual_route(self) -> None:
        regions = [{"id": value} for value in range(1, 4)]
        edges = [{"region_id": 1, "neighbor_region_id": 2}, {"region_id": 2, "neighbor_region_id": 3}]
        allowed = lambda region, _final: region["id"] != 2
        planner = MilitaryRoutePlanner()

        blocked = planner.plan(1, 3, regions, edges, allowed)
        invalid_manual = planner.plan(
            1, 3, regions, edges, lambda _region, _final: True,
            explicit_waypoints=[],
        )

        self.assertFalse(blocked.is_valid)
        self.assertIn("No legal route", blocked.rejection_reason)
        self.assertFalse(invalid_manual.is_valid)
        self.assertIn("non-adjacent", invalid_manual.rejection_reason)

    def test_legacy_map_without_adjacency_retains_direct_route_behavior(self) -> None:
        plan = MilitaryRoutePlanner().plan(
            1, 2, [{"id": 1}, {"id": 2}], None,
            lambda _region, _final: True,
        )
        self.assertEqual(plan.region_ids, (1, 2))

    def test_researched_and_trained_speed_capability_reduces_travel_estimate(self) -> None:
        state = GameState(tables={
            "unit_capability_projections": pl.DataFrame({
                "unit_id": ["USA-fighter-001"], "role": ["fighters"], "domain": ["air"],
                "capabilities_json": ['{"speed":2420.0}'],
            }),
        })
        system = MilitarySystem()
        source = {"id": 1, "owner": "USA", "infrastructure": 0.0}
        target = {"id": 2, "owner": "USA", "infrastructure": 0.0}
        locations = {1: GeoCoordinate(0.0, 0.0), 2: GeoCoordinate(30.0, 0.0)}
        unit = {"id": "USA-fighter-001", "owner": "USA", "unit_type": "fighter", "unit_domain": "air", "strength": 1}

        baseline = system._route_segment_minutes_for_unit(source, target, locations, unit, state)
        speed_factor = system._capability_speed_by_unit(state)[unit["id"]]
        trained = system._route_segment_minutes_for_unit(source, target, locations, unit, state, speed_factor)

        self.assertEqual(speed_factor, 1.1)
        self.assertLess(trained, baseline)

    def test_prepared_segment_cost_matches_reference_duration_for_route_edges(self) -> None:
        state = GameState()
        state.globals.update({
            "military_domain_duration_multipliers": {"land": 1.2, "air": 0.8},
            "military_force_size_duration_coefficient": 0.3,
            "military_infrastructure_duration_coefficient": 0.4,
            "military_telecom_coordination_coefficient": 0.2,
            "military_domestic_duration_multiplier": 0.9,
            "military_foreign_duration_multiplier": 1.3,
        })
        system = MilitarySystem()
        locations = {
            1: GeoCoordinate(0.0, 0.0),
            2: GeoCoordinate(15.0, 5.0),
        }
        sources = [{"id": 1}, {"id": 3}]
        targets = [
            {"id": 2, "owner": "USA", "infrastructure": 0.7, "telecom_capacity": 0.4},
            {"id": 3, "owner": "CAN", "infrastructure": 0.2, "communications": 0.8},
            {"id": 4, "owner": "", "infrastructure": 1.0},
        ]
        units = [
            {"owner": "USA", "unit_type": "army", "unit_domain": "land", "strength": 1000},
            {"owner": "USA", "unit_type": "fighter", "unit_domain": "air", "strength": 1},
        ]

        for unit in units:
            prepared = system._route_segment_cost_for_unit(
                locations, unit, state, capability_speed_multiplier=1.1
            )
            for source in sources:
                for target in targets:
                    self.assertEqual(
                        prepared(source, target),
                        system._route_segment_minutes_for_unit(
                            source,
                            target,
                            locations,
                            unit,
                            state,
                            capability_speed_multiplier=1.1,
                        ),
                    )

    def test_military_system_traverses_each_region_in_the_accepted_route(self) -> None:
        unit = UnitFactory().create("USA-1", "USA", "army", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        unit["readiness_status"] = "ready"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA", "USA", "USA"],
                "latitude": [0.0, 0.0, 0.0], "longitude": [0.0, 1.0, 2.0],
            }),
            "region_adjacency": pl.DataFrame({
                "region_id": [1, 2], "neighbor_region_id": [2, 3],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
        })
        system = MilitarySystem()
        state.current_actions = [ActionMoveUnit("player", "USA-1", 3)]
        system.update(state, 0.0)

        first_leg = state.get_table("units").to_dicts()[0]
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        self.assertEqual(first_leg["target_region_id"], 2)
        self.assertEqual(route["route_region_ids"], [1, 2, 3])

        state.current_actions = []
        state.time.total_minutes = first_leg["arrival_at_minute"]
        system.update(state, 0.0)
        second_leg = state.get_table("units").to_dicts()[0]
        self.assertEqual(second_leg["current_region_id"], 2)
        self.assertEqual(second_leg["target_region_id"], 3)
        self.assertTrue(second_leg["is_moving"])

        state.time.total_minutes = second_leg["arrival_at_minute"]
        system.update(state, 0.0)
        arrived = state.get_table("units").to_dicts()[0]
        self.assertEqual(arrived["current_region_id"], 3)
        self.assertFalse(arrived["is_moving"])
        self.assertEqual(state.get_table("unit_movement_routes")["status"][0], "arrived")

    def test_deployment_groups_can_split_and_remain_off_map_until_route_arrival(self) -> None:
        from modules.base.schema import ensure_base_tables

        unit = UnitFactory().create("USA-artillery-001", "USA", "artillery", 5, 0, GeoCoordinate(0.0, 0.0), 0)
        unit.update(
            unit_lifecycle="deployment_queued",
            production_order_id="order-USA-0001",
            source_region_id=1,
            source_latitude=0.0,
            source_longitude=0.0,
        )
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA", "USA", "USA"],
                "latitude": [0.0, 0.0, 0.0], "longitude": [0.0, 1.0, 2.0],
            }),
            "region_adjacency": pl.DataFrame({
                "region_id": [1, 2], "neighbor_region_id": [2, 3],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [5], "money_reserves": [0.0]}),
        })
        ensure_base_tables(state)
        state.update_table("unit_deployment_orders", pl.DataFrame([{
            "id": "deployment-order-USA-0001-001", "unit_id": unit["id"], "country_id": "USA",
            "production_order_id": "order-USA-0001", "quantity": 5, "source_region_id": 1,
            "destination_region_id": 0, "route_region_ids": [], "route_index": 0,
            "status": "queued", "created_at_minute": 0,
            "estimated_arrival_at_minute": 0, "blocking_reason": "",
        }], schema=state.get_table("unit_deployment_orders").schema))
        system = MilitarySystem()
        state.current_actions = [ActionDispatchUnitDeployment("USA", unit["id"], 3, 2)]
        system.update(state, 0.0)

        groups = state.get_table("units").sort("strength", descending=True).to_dicts()
        self.assertEqual(sorted(row["strength"] for row in groups), [2, 3])
        traveling = next(row for row in groups if row["strength"] == 2)
        self.assertEqual(traveling["unit_lifecycle"], "deployment_transit")
        self.assertEqual(traveling["current_region_id"], 0)
        self.assertTrue(traveling["is_moving"])
        self.assertEqual(state.get_table("unit_deployment_orders").filter(pl.col("unit_id") == traveling["id"])["status"][0], "in_transit")

        state.current_actions = []
        state.time.total_minutes = traveling["arrival_at_minute"]
        system.update(state, 0.0)
        traveling = next(row for row in state.get_table("units").to_dicts() if row["id"] == traveling["id"])
        self.assertEqual(traveling["unit_lifecycle"], "deployment_transit")
        self.assertEqual(traveling["current_region_id"], 0)
        self.assertEqual(traveling["target_region_id"], 3)

        state.time.total_minutes = traveling["arrival_at_minute"]
        system.update(state, 0.0)
        traveling = next(row for row in state.get_table("units").to_dicts() if row["id"] == traveling["id"])
        self.assertEqual(traveling["unit_lifecycle"], "available")
        self.assertEqual(traveling["current_region_id"], 3)
        self.assertEqual(state.get_table("unit_deployment_orders").filter(pl.col("unit_id") == traveling["id"])["status"][0], "delivered")


if __name__ == "__main__":
    unittest.main()
