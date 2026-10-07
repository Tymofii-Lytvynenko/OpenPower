from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.military.military_system import MOVEMENT_ROUTE_SCHEMA, UNIT_SCHEMA, MilitarySystem, UnitFactory
from modules.base.systems.military.naval_invasion_policy import NavalInvasionPolicy
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class NavalInvasionPolicyTest(unittest.TestCase):
    def test_moving_fleet_position_uses_short_spherical_arc_across_date_line(self) -> None:
        unit = {
            "is_moving": True,
            "departed_at_minute": 0,
            "arrival_at_minute": 10,
            "source_latitude": 0.0,
            "source_longitude": 179.0,
            "target_latitude": 0.0,
            "target_longitude": -179.0,
        }

        latitude, longitude = NavalInvasionPolicy()._position(unit, 5)

        self.assertAlmostEqual(latitude, 0.0, places=6)
        self.assertAlmostEqual(abs(longitude), 180.0, places=6)

    def test_requires_capital_ship_escort_within_configured_radius(self) -> None:
        state = GameState(tables={})
        state.globals["naval_invasion_escort_km"] = 750.0
        invading = {"id": "landing", "owner": "USA", "unit_domain": "land", "unit_type": "infantry", "strength": 100}
        target = {"id": 2, "owner": "CAN", "latitude": 0.0, "longitude": 0.0}
        carrier = {"id": "carrier", "owner": "USA", "unit_domain": "naval", "unit_type": "aircraft_carriers", "strength": 1, "latitude": 0.0, "longitude": 6.7}
        valid, reason = NavalInvasionPolicy().validate(state, invading, target, [invading, carrier], (0.0, 0.0))
        self.assertTrue(valid, reason)

        carrier["longitude"] = 6.9
        valid, reason = NavalInvasionPolicy().validate(state, invading, target, [invading, carrier], (0.0, 0.0))
        self.assertFalse(valid)
        self.assertIn("750", reason)

    def test_hostile_fleet_in_exclusion_zone_blocks_landing(self) -> None:
        state = GameState(tables={
            "countries_wars": pl.DataFrame({
                "id": ["war"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
            }),
        })
        invading = {"id": "landing", "owner": "USA", "unit_domain": "land", "unit_type": "infantry", "strength": 100, "latitude": 0.0, "longitude": 0.0}
        target = {"id": 2, "owner": "CAN", "latitude": 0.0, "longitude": 0.0}
        carrier = {"id": "carrier", "owner": "USA", "unit_domain": "naval", "unit_type": "aircraft_carriers", "strength": 1, "latitude": 0.0, "longitude": 0.0}
        enemy_fleet = {"id": "enemy", "owner": "CAN", "unit_domain": "naval", "unit_type": "destroyers", "strength": 1, "latitude": 0.0, "longitude": 10.0}
        valid, reason = NavalInvasionPolicy().validate(state, invading, target, [invading, carrier, enemy_fleet], (0.0, 0.0))
        self.assertFalse(valid)
        self.assertIn("1500", reason)

    def test_landing_conditions_are_rechecked_at_arrival_without_transferring_control(self) -> None:
        unit = UnitFactory().create("USA-infantry-001", "USA", "infantry", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        unit.update(
            is_moving=True,
            source_region_id=1,
            source_latitude=0.0,
            source_longitude=0.0,
            target_region_id=2,
            target_latitude=0.0,
            target_longitude=1.0,
            departed_at_minute=0,
            arrival_at_minute=60,
            movement_progress=0.0,
        )
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 1.0],
            }),
            "countries_wars": pl.DataFrame({
                "id": ["war"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
            }),
            "unit_movement_routes": pl.DataFrame([{
                "unit_id": unit["id"], "owner_country_id": "USA", "source_region_id": 1,
                "destination_region_id": 2, "route_region_ids": [1, 2], "route_index": 1,
                "destination_latitude": 0.0, "destination_longitude": 1.0,
                "has_custom_destination": False, "is_naval_invasion": True,
                "status": "in_transit", "rejection_reason": "", "updated_at_minute": 0,
            }], schema=MOVEMENT_ROUTE_SCHEMA),
        })

        state.time.total_minutes = 60
        stopped = MilitarySystem()._update_unit_movements(state, state.get_table("units"), 60).to_dicts()[0]

        self.assertEqual(stopped["unit_lifecycle"], "landing_blocked")
        self.assertFalse(stopped["is_moving"])
        self.assertEqual(stopped["current_region_id"], 1)
        self.assertEqual(state.get_table("regions").filter(pl.col("id") == 2)["owner"][0], "CAN")
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        self.assertEqual(route["status"], "blocked")
        self.assertIn("capital ship", route["rejection_reason"].lower())


if __name__ == "__main__":
    unittest.main()
