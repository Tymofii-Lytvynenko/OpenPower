import pytest

from src.core.map.geo import (
    EquirectangularProjection,
    GeoCoordinate,
    MapPixelCoordinate,
)


def test_pixel_coordinates_convert_to_unit_vectors() -> None:
    projection = EquirectangularProjection(360, 180)

    vector = projection.pixel_to_unit_vector(MapPixelCoordinate(180, 90))

    assert vector == pytest.approx((-1.0, 0.0, 0.0))


def test_zero_length_unit_vector_maps_to_origin_coordinate() -> None:
    projection = EquirectangularProjection(360, 180)

    assert projection.unit_vector_to_geo(0.0, 0.0, 0.0) == GeoCoordinate(0.0, 0.0)


def test_unit_vector_round_trip_normalizes_vector_length() -> None:
    projection = EquirectangularProjection(360, 180)
    expected = GeoCoordinate(latitude=45.0, longitude=90.0)
    vector = projection.geo_to_unit_vector(expected)

    actual = projection.unit_vector_to_geo(*(component * 5 for component in vector))

    assert actual.latitude == pytest.approx(expected.latitude)
    assert actual.longitude == pytest.approx(expected.longitude)
