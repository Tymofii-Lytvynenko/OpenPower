"""Geometry primitives used to detect tactical engagement-zone contact."""

from __future__ import annotations

from math import cos, radians, sqrt
from typing import Any

from src.core.map.geo import EquirectangularProjection, GeoCoordinate


EARTH_RADIUS_KM = 6371.0
ENGAGEMENT_RADIUS_KM = 50.0
_KILOMETERS_PER_LATITUDE_DEGREE = 110.574
_KILOMETERS_PER_LONGITUDE_DEGREE = 111.320
_GEOGRAPHY = EquirectangularProjection(360.0, 180.0)


def engagement_radius_km(unit_row: dict[str, Any]) -> float:
    """Return the fixed MVP zone radius while preserving a future data hook."""
    value = unit_row.get("engagement_radius_km")
    try:
        return max(0.0, float(value)) if value is not None else ENGAGEMENT_RADIUS_KM
    except (TypeError, ValueError):
        return ENGAGEMENT_RADIUS_KM


def first_zone_contact_fraction(
    start: GeoCoordinate,
    end: GeoCoordinate,
    zone_center: GeoCoordinate,
    radius_km: float,
) -> float | None:
    """Return the first point where a direct route enters a circular zone."""
    safe_radius = max(0.0, float(radius_km))
    if safe_radius <= 0.0:
        return None

    start_x, start_y = _relative_kilometers(start, zone_center)
    end_x, end_y = _relative_kilometers(end, zone_center)
    if start_x * start_x + start_y * start_y <= safe_radius * safe_radius:
        return 0.0

    delta_x, delta_y = end_x - start_x, end_y - start_y
    route_length_sq = delta_x * delta_x + delta_y * delta_y
    if route_length_sq <= 1e-9:
        return None

    quadratic_b = 2.0 * (start_x * delta_x + start_y * delta_y)
    quadratic_c = start_x * start_x + start_y * start_y - safe_radius * safe_radius
    discriminant = quadratic_b * quadratic_b - 4.0 * route_length_sq * quadratic_c
    if discriminant < 0.0:
        return None

    root = sqrt(discriminant)
    first = (-quadratic_b - root) / (2.0 * route_length_sq)
    second = (-quadratic_b + root) / (2.0 * route_length_sq)
    for fraction in (first, second):
        if 0.0 <= fraction <= 1.0:
            return fraction
    return None


def interpolate_geo(start: GeoCoordinate, end: GeoCoordinate, fraction: float) -> GeoCoordinate:
    """Interpolate a short strategic movement segment across the date line safely."""
    clamped = max(0.0, min(1.0, float(fraction)))
    latitude = start.latitude + (end.latitude - start.latitude) * clamped
    longitude_delta = _normalized_longitude(end.longitude - start.longitude)
    return GeoCoordinate(
        latitude=max(-90.0, min(90.0, latitude)),
        longitude=_normalized_longitude(start.longitude + longitude_delta * clamped),
    )


def distance_to_zone_km(point: GeoCoordinate, zone_center: GeoCoordinate) -> float:
    """Measure a point against a zone center for assertions and status displays."""
    return _GEOGRAPHY.geo_distance_km(point, zone_center)


def zone_edge_north(center: GeoCoordinate, radius_km: float) -> GeoCoordinate:
    """Provide a nearby geographic edge used to scale a zone marker on the globe."""
    latitude = center.latitude + max(0.0, float(radius_km)) / _KILOMETERS_PER_LATITUDE_DEGREE
    return GeoCoordinate(latitude=max(-89.5, min(89.5, latitude)), longitude=center.longitude)


def _relative_kilometers(point: GeoCoordinate, origin: GeoCoordinate) -> tuple[float, float]:
    longitude_delta = _normalized_longitude(point.longitude - origin.longitude)
    x = longitude_delta * _KILOMETERS_PER_LONGITUDE_DEGREE * cos(radians(origin.latitude))
    y = (point.latitude - origin.latitude) * _KILOMETERS_PER_LATITUDE_DEGREE
    return x, y


def _normalized_longitude(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0
