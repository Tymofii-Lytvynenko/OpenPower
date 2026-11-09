from __future__ import annotations

import polars as pl

from modules.base.systems.world.recognition_policy import (
    ai_recognition_vote,
    eligible_voters,
    is_un_member,
    regional_economic_access_allowed,
    regional_trade_access_allowed,
)
from src.shared.state import GameState


def test_un_membership_values_and_voter_roster_defaults():
    assert is_un_member(True)
    assert is_un_member(1)
    assert is_un_member(1.0)
    assert is_un_member(" YES ")
    assert is_un_member("y")
    assert not is_un_member(2)
    assert not is_un_member("no")

    countries = pl.DataFrame(
        {
            "id": ["CLAIM", "FORMER", "zulu", " alpha ", "dup", "DUP", None],
            "un_member": pl.Series(
                "un_member", [1, True, "yes", "Y", 1, 1.0, 1], dtype=pl.Object
            ),
        }
    )
    assert eligible_voters(countries, "claim", "former") == ("ALPHA", "DUP", "ZULU")
    assert eligible_voters(None, "CLAIM", "FORMER") == ()
    assert eligible_voters(pl.DataFrame(), "CLAIM", "FORMER") == ()
    assert eligible_voters(pl.DataFrame({"name": ["AAA"]}), "CLAIM", "FORMER") == ()
    assert eligible_voters(pl.DataFrame({"id": ["AAA"]}), "CLAIM", "FORMER") == ()


def test_vote_skips_malformed_relations_and_inactive_wars():
    state = GameState()
    state.tables["countries_relations"] = pl.DataFrame(
        {
            "source": ["YES_A", "NO_C"],
            "target": ["CLAIM", "CLAIM"],
            "value": [None, "not-a-number"],
        }
    )
    state.tables["countries_wars"] = pl.DataFrame(
        {"status": ["ended"], "attacker_id": ["YES_A"], "defender_id": ["CLAIM"]}
    )

    assert ai_recognition_vote(state, "YES_A", "CLAIM") == "yes"


def test_vote_uses_treaty_sides_when_members_are_absent():
    state = GameState()
    state.tables["countries_relations"] = pl.DataFrame(
        {"source": ["YES_A"], "target": ["CLAIM"], "value": [-40.0]}
    )
    state.tables["countries_treaties"] = pl.DataFrame(
        {
            "status": ["active"],
            "treaty_type": ["alliance"],
            "side_a": [["YES_A"]],
            "side_b": [["CLAIM"]],
        }
    )

    assert ai_recognition_vote(state, "YES_A", "CLAIM") == "yes"


def test_economic_access_rejects_invalid_region_and_recognition_schemas():
    assert not regional_economic_access_allowed(GameState(), 1, "AAA")

    missing_owner = GameState(tables={"regions": pl.DataFrame({"id": [1]})})
    assert not regional_economic_access_allowed(missing_owner, 1, "AAA")

    empty_regions = GameState(
        tables={"regions": pl.DataFrame(schema={"id": pl.Int32, "owner": pl.Utf8})}
    )
    assert not regional_economic_access_allowed(empty_regions, 1, "AAA")

    malformed_status = GameState(
        tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["AAA"]}),
            "regional_recognition_status": pl.DataFrame({"region_id": [1]}),
            "recognition_cases": pl.DataFrame(
                {
                    "id": ["case-1"],
                    "region_id": [1],
                    "claimant_id": ["AAA"],
                    "status": ["passed"],
                }
            ),
        }
    )
    assert not regional_economic_access_allowed(malformed_status, 1, "BBB")


def test_trade_access_rejects_invalid_region_and_non_owner_exporter():
    assert not regional_trade_access_allowed(GameState(), 1, "AAA", "BBB")

    missing_owner = GameState(tables={"regions": pl.DataFrame({"id": [1]})})
    assert not regional_trade_access_allowed(missing_owner, 1, "AAA", "BBB")

    valid_region = GameState(
        tables={"regions": pl.DataFrame({"id": [1], "owner": ["AAA"]})}
    )
    assert not regional_trade_access_allowed(valid_region, 999, "AAA", "BBB")
    assert not regional_trade_access_allowed(valid_region, 1, "BBB", "CCC")
