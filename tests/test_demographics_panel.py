from __future__ import annotations

import math
from contextlib import nullcontext
from unittest.mock import patch

import polars as pl

from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
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
                {"id": ["NULL", "HIGH", "NAN"], "human_dev": [None, 1.5, float("nan")]},
                schema={"id": pl.Utf8, "human_dev": pl.Float64},
            )
        }
    )

    assert DemographicsPanel._human_development_index(state, "NULL") is None
    assert DemographicsPanel._human_development_index(state, "HIGH") == 1.0
    assert DemographicsPanel._human_development_index(state, "NAN") is None
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


def test_demographics_panel_render_handles_closed_and_open_windows() -> None:
    state = GameState()
    context = PanelRenderContext(target_tag="AAA", is_own_country=True)
    panel = DemographicsPanel()

    with (
        patch(
            "src.client.ui.panels.demographics_panel.main_pillar_position",
            return_value=(10, 20),
        ),
        patch.object(WindowManager, "window", return_value=nullcontext(False)) as window,
        patch.object(panel, "_render_content") as content,
    ):
        assert panel.render(state, context) is False
        content.assert_not_called()
        window.assert_called_once_with(
            "DEMOGRAPHICS", x=10, y=20, w=240, h=480, test_id="demographics.panel"
        )

    with (
        patch(
            "src.client.ui.panels.demographics_panel.main_pillar_position",
            return_value=(10, 20),
        ),
        patch.object(WindowManager, "window", return_value=nullcontext(True)),
        patch.object(panel, "_render_content") as content,
    ):
        assert panel.render(state, context) is True
        content.assert_called_once_with(state, "AAA", True)


def test_demographics_panel_aggregates_age_cohorts_for_the_selected_country() -> None:
    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "owner": ["AAA", "AAA", "BBB"],
                    "pop_14": [10, None, 100],
                    "pop_15_64": [50, 60, 200],
                    "pop_65": [5, 10, 50],
                }
            ),
            "countries": pl.DataFrame({"id": ["AAA"], "human_dev": [0.7]}),
        }
    )
    meters: list[tuple[str, float]] = []

    with (
        patch("src.client.ui.panels.demographics_panel.imgui"),
        patch.object(Prims, "header"),
        patch.object(Prims, "right_align_text"),
        patch.object(
            Prims,
            "meter",
            side_effect=lambda label, value, *_args: meters.append((label, value)),
        ),
    ):
        DemographicsPanel()._render_content(state, "AAA", False)

    values = dict(meters)
    assert math.isclose(values["Youth: 10"], 10 / 135 * 100)
    assert math.isclose(values["Working: 110"], 110 / 135 * 100)
    assert math.isclose(values["Elderly: 15"], 15 / 135 * 100)


def test_demographics_panel_supports_legacy_population_and_malformed_region_tables() -> None:
    states = [
        GameState(tables={"regions": pl.DataFrame({"owner": ["AAA"], "population": [120]})}),
        GameState(tables={"regions": pl.DataFrame({"wrong_owner_column": ["AAA"], "population": [120]})}),
    ]

    for state in states:
        meters: list[tuple[str, float]] = []
        with (
            patch("src.client.ui.panels.demographics_panel.imgui"),
            patch.object(Prims, "header"),
            patch.object(Prims, "right_align_text"),
            patch.object(
                Prims,
                "meter",
                side_effect=lambda label, value, *_args: meters.append((label, value)),
            ),
        ):
            DemographicsPanel()._render_content(state, "AAA", False)

        assert ("Youth: N/A", 0) in meters
        assert ("Working: N/A", 0) in meters
        assert ("Elderly: N/A", 0) in meters


def test_demographics_panel_opens_available_internal_policy_actions() -> None:
    opened: list[str] = []
    panel = DemographicsPanel(
        lambda: opened.append("migration"),
        lambda: opened.append("social"),
    )

    with (
        patch("src.client.ui.panels.demographics_panel.imgui") as imgui,
        patch.object(Prims, "header"),
        patch.object(Prims, "right_align_text"),
        patch.object(Prims, "meter"),
    ):
        imgui.button.side_effect = [True, True]
        panel._render_content(GameState(), "AAA", True)

    assert opened == ["migration", "social"]
