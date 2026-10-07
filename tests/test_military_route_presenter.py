from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class MilitaryRoutePresenterTest(unittest.TestCase):
    def test_unit_list_displays_authoritative_route_and_intended_action(self) -> None:
        unit = UnitFactory().create("USA-navy-001", "USA", "destroyer", 1, 1, GeoCoordinate(0.0, 0.0), 0)
        unit.update(is_moving=True, unit_lifecycle="available")
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2, 3], "owner": ["USA"] * 3, "name": ["Origin", "Waypoint", "Harbor"],
                "latitude": [0.0, 0.0, 0.0], "longitude": [0.0, 1.0, 2.0],
            }),
        })
        ensure_base_tables(state)
        state.update_table("unit_movement_routes", pl.DataFrame([{
            "unit_id": unit["id"], "owner_country_id": "USA", "source_region_id": 1,
            "destination_region_id": 3, "route_region_ids": [1, 2, 3], "route_index": 1,
            "destination_latitude": 0.0, "destination_longitude": 2.0,
            "has_custom_destination": False, "is_naval_invasion": True,
            "status": "in_transit", "rejection_reason": "", "updated_at_minute": 0,
        }], schema=state.get_table("unit_movement_routes").schema))

        row = MilitaryPresenter().unit_rows(state, "USA")[0]

        self.assertEqual(row.route_summary, "Landing: Origin → Waypoint → Harbor")

    def test_unit_list_surfaces_a_blocked_route_reason(self) -> None:
        unit = UnitFactory().create("USA-army-001", "USA", "army", 1, 1, GeoCoordinate(0.0, 0.0), 0)
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({"id": [1], "owner": ["USA"], "name": ["Capital"]}),
        })
        ensure_base_tables(state)
        state.update_table("unit_movement_routes", pl.DataFrame([{
            "unit_id": unit["id"], "owner_country_id": "USA", "source_region_id": 1,
            "destination_region_id": 2, "route_region_ids": [1], "route_index": 0,
            "status": "blocked", "rejection_reason": "Transit rights expired.",
        }], schema=state.get_table("unit_movement_routes").schema))

        row = MilitaryPresenter().unit_rows(state, "USA")[0]

        self.assertEqual(row.route_summary, "Blocked: Transit rights expired.")

    def test_unit_list_distinguishes_tactical_retreat_from_ordinary_movement(self) -> None:
        unit = UnitFactory().create("USA-army-002", "USA", "army", 1, 2, GeoCoordinate(10.0, 20.0), 0)
        unit.update(is_moving=True, unit_lifecycle="battle_retreating")
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({"id": [2], "owner": ["USA"], "name": ["Battlefield"]}),
        })
        ensure_base_tables(state)
        state.update_table("unit_movement_routes", pl.DataFrame([{
            "unit_id": unit["id"], "owner_country_id": "USA", "source_region_id": 2,
            "destination_region_id": 2, "route_region_ids": [2], "route_index": 0,
            "destination_latitude": 10.01, "destination_longitude": 20.0,
            "status": "retreating", "rejection_reason": "",
        }], schema=state.get_table("unit_movement_routes").schema))

        row = MilitaryPresenter().unit_rows(state, "USA")[0]

        self.assertEqual(row.route_summary, "Retreat to battle rear · Battlefield")


if __name__ == "__main__":
    unittest.main()
