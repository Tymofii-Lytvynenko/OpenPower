from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.alliance_policy import AlliancePolicy


def _war() -> SimpleNamespace:
    return SimpleNamespace(side_a=("AAA",), side_b=("BBB",))


def test_only_active_military_treaties_are_considered() -> None:
    treaties = pl.DataFrame(
        [
            {
                "id": "expired",
                "status": "ended",
                "type": "alliance",
                "members": ["AAA", "ALLY"],
            },
            {
                "id": "trade",
                "status": "active",
                "type": "trade",
                "members": ["AAA", "ALLY"],
            },
        ]
    )

    result = AlliancePolicy().expand(
        _war(), [{"owner": "ALLY"}], treaties
    )

    assert result.side_a == frozenset({"AAA"})
    assert result.rejected == (("ALLY", "no_direct_active_military_alliance"),)


def test_missing_treaty_members_fall_back_to_treaty_sides() -> None:
    treaties = pl.DataFrame(
        [
            {
                "id": "defense",
                "status": "active",
                "type": "defensive_alliance",
                "members": None,
                "side_a": ["AAA", "ALLY"],
                "side_b": ["OUTSIDE"],
            }
        ]
    )

    result = AlliancePolicy().expand(
        _war(), [{"owner": "ALLY"}], treaties
    )

    assert "ALLY" in result.side_a
    assert result.roles["ALLY"] == "ally"
    assert result.bases["ALLY"] == "treaty:defense"


def test_string_members_assign_allies_to_the_unambiguous_war_side() -> None:
    treaties = pl.DataFrame(
        [
            {
                "id": "side-a-defense",
                "status": "active",
                "type": "alliance",
                "members": "AAA,BBB,ALLY_A",
                "side_a": "AAA,ALLY_A",
                "side_b": "OUTSIDE",
            },
            {
                "id": "side-b-defense",
                "status": "active",
                "type": "defense_pact",
                "members": "AAA,BBB,ALLY_B",
                "side_a": "OUTSIDE",
                "side_b": "BBB,ALLY_B",
            },
        ]
    )

    result = AlliancePolicy().expand(
        _war(), [{"owner": "ALLY_A"}, {"owner": "ALLY_B"}], treaties
    )

    assert "ALLY_A" in result.side_a
    assert "ALLY_B" in result.side_b


def test_unallied_and_malformed_members_are_reported_without_expansion() -> None:
    policy = AlliancePolicy()
    outsider = policy.expand(_war(), [{"owner": "OUTSIDER"}], None)
    malformed = policy.expand(
        _war(),
        [{"owner": "ALLY"}],
        pl.DataFrame(
            [
                {
                    "id": "malformed",
                    "status": "active",
                    "type": "alliance",
                    "members": 17,
                    "side_a": None,
                    "side_b": None,
                }
            ]
        ),
    )

    assert outsider.rejected == (("OUTSIDER", "not_in_war"),)
    assert malformed.rejected == (("ALLY", "no_direct_active_military_alliance"),)
