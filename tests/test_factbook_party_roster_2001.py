from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.politics.political_policy import initialize_country_politics
from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig
from src.shared.state import GameState
from utils.import_factbook_party_roster_2001 import (
    COVERAGE_PATH,
    EXTRACT_COLUMNS,
    EXTRACT_PATH,
    FACTBOOK_PATH,
    SOURCE_FIELD,
    SOURCE_TEXT_URL,
    _read_game_country_ids,
    build_roster,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_factbook_party_roster_import_keeps_only_source_supported_records() -> None:
    rows, coverage, counts = build_roster(
        FACTBOOK_PATH.read_text(encoding="utf-8-sig"),
        _read_game_country_ids(),
    )

    assert counts["source_country_entries"] == 267
    assert counts["source_party_fields"] == 231
    assert counts["game_country_count"] == 209
    assert counts["game_countries_with_party_records"] == 197
    assert counts["party_record_count"] == 1405
    assert {row["country_id"] for row in rows} <= _read_game_country_ids()
    assert all(row["source_field"] == SOURCE_FIELD for row in rows)
    assert all(row["source_year"] == 2001 for row in rows)
    assert all(row["source_url"] == SOURCE_TEXT_URL for row in rows)
    assert all(
        not {"support_share", "vote_share", "votes", "is_ruling"}.intersection(row)
        for row in rows
    )
    assert not any(row["display_name"].casefold().startswith("several other groups") for row in rows)
    assert {
        row["country_id"]: row["status"]
        for row in coverage
        if row["status"] != "reported"
    } == {
        "ATA": "party_field_not_reported",
        "KOS": "no_separate_country_entry",
        "MNE": "no_separate_country_entry",
        "PSE": "party_field_not_reported",
        "SRB": "no_separate_country_entry",
        "SSD": "no_separate_country_entry",
        "TLS": "no_separate_country_entry",
    }
    antarctica_coverage = next(row for row in coverage if row["country_id"] == "ATA")
    assert antarctica_coverage["status"] == "party_field_not_reported"
    assert "continent-level game profile" in antarctica_coverage["source_note"]


def test_factbook_party_roster_preserves_named_us_party_leader_and_source_notes() -> None:
    rows, _, _ = build_roster(
        FACTBOOK_PATH.read_text(encoding="utf-8-sig"),
        _read_game_country_ids(),
    )
    democratic_party = next(
        row
        for row in rows
        if row["country_id"] == "USA" and row["display_name"] == "Democratic Party"
    )
    republican_party = next(
        row
        for row in rows
        if row["country_id"] == "USA" and row["display_name"] == "Republican Party"
    )

    assert "Terence McAULIFFE" in democratic_party["leaders_text"]
    assert democratic_party["leader_status"] == "reported"
    assert "James S. GILMORE III" in republican_party["leaders_text"]
    assert republican_party["leader_status"] == "reported"
    assert republican_party["source_reference"].endswith("United States, Political parties and leaders")
    assert republican_party["source_year"] == 2001
    assert republican_party["source_notes"].startswith("several other groups or parties")


def test_factbook_party_roster_files_and_world_loader_match_country_coverage() -> None:
    stored_rows = _read_tsv(EXTRACT_PATH)
    stored_coverage = _read_tsv(COVERAGE_PATH)
    manifest = json.loads(
        (ROOT / "modules/base/data/sources/2001/country_party_roster_factbook_2001.json")
        .read_text(encoding="utf-8")
    )

    assert len(stored_rows) == 1405
    assert len(stored_coverage) == 209
    assert set(stored_rows[0]) == set(EXTRACT_COLUMNS)
    assert manifest["counts"]["game_countries_with_party_records"] == 197
    assert manifest["counts"]["party_record_count"] == len(stored_rows)
    assert manifest["counts"]["uncovered_game_country_ids"] == [
        "ATA",
        "ESH",
        "KOS",
        "MAC",
        "MNE",
        "PSE",
        "SHN",
        "SRB",
        "SSD",
        "SXM",
        "TLS",
        "UMI",
    ]

    loader = DataLoader(GameConfig(ROOT))
    tables = loader._load_world_tables()
    roster = tables["country_party_roster_2001"]
    coverage = tables["country_party_roster_coverage_2001"]
    assert roster.height == len(stored_rows)
    assert coverage.height == len(stored_coverage)
    assert {"country_id", "display_name", "leaders_text", "source_year"}.issubset(roster.columns)
    assert not {"support_share", "vote_share", "is_ruling"}.intersection(roster.columns)
    assert set(coverage.filter(pl.col("status") != "reported")["country_id"].to_list()) == {
        "ATA",
        "ESH",
        "KOS",
        "MAC",
        "MNE",
        "PSE",
        "SHN",
        "SRB",
        "SSD",
        "SXM",
        "TLS",
        "UMI",
    }

    state = GameState()
    state.update_table("country_party_roster_2001", roster)
    state.update_table("country_party_roster_coverage_2001", coverage)
    registry = build_base_schema_registry()
    registry.ensure_state(state)
    assert registry.validate_state(state) == []
    assert registry.get("country_party_roster_2001").key_columns == ("id",)
    assert registry.get("country_party_roster_coverage_2001").key_columns == ("country_id",)
    assert state.get_table("country_party_roster_2001").schema["source_year"] == pl.Int32


def test_factbook_party_roster_stays_separate_from_generic_gameplay_fallbacks() -> None:
    countries = pl.read_csv(ROOT / "modules/base/data/countries/countries.tsv", separator="\t")
    _, gameplay_parties, _ = initialize_country_politics(
        countries,
        pl.DataFrame(),
        pl.DataFrame(),
        pl.DataFrame(),
        0,
    )

    assert countries.height == 209
    assert gameplay_parties.height == 209
    assert gameplay_parties["party_id"].unique().to_list() == ["incumbent"]
    assert gameplay_parties["display_name"].unique().to_list() == ["Incumbent"]
    assert gameplay_parties["support_share"].unique().to_list() == [1.0]
