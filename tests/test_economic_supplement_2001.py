import csv
import json

import pytest

from src.client.ui.panels.historical_economic_baseline import (
    historical_economic_tooltip,
)
from src.server.io.static_loader import StaticAssetLoader
from utils.import_economic_supplement_2001 import (
    COUNTRY_EXTENSION_PATH,
    DATA_DIR,
    LEDGER_COLUMNS,
    PROVENANCE_COLUMN,
    read_country_ids,
    read_supplement_records,
    write_country_extension,
)


def test_supplement_ledger_has_exact_year_observations_and_direct_sources():
    country_ids = read_country_ids()
    records = read_supplement_records(country_ids)

    assert len(country_ids) == 209
    assert sum(len(country_records) for country_records in records.values()) == 15
    assert (
        records["PRK"]["historical_gdp_snaama_current_usd_2001"]["value"] == 11021860465
    )
    assert (
        records["PRK"]["historical_gdp_per_capita_snaama_current_usd_2001"]["value"]
        == 476
    )
    assert (
        records["AND"]["historical_cpi_inflation_source_supplement_pct_2001"]["value"]
        == 2.77
    )
    assert (
        records["CUB"]["historical_cpi_inflation_source_supplement_pct_2001"]["value"]
        == -0.5
    )
    assert (
        records["MHL"]["historical_cpi_inflation_source_supplement_pct_2001"]["value"]
        == 1.8
    )
    assert (
        records["DMA"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 11
    )
    assert (
        records["KOS"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 57.1
    )
    assert (
        records["TWN"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 4.57
    )
    assert (
        records["LIE"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 1.2
    )
    assert (
        records["SMR"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 2.92
    )
    assert (
        records["MCO"]["historical_unemployment_reported_supplement_pct_2001"]["value"]
        == 2.45
    )

    for country_records in records.values():
        for observation in country_records.values():
            provenance = observation["provenance"]
            assert provenance["scenario_year"] == 2001
            assert provenance["observation_year"] == 2001
            assert provenance["source_url"].startswith("https://")
            assert provenance["source_release"]
            assert provenance["source_note"]


def test_country_extension_preserves_alternate_series_and_explicit_gaps(tmp_path):
    country_ids = read_country_ids()
    records = read_supplement_records(country_ids)
    output_path = tmp_path / COUNTRY_EXTENSION_PATH.name

    write_country_extension(country_ids, records, output_path)

    with output_path.open(encoding="utf-8", newline="") as stream:
        output_rows = list(csv.DictReader(stream, delimiter="\t"))
    rows = {row["id"]: row for row in output_rows}
    columns = output_rows[0].keys()

    assert len(output_rows) == len(country_ids)
    assert PROVENANCE_COLUMN in columns
    assert "historical_unemployment_modeled_ilo_pct_2001" not in columns
    assert "historical_unemployment_imf_weo_pct_2001" not in columns
    assert "historical_gdp_current_usd_2001" not in columns
    assert rows["PRK"]["historical_gdp_snaama_current_usd_2001"] == "11021860465"
    assert rows["PRK"]["historical_gdp_snaama_current_usd_2001_available"] == "true"
    assert rows["CUB"]["historical_cpi_inflation_source_supplement_pct_2001"] == "-0.5"
    assert rows["MHL"]["historical_cpi_inflation_source_supplement_pct_2001"] == "1.8"
    assert rows["KOS"]["historical_unemployment_reported_supplement_pct_2001"] == "57.1"
    assert rows["LIE"]["historical_unemployment_reported_supplement_pct_2001"] == "1.2"
    assert rows["SMR"]["historical_unemployment_reported_supplement_pct_2001"] == "2.92"
    assert rows["MCO"]["historical_unemployment_reported_supplement_pct_2001"] == "2.45"
    assert (
        rows["KOS"]["historical_unemployment_reported_supplement_pct_2001_available"]
        == "true"
    )
    assert rows["ZWE"]["historical_unemployment_reported_supplement_pct_2001"] == ""
    assert (
        rows["ZWE"]["historical_unemployment_reported_supplement_pct_2001_available"]
        == "false"
    )

    provenance = json.loads(rows["KOS"][PROVENANCE_COLUMN])
    assert (
        provenance["historical_unemployment_reported_supplement_pct_2001"][
            "observation_year"
        ]
        == 2001
    )
    assert (
        "Statistical Yearbook"
        in provenance["historical_unemployment_reported_supplement_pct_2001"][
            "source_release"
        ]
    )


def test_importer_rejects_neighbor_year_substitutions(tmp_path):
    ledger_path = tmp_path / "invalid.tsv"
    row = {
        "country_id": "PRK",
        "field": "historical_gdp_snaama_current_usd_2001",
        "scenario_year": "2001",
        "observation_year": "2000",
        "value": "100",
        "unit": "current US$",
        "series_id": "test series",
        "source_name": "test source",
        "source_release": "test release",
        "source_url": "https://example.test/source",
        "source_note": "test note",
    }
    with ledger_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=LEDGER_COLUMNS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(ValueError, match="Only exact 2001 observations"):
        read_supplement_records(["PRK"], ledger_path)


def test_static_loader_merges_supplement_as_independent_country_columns():
    class DataConfig:
        def get_data_dirs(self):
            return [DATA_DIR]

    countries = StaticAssetLoader(DataConfig())._load_countries()
    row = countries.filter(countries.get_column("id") == "PRK").to_dicts()[0]
    kos_row = countries.filter(countries.get_column("id") == "KOS").to_dicts()[0]

    assert row["historical_gdp_snaama_current_usd_2001"] == 11021860465
    assert (
        str(row["historical_gdp_snaama_current_usd_2001_available"]).lower() == "true"
    )
    assert kos_row["historical_unemployment_reported_supplement_pct_2001"] == 57.1
    assert "historical_gdp_current_usd_2001" in row


def test_new_source_supplements_are_visible_with_their_distinct_definitions():
    class DataConfig:
        def get_data_dirs(self):
            return [DATA_DIR]

    countries = StaticAssetLoader(DataConfig())._load_countries()
    mhl = countries.filter(countries.get_column("id") == "MHL")
    lie = countries.filter(countries.get_column("id") == "LIE")
    smr = countries.filter(countries.get_column("id") == "SMR")
    mco = countries.filter(countries.get_column("id") == "MCO")

    mhl_tooltip = historical_economic_tooltip(
        mhl,
        "historical_inflation_cpi_pct_2001",
        "0.5%",
        "inflation rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )
    assert "Alternative historical observation (Reported CPI inflation" in mhl_tooltip
    assert "1.8 % fiscal-year change" in mhl_tooltip
    assert "FY2001 (fiscal year ending September 30)" in mhl_tooltip
    assert "below 1%" in mhl_tooltip

    lie_unemployment_tooltip = historical_economic_tooltip(
        lie,
        "historical_unemployment_modeled_ilo_pct_2001",
        "0.5%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )
    assert "1.2 % of employees, registered unemployed at year-end" in lie_unemployment_tooltip
    assert "different denominator and coverage" in lie_unemployment_tooltip

    smr_unemployment_tooltip = historical_economic_tooltip(
        smr,
        "historical_unemployment_modeled_ilo_pct_2001",
        "0.5%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )
    assert "2.92 % annual average" in smr_unemployment_tooltip
    assert "separate strict-unemployment rate is 1.21%" in smr_unemployment_tooltip

    mco_unemployment_tooltip = historical_economic_tooltip(
        mco,
        "historical_unemployment_modeled_ilo_pct_2001",
        "0.5%",
        "unemployment rate",
        value_formatter=lambda value: f"{value:.1f}%",
    )
    assert "2.45 % on 1 January" in mco_unemployment_tooltip
    assert "cross-border job seekers" in mco_unemployment_tooltip
    assert "resident-only unemployment estimate" in mco_unemployment_tooltip
