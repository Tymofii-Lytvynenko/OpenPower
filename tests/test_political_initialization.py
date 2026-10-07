from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.state import GameState


def test_legacy_government_rows_initialize_canonical_state_once_without_changing_world() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["DEM", "MIL"],
                    "gvt_approval": [62.0, 31.0],
                    "gvt_stability": [71.0, 24.0],
                    "gvt_corruption": [12.0, 45.0],
                }
            ),
            "regions": pl.DataFrame(
                {"id": [1, 2], "owner": ["DEM", "MIL"], "controller": ["DEM", "MIL"]}
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["DEM", "MIL"],
                    "government_type": ["Multi-party democracy", "Military-led state"],
                }
            ),
        }
    )
    state.time.total_minutes = 60_000
    ensure_base_tables(state)

    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    first_governments = state.get_table("country_governments").clone()
    first_parties = state.get_table("political_parties").clone()
    first_revisions = dict(state.table_revisions)

    system.update(state, 0.0)

    governments = state.get_table("country_governments").sort("country_id")
    dem = governments.filter(pl.col("country_id") == "DEM").row(0, named=True)
    mil = governments.filter(pl.col("country_id") == "MIL").row(0, named=True)

    assert governments.height == 2
    assert dem["initialized"] is True
    assert dem["election_eligible"] is True
    assert dem["next_election_at_minute"] == 60_000 + 4 * 365 * 24 * 60
    assert dem["ruling_party_id"] == "incumbent"
    assert mil["initialized"] is True
    assert mil["election_eligible"] is False
    assert mil["next_election_at_minute"] == 0
    assert first_governments.equals(governments)
    assert first_parties.equals(state.get_table("political_parties").sort(["country_id", "party_id"]))
    assert state.table_revisions == first_revisions
    assert state.get_table("regions").sort("id")["owner"].to_list() == ["DEM", "MIL"]
    assert state.get_table("countries").select(
        "gvt_approval", "gvt_stability", "gvt_corruption"
    ).rows() == [(62.0, 71.0, 12.0), (31.0, 24.0, 45.0)]


def test_missing_lifecycle_state_uses_safe_non_electoral_fallback() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["UNK"]}),
            "country_governments": pl.DataFrame(
                {"country_id": ["UNK"], "government_type": ["Scenario-defined form"]}
            ),
        }
    )
    ensure_base_tables(state)

    PoliticalLifecycleSystem().update(state, 0.0)

    row = state.get_table("country_governments").row(0, named=True)
    assert row["government_form_id"] == "scenario-defined form"
    assert row["election_eligible"] is False
    assert row["next_election_at_minute"] == 0
    assert state.get_table("political_parties")["party_id"].to_list() == ["incumbent"]


def test_unassigned_existing_factions_receive_a_real_incumbent_authority() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"]}),
            "country_governments": pl.DataFrame(
                {"country_id": ["AAA"], "government_type": ["Transitional republic"]}
            ),
            "political_parties": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "party_id": ["opposition"],
                    "display_name": ["Opposition"],
                    "support_share": [0.4],
                    "organization": [0.5],
                    "policy_positions_json": ["{}"],
                    "eligible": [True],
                    "is_ruling": [False],
                    "updated_at_minute": [0],
                }
            ),
        }
    )
    ensure_base_tables(state)

    PoliticalLifecycleSystem().update(state, 0.0)

    government = state.get_table("country_governments").row(0, named=True)
    parties = state.get_table("political_parties").sort("party_id")
    ruling = parties.filter(pl.col("is_ruling"))
    assert government["ruling_party_id"] == "incumbent"
    assert ruling["party_id"].to_list() == ["incumbent"]


def test_political_indicators_are_bounded_independently() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB"],
                    "gvt_approval": [130.0, float("nan")],
                    "gvt_stability": [-8.0, 0.75],
                    "gvt_corruption": [float("inf"), 1.25],
                }
            ),
        }
    )
    ensure_base_tables(state)

    PoliticalLifecycleSystem().update(state, 0.0)

    values = state.get_table("countries").sort("id").select(
        "gvt_approval", "gvt_stability", "gvt_corruption"
    ).rows()
    assert values == [(100.0, 0.0, 10.0), (50.0, 75.0, 1.25)]
