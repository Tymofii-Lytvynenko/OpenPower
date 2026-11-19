"""Validate the supplemental land-metric research ledger for 2001."""
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = (
    ROOT
    / "modules/base/data/sources/2001/land_metric_research_candidates_2001.tsv"
)


def test_review_ledger_preserves_observation_years_and_dispositions():
    with LEDGER.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))

    assert len(rows) >= 15
    assert all(row["source_url"].startswith("https://") for row in rows)
    imported = {
        (row["country_id"], row["field"]): row
        for row in rows
        if row["disposition"].startswith("imported_")
    }
    assert set(imported) == {
        ("TWN", "reference_land_area_km2"),
        ("MCO", "arable_land_pct"),
        ("VAT", "arable_land_pct"),
        ("VAT", "forest_area_pct"),
        ("TWN", "forest_area_pct"),
        ("KOS", "forest_area_pct"),
    }
    assert all(row["current_field_available"] == "true" for row in imported.values())
    assert all(
        row["source_publication_year"] == "2001" and not row["observation_year"]
        for key, row in imported.items()
        if key not in {("TWN", "forest_area_pct"), ("KOS", "forest_area_pct")}
    )
    assert imported[("TWN", "forest_area_pct")]["source_publication_year"] == "2020"
    assert imported[("TWN", "forest_area_pct")]["observation_year"] == "2001"
    kosovo_forest = imported[("KOS", "forest_area_pct")]
    assert kosovo_forest["source_publication_year"] == "2018"
    assert kosovo_forest["observation_year"] == "2001"
    assert float(kosovo_forest["candidate_value"]) == 41.7
    assert "does not split Kosovo" in kosovo_forest["note"]

    taiwan_area = imported[("TWN", "reference_land_area_km2")]
    assert float(taiwan_area["candidate_value"]) == 32260
    assert "35980" in taiwan_area["note"] and "3720" in taiwan_area["note"]

    comparisons = {
        (row["country_id"], row["field"], row["source_item"]): row
        for row in rows
        if row["disposition"].startswith("comparison_only_")
    }
    tuvalu_forest = comparisons[
        ("TUV", "forest_area_pct", "Land use - forests and woodland")
    ]
    assert tuvalu_forest["observation_year"] == "1993"
    assert tuvalu_forest["current_field_available"] == "true"
    assert math.isclose(float(tuvalu_forest["current_value"]), 34.333333333333336)

    nauru_arable = comparisons[("NRU", "arable_land_pct", "Land use - arable land")]
    assert nauru_arable["observation_year"] == "1993"
    assert nauru_arable["current_field_available"] == "false"

    taiwan_forest = imported[("TWN", "forest_area_pct")]
    expected_forest_share = 2101719 / (36188.04 * 100) * 100
    assert taiwan_forest["observation_year"] == "2001"
    assert math.isclose(
        float(taiwan_forest["candidate_value"]), expected_forest_share, abs_tol=1e-12
    )


def test_2001_yugoslavia_park_rows_keep_montenegro_and_kosovo_scopes_distinct():
    with LEDGER.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))

    keyed = {(row["country_id"], row["field"]): row for row in rows}
    montenegro = keyed[("MNE", "national_park_area_all_surface_km2_2001")]
    serbia = keyed[("SRB", "national_park_area_all_surface_km2_2001")]
    serbia_area = keyed[("SRB", "reference_total_area_km2")]
    kosovo_area = keyed[("KOS", "reference_total_area_km2")]

    assert float(montenegro["candidate_value"]) == 908
    assert montenegro["observation_year"] == "2001"
    assert "land_water_not_separated" in montenegro["disposition"]

    assert float(serbia["candidate_value"]) == 1596
    assert "srb_kos_overlap" in serbia["disposition"]
    assert "Sharr" in serbia["note"]

    assert float(serbia_area["candidate_value"]) == 88361
    assert float(kosovo_area["candidate_value"]) == 10887
    assert "includes_kosovo" in serbia_area["disposition"]
    assert "overlap" in kosovo_area["disposition"]
