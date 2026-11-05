from __future__ import annotations

from unittest.mock import patch

import polars as pl

from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.demographics_panel import DemographicsPanel
from src.shared.state import GameState


def test_demographics_panel_reads_human_development_from_countries() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["AAA"], "human_dev": [0.73]}),
        }
    )

    assert DemographicsPanel._human_development_index(state, "AAA") == 0.73


def test_demographics_panel_preserves_available_hdi_and_marks_missing_values() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["NULL", "HIGH"], "human_dev": [None, 1.5]},
                schema={"id": pl.Utf8, "human_dev": pl.Float64},
            )
        }
    )

    assert DemographicsPanel._human_development_index(state, "NULL") is None
    assert DemographicsPanel._human_development_index(state, "HIGH") == 1.0
    assert DemographicsPanel._human_development_index(state, "UNKNOWN") is None


def test_demographics_panel_scales_hdi_ratio_for_percentage_meter() -> None:
    state = GameState(
        tables={"countries": pl.DataFrame({"id": ["AAA"], "human_dev": [0.73]})}
    )
    meters: list[tuple[str, float]] = []

    with (
        patch("src.client.ui.panels.demographics_panel.imgui"),
        patch.object(Prims, "header"),
        patch.object(Prims, "right_align_text"),
        patch.object(Prims, "meter", side_effect=lambda label, value, *_args: meters.append((label, value))),
    ):
        DemographicsPanel()._render_content(state, "AAA", False)

    assert ("HDI Score: 0.73", 73.0) in meters


def test_demographics_panel_marks_unavailable_hdi_in_the_meter_label() -> None:
    state = GameState(tables={"countries": pl.DataFrame({"id": ["AAA"]})})
    meters: list[tuple[str, float]] = []

    with (
        patch("src.client.ui.panels.demographics_panel.imgui"),
        patch.object(Prims, "header"),
        patch.object(Prims, "right_align_text"),
        patch.object(Prims, "meter", side_effect=lambda label, value, *_args: meters.append((label, value))),
    ):
        DemographicsPanel()._render_content(state, "AAA", False)

    assert ("HDI Score: N/A", 0.0) in meters
