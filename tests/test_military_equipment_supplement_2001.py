from __future__ import annotations

import csv
from pathlib import Path

import pytest

from utils.generate_military_inventory_2001 import generate_inventory_rows
from utils.import_military_equipment_supplement_2001 import apply_equipment_supplement

ROOT = Path(__file__).resolve().parents[1]
MILITARY_PATH = ROOT / "modules" / "base" / "data" / "countries" / "countries_mil.tsv"
SUPPLEMENT_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "sources"
    / "2001"
    / "military_equipment_inventory_supplement_2001.tsv"
)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_ledger_has_27_cited_or_near_year_equipment_counts() -> None:
    military = {row["id"]: row for row in _read_tsv(MILITARY_PATH)}
    supplements = _read_tsv(SUPPLEMENT_PATH)
    expected = {
        ("RUS", "military_ballistic_missile_submarines_quantity_2001"): "17",
        ("CHN", "military_aircraft_carriers_quantity_2001"): "0",
        ("IND", "military_aircraft_carriers_quantity_2001"): "1",
        ("USA", "military_aircraft_carriers_quantity_2001"): "12",
        ("USA", "military_ballistic_missile_submarines_quantity_2001"): "18",
        ("FRA", "military_aircraft_carriers_quantity_2001"): "1",
        ("FRA", "military_ballistic_missile_submarines_quantity_2001"): "4",
        ("GBR", "military_ballistic_missile_submarines_quantity_2001"): "4",
        ("GBR", "military_aircraft_carriers_quantity_2001"): "3",
        ("BHR", "military_tanks_quantity_2001"): "106",
        ("BHR", "military_artillery_quantity_2001"): "98",
        ("BHR", "military_infantry_vehicles_quantity_2001"): "365",
        ("KWT", "military_tanks_quantity_2001"): "385",
        ("KWT", "military_artillery_quantity_2001"): "59",
        ("KWT", "military_infantry_vehicles_quantity_2001"): "495",
        ("OMN", "military_tanks_quantity_2001"): "117",
        ("OMN", "military_artillery_quantity_2001"): "115",
        ("OMN", "military_infantry_vehicles_quantity_2001"): "183",
        ("QAT", "military_tanks_quantity_2001"): "44",
        ("QAT", "military_artillery_quantity_2001"): "40",
        ("QAT", "military_infantry_vehicles_quantity_2001"): "212",
        ("SAU", "military_tanks_quantity_2001"): "1055",
        ("SAU", "military_artillery_quantity_2001"): "448",
        ("SAU", "military_infantry_vehicles_quantity_2001"): "2870",
        ("ARE", "military_tanks_quantity_2001"): "331",
        ("ARE", "military_artillery_quantity_2001"): "270",
        ("ARE", "military_infantry_vehicles_quantity_2001"): "1053",
    }

    assert {
        (row["country_id"], row["field"]): row["value"] for row in supplements
    } == expected
    assert all(row["scenario_year"] == "2001" for row in supplements)
    assert all(row["observation_year"] in {"2000", "2001"} for row in supplements)
    assert all(
        row["source_date"].startswith(("2000", "2001"))
        and row["source_url"].startswith("https://")
        for row in supplements
    )
    assert all(
        row["source_reference"] and row["source_note"] and row["count_basis"]
        for row in supplements
    )
    assert all(
        military[row["country_id"]][row["field"]] == row["value"] for row in supplements
    )


def test_ledger_is_applied_after_focused_generation_without_touching_other_values() -> (
    None
):
    military_rows = _read_tsv(MILITARY_PATH)
    generated_rows = generate_inventory_rows(
        military_rows,
        {"RUS": 0.45, "CHN": 0.45, "IND": 0.45},
        {"RUS", "CHN", "IND"},
    )
    updated_rows = apply_equipment_supplement(
        generated_rows, _read_tsv(SUPPLEMENT_PATH)
    )
    before = {row["id"]: row for row in generated_rows}
    after = {row["id"]: row for row in updated_rows}

    assert after["RUS"]["military_ballistic_missile_submarines_quantity_2001"] == "17"
    assert after["CHN"]["military_aircraft_carriers_quantity_2001"] == "0"
    assert after["IND"]["military_aircraft_carriers_quantity_2001"] == "1"
    assert after["USA"]["military_aircraft_carriers_quantity_2001"] == "12"
    assert after["USA"]["military_ballistic_missile_submarines_quantity_2001"] == "18"
    assert after["FRA"]["military_aircraft_carriers_quantity_2001"] == "1"
    assert after["FRA"]["military_ballistic_missile_submarines_quantity_2001"] == "4"
    assert after["GBR"]["military_ballistic_missile_submarines_quantity_2001"] == "4"
    assert after["GBR"]["military_aircraft_carriers_quantity_2001"] == "3"
    assert after["BHR"]["military_tanks_quantity_2001"] == "106"
    assert after["BHR"]["military_artillery_quantity_2001"] == "98"
    assert after["BHR"]["military_infantry_vehicles_quantity_2001"] == "365"
    assert after["KWT"]["military_tanks_quantity_2001"] == "385"
    assert after["KWT"]["military_artillery_quantity_2001"] == "59"
    assert after["KWT"]["military_infantry_vehicles_quantity_2001"] == "495"
    assert after["OMN"]["military_tanks_quantity_2001"] == "117"
    assert after["OMN"]["military_artillery_quantity_2001"] == "115"
    assert after["OMN"]["military_infantry_vehicles_quantity_2001"] == "183"
    assert after["QAT"]["military_tanks_quantity_2001"] == "44"
    assert after["QAT"]["military_artillery_quantity_2001"] == "40"
    assert after["QAT"]["military_infantry_vehicles_quantity_2001"] == "212"
    assert after["SAU"]["military_tanks_quantity_2001"] == "1055"
    assert after["SAU"]["military_artillery_quantity_2001"] == "448"
    assert after["SAU"]["military_infantry_vehicles_quantity_2001"] == "2870"
    assert after["ARE"]["military_tanks_quantity_2001"] == "331"
    assert after["ARE"]["military_artillery_quantity_2001"] == "270"
    assert after["ARE"]["military_infantry_vehicles_quantity_2001"] == "1053"
    assert (
        after["RUS"]["military_tanks_quantity_2001"]
        == before["RUS"]["military_tanks_quantity_2001"]
    )
    assert (
        after["CHN"]["military_fighters_quantity_2001"]
        == before["CHN"]["military_fighters_quantity_2001"]
    )
    assert (
        after["IND"]["military_attack_submarines_quantity_2001"]
        == before["IND"]["military_attack_submarines_quantity_2001"]
    )
    assert after["USA"] == before["USA"]


def test_supplement_rejects_missing_provenance_duplicate_rows_and_non_inventory_fields() -> (
    None
):
    base = {
        "country_id": "RUS",
        "role": "ballistic_missile_submarines",
        "field": "military_ballistic_missile_submarines_quantity_2001",
        "value": "17",
        "scenario_year": "2001",
        "observation_year": "2001",
        "source_date": "2001-05",
        "evidence_kind": "published_operational_assessment",
        "confidence": "moderate",
        "count_basis": "operational_SSBNs",
        "source_name": "Bulletin of the Atomic Scientists",
        "source_reference": "Russian Nuclear Forces, 2001",
        "source_url": "https://journals.sagepub.com/doi/full/10.2968/057003023",
        "source_note": "The source assesses 17 operational SSBNs.",
    }

    with pytest.raises(ValueError, match="missing provenance"):
        apply_equipment_supplement(
            [
                {
                    "id": "RUS",
                    "military_ballistic_missile_submarines_quantity_2001": "15",
                }
            ],
            [{**base, "source_url": ""}],
        )
    with pytest.raises(ValueError, match="Duplicate military equipment supplement"):
        apply_equipment_supplement(
            [
                {
                    "id": "RUS",
                    "military_ballistic_missile_submarines_quantity_2001": "15",
                }
            ],
            [base, base],
        )
    with pytest.raises(
        ValueError, match="Unsupported military equipment supplement contract"
    ):
        apply_equipment_supplement(
            [
                {
                    "id": "RUS",
                    "military_ballistic_missile_submarines_quantity_2001": "15",
                }
            ],
            [{**base, "field": "military_count"}],
        )
