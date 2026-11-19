from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "sources"
    / "2001"
    / "military_equipment_candidates_2001.tsv"
)


def _read_candidates() -> list[dict[str, str]]:
    with CANDIDATES_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def _read_supplement() -> list[dict[str, str]]:
    path = (
        ROOT
        / "modules"
        / "base"
        / "data"
        / "sources"
        / "2001"
        / "military_equipment_inventory_supplement_2001.tsv"
    )
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_candidate_evidence_has_complete_provenance_and_narrow_scope() -> None:
    candidates = _read_candidates()
    imported = {(row["country_id"], row["field"]): row for row in _read_supplement()}
    expected = {
        ("USA", "military_aircraft_carriers_quantity_2001"): ("12", "2001-09-30"),
        ("USA", "military_ballistic_missile_submarines_quantity_2001"): (
            "18",
            "2001-09-30",
        ),
        ("FRA", "military_aircraft_carriers_quantity_2001"): ("1", "2001-11-22"),
        ("FRA", "military_ballistic_missile_submarines_quantity_2001"): (
            "4",
            "2001-07",
        ),
        ("GBR", "military_ballistic_missile_submarines_quantity_2001"): (
            "4",
            "2001-11",
        ),
        ("GBR", "military_aircraft_carriers_quantity_2001"): ("3", "2000-03-17"),
    }

    assert len(candidates) == len(expected)
    assert {
        (row["country_id"], row["field"]): (
            row["candidate_value"],
            row["observation_date"],
        )
        for row in candidates
    } == expected
    assert len({row["candidate_id"] for row in candidates}) == len(candidates)
    assert all(row["scenario_year"] == "2001" for row in candidates)
    for row in candidates:
        observation_date = row["observation_date"]
        if len(observation_date) == 7:
            date.fromisoformat(f"{observation_date}-01")
        else:
            date.fromisoformat(observation_date)
    assert {
        (row["country_id"], row["role"]): row["confidence"] for row in candidates
    } == {
        ("USA", "aircraft_carriers"): "high",
        ("USA", "ballistic_missile_submarines"): "high",
        ("FRA", "aircraft_carriers"): "high",
        ("FRA", "ballistic_missile_submarines"): "high",
        ("GBR", "ballistic_missile_submarines"): "high",
        ("GBR", "aircraft_carriers"): "moderate",
    }
    assert all(row["unit"] == "vessels" for row in candidates)
    assert all(row["source_url"].startswith("https://") for row in candidates)
    assert all(
        row["source_name"] and row["source_reference"] and row["source_note"]
        for row in candidates
    )
    assert all(row["operational_scope"] for row in candidates)
    assert all(
        row["implementation_status"] == "imported_to_maintained_supplement"
        for row in candidates
    )
    assert all(
        imported[(row["country_id"], row["field"])]["value"] == row["candidate_value"]
        for row in candidates
    )


def test_candidate_scope_does_not_claim_deployment_or_continuous_readiness() -> None:
    candidates = _read_candidates()
    by_country_role = {(row["country_id"], row["role"]): row for row in candidates}

    assert (
        "not implied"
        in by_country_role[("USA", "aircraft_carriers")]["operational_scope"]
    )
    assert (
        "not implied"
        in by_country_role[("USA", "ballistic_missile_submarines")]["operational_scope"]
    )
    assert (
        "60% availability"
        in by_country_role[("FRA", "aircraft_carriers")]["operational_scope"]
    )
