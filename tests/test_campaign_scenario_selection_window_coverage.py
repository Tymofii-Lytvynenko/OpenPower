from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.shared.campaign_scenario_selection_window as scenario_module
from src.client.ui.components.shared.campaign_scenario_selection_window import (
    CampaignScenarioSelectionWindow,
    _scenario_country_ids,
)


def _imgui_mock():
    imgui = Mock()
    imgui.Col_.text = 1
    imgui.begin_child.return_value = True
    imgui.selectable.return_value = (False, False)
    imgui.button.return_value = False
    return imgui


def test_render_routes_window_close_and_cancel(monkeypatch):
    state = {"open": True}

    @contextmanager
    def window(*_args, **_kwargs):
        yield state["open"]

    monkeypatch.setattr(scenario_module.WindowManager, "window", window)
    panel = CampaignScenarioSelectionWindow()
    panel._render_content = Mock()
    on_select, on_continue, on_cancel = Mock(), Mock(), Mock()

    panel.render(1280, 720, [], None, on_select, on_continue, on_cancel)
    state["open"] = False
    panel.render(1280, 720, [], None, on_select, on_continue, on_cancel)

    panel._render_content.assert_called_once_with([], None, on_select, on_continue, on_cancel)
    on_cancel.assert_called_once_with()


def test_content_selects_scenario_and_dispatches_continue_and_cancel(monkeypatch):
    imgui = _imgui_mock()
    imgui.begin_child.side_effect = [True, True]
    imgui.selectable.side_effect = [(True, False), (False, False)]
    imgui.button.side_effect = [False, False, False, True, True]
    monkeypatch.setattr(scenario_module, "imgui", imgui)
    ui = Mock()
    monkeypatch.setattr(scenario_module, "GMLWidgets", Mock(return_value=ui))
    preview = SimpleNamespace(
        scope="regional",
        max_duration_minutes=90,
        objectives=(),
        enabled_rules=(),
    )
    preview_scenario = Mock(return_value=preview)
    monkeypatch.setattr(scenario_module, "preview_campaign_scenario", preview_scenario)
    panel = CampaignScenarioSelectionWindow()
    on_select, on_continue, on_cancel = Mock(), Mock(), Mock()
    scenarios = [
        {"id": " "},
        {
            "id": "alpha",
            "title": "Alpha",
            "description": "A regional campaign.",
            "selectable_country_ids_json": '["ukr", "pol"]',
            "sandbox_allowed": False,
        },
        {"id": "beta", "title": "Beta"},
    ]

    panel._render_content(scenarios, "alpha", on_select, on_continue, on_cancel)

    on_select.assert_called_once_with("alpha")
    on_continue.assert_called_once_with()
    on_cancel.assert_called_once_with()
    preview_scenario.assert_called_once_with(scenarios[1])
    ui.frame.assert_any_call("frmInner/frmScenario/tabInfo")
    assert imgui.end_child.call_count == 2
    imgui.text_wrapped.assert_called_once_with(
        "A regional campaign.", test_id="new_game.scenario.description",
    )
    imgui.text_disabled.assert_any_call("Scenario outcome ends the campaign")


def test_scenario_list_handles_selection_empty_content_and_closed_child(monkeypatch):
    imgui = _imgui_mock()
    imgui.begin_child.side_effect = [True, True, False]
    imgui.selectable.side_effect = [(False, False), (True, False)]
    monkeypatch.setattr(scenario_module, "imgui", imgui)
    panel = CampaignScenarioSelectionWindow()
    ui = Mock()
    on_select = Mock()

    panel._render_scenario_list(
        ui,
        [{"id": "a", "title": ""}, {"id": " "}, {"id": "b"}],
        "b",
        on_select,
    )
    panel._render_scenario_list(ui, [], None, on_select)
    panel._render_scenario_list(ui, [], None, on_select)

    on_select.assert_called_once_with("b")
    imgui.text_wrapped.assert_called_once_with(
        "No enabled scenarios are available.", test_id="new_game.scenario.empty_list",
    )
    assert imgui.end_child.call_count == 3


def test_details_cover_closed_child_and_each_tab_state(monkeypatch):
    imgui = _imgui_mock()
    imgui.begin_child.side_effect = [True, True, True, True, True, True, True, False]
    imgui.button.side_effect = [
        False, False, False,
        False, False, False,
        False, True, False,
        False, True, False,
        False, False, True,
        False, False, True,
        True, False, False,
    ]
    monkeypatch.setattr(scenario_module, "imgui", imgui)
    previewer = Mock(side_effect=[
        SimpleNamespace(scope="global", max_duration_minutes=0, objectives=(), enabled_rules=()),
        SimpleNamespace(scope="global", max_duration_minutes=0, objectives=(), enabled_rules=()),
        SimpleNamespace(
            scope="regional",
            max_duration_minutes=30,
            objectives=(SimpleNamespace(title="Win", deadline="1937.01.01"),),
            enabled_rules=(),
        ),
        SimpleNamespace(scope="global", max_duration_minutes=0, objectives=(), enabled_rules=()),
        SimpleNamespace(scope="global", max_duration_minutes=0, objectives=(), enabled_rules=("no_wars",)),
        SimpleNamespace(scope="regional", max_duration_minutes=45, objectives=(), enabled_rules=()),
    ])
    monkeypatch.setattr(scenario_module, "preview_campaign_scenario", previewer)
    panel = CampaignScenarioSelectionWindow()
    ui = Mock()
    scenario = {"id": "alpha", "title": "Alpha", "sandbox_allowed": True}

    panel._render_details(ui, None)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)
    panel._render_details(ui, scenario)

    assert imgui.end_child.call_count == 8
    assert imgui.bullet_text.call_count == 2
    imgui.text_wrapped.assert_any_call(
        "Select an enabled campaign scenario to view its details.",
        test_id="new_game.scenario.empty_details",
    )
    imgui.text_disabled.assert_any_call("No limit", test_id="new_game.scenario.time_limit")
    imgui.text.assert_any_call("Time limit: 45 minutes")
    imgui.text_disabled.assert_any_call("Sandbox continuation enabled")
    imgui.text_wrapped.assert_any_call("This scenario has no configured objectives.", test_id="new_game.scenario.empty_objectives")
    imgui.text_wrapped.assert_any_call("No optional rules are enabled.", test_id="new_game.scenario.empty_rules")


def test_scenario_country_ids_normalize_json_and_reject_invalid_values():
    assert _scenario_country_ids(None) == []
    assert _scenario_country_ids({"selectable_country_ids_json": "not-json"}) == []
    assert _scenario_country_ids({"selectable_country_ids_json": '{"country": "UKR"}'}) == []
    assert _scenario_country_ids({
        "selectable_country_ids_json": '[" pol ", "UKR", "POL", "  "]',
    }) == ["POL", "UKR"]
    assert _scenario_country_ids({"selectable_country_ids_json": ["usa", "UKR"]}) == [
        "UKR", "USA",
    ]
