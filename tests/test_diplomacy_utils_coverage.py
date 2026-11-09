from types import SimpleNamespace

import polars as pl

from src.client.utils.diplomacy_utils import (
    _is_active_treaty,
    get_military_access_partners,
    get_military_allies,
    get_military_enemies,
    normalize_side,
)


def _state(tables=None, *, minute=100):
    tables = tables or {}
    return SimpleNamespace(
        tables=tables,
        time=SimpleNamespace(total_minutes=minute),
        get_table=lambda name: tables[name],
    )


def test_normalize_side_supports_tuples_and_delimited_strings():
    assert normalize_side(None) == set()
    assert normalize_side(("UKR", None, 7)) == {"UKR", "7"}
    assert normalize_side(" UKR, , POL ") == {"UKR", "POL"}
    assert normalize_side({"UKR"}) == set()


def test_military_allies_handles_missing_treaties_and_bilateral_sides():
    assert get_military_allies(_state(), "UKR") == set()
    assert get_military_allies(_state({"countries_treaties": pl.DataFrame()}), "UKR") == set()

    treaties = pl.DataFrame(
        [
            {
                "type": "alliance",
                "side_a": ["UKR", "POL"],
                "side_b": ["USA", "FRA"],
                "suspended_members": ["FRA"],
                "status": "active",
                "expires_at_minute": 0,
            },
            {
                "type": "military_pact",
                "side_a": ["CAN"],
                "side_b": ["UKR"],
                "suspended_members": [],
                "status": "active",
                "expires_at_minute": 150,
            },
            {
                "type": "defensive_pact",
                "side_a": ["MEX"],
                "side_b": ["BRA"],
                "suspended_members": [],
                "status": "active",
                "expires_at_minute": 0,
            },
            {
                "type": "alliance",
                "side_a": ["UKR"],
                "side_b": ["GER"],
                "suspended_members": ["UKR"],
                "status": "expired",
                "expires_at_minute": 0,
            },
        ]
    )

    assert get_military_allies(_state({"countries_treaties": treaties}), "ukr") == {
        "USA", "CAN"
    }

    member_treaties = pl.DataFrame(
        [
            {"type": "alliance", "members": ["UKR", "POL"], "status": "active"},
            {"type": "economic_treaty", "members": ["UKR", "MEX"], "status": "active"},
            {"type": "alliance", "members": ["UKR", "CAN"], "status": "expired"},
        ]
    )
    assert get_military_allies(_state({"countries_treaties": member_treaties}), "UKR") == {
        "POL"
    }


def test_military_access_uses_members_then_bilateral_sides_and_filters_expired_rows():
    assert get_military_access_partners(_state(), "UKR") == set()
    assert get_military_access_partners(
        _state({"countries_treaties": pl.DataFrame({"id": ["one"]})}), "UKR"
    ) == set()

    treaties = pl.DataFrame(
        [
            {
                "type": " MILITARY_ACCESS ",
                "members": ["ukr", "pol", "fra"],
                "side_a": ["UKR"],
                "side_b": ["Ignored by members"],
                "suspended_members": ["fra"],
                "expires_at_minute": 0,
            },
            {
                "type": "military_trespassing_right",
                "members": [],
                "side_a": ["CAN"],
                "side_b": ["UKR", "USA"],
                "suspended_members": ["USA"],
                "expires_at_minute": 0,
            },
            {
                "type": "military_access_agreement",
                "members": [],
                "side_a": ["UKR"],
                "side_b": ["MEX"],
                "suspended_members": [],
                "expires_at_minute": 0,
            },
            {
                "type": "military_access_agreement",
                "members": [],
                "side_a": ["UKR"],
                "side_b": ["GER"],
                "suspended_members": [],
                "expires_at_minute": 50,
            },
            {
                "type": "economic_treaty",
                "members": ["UKR", "MEX"],
                "side_a": [],
                "side_b": [],
                "suspended_members": [],
                "expires_at_minute": 0,
            },
        ]
    )

    assert get_military_access_partners(_state({"countries_treaties": treaties}), "ukr") == {
        "POL", "CAN", "MEX"
    }


def test_military_enemies_handles_missing_columns_and_enemy_on_second_side():
    assert get_military_enemies(_state(), "UKR") == set()
    assert get_military_enemies(
        _state({"countries_wars": pl.DataFrame({"id": ["war"]})}), "UKR"
    ) == set()

    wars = pl.DataFrame(
        [
            {"side_a": ["POL"], "side_b": ["UKR", "USA"], "status": " ACTIVE "},
            {"side_a": ["UKR"], "side_b": ["GER"], "status": "active"},
            {"side_a": ["UKR"], "side_b": ["FRA"], "status": "ended"},
        ]
    )
    assert get_military_enemies(_state({"countries_wars": wars}), "ukr") == {"POL", "GER"}


def test_treaty_expiration_parsing_treats_malformed_values_as_active():
    assert _is_active_treaty({"status": "active", "expires_at_minute": "bad"}, 100)
    assert not _is_active_treaty({"status": "active", "expires_at_minute": 100}, 100)
    assert not _is_active_treaty({"status": "suspended", "expires_at_minute": 0}, 100)
