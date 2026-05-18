from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, degrees, pi, radians, sin, sqrt


@dataclass(frozen=True)
class GeoCoordinate:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class MapPixelCoordinate:
    x: float
    y: float


class EquirectangularProjection:
    """
    Converts between real latitude/longitude and the project's equirectangular map.
    Longitude is normalized to [-180, 180); latitude is clamped to [-90, 90].
    """

    def __init__(self, map_width: float, map_height: float):
        self.map_width = max(float(map_width), 1.0)
        self.map_height = max(float(map_height), 1.0)

    def pixel_to_geo(self, pixel: MapPixelCoordinate) -> GeoCoordinate:
        longitude = (float(pixel.x) / self.map_width) * 360.0 - 180.0
        latitude = 90.0 - (float(pixel.y) / self.map_height) * 180.0
        return GeoCoordinate(
            latitude=self._clamp_latitude(latitude),
            longitude=self._normalize_longitude(longitude),
        )

    def geo_to_pixel(self, geo: GeoCoordinate) -> MapPixelCoordinate:
        longitude = self._normalize_longitude(geo.longitude)
        latitude = self._clamp_latitude(geo.latitude)
        x = ((longitude + 180.0) / 360.0) * self.map_width
        y = ((90.0 - latitude) / 180.0) * self.map_height
        return MapPixelCoordinate(
            x=x % self.map_width,
            y=max(0.0, min(self.map_height - 1.0, y)),
        )

    def pixel_to_unit_vector(self, pixel: MapPixelCoordinate) -> tuple[float, float, float]:
        return self.geo_to_unit_vector(self.pixel_to_geo(pixel))

    def geo_to_unit_vector(self, geo: GeoCoordinate) -> tuple[float, float, float]:
        latitude = radians(self._clamp_latitude(geo.latitude))
        longitude_angle = radians(self._normalize_longitude(geo.longitude) + 180.0)

        cos_lat = cos(latitude)
        return (
            cos_lat * cos(longitude_angle),
            -sin(latitude),
            cos_lat * sin(longitude_angle),
        )

    def unit_vector_to_geo(self, x: float, y: float, z: float) -> GeoCoordinate:
        length = sqrt(x * x + y * y + z * z)
        if length <= 1e-9:
            return GeoCoordinate(latitude=0.0, longitude=0.0)

        nx = x / length
        ny = y / length
        nz = z / length
        latitude = -degrees(asin(max(-1.0, min(1.0, ny))))
        longitude_angle = degrees(atan2(nz, nx))
        longitude = self._normalize_longitude(longitude_angle - 180.0)
        return GeoCoordinate(latitude=latitude, longitude=longitude)

    def uv_to_pixel(self, u: float, v: float) -> MapPixelCoordinate:
        x = (float(u) % 1.0) * self.map_width
        y = max(0.0, min(self.map_height - 1.0, (1.0 - float(v)) * self.map_height))
        return MapPixelCoordinate(x=x, y=y)

    def geo_distance_km(self, a: GeoCoordinate, b: GeoCoordinate) -> float:
        earth_radius_km = 6371.0
        lat1 = radians(self._clamp_latitude(a.latitude))
        lat2 = radians(self._clamp_latitude(b.latitude))
        d_lat = lat2 - lat1
        d_lon = radians(self._normalize_longitude(b.longitude - a.longitude))

        h = sin(d_lat * 0.5) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon * 0.5) ** 2
        return 2.0 * earth_radius_km * asin(min(1.0, sqrt(h)))

    def _clamp_latitude(self, latitude: float) -> float:
        return max(-90.0, min(90.0, float(latitude)))

    def _normalize_longitude(self, longitude: float) -> float:
        return (float(longitude) + 180.0) % 360.0 - 180.0
