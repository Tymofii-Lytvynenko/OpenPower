"""Shared movement location and duration policy for order validation and execution."""
import polars as pl

from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate

DEFAULT_MOVE_MINUTES = 1440


class MovementDurationPolicy:
    """Estimates direct movement duration from source and target geolocations."""

    def estimate_minutes(
        self,
        regions: pl.DataFrame,
        source_region_id: int,
        target_region_id: int,
    ) -> int:
        locations = self.region_locations(regions)
        source = locations.get(source_region_id)
        target = locations.get(target_region_id)

        if source is None or target is None:
            return DEFAULT_MOVE_MINUTES

        return self.estimate_between(source, target)

    def estimate_between(self, source: GeoCoordinate, target: GeoCoordinate) -> int:
        projection = EquirectangularProjection(360.0, 180.0)
        distance_km = projection.geo_distance_km(source, target)
        return self.estimate_from_distance(distance_km)

    def estimate_from_distance(self, distance_km: float) -> int:
        return int(max(360, min(10080, 360 + distance_km * 0.45)))

    def region_locations(self, regions: pl.DataFrame) -> dict[int, GeoCoordinate]:
        required = {"id"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        if {"latitude", "longitude"}.issubset(set(regions.columns)):
            return {
                int(row["id"]): GeoCoordinate(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
                for row in regions.select(["id", "latitude", "longitude"]).iter_rows(named=True)
                if row["id"] is not None
            }

        if {"center_x", "center_y"}.issubset(set(regions.columns)):
            projection = EquirectangularProjection(
                max(float(regions["center_x"].max() or 1.0) + 1.0, 1.0),
                max(float(regions["center_y"].max() or 1.0) + 1.0, 1.0),
            )
            return {
                int(row["id"]): projection.pixel_to_geo(
                    MapPixelCoordinate(float(row["center_x"]), float(row["center_y"]))
                )
                for row in regions.select(["id", "center_x", "center_y"]).iter_rows(named=True)
                if row["id"] is not None
            }

        return {}

