from types import SimpleNamespace

import polars as pl

from src.client.ui.components.hud.thematic_map_legend import ThematicMapLegend
from src.shared.state import GameState


def _legend(state, *, selected="UKR"):
    viewport = SimpleNamespace(
        selected_country_tag=selected,
        map_modes={},
    )
    return ThematicMapLegend(viewport)


def test_gradient_country_ranking_uses_same_region_source_as_map_mode():
    state = GameState(tables={
        "countries": pl.DataFrame([
            {"id": "UKR", "name": "Ukraine", "gdp": 900.0},
            {"id": "POL", "name": "Poland", "gdp": 100.0},
        ]),
        "regions": pl.DataFrame([
            {"id": 1, "owner": "UKR", "gdp": 100.0},
            {"id": 2, "owner": "POL", "gdp": 190.0},
            {"id": 3, "owner": "POL", "gdp": 210.0},
        ]),
        "countries_relations": pl.DataFrame([
            {"source": "UKR", "target": "POL", "value": 42.0},
        ]),
    })
    mode = SimpleNamespace(column_name="gdp", steps=10, use_percentile=True)

    rows = _legend(state)._ranked_countries(state, "UKR", "POL", mode)

    assert [row.tag for row in rows] == ["POL", "UKR"]
    assert rows[0].relation == 42.0
    assert rows[0].selected


def test_empire_list_uses_selected_country_and_active_military_allies():
    state = GameState(tables={
        "countries": pl.DataFrame([
            {"id": "UKR", "name": "Ukraine"},
            {"id": "POL", "name": "Poland"},
            {"id": "USA", "name": "United States"},
        ]),
        "countries_treaties": pl.DataFrame([
            {
                "id": "alliance-1",
                "type": "military_alliance",
                "members": ["UKR", "POL"],
                "status": "active",
                "expires_at_minute": 0,
                "suspended_members": [],
            },
        ]),
        "countries_relations": pl.DataFrame([
            {"source": "UKR", "target": "POL", "value": 42.0},
        ]),
    })

    rows = _legend(state)._empire_countries(state, "UKR", "UKR")

    assert [row.tag for row in rows] == ["UKR", "POL"]
    assert rows[0].selected
    assert rows[1].relation == 42.0
