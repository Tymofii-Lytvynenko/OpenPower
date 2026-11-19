from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from modules.base.schema import build_base_schema_registry
from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig
from src.shared.state import GameState

ROOT = Path(__file__).resolve().parents[1]


def _load_results() -> pl.DataFrame:
    return DataLoader(GameConfig(ROOT))._load_world_tables()["country_election_results"]


def test_election_results_preserve_event_outcomes_and_source_scope() -> None:
    results = _load_results()
    event_counts = {
        event_id: results.filter(pl.col("event_id") == event_id).height
        for event_id in results["event_id"].unique().to_list()
    }

    assert event_counts == {
        "BGD_2001_parliamentary": 55,
        "DNK_2001_folketing": 11,
        "KOS_2001_assembly": 26,
        "MNE_2001_parliamentary": 16,
        "TLS_2001_constituent_assembly": 12,
        "SRB_2000_assembly": 8,
    }

    bangladesh = results.filter(pl.col("event_id") == "BGD_2001_parliamentary")
    assert bangladesh["votes"].sum() == 55_736_625
    assert bangladesh["seats"].sum() == 300
    assert set(bangladesh["election_date"].to_list()) == {"2001-10-01"}
    assert bangladesh["result_date"].null_count() == 55
    assert all("reserved women seats" in value for value in bangladesh["result_scope"])

    denmark = results.filter(pl.col("event_id") == "DNK_2001_folketing")
    assert denmark["votes"].sum() == 3_449_668
    assert denmark["seats"].sum() == 175
    assert set(denmark["election_date"].to_list()) == {"2001-11-20"}
    assert denmark["result_date"].null_count() == 11
    assert all("Faroe Islands and Greenland" in value for value in denmark["geography"])
    assert (
        results.filter(pl.col("event_id") == "KOS_2001_assembly")["votes"].sum()
        == 788_303
    )
    assert (
        results.filter(pl.col("event_id") == "KOS_2001_assembly")["seats"].sum() == 120
    )

    montenegro = results.filter(pl.col("event_id") == "MNE_2001_parliamentary")
    assert montenegro["votes"].sum() == 363_404
    assert montenegro["seats"].sum() == 77
    assert montenegro["general_seats"].sum() == 72
    assert montenegro["special_seats"].sum() == 5
    assert (
        montenegro.filter(pl.col("result_label").str.starts_with("Victory for"))[
            "seats"
        ][0]
        == 36
    )

    timor = results.filter(pl.col("event_id") == "TLS_2001_constituent_assembly")
    assert timor["votes"].null_count() == 12
    assert timor["seats"].sum() == 75
    assert round(timor["vote_share_pct"].sum(), 1) == 95.8
    assert set(timor["election_date"].to_list()) == {"2001-08-30"}
    assert all(
        "13 district seats" in value for value in timor["result_scope"].to_list()
    )

    serbia = results.filter(pl.col("event_id") == "SRB_2000_assembly")
    assert serbia["votes"].sum() == 3_660_849
    assert serbia["seats"].sum() == 250
    assert serbia["vote_share_pct"].null_count() == 8
    assert set(serbia["election_date"].to_list()) == {"2000-12-23"}
    assert set(serbia["additional_election_date"].to_list()) == {"2001-01-10"}
    assert set(serbia["result_date"].to_list()) == {"2001-01-12"}


def test_election_results_remain_separate_from_gameplay_politics() -> None:
    results = _load_results()
    forbidden_columns = {
        "support",
        "support_share",
        "party_support",
        "is_ruling",
        "ruling_party_id",
        "election_eligible",
    }

    assert not forbidden_columns.intersection(results.columns)
    assert results["source_url"].null_count() == 0
    assert results["source_reference"].null_count() == 0
    assert results["geography"].null_count() == 0
    assert results["result_scope"].null_count() == 0

    state = GameState()
    state.update_table("country_election_results", results)
    registry = build_base_schema_registry()
    registry.ensure_state(state)
    assert registry.validate_state(state) == []
    assert registry.get("country_election_results").key_columns == ("id",)

    manifest = json.loads(
        (
            ROOT / "modules/base/data/sources/2001/country_election_results_2001.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["record_count"] == 128
    assert manifest["event_counts"] == {
        "BGD_2001_parliamentary": 55,
        "DNK_2001_folketing": 11,
        "KOS_2001_assembly": 26,
        "MNE_2001_parliamentary": 16,
        "SRB_2000_assembly": 8,
        "TLS_2001_constituent_assembly": 12,
    }
