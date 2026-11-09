import polars as pl

from src.shared.region_control import (
    country_region_control_proportion,
    region_controlled_by_country,
)
from src.shared.state import GameState


def test_control_proportion_counts_only_active_matching_occupations():
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "id": ["invalid", "2", "3", "4"],
                    "owner": ["AAA", "AAA", "AAA", "BBB"],
                }
            ),
            "occupations": pl.DataFrame(
                {
                    "region_id": ["invalid", "2", "3", "4"],
                    "controller_country_id": ["BBB", "BBB", "BBB", "BBB"],
                    "occupation_status": ["active", "inactive", "cancelled", "active"],
                }
            ),
        }
    )

    assert country_region_control_proportion(state, "bbb", "aaa") == 1 / 3


def test_inactive_occupation_statuses_do_not_grant_control():
    for status in ("inactive", "cancelled", "ended"):
        state = GameState(
            tables={
                "regions": pl.DataFrame({"id": [1], "owner": ["AAA"]}),
                "occupations": pl.DataFrame(
                    {
                        "region_id": [1],
                        "controller_country_id": ["BBB"],
                        "occupation_status": [status],
                    }
                ),
            }
        )

        assert country_region_control_proportion(state, "BBB", "AAA") == 0.0
        assert region_controlled_by_country(state, {"id": 1, "owner": "AAA"}, "BBB") is False
