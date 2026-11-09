import polars as pl
import pytest

from src.client.utils.coords_util import (
    _calculate_geo_centroid,
    _infer_map_width,
    calculate_centroid,
    image_to_world,
)
from src.core.map.geo import GeoCoordinate


def test_image_to_world_flips_vertical_axis_and_returns_floats() -> None:
    assert image_to_world(12, 25, 100) == (12.0, 75.0)


def test_calculate_centroid_returns_none_for_empty_dataframe() -> None:
    assert calculate_centroid(pl.DataFrame(), map_height=100) is None


def test_calculate_centroid_averages_image_centers_and_inverts_y() -> None:
    regions = pl.DataFrame({"center_x": [2, 4], "center_y": [10, 20]})

    assert calculate_centroid(regions, map_height=100) == (3.0, 85.0)


@pytest.mark.parametrize(
    "columns",
    [
        {"center_x": [None, None], "center_y": [2.0, 4.0]},
        {"center_x": [2.0, 4.0], "center_y": [None, None]},
    ],
    ids=["missing-x-average", "missing-y-average"],
)
def test_calculate_centroid_returns_none_when_image_average_is_missing(
    columns: dict[str, list[float | None]],
) -> None:
    assert calculate_centroid(pl.DataFrame(columns), map_height=100) is None


def test_calculate_centroid_projects_valid_geographic_centroid() -> None:
    regions = pl.DataFrame(
        {
            "latitude": [0.0, 0.0],
            "longitude": [0.0, 10.0],
        }
    )

    assert calculate_centroid(regions, map_height=180, map_width=360) == pytest.approx((185.0, 90.0))


def test_calculate_centroid_skips_rows_without_complete_coordinates() -> None:
    regions = pl.DataFrame(
        {
            "latitude": [None, 0.0, 0.0],
            "longitude": [0.0, None, 10.0],
            "center_x": [10.0, 20.0, 30.0],
            "center_y": [10.0, 20.0, 30.0],
        }
    )

    assert calculate_centroid(regions, map_height=180, map_width=360) == pytest.approx((190.0, 90.0))


def test_calculate_centroid_falls_back_when_geographic_points_cancel_out() -> None:
    regions = pl.DataFrame(
        {
            "latitude": [0.0, 0.0],
            "longitude": [0.0, 180.0],
            "center_x": [3.0, 5.0],
            "center_y": [20.0, 40.0],
        }
    )

    assert calculate_centroid(regions, map_height=100) == (4.0, 70.0)


def test_geo_centroid_returns_none_when_no_row_has_both_coordinates() -> None:
    regions = pl.DataFrame(
        {
            "latitude": [None, 12.0],
            "longitude": [4.0, None],
        }
    )

    assert _calculate_geo_centroid(regions) is None


def test_geo_centroid_returns_average_as_a_coordinate() -> None:
    regions = pl.DataFrame(
        {
            "latitude": [0.0, 0.0],
            "longitude": [0.0, 10.0],
        }
    )

    centroid = _calculate_geo_centroid(regions)

    assert centroid is not None
    assert centroid.latitude == pytest.approx(0.0)
    assert centroid.longitude == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("regions", "expected_width"),
    [
        (pl.DataFrame({"center_y": [1.0]}), 1.0),
        (pl.DataFrame({"center_x": [0.0]}), 2.0),
        (pl.DataFrame({"center_x": [None]}), 2.0),
        (pl.DataFrame({"center_x": [7.0, 9.0]}), 10.0),
    ],
    ids=["missing-column", "zero-max", "null-max", "positive-max"],
)
def test_infer_map_width_handles_missing_zero_null_and_positive_maximum(
    regions: pl.DataFrame,
    expected_width: float,
) -> None:
    assert _infer_map_width(regions) == expected_width
