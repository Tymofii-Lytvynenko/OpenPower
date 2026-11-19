import csv
import json
from pathlib import Path

import pytest

from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.import_development_supplement_2001 import (
    FIELD_SPECS,
    _parse_barrolee,
    _parse_wdi,
    build_records,
)

DATA = Path(__file__).resolve().parents[1] / "modules/base/data"
ROOT = Path(__file__).resolve().parents[1]


def _read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_wdi_parser_keeps_only_exact_year_values_and_rejects_mixed_year_payload():
    payload = json.dumps(
        [
            {"page": 1, "pages": 1},
            [
                {"countryiso3code": "TWN", "date": "2001", "value": 11.2},
                {"countryiso3code": "MCO", "date": "2001", "value": None},
            ],
        ]
    ).encode()

    assert _parse_wdi(payload) == {"TWN": 11.2}

    wrong_year = json.dumps(
        [
            {"page": 1, "pages": 1},
            [{"countryiso3code": "TWN", "date": "2000", "value": 11.2}],
        ]
    ).encode()
    with pytest.raises(ValueError, match="unexpected date"):
        _parse_wdi(wrong_year)


def test_barrolee_parser_selects_2000_both_sexes_population_15_plus():
    payload = (
        "WBcode,year,sex,agefrom,ageto,yr_sch\n"
        "TWN,2000,MF,15,999,9.58\n"
        "TWN,2000,MF,25,999,8.21\n"
        "TWN,2005,MF,15,999,10.00\n"
        "TWN,2000,MA,15,999,9.40\n"
    ).encode()

    assert _parse_barrolee(payload) == {"TWN": 9.58}
    assert _parse_barrolee(payload, age_from=25) == {"TWN": 8.21}


def test_supplement_fills_only_missing_primary_baselines_and_keeps_other_definitions_separate():
    rows = build_records(
        {"TWN", "MDA"},
        {
            "TWN": {
                "expected_years_schooling_available": "False",
                "gross_national_income_per_capita_ppp_available": "True",
                "mean_years_schooling_available": "False",
            },
            "MDA": {
                "expected_years_schooling_available": "False",
                "gross_national_income_per_capita_ppp_available": "False",
                "mean_years_schooling_available": "True",
            },
        },
        {"TWN": 11.3, "MDA": 11.2},
        {"TWN": 41000.0, "MDA": 22000.0},
        {"TWN": 9.58, "MDA": 7.5},
        {"TWN": 8.95, "MDA": 7.1},
    )
    by_id = {row["id"]: row for row in rows}
    school_field = "historical_school_life_expectancy_wdi_years_2001"
    gni_field = "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001"
    mean_field = "historical_mean_schooling_barrolee_years_population_15plus_2000"
    mean_25plus_field = "historical_mean_schooling_barrolee_years_population_25plus_2000"

    assert by_id["TWN"][school_field] == 11.3
    assert by_id["TWN"][school_field + "_available"] is True
    assert by_id["TWN"][gni_field] == ""
    assert by_id["TWN"][gni_field + "_available"] is False
    assert by_id["TWN"][mean_field] == 9.58
    assert by_id["TWN"][mean_field + "_observation_year"] == 2000
    assert by_id["TWN"][mean_25plus_field] == 8.95
    assert by_id["TWN"][mean_25plus_field + "_available"] is True
    assert by_id["TWN"][mean_25plus_field + "_source_scope"] == (
        "Total population aged 25 and over; both sexes."
    )
    assert by_id["MDA"][school_field] == 11.2
    assert by_id["MDA"][gni_field] == 22000.0
    assert by_id["MDA"][mean_field] == ""
    assert "separately" in FIELD_SPECS[school_field]["note"]
    assert "current international-dollar" in FIELD_SPECS[gni_field]["note"].lower()


def test_generated_data_fills_only_supported_2001_baseline_gaps():
    baseline = {
        row["id"]: row
        for row in _read_rows(DATA / "countries/countries_historical.tsv")
    }
    supplement = {
        row["id"]: row
        for row in _read_rows(
            DATA / "countries/countries_development_supplement_2001.tsv"
        )
    }
    expected = {
        "historical_school_life_expectancy_wdi_years_2001": {
            "KIR": "11.73747",
            "MDA": "11.27671",
            "SYC": "11.73897",
        },
        "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001": {
            "NRU": "6700.0",
            "PRI": "15840.0",
            "SDN": "2670.0",
        },
        "historical_mean_schooling_barrolee_years_population_15plus_2000": {
            "TWN": "9.58",
        },
        "historical_mean_schooling_barrolee_years_population_25plus_2000": {
            "TWN": "8.95",
        },
    }

    for field, values in expected.items():
        available = {
            country_id
            for country_id, row in supplement.items()
            if row[f"{field}_available"] == "True"
        }
        assert available == set(values)
        for country_id, value in values.items():
            assert supplement[country_id][field] == value
            assert baseline[country_id][_primary_field(field) + "_available"] == "False"
            assert supplement[country_id][f"{field}_source_url"].startswith("https://")
            assert supplement[country_id][f"{field}_observation_year"] in {
                "2000",
                "2001",
            }


def _primary_field(supplement_field):
    return {
        "historical_school_life_expectancy_wdi_years_2001": "expected_years_schooling",
        "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001": "gross_national_income_per_capita_ppp",
        "historical_mean_schooling_barrolee_years_population_15plus_2000": "mean_years_schooling",
        "historical_mean_schooling_barrolee_years_population_25plus_2000": "mean_years_schooling",
    }[supplement_field]


def test_static_country_loader_merges_the_development_supplement():
    countries = StaticAssetLoader(GameConfig(ROOT))._load_countries()

    kir = countries.filter(countries["id"] == "KIR").row(0, named=True)
    twn = countries.filter(countries["id"] == "TWN").row(0, named=True)
    assert kir["historical_school_life_expectancy_wdi_years_2001"] == pytest.approx(
        11.73747
    )
    assert kir["historical_school_life_expectancy_wdi_years_2001_available"] is True
    assert twn[
        "historical_mean_schooling_barrolee_years_population_15plus_2000"
    ] == pytest.approx(9.58)
    assert (
        twn[
            "historical_mean_schooling_barrolee_years_population_15plus_2000_observation_year"
        ]
        == 2000
    )
    assert twn[
        "historical_mean_schooling_barrolee_years_population_25plus_2000"
    ] == pytest.approx(8.95)
    assert (
        twn[
            "historical_mean_schooling_barrolee_years_population_25plus_2000_observation_year"
        ]
        == 2000
    )
