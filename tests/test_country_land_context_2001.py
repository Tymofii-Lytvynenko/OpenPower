from pathlib import Path
from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.country_more_info import CountryMoreInfoPanel
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from utils.generate_palestinian_reserve_context_2001 import (
    OUTPUT_PATH,
    build_rows,
    render_tsv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manual_country_values_fill_only_unavailable_land_fields():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    rows = {row["id"]: row for row in countries.to_dicts()}

    for country_id, field, expected in (
        ("NRU", "arable_land_pct", 0.0),
        ("SRB", "forest_area_pct", 27.0),
        ("SSD", "reference_total_area_km2", 644329.0),
        ("KOS", "other_land_pct", 5.5),
        ("TWN", "other_land_pct", 15.0),
        ("VAT", "reference_human_dev", 0.88),
        ("ATA", "birth_rate", 0.0),
        ("PSE", "terrestrial_protected_area_pct_2000", 2.0),
    ):
        model = SimpleNamespace(historical_metrics=rows[country_id])
        assert CountryMoreInfoPanel._historical_value(model, field) == expected

    model = SimpleNamespace(historical_metrics={
        "arable_land_pct": 12.0,
        "arable_land_pct_available": True,
        "countryinfo_scenario_values_2001_json": '{"arable_land_pct":99}',
    })
    assert CountryMoreInfoPanel._historical_value(model, "arable_land_pct") == 12.0

    vatican = SimpleNamespace(historical_metrics=rows["VAT"])
    assert "unavailable" not in CountryMoreInfoPanel._country_hdi_tooltip(vatican).lower()


def test_land_extensions_merge_without_multiplying_country_rows():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    montenegro = countries.filter(pl.col("id") == "MNE").row(0, named=True)
    serbia = countries.filter(pl.col("id") == "SRB").row(0, named=True)
    taiwan = countries.filter(pl.col("id") == "TWN").row(0, named=True)
    kosovo = countries.filter(pl.col("id") == "KOS").row(0, named=True)
    palestine = countries.filter(pl.col("id") == "PSE").row(0, named=True)

    assert countries.height == 209
    assert montenegro["scenario_other_land_2001_available"] is True
    assert montenegro["scenario_other_land_2001_pct"] == 21.1279
    assert serbia["scenario_other_land_2001_pct"] == 13.0418
    assert "including Kosovo" in serbia["scenario_other_land_2001_scope"]
    assert taiwan["scenario_other_land_2001_available"] is False
    assert taiwan["scenario_cia_land_use_other_2001_pct"] == 15.0
    assert kosovo["scenario_other_land_2001_available"] is False
    assert kosovo["scenario_cia_land_use_other_2001_pct"] == 5.5
    assert palestine["countryinfo_pna_west_bank_natural_reserves_2000_area_km2"] == 54.4
    assert palestine["countryinfo_pna_west_bank_natural_reserves_2001_area_km2"] == 54.0


def test_other_land_estimates_are_fallbacks_and_keep_their_provenance():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    montenegro = countries.filter(pl.col("id") == "MNE").row(0, named=True)
    taiwan = countries.filter(pl.col("id") == "TWN").row(0, named=True)
    direct = countries.filter(pl.col("id") == "FRA").row(0, named=True)

    estimate_model = SimpleNamespace(historical_metrics=montenegro)
    value, label = CountryMoreInfoPanel._other_land_display_value(
        estimate_model, None, "Other land (2001)"
    )
    assert value == 21.1279
    assert label == "Other land estimate"
    estimate_tooltip = CountryMoreInfoPanel._other_land_tooltip(estimate_model)
    assert "Low-confidence Other land scenario estimate" in estimate_tooltip
    assert "Land and forest: 2000" in estimate_tooltip
    assert "Montenegro national territory" in estimate_tooltip

    direct_model = SimpleNamespace(historical_metrics=direct)
    value, label = CountryMoreInfoPanel._other_land_display_value(
        direct_model,
        CountryMoreInfoPanel._historical_value(direct_model, "other_land_pct"),
        "Other land (2001)",
    )
    assert value is not None
    assert label == "Other land (2001)"

    taiwan_model = SimpleNamespace(historical_metrics=taiwan)
    value, label = CountryMoreInfoPanel._other_land_display_value(
        taiwan_model, None, "Other land (2001)"
    )
    assert value is None
    assert label == "Other land (2001)"
    taiwan_tooltip = CountryMoreInfoPanel._other_land_tooltip(taiwan_model)
    assert "CIA Factbook 2001 `other` category: 15.0000%" in taiwan_tooltip
    assert "not comparable to FAOSTAT Other land" in taiwan_tooltip

    kosovo_model = SimpleNamespace(
        historical_metrics=countries.filter(pl.col("id") == "KOS").row(0, named=True)
    )
    value, label = CountryMoreInfoPanel._other_land_display_value(
        kosovo_model, None, "Other land (2001)"
    )
    assert value is None
    assert label == "Other land (2001)"
    kosovo_tooltip = CountryMoreInfoPanel._other_land_tooltip(kosovo_model)
    assert "CIA Factbook 2001 `other` category: 5.5000%" in kosovo_tooltip
    assert "not comparable to FAOSTAT Other land" in kosovo_tooltip
    assert "not a territorial split" in kosovo_tooltip


def test_palestinian_reserve_context_is_scoped_and_not_a_national_percentage():
    countries = StaticAssetLoader(GameConfig(REPO_ROOT))._load_countries()
    palestine = countries.filter(pl.col("id") == "PSE").row(0, named=True)
    model = SimpleNamespace(historical_metrics=palestine)

    tooltip = CountryMoreInfoPanel._protected_area_tooltip(model)

    assert "2000: 54.4 km²" in tooltip
    assert "2001: about 54 km²" in tooltip
    assert "PNA-controlled natural-reserves context" in tooltip
    assert "West Bank" in tooltip
    assert "not a national-park value" in tooltip
    assert "Gaza row is blank" in tooltip
    assert "Terrestrial protected area: 2.0%" in tooltip


def test_palestinian_reserve_extension_keeps_one_row_for_both_observation_years():
    rows = build_rows()
    assert len(rows) == 1
    assert rows[0]["id"] == "PSE"
    assert rows[0]["countryinfo_pna_west_bank_natural_reserves_2000_area_km2"] == "54.4"
    assert rows[0]["countryinfo_pna_west_bank_natural_reserves_2001_area_km2"] == "54"
    assert len(render_tsv(rows).splitlines()) == 2
    assert OUTPUT_PATH.read_text(encoding="utf-8") == render_tsv(rows)
