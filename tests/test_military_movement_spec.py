from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import (
    UNIT_SCHEMA,
    MovementDurationPolicy,
    MilitarySystem,
    UnitFactory,
)
from src.core.map.geo import EquirectangularProjection, GeoCoordinate
from src.shared.actions import ActionBuildUnit, ActionMoveUnit
from src.shared.state import GameState


class MilitaryMovementSpecificationTest(unittest.TestCase):
    def test_haversine_distance_matches_equatorial_and_date_line_benchmarks(self) -> None:
        projection = EquirectangularProjection(360.0, 180.0)
        benchmarks = (
            (GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 1.0), 111.1949266),
            (GeoCoordinate(60.0, 0.0), GeoCoordinate(60.0, 1.0), 55.5970100),
            (GeoCoordinate(0.0, 179.0), GeoCoordinate(0.0, -179.0), 222.3898533),
        )

        for source, target, expected_km in benchmarks:
            with self.subTest(source=source, target=target):
                actual_km = projection.geo_distance_km(source, target)
                self.assertLessEqual(abs(actual_km - expected_km) / expected_km, 0.0001)

    def test_duration_formula_is_deterministic_and_clamped_at_minimum(self) -> None:
        policy = MovementDurationPolicy()
        one_degree = policy.estimate_between(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 1.0))
        zero_distance = policy.estimate_between(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 0.0))
        antipodal = policy.estimate_between(GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 180.0))

        self.assertEqual(one_degree, int(360 + 111.1949266 * 0.45))
        self.assertEqual(zero_distance, 360)
        self.assertEqual(antipodal, min(10_080, int(360 + 20_015.0868 * 0.45)))

    def test_movement_progress_reaches_exactly_one_at_authoritative_arrival_minute(self) -> None:
        unit = UnitFactory().create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        unit["readiness_status"] = "ready"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "USA"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
            }),
            "region_adjacency": pl.DataFrame({
                "region_id": [1], "neighbor_region_id": [2],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
        })
        system = MilitarySystem()
        state.current_actions = [ActionMoveUnit("player", unit["id"], 2)]
        system.update(state, 0.0)
        in_transit = state.get_table("units").to_dicts()[0]
        self.assertTrue(in_transit["is_moving"])
        self.assertEqual(in_transit["movement_progress"], 0.0)

        midpoint = in_transit["departed_at_minute"] + (in_transit["arrival_at_minute"] - in_transit["departed_at_minute"]) // 2
        state.current_actions = []
        state.time.total_minutes = midpoint
        system.update(state, 0.0)
        halfway = state.get_table("units").to_dicts()[0]
        self.assertEqual(
            halfway["movement_progress"],
            (midpoint - in_transit["departed_at_minute"]) / (in_transit["arrival_at_minute"] - in_transit["departed_at_minute"]),
        )

        state.time.total_minutes = in_transit["arrival_at_minute"]
        system.update(state, 0.0)
        arrived = state.get_table("units").to_dicts()[0]
        self.assertEqual(arrived["current_region_id"], 2)
        self.assertFalse(arrived["is_moving"])

    def test_rejected_invalid_move_preserves_fortified_readiness_and_location(self) -> None:
        unit = UnitFactory().create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(10.0, 20.0), 0)
        unit["readiness_status"] = "fortified"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
        })
        state.current_actions = [ActionMoveUnit("player", unit["id"], 999)]

        MilitarySystem().update(state, 0.0)

        after = state.get_table("units").to_dicts()[0]
        self.assertEqual(after["readiness_status"], "fortified")
        self.assertEqual((after["latitude"], after["longitude"], after["current_region_id"]), (10.0, 20.0, 1))
        feedback = state.get_table("unit_order_feedback").to_dicts()
        self.assertEqual(feedback[-1]["status"], "rejected")

    def test_selected_groups_validate_orders_independently(self) -> None:
        factory = UnitFactory()
        units = [
            factory.create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0),
            factory.create("USA-infantry-002", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0),
        ]
        for unit in units:
            unit["readiness_status"] = "ready"
        state = GameState(tables={
            "units": pl.DataFrame(units, schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "USA"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [200], "money_reserves": [0.0]}),
        })
        state.current_actions = [
            ActionMoveUnit("USA", units[0]["id"], 2),
            ActionMoveUnit("USA", units[1]["id"], 999),
        ]

        MilitarySystem().update(state, 0.0)

        after = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertTrue(after[units[0]["id"]]["is_moving"])
        self.assertEqual(after[units[0]["id"]]["target_region_id"], 2)
        self.assertFalse(after[units[1]["id"]]["is_moving"])
        self.assertEqual(after[units[1]["id"]]["current_region_id"], 1)
        feedback = {row["unit_id"]: row["status"] for row in state.get_table("unit_order_feedback").to_dicts()}
        self.assertEqual(feedback[units[0]["id"]], "accepted")
        self.assertEqual(feedback[units[1]["id"]], "rejected")

    def test_revoked_transit_right_stops_at_last_legal_waypoint(self) -> None:
        unit = UnitFactory().create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        unit["readiness_status"] = "ready"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA", "MEX", "USA"],
                "latitude": [0.0, 0.0, 0.0], "longitude": [0.0, 1.0, 2.0],
            }),
            "region_adjacency": pl.DataFrame({
                "region_id": [1, 2], "neighbor_region_id": [2, 3],
            }),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["transit"], "country_id": ["USA"], "effect": ["transit_rights"],
                "value": [1.0], "detail": ['["MEX"]'],
            }),
        })
        system = MilitarySystem()
        state.current_actions = [ActionMoveUnit("USA", unit["id"], 3)]
        system.update(state, 0.0)
        moving = state.get_table("units").to_dicts()[0]
        self.assertEqual(state.get_table("unit_movement_routes").to_dicts()[0]["route_region_ids"], [1, 2, 3])

        state.current_actions = []
        state.update_table("treaty_effects", pl.DataFrame(schema={
            "treaty_id": pl.Utf8, "country_id": pl.Utf8, "effect": pl.Utf8,
            "value": pl.Float64, "detail": pl.Utf8,
        }))
        state.time.total_minutes = moving["departed_at_minute"] + 1
        system.update(state, 0.0)

        stopped = state.get_table("units").to_dicts()[0]
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        self.assertFalse(stopped["is_moving"])
        self.assertEqual(stopped["current_region_id"], 1)
        self.assertEqual((stopped["latitude"], stopped["longitude"]), (0.0, 0.0))
        self.assertEqual(route["status"], "blocked")
        self.assertIn("access rights", route["rejection_reason"])

    def test_movement_route_and_progress_are_deterministic_after_ipc_roundtrip(self) -> None:
        unit = UnitFactory().create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        unit["readiness_status"] = "ready"
        original = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "USA"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
            }),
            "region_adjacency": pl.DataFrame({"region_id": [1], "neighbor_region_id": [2]}),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
        })
        original.current_actions = [ActionMoveUnit("USA", unit["id"], 2)]
        MilitarySystem().update(original, 0.0)
        original.current_actions = []
        restored = GameState.from_ipc(original.to_ipc())
        minute = original.get_table("units")["arrival_at_minute"][0] // 2
        original.time.total_minutes = minute
        restored.time.total_minutes = minute

        MilitarySystem().update(original, 0.0)
        MilitarySystem().update(restored, 0.0)

        self.assertTrue(original.get_table("units").equals(restored.get_table("units")))
        self.assertTrue(original.get_table("unit_movement_routes").equals(restored.get_table("unit_movement_routes")))

    def test_final_leg_batch_matches_reference_for_due_and_pending_units(self) -> None:
        factory = UnitFactory()
        units = [
            factory.create(f"USA-infantry-{index:03d}", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0)
            for index in (1, 2)
        ]
        for unit, arrival in zip(units, (10, 2), strict=True):
            unit.update(
                current_region_id=1,
                source_region_id=1,
                source_latitude=0.0,
                source_longitude=0.0,
                target_region_id=2,
                target_latitude=0.0,
                target_longitude=1.0,
                departed_at_minute=0,
                arrival_at_minute=arrival,
                movement_progress=0.0,
                is_moving=True,
            )

        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [200], "money_reserves": [0.0]}),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "USA"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
            }),
        })
        ensure_base_tables(state)
        unit_frame = pl.DataFrame(units, schema=UNIT_SCHEMA)
        route_frame = pl.DataFrame([{
            "unit_id": unit["id"], "owner_country_id": "USA",
            "source_region_id": 1, "destination_region_id": 2,
            "route_region_ids": [1, 2], "route_index": 1,
            "destination_latitude": 0.0, "destination_longitude": 1.0,
            "has_custom_destination": False, "is_naval_invasion": False,
            "status": "in_transit", "rejection_reason": "", "updated_at_minute": 0,
        } for unit in units], schema=state.get_table("unit_movement_routes").schema)
        state.update_table("units", unit_frame)
        state.update_table("unit_movement_routes", route_frame)

        slow_state = GameState.from_ipc(state.to_ipc())
        slow_system = MilitarySystem()
        slow_system._try_update_uncontested_movement_batch = lambda *_: None
        reference_units = slow_system._update_unit_movements(slow_state, unit_frame, 5)
        reference_routes = slow_state.get_table("unit_movement_routes")

        fast_state = GameState.from_ipc(state.to_ipc())
        fast_system = MilitarySystem()
        optimized_units = fast_system._update_unit_movements(fast_state, unit_frame, 5)

        self.assertTrue(optimized_units.equals(reference_units))
        self.assertTrue(fast_state.get_table("unit_movement_routes").equals(reference_routes))

    def test_missing_home_region_does_not_charge_recruitment_or_change_force_count(self) -> None:
        state = GameState(tables={
            "units": pl.DataFrame(schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [2], "owner": ["CAN"], "latitude": [0.0], "longitude": [0.0],
            }),
            "countries": pl.DataFrame({
                "id": ["USA"], "military_count": [10], "money_reserves": [5_000_000.0],
            }),
        })
        state.current_actions = [ActionBuildUnit("player", "USA", "infantry", 5)]

        result = MilitarySystem()._process_build_actions(state, state.get_table("units"))

        country = state.get_table("countries").to_dicts()[0]
        self.assertEqual(country["military_count"], 10)
        self.assertEqual(country["money_reserves"], 5_000_000.0)
        self.assertTrue(result.is_empty())

    def test_recruitment_charges_one_million_per_group_and_spawns_at_home_region(self) -> None:
        state = GameState(tables={
            "units": pl.DataFrame(schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [7], "owner": ["USA"], "latitude": [35.0], "longitude": [-80.0],
            }),
            "countries": pl.DataFrame({
                "id": ["USA"], "military_count": [10], "money_reserves": [5_000_000.0],
            }),
        })
        state.current_actions = [ActionBuildUnit("USA", "USA", "infantry", 3)]

        units = MilitarySystem()._process_build_actions(state, state.get_table("units"))

        country = state.get_table("countries").to_dicts()[0]
        recruited = units.to_dicts()[0]
        self.assertEqual(country["military_count"], 13)
        self.assertEqual(country["money_reserves"], 2_000_000.0)
        self.assertEqual(recruited["id"], "USA-infantry-001")
        self.assertEqual(recruited["strength"], 3)
        self.assertEqual(recruited["current_region_id"], 7)
        self.assertEqual((recruited["latitude"], recruited["longitude"]), (35.0, -80.0))

    def test_nonpositive_recruitment_is_rejected_without_charging_or_incrementing(self) -> None:
        state = GameState(tables={
            "units": pl.DataFrame(schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({"id": [7], "owner": ["USA"], "latitude": [0.0], "longitude": [0.0]}),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [10], "money_reserves": [5_000_000.0]}),
        })
        state.current_actions = [ActionBuildUnit("USA", "USA", "infantry", 0)]

        units = MilitarySystem()._process_build_actions(state, state.get_table("units"))

        country = state.get_table("countries").to_dicts()[0]
        self.assertEqual(country["military_count"], 10)
        self.assertEqual(country["money_reserves"], 5_000_000.0)
        self.assertTrue(units.is_empty())
        self.assertEqual(state.get_table("unit_order_feedback").to_dicts()[0]["status"], "rejected")

    def test_weekly_manpower_aggregation_uses_owned_working_age_population(self) -> None:
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA", "USA", "CAN"], "pop_15_64": [10, 25, 40],
            }),
            "countries": pl.DataFrame({"id": ["USA", "CAN", "MEX"]}),
        })

        MilitarySystem()._update_manpower(state)

        manpower = {row["id"]: row["total_core_manpower"] for row in state.get_table("countries").to_dicts()}
        self.assertEqual(manpower, {"USA": 35, "CAN": 40, "MEX": 0})

    def test_manpower_aggregation_cache_invalidates_when_region_revision_changes(self) -> None:
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["USA"], "pop_15_64": [35]}),
            "countries": pl.DataFrame({"id": ["USA"]}),
        })
        system = MilitarySystem()

        system._update_manpower(state)
        self.assertEqual(state.get_table("countries")["total_core_manpower"][0], 35)

        state.update_table("regions", pl.DataFrame({
            "id": [1, 2], "owner": ["USA", "CAN"], "pop_15_64": [35, 40],
        }))
        state.update_table("countries", pl.DataFrame({"id": ["USA", "CAN"]}))
        system._update_manpower(state)

        manpower = {row["id"]: row["total_core_manpower"] for row in state.get_table("countries").to_dicts()}
        self.assertEqual(manpower, {"USA": 35, "CAN": 40})


if __name__ == "__main__":
    unittest.main()
