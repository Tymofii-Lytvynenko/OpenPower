from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import polars as pl
import pytest

from src.client.ui.panels import resources_panel as resources_panel_module
from src.client.ui.panels.resources_panel import ResourcesPanel


def fake_imgui():
    ui = MagicMock()
    ui.Col_.child_bg = 1
    ui.Col_.frame_bg = 2
    ui.StyleVar_.item_spacing = 3
    ui.StyleVar_.frame_padding = 4
    ui.ChildFlags_.borders = 1
    ui.TableFlags_.scroll_y = 1
    ui.TableFlags_.borders = 2
    ui.TableFlags_.row_bg = 4
    ui.TableFlags_.resizable = 8
    ui.TableFlags_.sizing_stretch_prop = 16
    ui.TableFlags_.borders_inner_h = 32
    ui.TableColumnFlags_.width_fixed = 1
    ui.TableColumnFlags_.width_stretch = 2
    ui.TreeNodeFlags_.default_open = 1
    ui.SelectableFlags_.span_all_columns = 1
    ui.HoveredFlags_.allow_when_disabled = 1
    ui.InputTextFlags_.read_only = 1
    return ui


def ledger_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "country_id": ["USA", "CAN"],
        "game_resource_id": ["grain", "grain"],
        "category": ["Food", "Food"],
        "production_usd": [100.0, 900.0],
        "consumption_usd": [80.0, 800.0],
        "trade_usd": [-20.0, 100.0],
        "balance_usd": [20.0, 100.0],
    })


def test_content_renderer_draws_categories_and_resource_rows(monkeypatch) -> None:
    panel = ResourcesPanel()
    ui = fake_imgui()
    ui.begin_table.return_value = True
    ui.tree_node_ex.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    render_amount = Mock()
    monkeypatch.setattr(resources_panel_module.Prims, "right_align_text", render_amount)
    empty_state = Mock()
    monkeypatch.setattr(resources_panel_module, "draw_empty_state", empty_state)
    panel._draw_leaf_row = Mock()
    panel._render_controls = Mock()
    panel._render_market_flow_summary = Mock()
    state = SimpleNamespace(
        globals={"abbreviate_numbers": True},
        tables={"resource_ledger": ledger_frame()},
    )

    panel._render_content(state, "USA", True)

    assert ui.begin_child.call_args.args[0] == "table_view"
    assert ui.begin_table.call_args.args[:2] == ("ResourcesTable", 5)
    assert ui.tree_node_ex.call_count == 1
    assert panel._draw_leaf_row.call_count == 1
    assert panel._draw_leaf_row.call_args.args[:2] == ("grain", "Grain")
    assert panel._draw_leaf_row.call_args.args[-2:] == (state, "USA")
    assert render_amount.call_count == 4
    empty_state.assert_not_called()
    ui.end_table.assert_called_once()
    ui.pop_style_var.assert_called_once()
    ui.end_child.assert_called_once()
    panel._render_controls.assert_called_once_with(state, "USA", True)
    panel._render_market_flow_summary.assert_called_once_with(
        state,
        "USA",
        is_own=True,
        gml_id="Resources_Window/frmInner/frmResources/frmStockMarket",
    )


def test_content_renderer_shows_empty_state_for_empty_country_ledger(monkeypatch) -> None:
    panel = ResourcesPanel()
    ui = fake_imgui()
    ui.begin_table.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    empty_state = Mock()
    monkeypatch.setattr(resources_panel_module, "draw_empty_state", empty_state)
    panel._render_controls = Mock()
    panel._render_market_flow_summary = Mock()
    empty_ledger = ledger_frame().filter(pl.col("country_id") == "MEX")
    state = SimpleNamespace(globals={}, tables={"resource_ledger": empty_ledger})

    panel._render_content(state, "MEX", False)

    empty_state.assert_called_once_with("No resource data available.")
    ui.end_table.assert_called_once()


def test_leaf_row_selects_resource_syncs_policy_and_colors_negative_balance(monkeypatch) -> None:
    panel = ResourcesPanel()
    ui = fake_imgui()
    ui.selectable.side_effect = [(True, None), (False, None)]
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    right_align = Mock()
    monkeypatch.setattr(resources_panel_module.Prims, "right_align_text", right_align)
    panel._refresh_current_draft = Mock()
    panel._sync_policy_from_state = Mock()
    state = object()

    panel._draw_leaf_row("grain", "Grain", 10, 8, -1, -2, True, state, "USA")
    panel._draw_leaf_row("grain", "Grain", 10, 8, -1, 0, False, state, "USA")

    assert panel.selected_resource == "grain"
    assert panel.current_policy_key is None
    panel._refresh_current_draft.assert_called_once()
    panel._sync_policy_from_state.assert_called_once_with(state, "USA")
    assert ui.selectable.call_args_list[0].args[1] is False
    assert ui.selectable.call_args_list[1].args[1] is True
    assert right_align.call_count == 8
    assert right_align.call_args_list[3].args[1] == resources_panel_module.GAMETHEME.colors.negative
    assert right_align.call_args_list[-1].args[1] == resources_panel_module.GAMETHEME.colors.positive


def test_controls_render_live_totals_and_production_action(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel.selected_resource = "grain"
    panel.current_policy_key = ("USA", "grain")
    panel._sync_policy_from_state = Mock()
    panel._render_tax_control = Mock()
    panel._render_unavailable_resource_value = Mock()
    panel._set_current_draft_value = Mock()
    panel._increase_production_dialog.open = Mock()
    ui = fake_imgui()
    ui.combo.side_effect = [(True, 1), (True, 1), (False, 0)]
    ui.is_item_hovered.side_effect = [True, True, True]
    ui.button.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    separator = Mock()
    monkeypatch.setattr(resources_panel_module, "draw_gml_separator", separator)
    ledger = ledger_frame()
    state = SimpleNamespace(
        tables={
            "resource_ledger": ledger,
            "countries": pl.DataFrame({"id": ["USA"], "gdp": [1000.0]}),
        }
    )

    panel._render_controls(state, "USA", True)

    panel._sync_policy_from_state.assert_called_once_with(state, "USA")
    assert [call.args for call in panel._set_current_draft_value.call_args_list] == [
        ("management", 1),
        ("status", 1),
    ]
    assert ui.text.call_args_list[1].args[0] == "10.00 %"
    assert ui.text.call_args_list[2].args[0] == "20"
    assert ui.text.call_args_list[3].args[0] == "$ -20"
    assert separator.call_args.args[0].endswith("picSep")
    assert panel._render_unavailable_resource_value.call_count == 2
    panel._render_tax_control.assert_called_once()
    panel._increase_production_dialog.open.assert_called_once_with("USA", "grain")
    assert ui.set_tooltip.call_count == 3
    assert ui.begin_disabled.call_count == 2
    ui.push_style_color.assert_called_once()
    ui.pop_style_color.assert_called_once()
    ui.pop_style_var.assert_called_once()


def test_controls_disable_policy_and_report_pending_production(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel._pending_production_increases[("USA", "grain")] = object()
    panel._sync_policy_from_state = Mock()
    panel._render_tax_control = Mock()
    panel._render_unavailable_resource_value = Mock()
    ui = fake_imgui()
    ui.combo.side_effect = [(False, 0), (False, 0), (False, 0)]
    ui.is_item_hovered.return_value = True
    ui.button.return_value = False
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module, "draw_gml_separator", Mock())

    panel._render_controls(SimpleNamespace(tables={}), "USA", False)

    assert ui.begin_disabled.call_count == 3
    assert ui.end_disabled.call_count == 3
    assert ui.is_item_hovered.call_count == 4
    assert "awaiting an authoritative result" in ui.set_tooltip.call_args.args[0]


@pytest.mark.parametrize(
    "key,expected",
    [("global_tax_modifier", "Unavailable"), ("desired_trade", "N/A")],
)
def test_unavailable_policy_controls_show_read_only_reason(monkeypatch, key, expected) -> None:
    panel = ResourcesPanel()
    ui = fake_imgui()
    ui.is_item_hovered.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    widgets = SimpleNamespace(path=Mock(side_effect=lambda value: f"gml/{value}"))
    widgets.arrow_button = Mock(return_value=False)
    monkeypatch.setattr(resources_panel_module, "GMLWidgets", lambda _root: widgets)

    panel._render_unavailable_resource_value(key, "step", "No policy field is available.")

    assert ui.input_text.call_args.args[1] == expected
    assert ui.input_text.call_args.kwargs["gml_enabled"] is False
    assert widgets.arrow_button.call_count == 2
    assert ui.set_tooltip.call_args.args == ("No policy field is available.",)
    ui.end_disabled.assert_called_once()
    ui.pop_style_var.assert_called_once()


def test_tax_control_clamps_input_and_decrements_through_arrow(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel.current_policy_key = ("USA", "grain")
    panel._policy_drafts[panel.current_policy_key] = resources_panel_module.ResourcePolicyDraft(0, 0, 0, 0, 0, 0)
    panel.draft_tax = 10
    ui = fake_imgui()
    ui.input_int.return_value = (True, 105)
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    widgets = SimpleNamespace(path=Mock(side_effect=lambda value: f"gml/{value}"))
    widgets.arrow_button = Mock(return_value=True)
    monkeypatch.setattr(resources_panel_module, "GMLWidgets", lambda _root: widgets)

    panel._render_tax_control()

    assert ui.input_int.call_args.args[1] == 10
    assert widgets.arrow_button.call_args.kwargs["enabled"] is True
    assert panel.draft_tax == 99
    assert panel._policy_drafts[panel.current_policy_key].tax == 99
    ui.pop_style_var.assert_called_once()


def test_content_renderer_reports_malformed_ledger_without_skipping_cleanup(monkeypatch) -> None:
    panel = ResourcesPanel()
    ui = fake_imgui()
    ui.begin_table.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    panel._render_controls = Mock()
    panel._render_market_flow_summary = Mock()
    state = SimpleNamespace(
        globals={},
        tables={"resource_ledger": pl.DataFrame({"id": [1]})},
    )

    panel._render_content(state, "USA", True)

    assert "Resource ledger data is invalid" in ui.text_disabled.call_args.args[0]
    ui.end_table.assert_called_once()
    ui.pop_style_var.assert_called_once()
    ui.end_child.assert_called_once()


def test_controls_explain_missing_ledger_schema(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel.selected_resource = "grain"
    panel._sync_policy_from_state = Mock()
    panel._render_tax_control = Mock()
    panel._render_unavailable_resource_value = Mock()
    ui = fake_imgui()
    ui.combo.side_effect = [(False, 0), (False, 0), (False, 0)]
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    monkeypatch.setattr(resources_panel_module, "draw_gml_separator", Mock())
    state = SimpleNamespace(tables={"resource_ledger": pl.DataFrame({"id": [1]})})

    panel._render_controls(state, "USA", True)

    assert panel._panel_diagnostic.startswith("Resource ledger is missing columns:")
    assert any(
        panel._panel_diagnostic in call.args
        for call in ui.text_disabled.call_args_list
    )


def test_metric_cards_handle_closed_table_and_show_hovered_exact_values(monkeypatch) -> None:
    panel = ResourcesPanel()
    flows = pl.DataFrame({
        "production_usd": [100.0],
        "consumption_usd": [80.0],
        "imports": [5.0],
        "exports": [10.0],
        "balance_usd": [20.0],
    })
    ui = fake_imgui()
    ui.begin_table.side_effect = [False, True]
    ui.is_item_hovered.return_value = True
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    right_align = Mock()
    monkeypatch.setattr(resources_panel_module.Prims, "right_align_text", right_align)

    panel._render_flow_metric_cards(flows)
    assert ui.end_table.call_count == 0
    panel._render_flow_metric_cards(flows)

    assert right_align.call_count == 5
    assert ui.set_tooltip.call_count == 5
    assert ui.end_table.call_count == 1


def test_flow_plot_and_table_handle_empty_closed_and_rendered_states(monkeypatch) -> None:
    panel = ResourcesPanel()
    empty_flows = pl.DataFrame(schema={
        "game_resource_id": pl.String,
        "production_usd": pl.Float64,
        "consumption_usd": pl.Float64,
        "imports": pl.Float64,
        "exports": pl.Float64,
        "balance_usd": pl.Float64,
        "net_trade_usd": pl.Float64,
    })
    flows = pl.DataFrame({
        "game_resource_id": ["grain"],
        "production_usd": [100.0],
        "consumption_usd": [80.0],
        "imports": [5.0],
        "exports": [10.0],
        "balance_usd": [20.0],
        "net_trade_usd": [-3.0],
    })
    ui = fake_imgui()
    ui.begin_table.side_effect = [False, True]
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    empty_state = Mock()
    monkeypatch.setattr(resources_panel_module, "draw_empty_state", empty_state)
    plot = resources_panel_module.implot
    monkeypatch.setattr(plot, "begin_plot", Mock(return_value=False))
    end_plot = Mock()
    monkeypatch.setattr(plot, "end_plot", end_plot)
    right_align = Mock()
    monkeypatch.setattr(resources_panel_module.Prims, "right_align_text", right_align)

    panel._render_market_balance_plot(empty_flows)
    empty_state.assert_called_once()
    panel._render_market_balance_plot(flows)
    plot.begin_plot.assert_called_once()
    end_plot.assert_not_called()

    panel._render_market_flow_table(empty_flows)
    assert ui.begin_table.call_count == 0
    panel._render_market_flow_table(flows)
    assert ui.begin_table.call_count == 1
    panel._render_market_flow_table(flows)

    assert ui.end_table.call_count == 1
    assert right_align.call_count == 3


def test_market_summary_handles_unavailable_data_and_tax_arrow(monkeypatch) -> None:
    panel = ResourcesPanel()
    panel.selected_resource = "grain"
    panel.current_policy_key = ("USA", "grain")
    panel.draft_tax = 5
    panel._set_draft_tax = Mock()
    ui = fake_imgui()
    ui.get_content_region_avail.return_value = SimpleNamespace(x=470.0, y=300.0)
    ui.get_window_pos.return_value = SimpleNamespace(x=10.0, y=20.0)
    monkeypatch.setattr(resources_panel_module, "imgui", ui)
    widgets = SimpleNamespace(arrow_button_at=Mock(return_value=True))
    monkeypatch.setattr(resources_panel_module, "GMLWidgets", lambda _root: widgets)
    panel._resource_flow_frame = Mock(side_effect=ValueError("missing balance field"))

    panel._render_market_flow_summary(SimpleNamespace(tables={}), "USA", is_own=True)

    widgets.arrow_button_at.assert_called_once()
    panel._set_draft_tax.assert_called_once_with(6)
    assert "Resource market data is unavailable." in ui.text_wrapped.call_args.args
    ui.end_child.assert_called_once()
    ui.pop_style_color.assert_called_once()


def test_sync_without_selection_and_missing_draft_mutation_keep_panel_clean() -> None:
    panel = ResourcesPanel()
    panel._sync_policy_from_state(SimpleNamespace(tables={}), "USA")

    assert panel.current_policy_key is None
    assert panel.has_unsaved_changes is False
    panel.current_policy_key = ("USA", "grain")
    panel._set_current_draft_value("tax", 10)
    assert panel.has_unsaved_changes is False


def test_clean_existing_policy_draft_rebases_on_new_authoritative_snapshot() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    panel.selected_resource = "grain"
    panel._policy_drafts[key] = resources_panel_module.ResourcePolicyDraft(0, 0, 0, 0, 0, 0)

    panel._sync_policy_from_state(
        SimpleNamespace(tables={"domestic_production": pl.DataFrame([{
            "country_id": "USA",
            "game_resource_id": "grain",
            "is_gov_controlled": False,
            "is_legal": True,
            "tax_rate": 0.12,
        }])}),
        "USA",
    )

    assert panel._policy_drafts[key].baseline == (0, 0, 12)
    assert panel._policy_drafts[key].values == (0, 0, 12)


def test_rejection_match_skips_other_action_actor_status_country_and_resource() -> None:
    panel = ResourcesPanel()
    key = ("USA", "grain")
    pending = resources_panel_module.PendingResourcePolicy((1, 1, 20), "player-1", 0)
    results = [
        {"action_type": "OtherAction", "player_id": "player-1", "status": "rejected"},
        {"action_type": "ActionUpdateResourcePolicy", "player_id": "other", "status": "rejected"},
        {"action_type": "ActionUpdateResourcePolicy", "player_id": "player-1", "status": "applied"},
        {"action_type": "ActionUpdateResourcePolicy", "player_id": "player-1", "status": "rejected", "country_id": "CAN"},
        {"action_type": "ActionUpdateResourcePolicy", "player_id": "player-1", "status": "failed", "country_id": "USA", "resource_id": "oil"},
        {"action_type": "ActionUpdateResourcePolicy", "player_id": "player-1", "status": "failed", "country_id": " usa ", "resource_id": " GRAIN "},
    ]
    state = SimpleNamespace(journal=SimpleNamespace(command_results=results))

    assert panel._find_policy_rejection(state, key, pending) == results[-1]
