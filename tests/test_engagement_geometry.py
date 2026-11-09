from src.core.map.engagement_geometry import (
    ENGAGEMENT_RADIUS_KM,
    distance_to_zone_km,
    engagement_radius_km,
    first_zone_contact_fraction,
    interpolate_geo,
    zone_edge_north,
)
from src.core.map.geo import GeoCoordinate


def test_engagement_radius_uses_default_and_sanitizes_overrides():
    assert engagement_radius_km({}) == ENGAGEMENT_RADIUS_KM
    assert engagement_radius_km({"engagement_radius_km": "invalid"}) == ENGAGEMENT_RADIUS_KM
    assert engagement_radius_km({"engagement_radius_km": -2}) == 0.0
    assert engagement_radius_km({"engagement_radius_km": 75}) == 75.0


def test_first_zone_contact_handles_disabled_inside_stationary_and_missed_routes():
    center = GeoCoordinate(0.0, 0.0)
    outside = GeoCoordinate(0.0, 2.0)

    assert first_zone_contact_fraction(outside, center, center, 0.0) is None
    assert first_zone_contact_fraction(center, outside, center, 50.0) == 0.0
    assert first_zone_contact_fraction(outside, outside, center, 50.0) is None
    assert first_zone_contact_fraction(
        GeoCoordinate(2.0, -2.0), GeoCoordinate(2.0, 2.0), center, 50.0
    ) is None


def test_first_zone_contact_finds_entry_across_the_date_line():
    fraction = first_zone_contact_fraction(
        GeoCoordinate(0.0, 179.0),
        GeoCoordinate(0.0, -179.0),
        GeoCoordinate(0.0, 180.0),
        50.0,
    )

    assert fraction is not None
    assert 0.0 < fraction < 0.5


def test_interpolation_clamps_fraction_and_wraps_longitude():
    start = GeoCoordinate(10.0, 179.0)
    end = GeoCoordinate(20.0, -179.0)

    assert interpolate_geo(start, end, -1.0) == GeoCoordinate(10.0, 179.0)
    midpoint = interpolate_geo(start, end, 0.5)
    assert midpoint.latitude == 15.0
    assert midpoint.longitude == -180.0
    assert interpolate_geo(start, end, 2.0) == end


def test_zone_edge_and_distance_helpers_clamp_coordinates():
    center = GeoCoordinate(89.0, 30.0)

    edge = zone_edge_north(center, 1000.0)
    assert edge == GeoCoordinate(89.5, 30.0)
    assert zone_edge_north(center, -5.0) == center
    assert distance_to_zone_km(center, center) == 0.0
