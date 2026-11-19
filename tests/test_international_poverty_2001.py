import csv
import json
from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.country_more_info import (
    CountryMoreInfoPanel,
    CountryMoreInfoPresenter,
)
from src.server.io.static_loader import StaticAssetLoader
from utils.import_international_poverty_2001 import (
    ALTERNATE_AVAILABILITY_FIELD,
    ALTERNATE_VALUE_FIELD,
    AVAILABILITY_FIELD,
    COUNTRY_EXTENSION_PATH,
    EXTENSION_COLUMNS,
    VALUE_FIELD,
    read_country_ids,
    read_survey_records,
    write_country_extension,
)


def test_pip_snapshot_keeps_only_exact_national_survey_records_and_alternates():
    country_ids = read_country_ids()
    records, unavailable_notes = read_survey_records(country_ids)

    assert len(country_ids) == 199
    assert len(records) == 46
    assert sum(1 + (alternate is not None) for _, alternate in records.values()) == 47
    assert records["ARM"][0]["headcount"] == 0.2414
    assert records["ARM"][0]["poverty_line"] == 3
    assert records["ARM"][0]["survey_year"] == 2001
    assert records["NIC"][0]["welfare_type"] == "consumption"
    assert records["NIC"][1]["welfare_type"] == "income"
    assert records["NIC"][1]["headcount"] == 0.2631
    assert records["MLI"][0]["survey_year"] == 2001.08
    assert "not listed" in unavailable_notes["AFG"]


def test_country_extension_keeps_explicit_gaps_and_loads_as_static_country_data(
    tmp_path,
):
    country_ids = read_country_ids()
    records, unavailable_notes = read_survey_records(country_ids)
    extension_path = tmp_path / "countries" / COUNTRY_EXTENSION_PATH.name
    extension_path.parent.mkdir(parents=True)
    output_path = tmp_path / "countries" / "countries.tsv"
    output_path.write_text(
        "id\tname\nARM\tArmenia\nNIC\tNicaragua\nAFG\tAfghanistan\n",
        encoding="utf-8",
    )

    write_country_extension(country_ids, records, unavailable_notes, extension_path)

    with extension_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    by_id = {row["id"]: row for row in rows}
    assert len(rows) == 199
    assert tuple(rows[0]) == EXTENSION_COLUMNS
    assert by_id["ARM"][AVAILABILITY_FIELD] == "true"
    assert by_id["ARM"][VALUE_FIELD] == "24.14"
    assert by_id["ARM"][f"{VALUE_FIELD}_survey_year"] == "2001"
    assert by_id["ARM"][f"{VALUE_FIELD}_poverty_line_usd_per_person_per_day"] == "3"
    assert by_id["ARM"][f"{VALUE_FIELD}_ppp_year"] == "2021"
    assert "not age-disaggregated" in by_id["ARM"][f"{VALUE_FIELD}_population_scope"]
    assert by_id["ARM"][f"{VALUE_FIELD}_source_version"] == "20260922_2021_01_02_PROD"
    assert by_id["NIC"][ALTERNATE_AVAILABILITY_FIELD] == "true"
    assert by_id["NIC"][ALTERNATE_VALUE_FIELD] == "26.31"
    assert by_id["AFG"][AVAILABILITY_FIELD] == "false"
    assert by_id["AFG"]["historical_poverty_global_3usd_2021_ppp_unavailable_note"]

    loader = StaticAssetLoader(SimpleNamespace(get_data_dirs=lambda: [tmp_path]))
    loaded = {row["id"]: row for row in loader._load_countries().to_dicts()}
    assert loaded["ARM"][VALUE_FIELD] == 24.14
    assert loaded["NIC"][ALTERNATE_VALUE_FIELD] == 26.31
    assert loaded["AFG"][AVAILABILITY_FIELD] is False


def _country_model(country_row):
    return CountryMoreInfoPresenter().build(
        SimpleNamespace(
            globals={},
            tables={"countries": pl.DataFrame([country_row])},
        ),
        str(country_row["id"]),
    )


def test_country_information_tooltips_keep_pip_development_and_area_sources_separate():
    pip_row = {
        "id": "NIC",
        "name": "Nicaragua",
        VALUE_FIELD: 29.43,
        AVAILABILITY_FIELD: True,
        f"{VALUE_FIELD}_survey_year": 2001.0,
        f"{VALUE_FIELD}_welfare_type": "consumption",
        f"{VALUE_FIELD}_survey_acronym": "EMNV",
        f"{VALUE_FIELD}_population_scope": "Population living in households; not age-disaggregated.",
        f"{VALUE_FIELD}_source_url": "https://api.worldbank.org/pip/v1/pip?country=NIC",
        ALTERNATE_VALUE_FIELD: 26.31,
        ALTERNATE_AVAILABILITY_FIELD: True,
        f"{ALTERNATE_VALUE_FIELD}_welfare_type": "income",
    }
    tooltip = CountryMoreInfoPanel()._historical_demographics_tooltip(
        _country_model(pip_row)
    )
    assert "$3/day (2021 PPP) poverty headcount: 29.43%" in tooltip
    assert "same survey using income" in tooltip
    assert "not age-disaggregated" in tooltip
    assert "separate from the country-specific national poverty line" in tooltip
    unavailable_tooltip = CountryMoreInfoPanel()._historical_demographics_tooltip(
        _country_model(
            {
                "id": "AFG",
                "name": "Afghanistan",
                "historical_poverty_global_3usd_2021_ppp_pct_available": False,
                "historical_poverty_global_3usd_2021_ppp_unavailable_note": (
                    "Game country code is not listed by the PIP API."
                ),
            }
        )
    )
    assert "Game country code is not listed by the PIP API" in unavailable_tooltip

    development_row = {
        "id": "KIR",
        "name": "Kiribati",
        "historical_school_life_expectancy_wdi_years_2001": 11.73747,
        "historical_school_life_expectancy_wdi_years_2001_available": True,
        "historical_school_life_expectancy_wdi_years_2001_observation_year": 2001,
        "historical_school_life_expectancy_wdi_years_2001_source": "World Bank WDI SE.SCH.LIFE",
        "historical_school_life_expectancy_wdi_years_2001_source_scope": "Primary through tertiary education; both sexes.",
        "historical_school_life_expectancy_wdi_years_2001_source_note": "Separate from UNDP expected years of schooling.",
        "historical_school_life_expectancy_wdi_years_2001_source_url": "https://api.worldbank.org/v2/country/all/indicator/SE.SCH.LIFE?date=2001",
        "historical_mean_schooling_barrolee_years_population_25plus_2000": 8.95,
        "historical_mean_schooling_barrolee_years_population_25plus_2000_available": True,
        "historical_mean_schooling_barrolee_years_population_25plus_2000_observation_year": 2000,
        "historical_mean_schooling_barrolee_years_population_25plus_2000_source": "Barro-Lee 2013 educational attainment dataset, version 2.2",
        "historical_mean_schooling_barrolee_years_population_25plus_2000_source_scope": "Total population aged 25 and over; both sexes.",
        "historical_mean_schooling_barrolee_years_population_25plus_2000_source_note": "Retrospective 2000 estimate; source series remains distinct.",
        "historical_mean_schooling_barrolee_years_population_25plus_2000_source_url": "https://barrolee.github.io/BarroLeeDataSet/BLData/BL2013_MF2599_v2.2.csv",
    }
    development_tooltip = CountryMoreInfoPanel()._development_supplement_tooltip(
        _country_model(development_row)
    )
    assert "School life expectancy (years): 11.74" in development_tooltip
    assert "Primary through tertiary education; both sexes." in development_tooltip
    assert "Separate from UNDP expected years of schooling." in development_tooltip
    assert "Mean schooling, ages 25+ (years): 8.95" in development_tooltip
    assert "observation year 2000" in development_tooltip
    assert "Total population aged 25 and over; both sexes." in development_tooltip

    national_line_tooltip = CountryMoreInfoPanel()._historical_demographics_tooltip(
        _country_model(
            {
                "id": "ETH",
                "name": "Ethiopia",
                "historical_national_poverty_supplement_pct": 44.2,
                "historical_national_poverty_supplement_available": True,
                "historical_national_poverty_supplement_reference_year": 1999,
                "historical_national_poverty_supplement_survey_period": "1999/2000",
                "historical_national_poverty_supplement_line_definition": "Government cost-of-basic-needs national line.",
                "historical_national_poverty_supplement_welfare_measure": "Total household consumption expenditure.",
                "historical_national_poverty_supplement_scope": "National population; urban and rural.",
                "historical_national_poverty_supplement_method": "Survey headcount.",
                "historical_national_poverty_supplement_source": "World Bank WDI SI.POV.NAHC; Ethiopia HICES",
                "historical_national_poverty_supplement_source_note": "Observation year 1999 maps to the 1999/2000 survey.",
                "historical_national_poverty_supplement_source_url": "https://documents1.worldbank.org/curated/en/683561468773953737/pdf/multi0page.pdf",
            }
        )
    )
    assert "National poverty-line alternative: 44.2%" in national_line_tooltip
    assert "observation year 1999; survey period 1999/2000" in national_line_tooltip
    assert "Government cost-of-basic-needs national line." in national_line_tooltip
    assert "Total household consumption expenditure." in national_line_tooltip
    assert "https://documents1.worldbank.org/curated/en/683561468773953737/pdf/multi0page.pdf" in national_line_tooltip


def test_water_and_total_area_tooltips_show_provenance_and_source_conflict():
    provenance = {
        "reference_land_area_km2": {
            "observation_year": 2001,
            "source": "AG.LND.TOTL.K2",
            "source_note": "World Bank observation dated 2001",
        },
        "reference_total_area_km2": {
            "observation_year": 2001,
            "source": "AG.SRF.TOTL.K2",
            "source_note": "World Bank observation dated 2001",
        },
        "reference_water_area_km2": {
            "observation_year": None,
            "source": "CIA Factbook 2001",
            "source_note": "CIA Factbook 2001 edition; estimate year not stated",
            "url": "https://www.gutenberg.org/ebooks/27638",
        },
    }
    model = _country_model(
        {
            "id": "UKR",
            "name": "Ukraine",
            "reference_land_area_km2": 579350,
            "reference_land_area_km2_available": True,
            "reference_total_area_km2": 603550,
            "reference_total_area_km2_available": True,
            "reference_water_area_km2": 0,
            "reference_water_area_km2_available": True,
            "historical_metric_provenance_json": json.dumps(provenance),
        }
    )
    panel = CountryMoreInfoPanel()

    water_tooltip = panel._historical_area_tooltip(model, "reference_water_area_km2")
    total_tooltip = panel._historical_area_tooltip(model, "reference_total_area_km2")

    assert "CIA Factbook 2001" in water_tooltip
    assert "observation year not stated" in water_tooltip
    assert (
        "WDI 2001 total surface (603 550 km²) minus WDI 2001 land (579 350 km²)"
        in water_tooltip
    )
    assert "24 200 km² of water" in water_tooltip
    assert "direct CIA Factbook value is 0 km²" in water_tooltip
    assert "retained without substitution" in water_tooltip
    assert "AG.SRF.TOTL.K2" in total_tooltip
    assert "observation year 2001" in total_tooltip
    assert "Related water-area source difference" in total_tooltip
    assert "both source records are preserved" in total_tooltip
