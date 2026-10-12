from unittest.mock import Mock

import polars as pl
import pytest

from modules.base.systems.military.military_system import DEFAULT_MOVE_MINUTES, MovementDurationPolicy
from modules.base.systems.military.region_travel_time import RegionTravelTime


@pytest.mark.parametrize(
    "regions",
    [
        pl.DataFrame({"id": [1, 2, 3], "latitude": [0.0, 20.0, 40.0], "longitude": [0.0, 30.0, 60.0]}),
        pl.DataFrame({"id": [1, 2, 3], "center_x": [10.0, 20.0, 40.0], "center_y": [5.0, 10.0, 20.0]}),
    ],
)
def test_index_preserves_movement_estimates_and_builds_only_once(regions: pl.DataFrame) -> None:
    original = MovementDurationPolicy()
    policy = Mock(wraps=original)
    travel_time = RegionTravelTime(regions, duration_policy=policy)
    policy.region_locations.assert_not_called()

    for source, target in [(1, 2), (2, 3), (3, 1), (1, 2), (1, 1)]:
        assert travel_time.estimate_minutes(source, target) == original.estimate_minutes(regions, source, target)
    policy.region_locations.assert_called_once_with(regions)


@pytest.mark.parametrize("regions", [None, pl.DataFrame(), pl.DataFrame({"id": [1, 2]})])
def test_missing_coordinates_preserve_default_duration(regions: pl.DataFrame | None) -> None:
    policy = Mock(wraps=MovementDurationPolicy())
    travel_time = RegionTravelTime(regions, duration_policy=policy)

    assert travel_time.estimate_minutes(1, 2) == DEFAULT_MOVE_MINUTES
    assert travel_time.estimate_minutes(2, 3) == DEFAULT_MOVE_MINUTES
    assert policy.region_locations.call_count == (0 if regions is None else 1)


def test_unknown_region_preserves_default_duration() -> None:
    regions = pl.DataFrame({"id": [1], "latitude": [0.0], "longitude": [0.0]})
    assert RegionTravelTime(regions).estimate_minutes(1, 999) == DEFAULT_MOVE_MINUTES
