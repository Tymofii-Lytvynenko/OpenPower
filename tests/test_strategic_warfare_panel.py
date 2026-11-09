from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.military.strategic_planner import StrategicPlanner
from src.client.ui.panels.military.strategic_warfare_panel import StrategicWarfarePanel
from src.shared.actions import ActionProduceStrategicWeapon
from src.shared.state import GameState
from src.client.ui.panels.military.strategic_plan import StrategicPlan


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


def test_strategic_draft_builds_only_authorized_intent():
    state = _strategic_ui_state()
    plan = StrategicPlan(country="USA", target_region=2, selected_weapons={"usa-icbm"})
    actions, reasons = plan.actions(state, MilitaryPresenter(), "local")
    assert not reasons
    assert len(actions) == 1
    assert actions[0].target_country_tag == "CAN"
    assert state.tables["strategic_launch_orders"].is_empty()


def test_planner_preserves_selected_payload_profile_in_launch_action():
    state = _strategic_ui_state()
    presenter = MilitaryPresenter()
    planner = StrategicPlanner(presenter)
    selected_payloads = {"usa-icbm": 2}

    planner.open("USA", 2, payload_levels=selected_payloads)
    selected_payloads["usa-icbm"] = 1
    planner.plan.selected_weapons.add("usa-icbm")

    actions, reasons = planner.plan.actions(state, presenter, "local")

    assert not reasons
    assert len(actions) == 1
    assert actions[0].payload_level == 2


def test_strategic_draft_rechecks_inventory_before_dispatch():
    state = _strategic_ui_state()
    plan = StrategicPlan(country="USA", target_region=2, selected_weapons={"usa-icbm"})
    state.update_table("strategic_weapons", state.tables["strategic_weapons"].with_columns(pl.lit(0).alias("ready")))
    actions, reasons = plan.actions(state, MilitaryPresenter(), "local")
    assert not actions
    assert any("not ready" in reason for reason in reasons)


def test_multiple_target_draft_is_not_partially_dispatched():
    state = _strategic_ui_state()
    weapon = state.tables["strategic_weapons"].to_dicts()[0]
    weapon["launch_cost"] = 60.0
    state.update_table("strategic_weapons", pl.DataFrame([weapon, dict(weapon,id="second")],
                       schema=state.tables["strategic_weapons"].schema))
    plan = StrategicPlan(country="USA", selected_weapons={"usa-icbm", "second"},
                         assignments={"usa-icbm": 2, "second": 2})
    actions, reasons = plan.actions(state, MilitaryPresenter(), "local", multiple=True)
    assert not actions
    assert any("complete launch plan" in reason for reason in reasons)


def test_draft_needs_current_target_and_authorization():
    state = _strategic_ui_state()
    plan = StrategicPlan(country="USA", target_region=2, selected_weapons={"missing", "usa-icbm"})
    assert not plan.actions(state, MilitaryPresenter(), "local")[0]
    plan.selected_weapons = {"usa-icbm"}
    state.update_table("countries_wars", state.tables["countries_wars"].clear())
    actions, reasons = plan.actions(state, MilitaryPresenter(), "local")
    assert not actions and reasons


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
        for call in (
            mock_imgui.text.call_args_list
            + mock_imgui.text_disabled.call_args_list
            + mock_imgui.text_wrapped.call_args_list
        )
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
    mock_imgui.button.side_effect = lambda label, *args, **kwargs: label.startswith("PRODUCE ONE")

    with patch("src.client.ui.panels.military.strategic_warfare_panel.imgui", mock_imgui), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_required_tables"
    ), patch("src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text"):
        panel._render_content(state, context)

    action = send_action.call_args.args[0]
    assert isinstance(action, ActionProduceStrategicWeapon)
    assert action.country_tag == "USA"
    assert action.weapon_id == "usa-icbm"
    assert action.quantity == 1


@pytest.mark.parametrize(
    ("viewport_width", "window_open", "content_available"),
    [
        (800, False, True),
        (1600, True, False),
        (1600, True, True),
    ],
)
def test_render_positions_window_and_opens_planner_only_for_available_content(
    viewport_width: int,
    window_open: bool,
    content_available: bool,
) -> None:
    panel = StrategicWarfarePanel()
    context = SimpleNamespace()
    mock_imgui = MagicMock()
    mock_imgui.get_main_viewport.return_value.size = SimpleNamespace(
        x=viewport_width,
        y=400,
    )
    window = MagicMock()
    window.return_value.__enter__.return_value = window_open
    panel._render_content = MagicMock(return_value=content_available)
    panel._planner.render = MagicMock()

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.WindowManager.window",
        window,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.WIDE_LAYOUT_MIN_WIDTH",
        1000,
    ):
        result = panel.render(_strategic_ui_state(), context)

    max_x = max(0.0, viewport_width - panel._GML_SIZE[0] - panel._VIEWPORT_MARGIN)
    expected_x = (
        max_x
        if viewport_width < 1000
        else min(max(panel._INITIAL_POSITION[0], viewport_width - panel._GML_SIZE[0] * 2.0), max_x)
    )
    assert window.call_args.kwargs["x"] == expected_x
    assert window.call_args.kwargs["y"] == 0.0
    assert result is window_open
    assert panel._render_content.call_count == int(window_open)
    assert panel._planner.render.call_count == int(window_open and content_available)


def test_content_returns_when_required_tables_are_missing() -> None:
    panel = StrategicWarfarePanel()

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_required_tables",
        return_value=False,
    ):
        assert panel._render_content(_strategic_ui_state(), SimpleNamespace()) is False


def test_content_opens_owned_target_planner_and_renders_empty_inventory() -> None:
    panel = StrategicWarfarePanel()
    panel._presenter = MagicMock()
    panel._presenter.strategic_inventory_for_country.return_value = []
    panel._presenter.strategic_payload_profiles.return_value = {}
    panel._planner.open = MagicMock()
    panel._render_defenses = MagicMock()
    panel._render_production_orders = MagicMock()
    panel._render_recent_strikes = MagicMock()
    context = SimpleNamespace(
        target_tag=" usa ",
        selected_region_id=2,
        is_own_country=True,
    )
    mock_imgui = MagicMock()
    mock_imgui.button.return_value = True

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_required_tables",
        return_value=True,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.draw_empty_state",
    ) as draw_empty:
        assert panel._render_content(_strategic_ui_state(), context) is True

    panel._planner.open.assert_called_once_with("USA", 2, payload_levels={})
    draw_empty.assert_called_once()
    panel._render_defenses.assert_called_once()
    panel._render_production_orders.assert_called_once()
    panel._render_recent_strikes.assert_called_once()


def test_weapon_selection_prepares_launch_and_renders_each_target_defense_state() -> None:
    state = _strategic_ui_state()
    panel = StrategicWarfarePanel()
    context = SimpleNamespace(
        target_tag="USA",
        selected_region_id=2,
        is_own_country=True,
        net_client=SimpleNamespace(player_id="USA", send_action=MagicMock()),
    )
    row = {
        "id": "usa-icbm",
        "weapon_class": "icbm",
        "ready": 1,
        "quantity": 2,
        "defense_rating": 0.25,
        "research_permitted": True,
        "payload_cap": 2,
        "payload_level": 1,
    }
    defense = {
        "interception_probability": 0.3,
        "covered_layers": [
            {
                "layer": "long_range",
                "covered": True,
                "researched_and_operational": True,
                "coverage_region_ids": [1],
                "coverage_radius_km": 20.0,
                "range_km": 100.0,
                "effective_first_attempt_probability": 0.6,
                "effective_second_attempt_probability": 0.5,
                "layer_interception_probability": 0.8,
            },
            {
                "layer": "mid_range",
                "covered": True,
                "researched_and_operational": False,
            },
            {
                "layer": "point",
                "covered": False,
                "researched_and_operational": True,
                "coverage_radius_km": 10.0,
            },
        ],
    }
    mock_imgui = MagicMock()
    mock_imgui.begin_combo.return_value = True
    mock_imgui.selectable.side_effect = lambda label, *_args, **_kwargs: (
        label == "cabinet" or label.startswith("Level 2:"),
        False,
    )
    mock_imgui.button.side_effect = lambda label, *_args, **_kwargs: label.startswith(
        "PREPARE MILITARY"
    )

    with patch.object(
        panel._presenter,
        "strategic_authorization_contexts",
        return_value=["cabinet"],
    ), patch.object(
        panel._presenter,
        "strategic_payload_profiles",
        return_value={1: (100.0, 1.0), 2: (200.0, 2.0)},
    ), patch.object(
        panel._presenter,
        "strategic_defense_estimate_for_region",
        return_value=defense,
    ), patch.object(
        panel._presenter,
        "strategic_launch_preview",
        return_value={
            "authorization": "authorized by cabinet",
            "flight_minutes": 4,
            "reasons": [],
            "can_launch": True,
        },
    ), patch.object(
        panel._presenter,
        "strategic_production_preview",
        return_value={"can_produce": False, "reasons": ["Production is unavailable."]},
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text",
    ):
        panel._render_weapon(state, context, "USA", row, {1: (100.0, 1.0), 2: (200.0, 2.0)})

    assert panel._selected_payloads["usa-icbm"] == 2
    assert panel._selected_authorization_contexts["USA"] == "cabinet"
    assert panel._planner.plan.target_mode == "military"
    assert panel._planner.plan.selected_weapons == {"usa-icbm"}
    assert panel._planner.plan.authorization_context == "cabinet"
    assert panel._planner.plan.payload_levels["usa-icbm"] == 2
    assert mock_imgui.same_line.call_count == 2
    rendered = " ".join(str(call.args[0]) for call in mock_imgui.text_wrapped.call_args_list)
    assert "covers target" in rendered
    assert "inactive or unresearched" in rendered
    assert "outside coverage" in rendered
    assert "regions 1; radius 20 km; range 100 km" in rendered
    assert "no configured area" in rendered


def test_weapon_without_research_and_pending_launch_shows_blocking_reasons() -> None:
    panel = StrategicWarfarePanel()
    mock_imgui = MagicMock()
    row = {
        "id": "usa-icbm",
        "weapon_class": "icbm",
        "ready": 0,
        "quantity": 1,
        "research_permitted": False,
    }
    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text",
    ):
        panel._render_weapon(_strategic_ui_state(), SimpleNamespace(), "USA", row, {})

    mock_imgui.text_wrapped.assert_any_call(
        "Unavailable: complete the strategic program and weapon research first."
    )

    state = _strategic_ui_state()
    row["research_permitted"] = True
    row["pending_order_status"] = "pending"
    row["pending_target_region_id"] = 2
    panel._presenter.strategic_authorization_contexts = MagicMock(return_value=[])
    panel._presenter.strategic_payload_profiles = MagicMock(return_value={})
    panel._presenter.strategic_launch_preview = MagicMock(
        return_value={
            "authorization": "not authorized",
            "flight_minutes": 0,
            "reasons": ["Authorization is required."],
            "can_launch": False,
        }
    )
    panel._presenter.strategic_production_preview = MagicMock(
        return_value={"can_produce": False, "reasons": ["Production is unavailable."]}
    )
    context = SimpleNamespace(
        selected_region_id=None,
        is_own_country=True,
        net_client=None,
    )

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ), patch(
        "src.client.ui.panels.military.strategic_warfare_panel.Prims.right_align_text",
    ):
        panel._render_weapon(state, context, "USA", row, {})

    rendered = " ".join(str(call.args[0]) for call in mock_imgui.text_wrapped.call_args_list)
    assert "Select an enemy region to preview target coverage" in rendered
    assert "Authorization is required." in rendered
    assert "Pending launch · target region 2" in rendered
    assert "Production is unavailable." in rendered


def test_target_defense_handles_missing_estimate_and_empty_layer_list() -> None:
    panel = StrategicWarfarePanel()
    state = _strategic_ui_state()
    mock_imgui = MagicMock()
    panel._presenter.strategic_defense_estimate_for_region = MagicMock(
        return_value={"interception_probability": 0.0, "covered_layers": []}
    )

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ):
        panel._render_target_defense(state, "USA", 2, None, "")
        panel._render_target_defense(state, "USA", 2, {"id": 2}, "CAN")

    panel._presenter.strategic_defense_estimate_for_region.assert_called_once_with(
        state,
        "CAN",
        2,
    )
    rendered = " ".join(str(call.args[0]) for call in mock_imgui.text_wrapped.call_args_list)
    assert "Select an enemy region" in rendered
    assert "No configured defense layer" in rendered


def test_panel_history_sections_show_empty_states_and_recent_records() -> None:
    panel = StrategicWarfarePanel()
    mock_imgui = MagicMock()
    defenses = [
        {
            "layer": "long_range",
            "operational": True,
            "researched": True,
            "readiness": 1.0,
            "range_km": 1000.0,
            "first_attempt_probability": None,
        },
        {
            "layer": "point",
            "operational": True,
            "researched": False,
            "readiness": 0.5,
            "range_km": 100.0,
            "first_attempt_probability": None,
        },
    ]
    production_orders = [
        {"weapon_id": "usa-icbm", "quantity": 2, "status": "queued", "reason": "Budget approved."}
    ]
    launch_orders = [
        {"country_id": "", "target_mode": "civilian", "status": "resolved", "reason": "Impact recorded."}
    ]
    impacts = [
        {"region_id": 2, "category": "population", "severity": 0.25, "collateral": True},
        {"region_id": 3, "category": "infrastructure", "severity": 0.1, "collateral": False},
    ]

    with patch(
        "src.client.ui.panels.military.strategic_warfare_panel.imgui",
        mock_imgui,
    ):
        panel._presenter.missile_defense_for_country = MagicMock(side_effect=[[], defenses])
        panel._render_defenses(_strategic_ui_state(), "USA")
        panel._render_defenses(_strategic_ui_state(), "USA")

        panel._presenter.strategic_production_orders_for_country = MagicMock(
            side_effect=[[], production_orders]
        )
        panel._render_production_orders(_strategic_ui_state(), "USA")
        panel._render_production_orders(_strategic_ui_state(), "USA")

        panel._presenter.strategic_orders_for_country = MagicMock(
            side_effect=[[], launch_orders]
        )
        panel._presenter.strategic_impacts_for_country = MagicMock(side_effect=[[], impacts])
        panel._render_recent_strikes(_strategic_ui_state(), "USA")
        panel._render_recent_strikes(_strategic_ui_state(), "USA")

    disabled = " ".join(str(call.args[0]) for call in mock_imgui.text_disabled.call_args_list)
    rendered = " ".join(str(call.args[0]) for call in mock_imgui.text_wrapped.call_args_list)
    assert "No missile-defense layers are fielded." in disabled
    assert "No strategic weapon production orders." in disabled
    assert "No known launch orders." in disabled
    assert "readiness 100% · range 1,000 km · first attempt 60%" in rendered
    assert "Unknown · civilian · resolved" in " ".join(
        str(call.args[0]) for call in mock_imgui.text.call_args_list
    )
    assert "collateral" in rendered
    assert "intended" in rendered
