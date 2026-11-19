"""Resource UI drafts survive navigation and authoritative command outcomes."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest

from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from src.client.ui.panels import resources_panel as panel_module
from src.client.ui.panels.resources_panel import ResourcesPanel
from src.shared.state import GameState


def setup_policy():
    state = GameState(tables={
        "countries": pl.DataFrame({"id": ["AAA"], "global_resource_tax_modifier": [0.02]}),
        "domestic_production": pl.DataFrame({
            "country_id": ["AAA", "AAA"], "game_resource_id": ["cereals", "fossil_fuels"],
            "domestic_production": [100.0, 200.0], "is_legal": [True, True],
            "is_gov_controlled": [False, False], "tax_rate": [0.05, 0.05],
            "desired_trade_usd": [0.0, 0.0], "meet_consumption": [True, True],
        }),
    }, globals={"player_country_map": {"player": "AAA"}})
    panel = ResourcesPanel()
    panel.selected_resource = "cereals"
    panel._sync_policy_from_state(state, "AAA")
    client = SimpleNamespace(player_id="player", actions=[])
    client.send_action = client.actions.append
    return state, panel, client


def test_two_resources_share_one_global_rate_and_wait_for_full_snapshot_ack():
    state, panel, client = setup_policy()
    original = state.tables["domestic_production"].clone()
    panel._set_market_policy_value("global_tax_modifier", 0.15)
    panel._set_market_policy_value("meet_consumption", False)
    panel._set_market_policy_value("desired_trade_usd", -20e6)
    panel.selected_resource = "fossil_fuels"
    panel._sync_policy_from_state(state, "AAA")
    assert panel._policy_drafts[("AAA", "fossil_fuels")].market_values.global_tax_modifier == 0.15
    panel._set_market_policy_value("meet_consumption", False)
    panel._set_market_policy_value("desired_trade_usd", 30e6)
    assert state.tables["domestic_production"].equals(original)
    assert state.tables["countries"]["global_resource_tax_modifier"][0] == 0.02

    panel._dispatch_policy_updates(client, "AAA", state)
    assert len(client.actions) == 2
    assert sum(action.global_tax_modifier is not None for action in client.actions) == 1
    panel._sync_policy_from_state(state, "AAA")
    assert len(panel._pending_policy_updates) == 2
    state.current_actions = client.actions
    InternalEconomySystem().update(state, 0.0)
    panel._sync_policy_from_state(state, "AAA")
    panel.selected_resource = "cereals"
    panel._sync_policy_from_state(state, "AAA")
    assert not panel.has_unsaved_changes
    assert not panel._pending_policy_updates
    assert state.tables["countries"]["global_resource_tax_modifier"][0] == 0.15
    assert state.tables["domestic_production"]["desired_trade_usd"].to_list() == [-20e6, 30e6]


def test_rejected_market_command_retains_editable_draft_for_retry():
    state, panel, client = setup_policy()
    client.player_id = "intruder"
    panel._set_market_policy_value("meet_consumption", False)
    panel._set_market_policy_value("desired_trade_usd", -5e6)
    panel._dispatch_policy_updates(client, "AAA", state)
    state.current_actions = client.actions
    InternalEconomySystem().update(state, 0.0)
    panel._sync_policy_from_state(state, "AAA")
    assert not panel._pending_policy_updates
    assert panel.has_unsaved_changes
    assert panel._policy_drafts[("AAA", "cereals")].market_values.desired_trade_usd == -5e6
    assert state.tables["domestic_production"]["desired_trade_usd"][0] == 0.0


def test_discard_clears_unsubmitted_global_and_resource_edits():
    state, panel, _ = setup_policy()
    panel._set_market_policy_value("global_tax_modifier", 0.25)
    panel._set_market_policy_value("meet_consumption", False)
    panel._discard_unsubmitted_drafts()
    panel._sync_policy_from_state(state, "AAA")
    assert not panel.has_unsaved_changes
    assert panel._policy_drafts[("AAA", "cereals")].market_values.global_tax_modifier == 0.02


def test_pending_global_change_is_not_dispatched_twice_while_switching_resources():
    state, panel, client = setup_policy()
    panel._set_market_policy_value("global_tax_modifier", 0.25)
    panel.selected_resource = "fossil_fuels"
    panel._sync_policy_from_state(state, "AAA")
    panel._dispatch_policy_updates(client, "AAA", state)
    panel._dispatch_policy_updates(client, "AAA", state)
    assert len(client.actions) == 1


def test_controls_convert_percent_and_import_millions_without_touching_snapshot(monkeypatch):
    state, panel, _ = setup_policy()
    ui = MagicMock()
    ui.input_float.side_effect = [(True, 12.5), (True, 2.5)]
    ui.combo.return_value = (True, 1)
    ui.is_item_hovered.return_value = False
    monkeypatch.setattr(panel_module, "imgui", ui)
    widgets = SimpleNamespace(path=lambda slot: slot, arrow_button=lambda *args, **kwargs: False)
    monkeypatch.setattr(panel_module, "GMLWidgets", lambda _: widgets)
    panel._render_global_tax_control("AAA")
    panel._set_market_policy_value("meet_consumption", False)
    panel._render_trade_direction()
    panel._render_desired_trade_control()
    values = panel._policy_drafts[("AAA", "cereals")].market_values
    assert values.global_tax_modifier == pytest.approx(0.125)
    assert values.desired_trade_usd == -2_500_000.0
    assert state.tables["countries"]["global_resource_tax_modifier"][0] == 0.02


def test_disabled_controls_and_nonfinite_input_cannot_edit_draft(monkeypatch):
    _, panel, _ = setup_policy()
    ui = MagicMock()
    ui.input_float.return_value = (True, float("nan"))
    monkeypatch.setattr(panel_module, "imgui", ui)
    monkeypatch.setattr(panel_module, "GMLWidgets", lambda _: SimpleNamespace(path=lambda slot: slot, arrow_button=lambda *args, **kwargs: False))
    panel._render_global_tax_control("AAA")
    assert not panel.has_unsaved_changes
    panel._market_controls_enabled = False
    panel._set_market_policy_value("global_tax_modifier", 0.5)
    assert not panel.has_unsaved_changes


def test_market_only_edit_preserves_fractional_authoritative_sector_tax():
    state, panel, client = setup_policy()
    state.tables["domestic_production"] = state.tables["domestic_production"].with_columns(pl.lit(0.057).alias("tax_rate"))
    panel._sync_policy_from_state(state, "AAA")
    panel._set_market_policy_value("global_tax_modifier", 0.15)
    panel._dispatch_policy_updates(client, "AAA", state)
    assert client.actions[0].tax_rate == 0.057
    state.current_actions = client.actions
    InternalEconomySystem().update(state, 0.0)
    assert state.tables["domestic_production"]["tax_rate"].to_list() == [0.057, 0.057]
