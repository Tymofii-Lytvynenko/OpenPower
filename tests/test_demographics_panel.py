from __future__ import annotations

import polars as pl

from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.shared.state import GameState


def test_demographics_panel_reads_human_development_from_countries() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"], "human_dev": [0.73]}),
        }
    )

    assert DemographicsPanel._human_development_index(state, "AAA") == 0.73


def test_demographics_panel_uses_safe_human_development_fallbacks() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["NULL", "HIGH"], "human_dev": [None, 1.5]},
                schema={"id": pl.Utf8, "human_dev": pl.Float64},
            )
        }
    )

    assert DemographicsPanel._human_development_index(state, "NULL") == 0.0
    assert DemographicsPanel._human_development_index(state, "HIGH") == 1.0
    assert DemographicsPanel._human_development_index(state, "UNKNOWN") == 0.0
