"""Validate staged supplementary land-metric evidence and calculations."""
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "modules/base/data/sources/2001/land_metrics_supplement_candidates_2001.tsv"


def test_supplement_ledger_preserves_scope_years_and_derived_values():
    with LEDGER.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))

    keyed = {(row["country_id"], row["field"]): row for row in rows}
    assert len(keyed) == len(rows) == 7
    assert all(
        "candidate" in row["status"] or "scope_review" in row["status"]
        or row["status"] in {
            "approved_for_import_adjacent_year",
            "approved_for_import_alternative_definition",
        }
        for row in rows
    )
    assert all(row["source_url"].startswith("https://") for row in rows)

    kos_area = keyed[("KOS", "reference_total_area_km2")]
    assert float(kos_area["candidate_value"]) == 10887
    assert kos_area["status"] == "scope_review_required_srb_contains_kosovo"

    assert float(keyed[("KOS", "arable_land_pct")]["candidate_value"]) == 27.4
    assert float(keyed[("KOS", "forest_area_pct")]["candidate_value"]) == 41.7

    mne_land = keyed[("MNE", "reference_land_area_km2")]
    assert math.isclose(float(mne_land["candidate_value"]), 13450)
    assert mne_land["observation_year"] == "2000"
    assert mne_land["status"] == "approved_for_import_adjacent_year"

    mne_water = keyed[("MNE", "reference_water_area_km2")]
    assert math.isclose(float(mne_water["candidate_value"]), 360)
    assert mne_water["observation_year"] == "2000"
    assert mne_water["status"] == "approved_for_import_adjacent_year"

    for field in ("forest_area_pct", "arable_land_pct"):
        row = keyed[("MNE", field)]
        expected = float(row["source_value"]) / float(row["denominator_value"]) * 100
        assert math.isclose(float(row["candidate_value"]), expected, rel_tol=0, abs_tol=1e-12)
    assert keyed[("MNE", "forest_area_pct")]["status"] == "approved_for_import_adjacent_year"
    assert keyed[("MNE", "arable_land_pct")]["status"] == "approved_for_import_alternative_definition"
