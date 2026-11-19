from __future__ import annotations

import csv
from pathlib import Path

from utils.generate_military_inventory_2001 import generate_inventory_rows
from utils.import_military_personnel_supplement_2001 import apply_personnel_supplement

ROOT = Path(__file__).resolve().parents[1]
MILITARY_PATH = ROOT / "modules" / "base" / "data" / "countries" / "countries_mil.tsv"
SUPPLEMENT_PATH = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_personnel_supplemental_2001.tsv"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def _supplement(country_id: str, value: str, observation_year: str = "2001") -> dict[str, str]:
    return {
        "country_id": country_id,
        "field": "military_count",
        "scenario_year": "2001",
        "observation_year": observation_year,
        "value": value,
        "evidence_kind": "contemporary_force_status",
        "confidence": "moderate",
        "source_name": "Test source",
        "publication_year": "2001",
        "source_reference": "Test source, 2001",
        "source_url": "https://example.org/source",
        "source_scope": "Active military personnel",
        "method": "Direct reported count",
        "source_note": "A test observation.",
    }


def test_source_backed_personnel_counts_match_the_2001_scenario_rows() -> None:
    military = {row["id"]: row for row in _read_tsv(MILITARY_PATH)}
    supplements = _read_tsv(SUPPLEMENT_PATH)

    expected = {
        "AND": "0", "BTN": "6000", "CIV": "14000", "COM": "1070", "DMA": "0", "FSM": "0",
        "GRD": "0", "KIR": "0", "KNA": "0", "LCA": "0", "LIE": "0",
        "MDV": "5000", "MHL": "0", "NRU": "0", "PLW": "0", "STP": "1000",
        "SWZ": "2700", "TLS": "941", "TUV": "0", "TWN": "400000", "VAT": "106",
        "VCT": "0", "WSM": "0",
        "TON": "390", "VUT": "256",
    }
    assert {row["country_id"]: row["value"] for row in supplements} == expected
    assert all(row["scenario_year"] == "2001" for row in supplements)
    assert all(row["observation_year"] and row["publication_year"] for row in supplements)
    assert all(row["source_scope"] and row["method"] and row["source_note"] for row in supplements)
    assert all(military[row["country_id"]][row["field"]] == row["value"] for row in supplements)
    assert all(
        int(military[country_id]["military_infantry_quantity_2001"])
        <= int(military[country_id]["military_count"])
        for country_id in ("CIV", "SWZ", "TLS", "TON", "VUT")
    )
    assert len(supplements) == 25
    assert sum(row["observation_year"] == "2001" for row in supplements) == 17
    assert sum(row["observation_year"] == "2002" for row in supplements) == 5
    assert sum(row["observation_year"] == "2000" for row in supplements) == 2
    assert sum(row["observation_year"] == "1999" for row in supplements) == 1
    target_gaps = {
        "AFG", "AND", "ATA", "BTN", "CIV", "COM", "DMA", "FSM", "GRD", "KIR",
        "KNA", "KOS", "LCA", "LIE", "MCO", "MDV", "MHL", "MNE", "NRU", "PLW",
        "PSE", "SLB", "SMR", "SOM", "SSD", "STP", "SWZ", "TLS", "TUV", "TWN",
        "VAT", "VCT", "WSM", "PRI",
    }
    assert target_gaps - (set(expected) & target_gaps) == {
        "AFG", "ATA", "KOS", "MCO", "MNE", "PSE", "SLB", "SMR", "SOM", "SSD", "PRI",
    }


def test_supplement_updates_personnel_without_rewriting_role_inventory() -> None:
    rows = [
        {"id": "TON", "military_count": "500", "military_infantry_quantity_2001": "500"},
        {"id": "VUT", "military_count": "300", "military_infantry_quantity_2001": "300"},
    ]
    supplements = [_supplement("TON", "390", "2002"), _supplement("VUT", "256", "2002")]

    updated = apply_personnel_supplement(rows, supplements)

    assert [(row["military_count"], row["military_infantry_quantity_2001"]) for row in updated] == [
        ("390", "500"),
        ("256", "300"),
    ]
    assert rows[0]["military_count"] == "500"


def test_supplement_rejects_missing_attribution_and_duplicate_country_fields() -> None:
    row = {"id": "TON", "military_count": "500"}
    valid = _supplement("TON", "390", "2002")

    try:
        apply_personnel_supplement([row], [{**valid, "source_url": ""}])
    except ValueError as exc:
        assert "missing source attribution" in str(exc)
    else:
        raise AssertionError("A military supplement without a source URL must be rejected.")

    try:
        apply_personnel_supplement([row], [{**valid, "source_scope": ""}])
    except ValueError as exc:
        assert "missing source attribution" in str(exc)
    else:
        raise AssertionError("A military supplement without source scope must be rejected.")

    try:
        apply_personnel_supplement([row], [{**valid, "observation_year": "unknown"}])
    except ValueError as exc:
        assert "four-digit observation_year" in str(exc)
    else:
        raise AssertionError("A military supplement without an observation year must be rejected.")

    try:
        apply_personnel_supplement([row], [valid, valid])
    except ValueError as exc:
        assert "Duplicate military personnel supplement" in str(exc)
    else:
        raise AssertionError("Duplicate military personnel supplements must be rejected.")


def test_focused_generation_only_rewrites_selected_countries() -> None:
    rows = [
        {"id": "TON", "military_count": "390", "military_infantry_quantity_2001": "500"},
        {"id": "VUT", "military_count": "256", "military_infantry_quantity_2001": "300"},
        {"id": "BTN", "military_count": "6000", "military_infantry_quantity_2001": "5739"},
    ]

    updated = generate_inventory_rows(rows, {"TON": 0.693, "VUT": 0.568, "BTN": 0.607}, {"TON", "VUT"})

    assert updated[0]["military_infantry_quantity_2001"] == "390"
    assert updated[1]["military_infantry_quantity_2001"] == "256"
    assert updated[2] == rows[2]
