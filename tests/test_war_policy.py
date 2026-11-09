from modules.base.systems.military.war_policy import (
    countries_are_hostile,
    hostile_country_pairs,
)


def test_war_policy_normalizes_active_sides_and_skips_inactive_wars():
    wars = [
        {"status": "ended", "side_a": ["USA"], "side_b": ["CAN"]},
        {"status": "ongoing", "side_a": [" usa ", "CAN"], "side_b": ["CAN", "MEX"]},
        {"status": "", "side_a": ["POL"], "side_b": ["UKR"]},
    ]

    assert hostile_country_pairs(wars) == {
        frozenset({"USA", "CAN"}),
        frozenset({"USA", "MEX"}),
        frozenset({"CAN", "MEX"}),
        frozenset({"POL", "UKR"}),
    }
    assert countries_are_hostile(wars, " usa ", "mex")
    assert not countries_are_hostile(wars, "USA", "USA")
    assert not countries_are_hostile(wars, "", "MEX")
