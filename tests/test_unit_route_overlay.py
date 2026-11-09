from __future__ import annotations

import unittest
from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.client.renderers.unit_route_overlay import (
    AFFILIATION_ALLIED,
    AFFILIATION_HOSTILE,
    AFFILIATION_NEUTRAL,
    AFFILIATION_OWN,
    ROUTE_COLORS,
    _coordinate,
    _region_coordinate,
    sample_route_waypoints,
    selected_unit_route_overlays,
)
from src.client.renderers.unit_renderer import UnitRenderer
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class UnitRouteOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.units = []
        route_rows = []
        for owner, unit_id, route_id in (
            ("USA", "own", [1, 2, 3]),
            ("MEX", "ally", [1, 2]),
            ("CAN", "enemy", [1, 3]),
            ("BRA", "neutral", [1, 2]),
        ):
            unit = UnitFactory().create(unit_id, owner, "army", 100, 1, GeoCoordinate(0.0, 0.0), 0)
            unit.update(latitude=0.0, longitude=0.0, engagement_mode="assault" if unit_id == "own" else "")
            self.units.append(unit)
            route_rows.append({
                "unit_id": unit_id,
                "owner_country_id": owner,
                "route_region_ids": route_id,
                "route_index": 1,
                "destination_latitude": 0.0,
                "destination_longitude": 2.0,
                "has_custom_destination": unit_id == "own",
                "is_naval_invasion": unit_id == "ally",
                "status": "in_transit",
                "rejection_reason": "",
            })
        self.state = GameState(tables={
            "units": pl.DataFrame(self.units, schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({
                "id": [1, 2, 3],
                "latitude": [0.0, 0.0, 1.0],
                "longitude": [0.0, 1.0, 2.0],
            }),
            "unit_movement_routes": pl.DataFrame(route_rows),
            "countries_treaties": pl.DataFrame([{
                "id": "alliance-usa-mex",
                "type": "alliance",
                "members": ["USA", "MEX"],
                "status": "active",
            }]),
            "countries_wars": pl.DataFrame([{
                "id": "war-usa-can",
                "side_a": ["USA"],
                "side_b": ["CAN"],
                "status": "active",
            }]),
        })

    def _state_with_tables(self, **overrides) -> GameState:
        tables = {
            name: self.state.get_table(name)
            for name in (
                "units",
                "regions",
                "unit_movement_routes",
                "countries_treaties",
                "countries_wars",
            )
        }
        tables.update(overrides)
        return GameState(tables=tables)

    def test_selected_routes_are_styled_by_the_existing_diplomatic_map_palette(self) -> None:
        overlays = selected_unit_route_overlays(
            self.state,
            {"own", "ally", "enemy", "neutral"},
            "USA",
        )

        by_unit = {overlay.unit_id: overlay for overlay in overlays}
        self.assertEqual(by_unit["own"].affiliation, AFFILIATION_OWN)
        self.assertEqual(by_unit["own"].action_label, "Move and attack")
        self.assertEqual(by_unit["ally"].affiliation, AFFILIATION_ALLIED)
        self.assertEqual(by_unit["ally"].action_label, "Naval landing")
        self.assertEqual(by_unit["enemy"].affiliation, AFFILIATION_HOSTILE)
        self.assertEqual(by_unit["neutral"].affiliation, AFFILIATION_NEUTRAL)
        self.assertEqual(by_unit["own"].color, ROUTE_COLORS[AFFILIATION_OWN])
        self.assertIsNotNone(by_unit["ally"].dash_lengths)
        self.assertIsNone(by_unit["own"].dash_lengths)

    def test_custom_destination_and_current_unit_position_define_route_endpoints(self) -> None:
        overlays = selected_unit_route_overlays(self.state, {"own"}, "USA")

        self.assertEqual(len(overlays), 1)
        route = overlays[0]
        self.assertEqual(route.waypoints[0], GeoCoordinate(0.0, 0.0))
        self.assertEqual(route.waypoints[-1], GeoCoordinate(0.0, 2.0))
        self.assertEqual(route.label, "Move and attack · USA")

    def test_route_samples_use_short_path_across_longitude_seam(self) -> None:
        points = sample_route_waypoints((GeoCoordinate(0.0, 179.0), GeoCoordinate(0.0, -179.0)), 4)

        self.assertEqual(len(points), 5)
        self.assertAlmostEqual(abs(points[2].longitude), 180.0, places=5)

    def test_long_route_projection_sampling_is_bounded_and_keeps_endpoints(self) -> None:
        waypoints = [
            GeoCoordinate(float((index % 160) - 80), float((index % 360) - 180))
            for index in range(1_000)
        ]

        samples = sample_route_waypoints(waypoints)

        self.assertLessEqual(len(samples), 256)
        self.assertEqual(samples[0], waypoints[0])
        self.assertEqual(samples[-1], waypoints[-1])

    def test_empty_inputs_and_incomplete_route_tables_return_no_overlays(self) -> None:
        self.assertEqual(selected_unit_route_overlays(None, ["own"], "USA"), [])
        self.assertEqual(selected_unit_route_overlays(self.state, [], "USA"), [])

        units = pl.DataFrame({"id": ["own"], "owner": ["USA"]})
        routes = pl.DataFrame({"unit_id": ["own"], "route_region_ids": [[1]]})
        regions = pl.DataFrame({"id": [1], "latitude": [0.0], "longitude": [0.0]})
        incomplete_tables = (
            {"units": units, "unit_movement_routes": routes},
            {"units": pl.DataFrame({"tag": ["own"]}), "unit_movement_routes": routes, "regions": regions},
            {"units": units, "unit_movement_routes": pl.DataFrame({"route": ["invalid"]}), "regions": regions},
            {"units": units, "unit_movement_routes": routes, "regions": pl.DataFrame({"id": [1]})},
        )

        for tables in incomplete_tables:
            state = SimpleNamespace(tables=tables)
            self.assertEqual(selected_unit_route_overlays(state, ["own"], "USA"), [])

    def test_orphaned_inactive_and_route_without_destination_are_skipped(self) -> None:
        routes = self.state.get_table("unit_movement_routes").filter(pl.col("unit_id") == "own")
        units_without_owner = self.state.get_table("units").filter(pl.col("id") != "own")
        orphaned_state = self._state_with_tables(
            units=units_without_owner,
            unit_movement_routes=routes.with_columns(pl.lit("missing-unit").alias("unit_id")),
        )
        self.assertEqual(selected_unit_route_overlays(orphaned_state, ["missing-unit"], "USA"), [])

        inactive_state = self._state_with_tables(
            unit_movement_routes=routes.with_columns(pl.lit("queued").alias("status")),
        )
        self.assertEqual(selected_unit_route_overlays(inactive_state, ["own"], "USA"), [])

        route_without_destination = routes.with_columns(
            pl.lit([], dtype=pl.List(pl.Int64)).alias("route_region_ids"),
        )
        incomplete_state = self._state_with_tables(unit_movement_routes=route_without_destination)
        self.assertEqual(selected_unit_route_overlays(incomplete_state, ["own"], "USA"), [])

    def test_each_active_route_status_gets_a_player_facing_label(self) -> None:
        route = self.state.get_table("unit_movement_routes").filter(pl.col("unit_id") == "own")

        for status, label in (
            ("blocked", "Blocked"),
            ("interrupted", "Interrupted"),
            ("retreating", "Retreating"),
            ("in_transit", "In transit"),
        ):
            state = self._state_with_tables(
                unit_movement_routes=route.with_columns(pl.lit(status).alias("status")),
            )
            overlays = selected_unit_route_overlays(state, ["own"], "USA")

            self.assertEqual(len(overlays), 1)
            self.assertEqual(overlays[0].status_label, label)

    def test_missing_unit_position_uses_the_previous_route_region_as_start(self) -> None:
        units = self.state.get_table("units").to_dicts()
        own_unit = next(row for row in units if row["id"] == "own")
        own_unit["latitude"] = None
        own_unit["longitude"] = None
        routes = self.state.get_table("unit_movement_routes").filter(pl.col("unit_id") == "own").with_columns(
            pl.lit([1, 2, 3], dtype=pl.List(pl.Int64)).alias("route_region_ids"),
            pl.lit(1).alias("route_index"),
            pl.lit(False).alias("has_custom_destination"),
        )
        state = self._state_with_tables(
            units=pl.DataFrame(units, schema=UNIT_SCHEMA),
            unit_movement_routes=routes,
        )

        overlays = selected_unit_route_overlays(state, ["own"], "USA")

        self.assertEqual(
            overlays[0].waypoints,
            (GeoCoordinate(0.0, 0.0), GeoCoordinate(0.0, 1.0), GeoCoordinate(1.0, 2.0)),
        )

    def test_sampling_and_coordinate_helpers_handle_empty_and_invalid_geometry(self) -> None:
        point = GeoCoordinate(10.0, 20.0)
        self.assertEqual(sample_route_waypoints([]), [])
        self.assertEqual(sample_route_waypoints([point]), [point])
        self.assertIsNone(_region_coordinate(None))

        for invalid in (None, "north", 10**400):
            self.assertIsNone(_coordinate(invalid, 0.0))
        for latitude, longitude in ((float("nan"), 0.0), (90.1, 0.0), (0.0, 180.1)):
            self.assertIsNone(_coordinate(latitude, longitude))

    def test_route_with_unknown_region_does_not_render_a_single_point(self) -> None:
        routes = self.state.get_table("unit_movement_routes").filter(pl.col("unit_id") == "own").with_columns(
            pl.lit([999], dtype=pl.List(pl.Int64)).alias("route_region_ids"),
            pl.lit(0).alias("route_index"),
            pl.lit(False).alias("has_custom_destination"),
        )
        state = self._state_with_tables(unit_movement_routes=routes)

        self.assertEqual(selected_unit_route_overlays(state, ["own"], "USA"), [])

    def test_renderer_reuses_route_snapshot_until_an_authoritative_revision_changes(self) -> None:
        renderer = object.__new__(UnitRenderer)
        renderer._route_overlay_cache_key = None
        renderer._route_overlay_cache = []

        first = renderer._get_selected_route_overlays(self.state, ["own"], "USA")
        cached = renderer._get_selected_route_overlays(self.state, ["own"], "USA")
        self.assertIs(first, cached)

        unit_rows = self.state.get_table("units").to_dicts()
        unit_rows[0]["owner"] = "CAN"
        self.state.update_table("units", pl.DataFrame(unit_rows, schema=UNIT_SCHEMA))
        refreshed = renderer._get_selected_route_overlays(self.state, ["own"], "USA")

        self.assertIsNot(first, refreshed)
        self.assertEqual(refreshed[0].affiliation, AFFILIATION_HOSTILE)


if __name__ == "__main__":
    unittest.main()
