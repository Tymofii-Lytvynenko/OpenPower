import polars as pl

from src.shared.treaties import (
    active_treaty_members,
    decode_conditions,
    normalize_country_tags,
    share_active_treaty,
    treaty_members,
)


def _treaty_frame(*rows: dict[str, object]) -> pl.DataFrame:
    return pl.DataFrame(list(rows))


def test_normalize_country_tags_accepts_persisted_legacy_shapes() -> None:
    assert normalize_country_tags(None) == ()
    assert normalize_country_tags(" usa, can, ,USA ") == ("CAN", "USA")
    assert normalize_country_tags([" mex ", "usa", ""]) == ("MEX", "USA")
    assert normalize_country_tags(42) == ("42",)


def test_treaty_members_falls_back_to_the_union_of_both_sides() -> None:
    assert treaty_members(
        {"members": [], "side_a": "usa, mex", "side_b": ["can", "usa"]}
    ) == ("CAN", "MEX", "USA")
    assert treaty_members({"members": "can, usa", "side_a": "mex"}) == ("CAN", "USA")


def test_share_active_treaty_checks_types_membership_and_suspensions() -> None:
    treaties = _treaty_frame(
        {
            "type": "trade",
            "status": "active",
            "members": ["USA", "MEX"],
            "suspended_members": [],
        },
        {
            "type": "alliance",
            "status": "active",
            "members": ["USA", "CAN"],
            "suspended_members": [],
        },
        {
            "type": "alliance",
            "status": "active",
            "members": ["USA", "MEX"],
            "suspended_members": ["MEX"],
        },
    )

    assert not share_active_treaty(treaties, "", "CAN", ["alliance"])
    assert share_active_treaty(treaties, " usa ", "can", ["alliance"])
    assert not share_active_treaty(treaties, "USA", "MEX", ["alliance"])
    assert not share_active_treaty(treaties, "USA", "CAN", ["trade"])


def test_active_treaty_members_filters_type_and_suspended_members() -> None:
    treaties = _treaty_frame(
        {
            "type": "trade",
            "status": "active",
            "members": ["USA", "MEX"],
            "side_a": None,
            "side_b": None,
            "suspended_members": [],
        },
        {
            "type": "alliance",
            "status": "active",
            "members": ["USA", "CAN"],
            "side_a": None,
            "side_b": None,
            "suspended_members": ["CAN"],
        },
        {
            "type": "alliance",
            "status": "active",
            "members": [],
            "side_a": "MEX",
            "side_b": "CAN",
            "suspended_members": ["MEX", "CAN"],
        },
        {
            "type": "alliance",
            "status": "active",
            "members": None,
            "side_a": " usa ",
            "side_b": "can, mex",
            "suspended_members": ["MEX"],
        },
    )

    assert active_treaty_members(treaties, "alliance") == (("USA",), ("CAN", "USA"))


def test_decode_conditions_recovers_from_invalid_json() -> None:
    assert decode_conditions("not-json")
