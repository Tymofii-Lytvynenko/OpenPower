import json
from pathlib import Path

from src.client.ui.panels.historical_economic_baseline import (
    _COUNTRY_SCENARIO_KEYS,
    HISTORICAL_ECONOMIC_BASELINES,
    historical_economic_tooltip,
)
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig


def test_manual_economic_values_cover_missing_primary_fields():
    root = Path(__file__).resolve().parents[1]
    countries = StaticAssetLoader(GameConfig(root))._load_countries()
    for row in countries.to_dicts():
        manual = json.loads(row.get("countryinfo_economic_values_2001_json") or "{}")
        for field in HISTORICAL_ECONOMIC_BASELINES:
            if row.get(f"{field}_available") is False:
                assert _COUNTRY_SCENARIO_KEYS[field] in manual, (row["id"], field)
                tooltip = historical_economic_tooltip(row, field, "0", "value")
                assert "2001 baseline (" in tooltip
                assert "2001 historical baseline: unavailable" not in tooltip


def test_manual_economic_zero_and_source_priority():
    field = "historical_unemployment_modeled_ilo_pct_2001"
    row = {
        f"{field}_available": False,
        "countryinfo_economic_values_2001_json": '{"unemployment":0}',
    }
    assert ": 0." in historical_economic_tooltip(row, field, "0", "unemployment")
    row.update({field: 7.5, f"{field}_available": True})
    tooltip = historical_economic_tooltip(row, field, "0", "unemployment")
    assert "7.5" in tooltip
    assert "2001 baseline (" not in tooltip
