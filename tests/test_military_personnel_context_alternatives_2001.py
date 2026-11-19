from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "sources"
    / "2001"
    / "military_personnel_context_alternatives_2001.tsv"
)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_context_table_covers_each_unresolved_roster_id_without_claiming_primary_eligibility() -> (
    None
):
    rows = _read_tsv(CONTEXT_PATH)
    expected_ids = {
        "AFG",
        "ATA",
        "KOS",
        "MCO",
        "MNE",
        "PRI",
        "PSE",
        "SLB",
        "SMR",
        "SOM",
        "SSD",
    }

    assert len(rows) == len(expected_ids)
    assert {row["country_id"] for row in rows} == expected_ids
    assert all(row["scenario_year"] == "2001" for row in rows)
    assert all(row["primary_active_personnel_eligible"] == "no" for row in rows)
    assert all(
        row["context_kind"] and row["force_scope"] and row["limitation"] for row in rows
    )
    assert all(
        row["source_name"]
        and row["source_date"]
        and row["source_reference"]
        and row["source_url"].startswith("https://")
        for row in rows
    )
    for row in rows:
        source_date = row["source_date"]
        if len(source_date) == 4:
            assert source_date.isdigit()
        elif len(source_date) == 7:
            date.fromisoformat(f"{source_date}-01")
        else:
            date.fromisoformat(source_date)
    assert all(
        not row["context_value"] or int(row["context_value"]) >= 0 for row in rows
    )


def test_afghanistan_estimate_is_reproducible_and_nonstate_scope_is_explicit() -> None:
    rows = {row["country_id"]: row for row in _read_tsv(CONTEXT_PATH)}
    afghanistan = rows["AFG"]
    taliban_midpoint = (40_000 + 45_000) // 2
    foreign_fighter_midpoint = (8_000 + 12_000) // 2
    northern_alliance_midpoint = (22_000 + 25_000) // 2

    assert int(afghanistan["context_value"]) == (
        taliban_midpoint - foreign_fighter_midpoint + northern_alliance_midpoint
    )
    assert afghanistan["context_kind"] == "derived_conflict_participant_estimate"
    assert afghanistan["confidence"] == "low"
    assert "not a national armed-forces headcount" in afghanistan["limitation"]


def test_noncounts_are_labeled_as_ceilings_or_narrow_scope_proxies() -> None:
    rows = {row["country_id"]: row for row in _read_tsv(CONTEXT_PATH)}

    assert rows["KOS"]["context_kind"] == "authorized_active_ceiling"
    assert rows["PSE"]["context_kind"] == "authorized_security_force_ceiling"
    assert rows["MNE"]["context_kind"] == "territorial_federal_force_presence"
    assert rows["MNE"]["context_value"] == "15000"
    assert rows["SMR"]["context_value"] == ""
    assert rows["SSD"]["context_value"] == ""
    assert rows["ATA"]["context_kind"] == "scope_based_scenario_zero"
