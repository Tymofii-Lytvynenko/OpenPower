from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import polars as pl

import src.client.ui.panels.resources_panel as resources_panel_module
import pytest
from src.client.ui.panels.resources_panel import ResourcesPanel


@pytest.mark.parametrize("amount, expected", [
    (220850000000.0, "$ 220.8 B"),
    (1315000000000.0, "$ 1.3 T"),
    (-807500000000.0, "$ -807.5 B"),
])
def test_live_country_totals_have_compact_units(amount, expected):
    assert ResourcesPanel()._fmt_money(amount, abbreviate=True) == expected


def _market_state() -> SimpleNamespace:
    return SimpleNamespace(
        tables={
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": ["AAA", "AAA", "BBB"],
                    "game_resource_id": ["grain", "oil", "grain"],
                    "category": ["Food", "Energy", "Food"],
                    "production_usd": [100.0, 10.0, 900.0],
                    "consumption_usd": [80.0, 15.0, 800.0],
                    "trade_usd": [0.0, -20.0, 0.0],
                    "balance_usd": [20.0, -10.0, 100.0],
                }
            ),
            "trade_network": pl.DataFrame(
                {
                    "exporter_id": ["AAA", "BBB"],
                    "importer_id": ["BBB", "AAA"],
                    "game_resource_id": ["grain", "oil"],
                    "trade_value_usd": [20.0, 30.0],
                }
            ),
        }
    )


def test_resource_flow_projection_shows_country_production_consumption_trade_and_balance():
    panel = ResourcesPanel()

    flows = panel._resource_flow_frame(_market_state(), "AAA")

    grain = flows.filter(pl.col("game_resource_id") == "grain").row(0, named=True)
    oil = flows.filter(pl.col("game_resource_id") == "oil").row(0, named=True)
    assert grain["production_usd"] == 100.0
    assert grain["consumption_usd"] == 80.0
    assert grain["exports"] == 20.0
    assert grain["imports"] == 0.0
    assert grain["net_trade_usd"] == 20.0
    assert grain["balance_usd"] == 20.0
    assert oil["imports"] == 30.0
    assert oil["exports"] == 0.0
    assert oil["net_trade_usd"] == -30.0
    assert oil["balance_usd"] == -10.0


def test_resource_flow_projection_reuses_immutable_snapshot_results():
    panel = ResourcesPanel()
    state = _market_state()

    first = panel._resource_flow_frame(state, "AAA")
    second = panel._resource_flow_frame(state, "AAA")

    assert first is second


def test_resource_flow_projection_refreshes_for_new_country_and_trade_snapshot():
    panel = ResourcesPanel()
    state = _market_state()
    first = panel._resource_flow_frame(state, "AAA")

    other_country = panel._resource_flow_frame(state, "BBB")
    assert other_country is not first
    assert other_country.filter(pl.col("game_resource_id") == "grain").item(0, "production_usd") == 900.0

    state.tables["trade_network"] = None
    without_trade = panel._resource_flow_frame(state, "AAA")
    assert without_trade is not first
    assert without_trade["exports"].sum() == 0.0
    assert without_trade["imports"].sum() == 0.0


def test_resource_flow_projection_reports_missing_schema_instead_of_masking_it():
    panel = ResourcesPanel()
    state = SimpleNamespace(tables={"resource_ledger": pl.DataFrame({"id": [1]})})

    try:
        panel._resource_flow_frame(state, "AAA")
    except ValueError as error:
        assert "resource_ledger" in str(error)
        assert "balance_usd" in str(error)
    else:
        raise AssertionError("Malformed resource schema must be reported")


def test_resource_summary_renders_five_implot_series_and_metric_cards(monkeypatch):
    panel = ResourcesPanel()
    imgui = resources_panel_module.imgui
    implot = resources_panel_module.implot
    monkeypatch.setattr(
        imgui,
        "get_content_region_avail",
        lambda: SimpleNamespace(x=470.0, y=300.0),
    )
    monkeypatch.setattr(imgui, "get_window_pos", lambda: SimpleNamespace(x=0.0, y=0.0))
    monkeypatch.setattr(imgui, "set_cursor_screen_pos", Mock())
    for name in (
        "push_style_color",
        "pop_style_color",
        "end_child",
        "text_colored",
        "text_disabled",
        "separator",
        "text_wrapped",
        "dummy",
        "same_line",
        "begin_child",
        "text",
        "table_setup_column",
        "table_headers_row",
        "table_next_row",
        "table_next_column",
        "end_table",
    ):
        monkeypatch.setattr(imgui, name, Mock())
    monkeypatch.setattr(imgui, "begin_table", Mock(side_effect=lambda name, *args: name == "ResourceMetrics"))
    monkeypatch.setattr(imgui, "is_item_hovered", Mock(return_value=False))
    monkeypatch.setattr(resources_panel_module.GMLWidgets, "arrow_button_at", Mock(return_value=False))
    render_amount = Mock()
    monkeypatch.setattr(resources_panel_module.Prims, "right_align_text", render_amount)
    monkeypatch.setattr(implot, "begin_plot", Mock(return_value=True))
    for name in ("setup_axes", "setup_axis_ticks", "plot_bars", "end_plot"):
        monkeypatch.setattr(implot, name, Mock())

    panel._render_market_flow_summary(_market_state(), "AAA")

    assert implot.plot_bars.call_count == 5
    assert [call.args[0] for call in implot.plot_bars.call_args_list] == [
        "Production",
        "Consumption",
        "Imports",
        "Exports",
        "Balance",
    ]
    assert implot.setup_axis_ticks.call_args.args[2] == ["Grain", "Oil"]
    assert [call.args[0] for call in render_amount.call_args_list] == [
        "$110", "$95", "$30", "$20", "$10",
    ]

