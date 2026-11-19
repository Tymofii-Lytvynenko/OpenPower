from pathlib import Path

import polars as pl

from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.generate_poverty_scenario_estimates_2001 import (
    OUTPUT_PATH,
    PIP_AVAILABLE,
    PIP_VALUE,
    _read_tsv,
    generate_rows,
    render_tsv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scenario_estimates_cover_only_missing_pip_rows_and_keep_nonapplicable_gaps():
    rows = generate_rows()
    pip_rows = {
        row["id"]: row
        for row in _read_tsv(
            OUTPUT_PATH.parents[0] / "countries_poverty_international_2001.tsv"
        )
    }
    country_rows = _read_tsv(OUTPUT_PATH.parents[0] / "countries.tsv")
    row_ids = {row["id"] for row in rows}

    assert len(country_rows) == 199
    assert len(rows) == 153
    assert row_ids.isdisjoint(
        country_id
        for country_id, row in pip_rows.items()
        if row[PIP_AVAILABLE].lower() == "true" and row[PIP_VALUE]
    )
    assert row_ids == {row["id"] for row in country_rows} - {
        country_id
        for country_id, row in pip_rows.items()
        if row[PIP_AVAILABLE].lower() == "true" and row[PIP_VALUE]
    }

    estimates = {row["id"]: row for row in rows}
    available = "gameplay_poverty_estimate_3usd_2021_ppp_pct_available"
    confidence = "gameplay_poverty_estimate_3usd_2021_ppp_confidence"
    source_note = "gameplay_poverty_estimate_3usd_2021_ppp_source_note"
    assert sum(row[available] == "true" for row in rows) == 151
    assert sum(row[available] == "false" for row in rows) == 2
    assert estimates["ATA"][available] == "false"
    assert estimates["ATA"][confidence] == "not_applicable"
    assert estimates["VAT"][available] == "false"
    assert estimates["VAT"][confidence] == "none"

    for row in rows:
        assert (
            row["gameplay_poverty_estimate_3usd_2021_ppp_line_usd_per_person_per_day"]
            == "3"
        )
        assert row["gameplay_poverty_estimate_3usd_2021_ppp_line_ppp_year"] == "2021"
        assert (
            row["gameplay_poverty_estimate_3usd_2021_ppp_training_observation_count"]
            == "46"
        )
        assert (
            "not a national poverty-line observation" in row[source_note]
            or row[available] == "false"
        )
        if row[available] == "true":
            value = float(row["gameplay_poverty_estimate_3usd_2021_ppp_pct"])
            assert 0 <= value <= 100
            assert (
                row["gameplay_poverty_estimate_3usd_2021_ppp_type"] == "gameplay_model"
            )
            assert row["gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_ids"]


def test_generated_tsv_is_deterministic_and_matches_checked_in_output():
    rows = generate_rows()
    expected = render_tsv(rows)

    assert OUTPUT_PATH.read_text(encoding="utf-8") == expected
    assert render_tsv(generate_rows()) == expected


def test_static_country_loader_keeps_scenario_estimate_fields_namespaced():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    afghanistan = countries.filter(pl.col("id") == "AFG").row(0, named=True)

    assert countries.height == 199
    assert not {"available", "scenario_year", "method", "confidence"}.intersection(
        countries.columns
    )
    assert afghanistan["gameplay_poverty_estimate_3usd_2021_ppp_pct"] > 0
    assert afghanistan["gameplay_poverty_estimate_3usd_2021_ppp_pct_available"] is True
    assert afghanistan["historical_poverty_global_3usd_2021_ppp_pct_available"] is False
