import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_DATA = ROOT / "modules/base/data/countries"
SUPPLEMENT_PATH = COUNTRY_DATA / "countries_poverty_national_supplement_2001.tsv"
PRIMARY_PATH = COUNTRY_DATA / "countries_historical.tsv"


def _rows_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            row["id"]: row
            for row in csv.DictReader(source, delimiter="\t")
        }


def test_national_poverty_supplement_has_unique_ids_and_provenance():
    with SUPPLEMENT_PATH.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))

    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))

    required_fields = (
        "historical_national_poverty_supplement_survey_period",
        "historical_national_poverty_supplement_line_definition",
        "historical_national_poverty_supplement_welfare_measure",
        "historical_national_poverty_supplement_scope",
        "historical_national_poverty_supplement_method",
        "historical_national_poverty_supplement_source",
        "historical_national_poverty_supplement_source_url",
        "historical_national_poverty_supplement_source_note",
    )
    for row in rows:
        assert row["historical_national_poverty_supplement_available"] == "True"
        assert row["historical_national_poverty_supplement_pct"]
        assert all(row[field] for field in required_fields)


def test_bih_and_civ_are_separate_survey_observations():
    supplement = _rows_by_id(SUPPLEMENT_PATH)
    primary = _rows_by_id(PRIMARY_PATH)

    bih = supplement["BIH"]
    assert bih["historical_national_poverty_supplement_pct"] == "19.5"
    assert bih["historical_national_poverty_supplement_reference_year"] == "2001"
    assert bih["historical_national_poverty_supplement_survey_period"] == (
        "2001-09-26 to 2001-11-23"
    )
    assert "2,198" in bih["historical_national_poverty_supplement_line_definition"]
    assert "Brčko was excluded" in bih["historical_national_poverty_supplement_scope"]
    assert "±3.6 percentage points" in bih[
        "historical_national_poverty_supplement_method"
    ]
    assert bih["historical_national_poverty_supplement_source_url"].endswith(
        "/25343.pdf"
    )

    civ = supplement["CIV"]
    assert civ["historical_national_poverty_supplement_pct"] == "38.4"
    assert civ["historical_national_poverty_supplement_reference_year"] == "2002"
    assert civ["historical_national_poverty_supplement_survey_period"].startswith(
        "2002 ENV"
    )
    assert "183,450" in civ["historical_national_poverty_supplement_line_definition"]
    assert "five detailed strata" in civ["historical_national_poverty_supplement_scope"]
    assert civ["historical_national_poverty_supplement_source_url"].endswith(
        "/catalog/19"
    )

    for country_id in ("BIH", "CIV"):
        assert primary[country_id]["historical_poverty_rate_pct"] == ""
        assert primary[country_id]["historical_poverty_rate_pct_available"] == "False"
