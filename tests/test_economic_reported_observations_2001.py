from __future__ import annotations

import csv
import json

import pytest

from utils.import_economic_reported_observations_2001 import (
    LEDGER_COLUMNS,
    read_country_ids,
    read_source_records,
    write_country_extension,
)


def test_economic_reported_observations_preserve_source_year_and_scope():
    records = read_source_records(read_country_ids())

    assert records["SMR"]["historical_cpi_staff_estimate_pct_2001"]["value"] == 3.3
    assert (
        records["AFG"]["historical_cpi_kabul_yoy_pct_fy2001_02"]["provenance"][
            "observation_year"
        ]
        == "2001-02"
    )
    assert records["KIR"]["historical_unemployment_census_pct_2000"]["value"] == 1.6
    assert (
        records["TUV"]["historical_unemployment_census_pct_2002"]["provenance"]["unit"]
        == "% of labour force, residents aged 15+"
    )
    assert (
        len([record for country in records.values() for record in country.values()])
        == 9
    )


def test_economic_reported_extension_has_full_roster_and_explicit_availability(
    tmp_path,
):
    country_ids = read_country_ids()
    records = read_source_records(country_ids)
    output_path = tmp_path / "countries_economic_reported_observations_2001.tsv"

    write_country_extension(country_ids, records, output_path)

    with output_path.open(encoding="utf-8", newline="") as stream:
        rows = {row["id"]: row for row in csv.DictReader(stream, delimiter="\t")}
    assert set(rows) == set(country_ids)
    assert rows["SMR"]["historical_cpi_staff_estimate_pct_2001_available"] == "true"
    assert rows["ATA"]["historical_cpi_staff_estimate_pct_2001_available"] == "false"
    assert rows["ATA"]["historical_cpi_staff_estimate_pct_2001"] == ""
    provenance = json.loads(
        rows["SMR"]["historical_economic_reported_observation_provenance_json"]
    )
    assert (
        provenance["historical_cpi_staff_estimate_pct_2001"]["observation_year"]
        == "2001"
    )


def test_economic_reported_importer_rejects_duplicate_observations(tmp_path):
    source_path = tmp_path / "duplicate.tsv"
    row = {
        "country_id": "SMR",
        "field": "historical_cpi_staff_estimate_pct_2001",
        "scenario_year": "2001",
        "observation_period": "calendar year 2001",
        "observation_year": "2001",
        "value": "3.3",
        "unit": "% annual average",
        "series_id": "CPI",
        "source_name": "IMF",
        "source_release": "2001 report",
        "source_url": "https://example.org/source.pdf",
        "source_note": "A test source record.",
    }
    with source_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LEDGER_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)
        writer.writerow(row)

    with pytest.raises(ValueError, match="Duplicate"):
        read_source_records(read_country_ids(), source_path)
