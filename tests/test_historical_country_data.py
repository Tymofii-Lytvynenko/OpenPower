"""Regression checks for historically dated scenario inputs and missing-data semantics."""
import csv
import json
import math
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import tomllib

from src.client.ui.panels.country_more_info import (
    CountryMoreInfoPanel,
    CountryMoreInfoPresenter,
)
from utils.import_historical_country_data import (
    apply_land_metric_supplements,
    apply_wdi_observations,
    factbook_land_metric_supplement_records,
    faostat_land_use_records,
    historical_land_metric_supplement_records,
    human_development_backfills,
    map_unsd_protected_area_records,
    national_land_metric_supplement_records,
    observations,
    parse_undp_records,
    parse_unsd_protected_area_records,
)

DATA = Path(__file__).resolve().parents[1] / "modules/base/data"


def read_rows(path):
    with path.open(encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_historical_observations_are_dated_and_country_specific():
    rows = read_rows(DATA / "countries/countries_historical.tsv")
    assert len(rows) == len({row["id"] for row in rows}) == 199
    assert {row["reference_year"] for row in rows} == {"2001"}
    assert len({row["birth_rate"] for row in rows if row["birth_rate"]}) > 150
    demographics = read_rows(DATA / "countries/countries_dem.tsv")
    assert len({row["fertility_rate"] for row in demographics}) > 150
    assert len({row["life_expectancy"] for row in demographics}) > 150


def test_wdi_xkx_observations_map_to_kos_without_filling_null_area_values():
    cases = {
        "SP.DYN.TFRT.IN": ("fertility_rate", 2.765),
        "SP.DYN.LE00.IN": ("life_expectancy", 71.782),
        "SP.DYN.CBRT.IN": ("birth_rate", 18.58),
        "SP.DYN.CDRT.IN": ("death_rate", 5.59),
    }
    countries = {"KOS": {"id": "KOS"}}
    provenance = []
    for indicator, (field, expected_value) in cases.items():
        source_records = [
            record for record in observations(indicator)
            if record["countryiso3code"] == "XKX" and record["date"] == "2001"
        ]
        assert len(source_records) == 1
        provenance.extend(apply_wdi_observations(countries, field, indicator, source_records))
        assert countries["KOS"][field] == expected_value

    by_field = {record["field"]: record for record in provenance}
    for indicator, (field, _) in cases.items():
        assert by_field[field]["source"] == indicator
        assert by_field[field]["observation_year"] == 2001
        assert by_field[field]["source_scope"] == "Kosovo"
        assert "XKX mapped to game country ID KOS" in by_field[field]["source_note"]

    imported_kos = next(
        row for row in read_rows(DATA / "countries/countries_historical.tsv")
        if row["id"] == "KOS"
    )
    imported_provenance = json.loads(imported_kos["historical_metric_provenance_json"])
    for field, expected_value in (
        ("birth_rate", 18.58),
        ("death_rate", 5.59),
        ("fertility_rate", 2.765),
        ("life_expectancy", 71.782),
    ):
        assert float(imported_kos[field]) == expected_value
        assert imported_provenance[field]["observation_year"] == 2001
        assert "XKX mapped to game country ID KOS" in imported_provenance[field]["source_note"]

    for indicator, field in (
        ("AG.LND.ARBL.ZS", "arable_land_pct"),
        ("AG.LND.FRST.ZS", "forest_area_pct"),
        ("AG.LND.TOTL.K2", "reference_land_area_km2"),
        ("AG.SRF.TOTL.K2", "reference_total_area_km2"),
    ):
        source_records = [
            record for record in observations(indicator)
            if record["countryiso3code"] == "XKX" and record["date"] == "2001"
        ]
        assert len(source_records) == 1 and source_records[0]["value"] is None
        assert apply_wdi_observations(countries, field, indicator, source_records) == []
        assert field not in countries["KOS"]


def test_history_baseline_fields_keep_field_level_source_and_availability():
    rows = read_rows(DATA / "countries/countries_historical.tsv")
    fields = (
        "birth_rate", "death_rate", "fertility_rate", "life_expectancy", "arable_land_pct",
        "forest_area_pct", "reference_land_area_km2", "reference_total_area_km2",
        "reference_water_area_km2", "national_park_land_area_km2_2001",
        "national_park_land_coverage_pct_2001", "other_land_pct", "reference_human_dev",
        "reference_life_expectancy", "expected_years_schooling", "mean_years_schooling",
        "gross_national_income_per_capita_ppp", "terrestrial_protected_area_pct_2000",
        "historical_poverty_rate_pct", "climate_description",
    )

    for row in rows:
        provenance = json.loads(row["historical_metric_provenance_json"])
        for field in fields:
            available = row[f"{field}_available"].lower() == "true"
            assert available == (field in provenance), (row["id"], field)
            if not available:
                continue
            source = provenance[field]
            assert source["year"] == 2001
            assert source["source"]
            assert source["url"]

    usa = next(row for row in rows if row["id"] == "USA")
    usa_provenance = json.loads(usa["historical_metric_provenance_json"])
    assert usa_provenance["birth_rate"]["observation_year"] == 2001
    assert usa_provenance["terrestrial_protected_area_pct_2000"]["observation_year"] == 2000
    montenegro = next(row for row in rows if row["id"] == "MNE")
    montenegro_provenance = json.loads(montenegro["historical_metric_provenance_json"])
    assert montenegro["reference_water_area_km2_available"] == "True"
    assert montenegro_provenance["reference_water_area_km2"]["observation_year"] == 2000
    assert montenegro_provenance["reference_water_area_km2"]["source"].startswith("FAO Global Forest")


def test_missing_poverty_values_use_only_exact_2001_wdi_fallbacks():
    historical = {
        row["id"]: row for row in read_rows(DATA / "countries/countries_historical.tsv")
    }
    provenance_rows = read_rows(DATA / "sources/2001/provenance.tsv")
    wdi_rows = {
        row["id"]: row for row in provenance_rows
        if row["field"] == "historical_poverty_rate_pct" and row["source"] == "SI.POV.NAHC"
    }
    assert set(wdi_rows) == {"CPV", "TLS", "UZB"}
    for code, value in {"CPV": 56.8, "TLS": 36.3, "UZB": 27.5}.items():
        row = historical[code]
        record = json.loads(row["historical_metric_provenance_json"])["historical_poverty_rate_pct"]
        assert float(row["historical_poverty_rate_pct"]) == value
        assert row["historical_poverty_rate_year"] == "2001"
        assert record["source"] == "SI.POV.NAHC"
        assert record["observation_year"] == 2001
        assert "not comparable across countries" in record["source_note"]
        assert "SI.POV.NAHC?date=2001" in record["url"]
        assert wdi_rows[code]["observation_year"] == "2001"


def test_supplemental_climate_context_retains_scope_and_document_year():
    historical = {
        row["id"]: row for row in read_rows(DATA / "countries/countries_historical.tsv")
    }
    expected_years = {"KOS": 2007, "MNE": 2001, "SRB": 2001, "SSD": 2001, "TLS": 2000}
    for code, source_year in expected_years.items():
        row = historical[code]
        record = json.loads(row["historical_metric_provenance_json"])["climate_description"]
        assert row["climate_description_available"] == "True"
        assert row["climate_description"]
        assert record["year"] == 2001
        assert record["observation_year"] is None
        assert record["source_year"] == source_year
        assert record["source_scope"]
        assert record["url"]
    assert "proxy" in json.loads(
        historical["MNE"]["historical_metric_provenance_json"]
    )["climate_description"]["source_note"].lower()
    assert "1999" in json.loads(
        historical["KOS"]["historical_metric_provenance_json"]
    )["climate_description"]["source_note"]


def test_country_info_tooltips_distinguish_climate_context_and_wdi_poverty_source():
    poverty_record = {
        "year": 2001,
        "observation_year": 2001,
        "source": "SI.POV.NAHC",
        "source_note": "Exact 2001 national poverty headcount ratio.",
        "url": "https://api.worldbank.org/v2/country/all/indicator/SI.POV.NAHC?date=2001",
    }
    model = SimpleNamespace(historical_metrics={
        "historical_poverty_rate_pct": 56.8,
        "historical_poverty_rate_year": 2001,
        "historical_metric_provenance_json": json.dumps({
            "historical_poverty_rate_pct": poverty_record,
        }),
    })
    poverty_tooltip = CountryMoreInfoPanel()._historical_demographics_tooltip(model)
    assert "observation year 2001" in poverty_tooltip
    assert "SI.POV.NAHC" in poverty_tooltip
    assert "not cross-country comparable" in poverty_tooltip

    climate_record = {
        "year": 2001,
        "observation_year": None,
        "source": "CIA World Factbook 2001",
        "source_year": 2001,
        "source_scope": "Federal Republic of Yugoslavia territory; proxy rather than a separate national entry",
        "source_note": "Territory proxy for Serbia and Montenegro; not a 2001 weather observation.",
        "url": "https://www.gutenberg.org/ebooks/27638",
    }
    climate_model = SimpleNamespace(historical_metrics={
        "historical_metric_provenance_json": json.dumps({"climate_description": climate_record}),
    })
    climate_tooltip = CountryMoreInfoPanel._climate_context_tooltip(climate_model)
    assert "territory or regional proxy" in climate_tooltip
    assert "Source document/edition year: 2001" in climate_tooltip


def test_country_info_labels_modeled_pip_poverty_as_a_gameplay_estimate():
    prefix = "gameplay_poverty_estimate_3usd_2021_ppp"
    model = SimpleNamespace(
        historical_metrics={
            f"{prefix}_pct": 42.7,
            f"{prefix}_pct_available": True,
            f"{prefix}_type": "gameplay_model",
            f"{prefix}_confidence": "low",
            f"{prefix}_method": "Weighted nearest-neighbor estimate.",
            f"{prefix}_training_observation_count": 46,
            f"{prefix}_nearest_training_ids": "KEN,UGA,TZA,ETH,RWA",
            f"{prefix}_hdi_input_2001": 0.55,
            f"{prefix}_hdi_input_quality": "UNDP HDR 2025 retrospective series",
            f"{prefix}_gni_per_capita_ppp_current_intl_dollars_2001": 1800,
            f"{prefix}_source_note": "Scenario-only output, not a survey result.",
            f"{prefix}_source_urls": "https://api.worldbank.org/pip/v1/pip",
            "historical_poverty_global_3usd_2021_ppp_pct_available": False,
            "historical_poverty_global_3usd_2021_ppp_unavailable_note": (
                "no exact-year national survey record available"
            ),
        }
    )

    tooltip = CountryMoreInfoPanel()._historical_demographics_tooltip(model)

    assert "PIP $3/day (2021 PPP) poverty headcount: unavailable" in tooltip
    assert "OpenPower gameplay estimate" in tooltip
    assert "42.70% (confidence low; not a survey result or national-line estimate)" in tooltip
    assert "46 exact-year" not in tooltip
    assert "nearest source records: KEN,UGA,TZA,ETH,RWA" in tooltip
    assert "Scenario-only output, not a survey result." in tooltip
    assert "Model input sources: https://api.worldbank.org/pip/v1/pip" in tooltip


def test_population_extension_has_one_record_per_master_region():
    regions = read_rows(DATA / "regions/regions.tsv")
    population = read_rows(DATA / "regions/regions_pop.tsv")
    assert len(population) == len({row["hex"] for row in population})
    assert {row["hex"] for row in population} == {row["hex"] for row in regions}
    owners = {row["hex"]: row["owner"] for row in regions}
    for row in population:
        if row["hex"] in {"#7BA9D9", "#F5AE97"}:
            assert row["_owner"] == owners[row["hex"]]


def test_explicit_missing_observation_survives_numeric_null_normalization():
    state = SimpleNamespace(tables={"countries": pl.DataFrame([
        {"id": "AAA", "birth_rate": 0.0, "birth_rate_available": False,
         "death_rate": 0.0, "death_rate_available": True},
    ])})
    model = CountryMoreInfoPresenter().build(state, "AAA")
    panel = CountryMoreInfoPanel()
    assert panel._historical_rate(model, "birth_rate") == "—"
    assert panel._historical_rate(model, "death_rate") == "0.00 ‰"


def test_reference_geography_keeps_historical_boundaries_separate_from_control():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{"id": "AAA", "reference_total_area_km2": 120.0}]),
        "regions": pl.DataFrame([{"id": 1, "owner": "AAA", "area_km2": 30.0}]),
    })
    model = CountryMoreInfoPresenter().build(state, "AAA")
    assert model.land_area_km2 == 30.0
    assert CountryMoreInfoPanel()._historical_area(model, "reference_total_area_km2") == "120"


def test_official_world_aggregate_is_used_instead_of_country_average():
    with (DATA / "world/historical_world_indicators.toml").open("rb") as stream:
        rows = tomllib.load(stream)["historical_world_indicators"]
    state = SimpleNamespace(tables={
        "historical_world_indicators": pl.from_dicts(rows),
        "countries": pl.DataFrame([{"id": "AAA", "human_dev": 0.9}]),
    })
    model = CountryMoreInfoPresenter().build(state, "AAA")
    assert model.human_dev_pct == 90
    assert model.world_human_dev_pct == 65.7
    assert model.world_human_dev_year == 2001
    for invalid in (float("nan"), 1.1, None):
        state.tables["historical_world_indicators"] = pl.DataFrame([
            {"id": "WLD", "year": 2001, "reference_human_dev": invalid},
        ])
        assert CountryMoreInfoPresenter().build(state, "AAA").world_human_dev_pct is None


def test_undp_parser_selects_2001_and_preserves_unavailable_values():
    payload = b"iso3,hdi_2000,hdi_2001,hdi_2002,le_2001\nAAA,0.6,0.7,0.8,65\nBBB,0.8,,0.9,..\nCCC,0.8,nan,0.9,inf\n"
    records = parse_undp_records(payload)
    assert records["AAA"] == {"reference_human_dev": 0.7, "reference_life_expectancy": 65.0}
    assert records["BBB"] == records["CCC"] == {}


def test_scenario_hdi_matches_dated_source_and_availability_flags():
    records = parse_undp_records((DATA / "sources/2001/undp_hdr2025.csv").read_bytes())
    backfills = human_development_backfills()
    demographics = {row["id"]: row for row in read_rows(DATA / "countries/countries_dem.tsv")}
    historical = {row["id"]: row for row in read_rows(DATA / "countries/countries_historical.tsv")}
    official_count = 0
    available_count = 0
    for code, row in demographics.items():
        value = records.get(code, {}).get("reference_human_dev")
        if value is not None:
            assert float(row["human_dev"]) == value
            assert historical[code]["reference_human_dev_status"] == "official_undp_hdr2025"
            official_count += 1
            expected_value = value
        else:
            backfill = backfills[code]
            assert float(row["human_dev"]) == backfill["simulation_value"]
            assert historical[code]["reference_human_dev_status"] == backfill["status"]
            expected_value = backfill["value"]
        assert historical[code]["reference_human_dev_available"] == str(expected_value is not None)
        if expected_value is not None:
            assert float(historical[code]["reference_human_dev"]) == expected_value
            available_count += 1
    assert official_count == 170
    assert available_count == 197


def test_country_hdi_ui_distinguishes_legacy_scores_and_neutral_fallbacks():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([
            {
                "id": "ATG", "human_dev": 0.798,
                "reference_human_dev": 0.798, "reference_human_dev_available": True,
                "reference_human_dev_status": "official_legacy_method",
                "reference_human_dev_method": "Published UNDP HDI for 2001.",
            },
            {
                "id": "VAT", "human_dev": 0.5,
                "reference_human_dev_available": False,
                "reference_human_dev_status": "not_reported",
                "reference_human_dev_method": "No official 2001 value is available.",
            },
        ]),
        "regions": pl.DataFrame(),
    })
    panel = CountryMoreInfoPanel()

    class RecordingWidgets:
        def __init__(self):
            self.texts = {}
            self.meters = {}

        def text(self, path, value, **kwargs):
            self.texts[path] = (value, kwargs)

        def meter(self, path, value, *args, **kwargs):
            self.meters[path] = value

        @staticmethod
        def path(value):
            return value

    state.tables["countries"] = state.tables["countries"].filter(pl.col("id") == "ATG")
    atg_model = CountryMoreInfoPresenter().build(state, "ATG")
    widgets = RecordingWidgets()
    panel._render_human_development_frame(widgets, atg_model)
    value, options = widgets.texts["frmHumanDevelopment/frmInner/lblCountry"]
    assert value == "Antigua and Barbuda: 79.8 %"
    assert "older HDR 2003 method" in options["tooltip"]
    assert widgets.meters["frmHumanDevelopment/frmInner/picCountry"] == 0.798

    state.tables["countries"] = pl.DataFrame([
        {
            "id": "VAT", "human_dev": 0.5,
            "reference_human_dev_available": False,
            "reference_human_dev_status": "not_reported",
            "reference_human_dev_method": "No official 2001 value is available.",
        },
    ])
    vat_model = CountryMoreInfoPresenter().build(state, "VAT")
    widgets = RecordingWidgets()
    panel._render_human_development_frame(widgets, vat_model)
    value, options = widgets.texts["frmHumanDevelopment/frmInner/lblCountry"]
    assert value == "Holy See (Vatican City State): —"
    assert "neutral 0.50 fallback" in options["tooltip"]
    assert widgets.meters["frmHumanDevelopment/frmInner/picCountry"] == 0.0


def test_unsd_parser_selects_the_2000_proportion_column():
    payload = b"""<table>
    <tr><th>Country</th><th>1990</th><th>2000</th><th>2009</th></tr>
    <tr><td></td><td>Ukraine</td><td><div>1.8</div></td><td><div>3.5</div></td><td><div>3.5</div></td></tr>
    <tr><td></td><td>Missing</td><td><div>..</div></td><td><div>..</div></td><td><div>..</div></td></tr>
    </table>"""
    records = parse_unsd_protected_area_records(payload)
    assert records == {"Ukraine": 3.5}


def test_unsd_aliases_map_to_game_country_codes_without_guessing():
    records = map_unsd_protected_area_records(
        {
            "Cape Verde": 2.5,
            "Korea, Dem. People's Rep.": 3.9,
            "Dem. Rep. of the Congo": 10.0,
            "Not a country": 42.0,
        },
        {"CPV", "PRK", "COD"},
    )
    assert records == {
        "CPV": ("Cape Verde", 2.5),
        "PRK": ("Korea, Dem. People's Rep.", 3.9),
        "COD": ("Dem. Rep. of the Congo", 10.0),
    }


def test_protected_area_data_retains_its_2000_year_and_country_availability():
    source_rows = read_rows(DATA / "sources/2001/unsd_terrestrial_protected_areas_2010.tsv")
    park_evidence = read_rows(DATA / "sources/2001/national_park_terrestrial_2001_evidence.tsv")
    assert len(source_rows) == len({row["id"] for row in source_rows})
    assert len(source_rows) >= 180
    source_by_code = {row["id"]: row for row in source_rows}
    override_by_code = {
        row["id"]: row for row in park_evidence
        if row["terrestrial_protected_area_pct_2000_override"].strip()
    }
    assert source_by_code["UKR"]["terrestrial_protected_area_pct_2000"] == "3.5"
    assert source_by_code["USA"]["terrestrial_protected_area_pct_2000"] == "14.8"

    historical = {
        row["id"]: row for row in read_rows(DATA / "countries/countries_historical.tsv")
    }
    for code, row in historical.items():
        expected_available = code in source_by_code or code in override_by_code
        assert row["terrestrial_protected_area_pct_2000_available"] == str(expected_available)
        if expected_available:
            expected_value = (
                source_by_code[code]["terrestrial_protected_area_pct_2000"]
                if code in source_by_code
                else override_by_code[code]["terrestrial_protected_area_pct_2000_override"]
            )
            assert float(row["terrestrial_protected_area_pct_2000"]) == float(
                expected_value
            )

    assert historical["MDV"]["terrestrial_protected_area_pct_2000"] == "0.0"
    assert "not a direct unsd observation" in historical["MDV"]["terrestrial_protected_area_method"].lower()
    assert historical["NRU"]["terrestrial_protected_area_pct_2000_available"] == "True"
    assert float(historical["NRU"]["terrestrial_protected_area_pct_2000"]) == 0.0
    assert historical["NRU"]["terrestrial_protected_area_source"].startswith("Pacific Community")
    assert "April 2000" in historical["NRU"]["terrestrial_protected_area_method"]
    for code, expected in {
        "KOS": (390.0, 3.5823),
        "STP": (0.0, 0.0),
    }.items():
        assert historical[code]["terrestrial_protected_area_pct_2000_available"] == "False"
        assert historical[code]["national_park_land_area_km2_2001_available"] == "True"
        assert float(historical[code]["national_park_land_area_km2_2001"]) == expected[0]
        assert float(historical[code]["national_park_land_coverage_pct_2001"]) == expected[1]

    taiwan = historical["TWN"]
    assert taiwan["terrestrial_protected_area_pct_2000_available"] == "True"
    assert float(taiwan["terrestrial_protected_area_pct_2000"]) == 18.7
    assert taiwan["terrestrial_protected_area_source"].startswith("Republic of China")
    assert "excludes maritime area" in taiwan["terrestrial_protected_area_method"]
    assert float(taiwan["national_park_land_area_km2_2001"]) == 3076.59
    assert float(taiwan["national_park_land_coverage_pct_2001"]) == 8.5017

    assert historical["MNE"]["terrestrial_protected_area_pct_2000_available"] == "True"
    assert historical["MNE"]["national_park_land_area_km2_2001_available"] == "True"
    assert float(historical["MNE"]["national_park_land_area_km2_2001"]) == 538.3
    assert float(historical["MNE"]["national_park_land_coverage_pct_2001"]) == 4.0022
    assert "lower bound" in historical["MNE"]["national_park_notes"].lower()
    assert historical["MNE"]["national_park_status"] == (
        "park_only_inference_conservative_lower_bound_from_2001_stats"
    )

    nauru = historical["NRU"]
    assert nauru["national_park_land_area_km2_2001_available"] == "True"
    assert nauru["national_park_land_coverage_pct_2001_available"] == "True"
    assert float(nauru["national_park_land_area_km2_2001"]) == 0.0
    assert float(nauru["national_park_land_coverage_pct_2001"]) == 0.0
    assert nauru["national_park_status"] == "reported_zero_in_2000_environmental_inventory"

    provenance = read_rows(DATA / "sources/2001/provenance.tsv")
    ukraine_source = next(
        row for row in provenance
        if row["id"] == "UKR" and row["field"] == "terrestrial_protected_area_pct_2000"
    )
    nauru_source = next(
        row for row in provenance
        if row["id"] == "NRU" and row["field"] == "terrestrial_protected_area_pct_2000"
    )
    taiwan_source = next(
        row for row in provenance
        if row["id"] == "TWN" and row["field"] == "terrestrial_protected_area_pct_2000"
    )
    assert ukraine_source["year"] == "2001"
    assert ukraine_source["observation_year"] == "2000"
    assert "not national-parks-only" in ukraine_source["source_note"]
    assert nauru_source["observation_year"] == "2000"
    assert "reported_zero_in_2000_environmental_inventory" in nauru_source["source_note"]
    assert taiwan_source["observation_year"] == "2000"
    assert "Statistical Yearbook 2009, Table 69" in taiwan_source["source_note"]


def test_palestinian_natural_reserve_observations_keep_their_year_and_scope():
    rows = read_rows(DATA / "sources/2001/palestinian_natural_reserves_2001_candidate.tsv")
    by_year = {row["observation_year"]: row for row in rows}

    assert by_year["2000"]["value"] == "54.4"
    assert by_year["2000"]["precision"] == "0.1 km2, PCBS-reported"
    assert "Palestinian National Authority" in by_year["2000"]["coverage_limit"]
    assert by_year["2001"]["value"] == "54"
    assert by_year["2001"]["precision"] == "approximate"
    assert "unchanged" in by_year["2001"]["handling_note"]
    pse = next(
        row for row in read_rows(DATA / "countries/countries_historical.tsv") if row["id"] == "PSE"
    )
    assert pse["terrestrial_protected_area_pct_2000_available"] == "False"
    assert not pse["terrestrial_protected_area_pct_2000"]


def test_country_info_labels_and_discloses_the_protected_area_proxy():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{
            "id": "UKR",
            "terrestrial_protected_area_pct_2000": 3.5,
            "terrestrial_protected_area_pct_2000_available": True,
        }]),
        "regions": pl.DataFrame(),
    })
    model = CountryMoreInfoPresenter().build(state, "UKR")

    class RecordingWidgets:
        def __init__(self):
            self.texts = {}

        def picture(self, *args, **kwargs):
            return None

        def meter(self, *args, **kwargs):
            return None

        def text(self, path, value, **kwargs):
            self.texts[path] = (value, kwargs)

    widgets = RecordingWidgets()
    CountryMoreInfoPanel()._render_land_frame(widgets, model)
    assert widgets.texts["frmLand/lblNationalParks"][0] == "Protected areas (2000)"
    value, options = widgets.texts["frmLand/txtNationalParks"]
    assert value == "3.5 %"
    assert "protection categories beyond national parks" in options["tooltip"]
    assert "unstats.un.org" in options["tooltip"]


def test_country_info_shows_park_only_value_when_broad_total_is_unavailable():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{
            "id": "TWN",
            "national_park_land_area_km2_2001": 3076.59,
            "national_park_land_area_km2_2001_available": True,
            "national_park_land_coverage_pct_2001": 8.5017,
            "national_park_land_coverage_pct_2001_available": True,
            "national_park_status": "official_2001_inventory_sum",
            "national_park_source_url": "https://example.test/parks-2001.pdf",
            "national_park_denominator_source_url": "https://example.test/area-2001.pdf",
            "national_park_notes": "Six official national parks; marine area excluded.",
            "terrestrial_protected_area_pct_2000_available": False,
        }]),
        "regions": pl.DataFrame(),
    })
    model = CountryMoreInfoPresenter().build(state, "TWN")

    class RecordingWidgets:
        def __init__(self):
            self.texts = {}

        def picture(self, *args, **kwargs):
            return None

        def meter(self, *args, **kwargs):
            return None

        def text(self, path, value, **kwargs):
            self.texts[path] = (value, kwargs)

    widgets = RecordingWidgets()
    CountryMoreInfoPanel()._render_land_frame(widgets, model)
    assert widgets.texts["frmLand/lblNationalParks"][0] == "National parks (2001)"
    value, options = widgets.texts["frmLand/txtNationalParks"]
    assert value == "8.5 %"
    assert "Six official national parks" in options["tooltip"]
    assert "not the broader UNSD protected-area share" in options["tooltip"]


def test_faostat_other_land_is_dated_flagged_and_not_called_unusable():
    records = faostat_land_use_records({"AFG", "CHN", "SDN", "MNE", "SSD", "KOS"})
    assert records["AFG"]["source_country_name"] == "Afghanistan"
    assert records["AFG"]["other_land_flag"] in {"A", "E", "I", "X"}
    assert records["AFG"]["other_land_flag_description"]
    assert 0 <= records["AFG"]["other_land_pct"] <= 100
    assert "CHN" in records
    assert "SDN" in records
    assert not ({"MNE", "SSD", "KOS"} & records.keys())


def test_land_metric_supplements_fill_only_reviewed_gaps_and_keep_observation_years():
    country_ids = {"SDN", "TWN", "VAT", "MNE"}
    source_rows = historical_land_metric_supplement_records(country_ids)
    assert len(source_rows) == 8
    countries = {code: {"id": code} for code in country_ids}
    countries["TWN"]["arable_land_pct"] = 12.0

    provenance = apply_land_metric_supplements(countries, source_rows)
    by_key = {(row["id"], row["field"]): row for row in provenance}
    assert len(provenance) == 7
    assert countries["TWN"]["arable_land_pct"] == 12.0
    assert math.isclose(countries["SDN"]["arable_land_pct"], 6.892255892255893)
    assert math.isclose(countries["SDN"]["forest_area_pct"], 14.005117845117846)
    assert math.isclose(countries["SDN"]["reference_land_area_km2"], 2376000)
    assert math.isclose(countries["VAT"]["reference_land_area_km2"], 0.44)
    assert math.isclose(countries["MNE"]["reference_land_area_km2"], 13450)
    assert math.isclose(countries["MNE"]["reference_water_area_km2"], 360)
    assert by_key[("MNE", "forest_area_pct")]["observation_year"] == 2000
    assert "one-year-earlier" in by_key[("MNE", "forest_area_pct")]["source_note"]
    assert apply_land_metric_supplements(countries, source_rows) == []


def test_factbook_land_metrics_keep_unknown_observation_year_as_null_provenance():
    country_ids = {"KOS", "MCO", "VAT", "TWN"}
    source_rows = factbook_land_metric_supplement_records(country_ids)
    assert len(source_rows) == 5

    countries = {code: {"id": code} for code in country_ids}
    provenance = apply_land_metric_supplements(countries, source_rows)
    by_key = {(row["id"], row["field"]): row for row in provenance}

    assert countries["MCO"]["arable_land_pct"] == 0
    assert countries["VAT"]["arable_land_pct"] == 0
    assert countries["VAT"]["forest_area_pct"] == 0
    assert countries["TWN"]["reference_land_area_km2"] == 32260
    assert countries["KOS"]["forest_area_pct"] == 41.7
    assert by_key[("KOS", "forest_area_pct")]["observation_year"] == 2001
    assert by_key[("KOS", "forest_area_pct")]["source_year"] == 2018
    assert all(
        row["observation_year"] is None
        for key, row in by_key.items()
        if key != ("KOS", "forest_area_pct")
    )
    assert all(
        row["source_year"] == 2001
        for key, row in by_key.items()
        if key != ("KOS", "forest_area_pct")
    )
    assert "observation year" in by_key[("VAT", "forest_area_pct")]["source_note"]


def test_national_land_metric_supplements_keep_actual_years_and_scopes():
    source_rows = national_land_metric_supplement_records({"KOS", "MNE", "TWN"})
    assert len(source_rows) == 3

    countries = {code: {"id": code} for code in {"KOS", "MNE", "TWN"}}
    provenance = apply_land_metric_supplements(countries, source_rows)
    by_key = {(row["id"], row["field"]): row for row in provenance}

    assert math.isclose(countries["KOS"]["arable_land_pct"], 27.3261688252044)
    assert by_key[("KOS", "arable_land_pct")]["observation_year"] == 2000
    assert "297.5 thousand hectares" in by_key[("KOS", "arable_land_pct")]["source_note"]
    assert math.isclose(countries["MNE"]["arable_land_pct"], 3.522825278810409)
    assert by_key[("MNE", "arable_land_pct")]["observation_year"] == 2001
    assert "plough-land and gardens" in by_key[("MNE", "arable_land_pct")]["source_note"]
    assert math.isclose(countries["TWN"]["forest_area_pct"], 58.07772402152755)
    assert by_key[("TWN", "forest_area_pct")]["observation_year"] == 2001
    assert "national forest-land measure" in by_key[("TWN", "forest_area_pct")]["source_note"]


def test_arable_and_forest_tooltips_show_field_level_source_and_quality_note():
    model = SimpleNamespace(historical_metrics={
        "historical_metric_provenance_json": json.dumps({
            "arable_land_pct": {
                "source": "FAOSTAT Land Use (RL)",
                "observation_year": 2001,
                "source_year": 2026,
                "source_scope": "Sudan (former), M49 736",
                "source_note": "Numerator flag I: imputed by the receiving agency.",
                "url": "https://www.fao.org/faostat/en/#data/RL",
            }
        })
    })
    tooltip = CountryMoreInfoPanel._land_metric_tooltip(model, "arable_land_pct")
    assert "FAOSTAT Land Use (RL)" in tooltip
    assert "observation year 2001" in tooltip
    assert "imputed by the receiving agency" in tooltip
    assert "publication or release year: 2026" in tooltip


def test_country_info_labels_other_land_and_exposes_faostat_quality_flag():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{
            "id": "AFG",
            "other_land_pct": 40.2,
            "other_land_pct_available": True,
            "other_land_source_flag": "I",
            "other_land_source_flag_description": "Value imputed by a receiving agency",
        }]),
        "regions": pl.DataFrame(),
    })
    model = CountryMoreInfoPresenter().build(state, "AFG")

    class RecordingWidgets:
        def __init__(self):
            self.texts = {}

        def picture(self, *args, **kwargs):
            return None

        def meter(self, *args, **kwargs):
            return None

        def text(self, path, value, **kwargs):
            self.texts[path] = (value, kwargs)

    widgets = RecordingWidgets()
    CountryMoreInfoPanel()._render_land_frame(widgets, model)
    assert widgets.texts["frmLand/lblUnusable"][0] == "Other land (2001)"
    value, options = widgets.texts["frmLand/txtUnusable"]
    assert value == "40.2 %"
    assert "not a measure of land that cannot be used" in options["tooltip"]
    assert "quality flag I: Value imputed by a receiving agency" in options["tooltip"]
