import math

import polars as pl

from modules.base.systems.world.treaty_geography import TreatyGeography
from src.shared.state import GameState


def test_distance_limit_is_disabled_for_invalid_or_nonpositive_values():
    state = GameState()

    assert TreatyGeography.within_limit(state, "AAA", "BBB", 0) is True
    assert TreatyGeography.within_limit(state, "AAA", "BBB", "invalid") is True
    assert TreatyGeography.within_limit(state, "AAA", "BBB", 100.0) is False


def test_country_centroid_ignores_other_owners_and_regions_without_coordinates():
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "owner": ["BBB", "AAA", "AAA"],
                    "latitude": [10.0, None, 45.0],
                    "longitude": [20.0, 30.0, 60.0],
                }
            )
        }
    )

    centroid = TreatyGeography._country_centroid(state, "aaa")

    assert centroid is not None
    assert math.isclose(centroid[0], 45.0, abs_tol=1e-9)
    assert math.isclose(centroid[1], 60.0, abs_tol=1e-9)
    assert TreatyGeography.within_limit(state, "AAA", "AAA", 1.0) is True


def test_country_centroid_returns_none_without_points_or_when_vectors_cancel():
    missing = GameState(
        tables={
            "regions": pl.DataFrame(
                {"owner": ["BBB"], "latitude": [0.0], "longitude": [0.0]}
            )
        }
    )
    assert TreatyGeography._country_centroid(missing, "AAA") is None

    antipodal = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "owner": ["AAA", "AAA"],
                    "latitude": [0.0, 0.0],
                    "longitude": [0.0, 180.0],
                }
            )
        }
    )
    assert TreatyGeography._country_centroid(antipodal, "AAA") is None
