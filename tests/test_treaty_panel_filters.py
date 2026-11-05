from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.politics.treaties_live import (
    _matches_treaty_filter,
    _treaty_filter_options,
)
from src.shared.treaties import TREATY_DEFINITIONS
from src.client.ui.panels.politics.treaty_filters import treaty_member_tags


def test_treaty_filters_offer_country_catalog_and_full_supported_type_catalog():
    state = SimpleNamespace(
        globals={},
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["UKR", "POL", "DEU", "ZZZ"],
                    "name": ["Ukraine", "Poland", "Germany", "Inactive"],
                    "active": [True, True, True, False],
                }
            )
        },
    )
    rows = [
        {"id": "active", "type": "alliance", "members": ["UKR", "POL"]},
        {
            "id": "pending",
            "treaty_type": "economic_partnership",
            "side_a": ["DEU"],
            "side_b": ["UKR"],
        },
    ]

    members, types = _treaty_filter_options(state, rows)

    assert members == [
        ("DEU", "Germany (DEU)"),
        ("POL", "Poland (POL)"),
        ("UKR", "Ukraine (UKR)"),
    ]
    assert {key for key, _ in types} == set(TREATY_DEFINITIONS)
    assert _matches_treaty_filter(rows[1], "DEU", "economic_partnership")
    assert not _matches_treaty_filter(rows[1], "POL", "economic_partnership")
    assert not _matches_treaty_filter(rows[1], "DEU", "alliance")


def test_filter_falls_back_to_proposal_countries_and_keeps_unknown_types():
    row = {"source_country_id": "aaa", "target_country_id": "bbb", "type": "custom_pact"}
    assert set(treaty_member_tags(row)) == {"AAA", "BBB"}
    assert _matches_treaty_filter(row, "BBB", "custom_pact")
    state = SimpleNamespace(globals={}, tables={})
    members, types = _treaty_filter_options(state, [row])
    assert {tag for tag, _ in members} == {"AAA", "BBB"}
    assert ("custom_pact", "Custom Pact") in types
