from pathlib import Path

import polars as pl

from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.generate_other_land_supplement_2001 import (
    OUTPUT_PATH,
    generate_rows,
    render_tsv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_only_reconciled_country_scopes_receive_faostat_style_other_land_estimates():
    rows = {row["id"]: row for row in generate_rows()}

    assert set(rows) == {"ATA", "KOS", "MNE", "SRB", "SSD", "TWN"}
    assert rows["MNE"]["scenario_other_land_2001_available"] == "true"
    assert rows["MNE"]["scenario_other_land_2001_area_ha"] == "284170"
    assert rows["MNE"]["scenario_other_land_2001_pct"] == "21.1279"
    assert rows["MNE"]["scenario_other_land_2001_quality"] == "low"

    assert rows["SRB"]["scenario_other_land_2001_available"] == "true"
    assert rows["SRB"]["scenario_other_land_2001_area_ha"] == "1154850"
    assert rows["SRB"]["scenario_other_land_2001_pct"] == "13.0418"
    assert "including Kosovo" in rows["SRB"]["scenario_other_land_2001_scope"]
    assert rows["SRB"]["scenario_other_land_2001_source_flag"] == "I-derived"

    assert rows["ATA"]["scenario_other_land_2001_status"] == "not_applicable"
    assert rows["KOS"]["scenario_other_land_2001_available"] == "false"
    assert rows["KOS"]["scenario_cia_land_use_other_2001_pct"] == "5.50"
    assert rows["KOS"]["scenario_cia_land_use_other_2001_available"] == "true"
    assert "not comparable" in rows["KOS"]["scenario_cia_land_use_other_2001_source_note"]
    assert rows["SSD"]["scenario_other_land_2001_available"] == "false"
    assert rows["TWN"]["scenario_other_land_2001_available"] == "false"
    assert rows["TWN"]["scenario_cia_land_use_other_2001_pct"] == "15.00"
    assert rows["TWN"]["scenario_cia_land_use_other_2001_available"] == "true"

    generic_columns = {"available", "scenario_year", "method", "confidence"}
    assert generic_columns.isdisjoint(rows["MNE"])


def test_extension_is_namespaced_and_merged_into_country_data():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    montenegro = countries.filter(pl.col("id") == "MNE").row(0, named=True)
    serbia = countries.filter(pl.col("id") == "SRB").row(0, named=True)
    taiwan = countries.filter(pl.col("id") == "TWN").row(0, named=True)
    kosovo = countries.filter(pl.col("id") == "KOS").row(0, named=True)

    assert countries.height == 199
    assert montenegro["scenario_other_land_2001_pct"] == 21.1279
    assert montenegro["scenario_other_land_2001_available"] is True
    assert serbia["scenario_other_land_2001_pct"] == 13.0418
    assert "including Kosovo" in serbia["scenario_other_land_2001_scope"]
    assert taiwan["scenario_other_land_2001_available"] is False
    assert taiwan["scenario_cia_land_use_other_2001_pct"] == 15.0
    assert kosovo["scenario_other_land_2001_available"] is False
    assert kosovo["scenario_cia_land_use_other_2001_pct"] == 5.5
    assert kosovo["scenario_cia_land_use_other_2001_available"] is True
    assert "not a territorial split" in kosovo["scenario_cia_land_use_other_2001_source_note"]
    assert not {"available", "scenario_year", "method", "confidence"}.intersection(
        countries.columns
    )


def test_generated_extension_is_deterministic():
    assert OUTPUT_PATH.read_text(encoding="utf-8") == render_tsv(generate_rows())
