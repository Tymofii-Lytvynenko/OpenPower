"""Check sourced FAOSTAT land candidates without importing them into runtime data."""
import csv
import io
import math
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/base/data/sources/2001"
ARCHIVE = DATA / "faostat_land_use_2026.zip"
CANDIDATES = DATA / "faostat_land_metrics_candidates_2001.tsv"


def _source_rows():
    with zipfile.ZipFile(ARCHIVE) as archive:
        text = io.TextIOWrapper(
            archive.open("Inputs_LandUse_E_All_Data_(Normalized).csv"),
            encoding="utf-8-sig",
        )
        rows = csv.DictReader(text)
        return {
            (row["Area Code (M49)"].strip("'"), row["Item"]): row
            for row in rows
            if row["Year"] == "2001" and row["Element"] == "Area"
        }


def test_candidate_rows_match_faostat_2001_archive_and_calculations():
    source_rows = _source_rows()
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as stream:
        candidates = list(csv.DictReader(stream, delimiter="\t"))

    keys = [(row["country_id"], row["field"]) for row in candidates]
    assert len(keys) == len(set(keys)) == 7
    assert sum(row["status"] == "imported_to_historical_country_table" for row in candidates) == 5
    assert sum(row["status"] == "candidate_not_imported" for row in candidates) == 1
    assert sum(row["status"] == "comparison_only_currently_populated" for row in candidates) == 1
    with (ROOT / "modules/base/data/countries/countries_historical.tsv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        historical = {row["id"]: row for row in csv.DictReader(stream, delimiter="\t")}
    tuvalu = historical["TUV"]
    assert tuvalu["forest_area_pct_available"] == "True"
    assert math.isclose(float(tuvalu["forest_area_pct"]), 34.333333333333336)
    imported = [row for row in candidates if row["status"] == "imported_to_historical_country_table"]
    for row in imported:
        assert historical[row["country_id"]][f"{row['field']}_available"] == "True"
        assert math.isclose(
            float(historical[row["country_id"]][row["field"]]),
            float(row["candidate_value"]),
            rel_tol=0,
            abs_tol=1e-10,
        )
    assert {row["scenario_year"] for row in candidates} == {"2001"}
    assert {row["observation_year"] for row in candidates} == {"2001"}

    for row in candidates:
        source = source_rows[(row["source_country_m49"], row["source_item"])]
        assert float(source["Value"]) == float(row["source_value"])
        assert source["Unit"] == row["source_unit"]
        assert source["Flag"] == row["source_flag"]

        value = float(row["candidate_value"])
        if row["field"] == "reference_land_area_km2":
            assert math.isclose(value, float(source["Value"]) * 10, rel_tol=0, abs_tol=1e-9)
            continue

        denominator = source_rows[(row["source_country_m49"], row["denominator_item"])]
        assert float(denominator["Value"]) == float(row["denominator_value"])
        assert denominator["Unit"] == row["denominator_unit"]
        assert denominator["Flag"] == row["denominator_flag"]
        expected = float(source["Value"]) / float(denominator["Value"]) * 100
        assert math.isclose(value, expected, rel_tol=0, abs_tol=1e-10)
