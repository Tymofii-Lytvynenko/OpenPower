from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from modules.base.schema import ensure_base_tables
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.military.strategic_warfare_panel import StrategicWarfarePanel
from src.shared.actions import ActionProduceStrategicWeapon
from src.shared.state import GameState


def _strategic_ui_state() -> GameState:
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["USA", "CAN"], "money_reserves": [100.0, 100.0],
        }),
        "regions": pl.DataFrame({
            "id": [1, 2], "owner": ["USA", "CAN"], "latitude": [0.0, 0.0],
            "longitude": [0.0, 5.0],
        }),
        "countries_wars": pl.DataFrame({
            "id": ["war"], "name": ["War"], "side_a": [["USA"]], "side_b": [["CAN"]],
            "status": ["active"], "casus_belli": [""], "created_at": [""],
            "leader_a": ["USA"], "leader_b": ["CAN"], "intent_a": [""], "intent_b": [""],
        }),
    })
    ensure_base_tables(state)
    state.update_table("strategic_weapons", pl.DataFrame([{
        "id": "usa-icbm", "country_id": "USA", "weapon_type": "icbm", "weapon_class": "icbm",
        "quantity": 2, "ready": 2, "origin_region_id": 1, "range_km": 12000.0,
        "payload_level": 1, "max_payload_level": 2, "operational": True, "launch_cost": 0.0,
        "flight_minutes": 5, "production_cost": 25.0, "production_minutes": 5,
    }], schema=state.get_table("strategic_weapons").schema))
    state.update_table("research_tracks", pl.DataFrame([
        {"id": "usa-program", "country_id": "USA", "branch": "strategic_program", "research_level": 1},
        {"id": "usa-weapons", "country_id": "USA", "branch": "strategic_weapons", "research_level": 2},
        {"id": "can-program", "country_id": "CAN", "branch": "strategic_program", "research_level": 1},
        {"id": "can-defense", "country_id": "CAN", "branch": "strategic_defense", "research_level": 1},
    ], schema=state.get_table("research_tracks").schema))
    state.update_table("missile_defense_layers", pl.DataFrame([{
        "id": "can-long", "country_id": "CAN", "layer": "long_range", "researched": True,
        "operational": True, "coverage_region_ids": [2], "readiness": 1.0,
        "first_attempt_probability": None, "second_attempt_probability": None,
    }], schema=state.get_table("missile_defense_layers").schema))
    state.globals["strategic_authorization_policy"] = "war"
    return state


def test_strategic_previews_show_range_authorization_timing_and_layer_estimate() -> None:
    state = _strategic_ui_state()
    presenter = MilitaryPresenter()
    weapon = presenter.strategic_inventory_for_country(state, "USA")[0]

    preview = presenter.strategic_launch_preview(state, "USA", weapon, 2)
    defense = presenter.strategic_defense_estimate_for_region(state, "CAN", 2)

    assert preview["can_launch"] is True
    assert preview["authorization"] == "authorized by active war"
    assert preview["flight_minutes"] == 5
    assert preview["distance_km"] is not None
    assert defense["interception_probability"] == 0.8
    assert defense["covered_layers"][0]["covered"] is True
    assert defense["covered_layers"][0]["layer_interception_probability"] == 0.8


def test_explicit_authorization_preview_requires_a_configured_context() -> None:
    state = _strategic_ui_state()
    state.globals["strategic_authorization_policy"] = "explicit"
    state.globals["strategic_authorization_contexts"] = ["cabinet"]
    state.update_table("countries_wars", pl.DataFrame(schema=state.get_table("countries_wars").schema))
    presenter = MilitaryPresenter()
    weapon = presenter.strategic_inventory_for_country(state, "USA")[0]

    missing_context = presenter.strategic_launch_preview(state, "USA", weapon, 2)
    approved_context = presenter.strategic_launch_preview(state, "USA", weapon, 2, "cabinet")

    assert missing_context["can_launch"] is False
    assert "Select a configured launch authorization context." in missing_context["reasons"]
    assert approved_context["can_launch"] is True
    assert approved_context["authorization"] == "authorized by cabinet"


def test_panel_renders_all_configured_payload_options_and_target_defense_estimate() -> None:
    state = _strategic_ui_state()
    panel = StrategicWarfarePanel()
    context = SimpleNamespace(
        target_tag="USA", selected_region_id=2, is_own_country=True,
        net_client=SimpleNamespace(player_id="USA", send_action=MagicMock()),
    )
    mock_imgui = MagicMock()
    mock_imgui.begin_combo.return_value = True
    mock_imgui.selectable.return_value = (False, False)
    mock_imgui.button.return_value = False

    with patch("src.client.ui.panels.military.strategic_warfare_panel.imgui", mock_imgui), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_required_tables"
    ), patch("src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text"):
        panel._render_content(state, context)

    rendered = " ".join(
        str(call.args[0])
        for call in mock_imgui.text.call_args_list + mock_imgui.text_disabled.call_args_list
    )
    payload_options = " ".join(str(call.args[0]) for call in mock_imgui.selectable.call_args_list)
    assert "Level 2: 200 kt · 4.25 km" in payload_options
    assert "Configured interception estimate 80.0%" in rendered
    assert "long_range · covers target · first 60% · second 50%" in rendered
    assert "coverage regions 2" in rendered
    assert "Selected target: 2 · CAN · region 2" in rendered
    assert "authorized by active war" in rendered
    assert "Estimated resolution: 5 min" in rendered
    assert "Production: $25 · 5 min per weapon" in rendered


def test_panel_dispatches_production_action_for_configured_design() -> None:
    state = _strategic_ui_state()
    panel = StrategicWarfarePanel()
    send_action = MagicMock()
    context = SimpleNamespace(
        target_tag="USA", selected_region_id=2, is_own_country=True,
        net_client=SimpleNamespace(player_id="USA", send_action=send_action),
    )
    mock_imgui = MagicMock()
    mock_imgui.begin_combo.return_value = False
    mock_imgui.button.side_effect = [False, False, True]

    with patch("src.client.ui.panels.military.strategic_warfare_panel.imgui", mock_imgui), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_required_tables"
    ), patch("src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text"):
        panel._render_content(state, context)

    action = send_action.call_args.args[0]
    assert isinstance(action, ActionProduceStrategicWeapon)
    assert action.country_tag == "USA"
    assert action.weapon_id == "usa-icbm"
    assert action.quantity == 1
