from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.panels.service import objectives_window_content as content_module
from src.client.ui.panels.service.objectives_window_content import ObjectivesWindowContent


class FakeWidgets:
    calls = []
    button_results = {}
    rects = {}

    def __init__(self, root):
        self.root = root

    def path(self, slot):
        return f"{self.root}/{slot}"

    def frame(self, slot):
        self.calls.append(("frame", slot))

    def text_at(self, slot, value, **kwargs):
        self.calls.append(("text_at", slot, value, kwargs))

    def button_at(self, slot, label, test_id, **kwargs):
        self.calls.append(("button_at", slot, label, test_id, kwargs))
        return self.button_results.get(test_id, False)

    def rect(self, slot):
        return self.rects.get(slot)


class FakeSession:
    def __init__(self, *, group_rect=None, tab_names=("DESCRIPTION", "OBJECTIVES", "TIPS"), missing_tabs=()):
        self.group_rect = group_rect
        self.tab_names = tab_names
        self.missing_tabs = set(missing_tabs)

    def apply_tab_page_runtime_geometry(self, path):
        return SimpleNamespace(tab_names=self.tab_names)

    def rect_for(self, path):
        return self.group_rect

    def tab_button_rect(self, path, index):
        if index in self.missing_tabs:
            return None
        return SimpleNamespace(x=10 + index * 30, y=20, width=28, height=16)


def overview(*, campaign=None, scenario=None, objectives=()):
    return SimpleNamespace(campaign=campaign, scenario=scenario, objectives=list(objectives))


def install_ui(monkeypatch, *, child_open=True, session=None):
    FakeWidgets.calls = []
    FakeWidgets.button_results = {}
    FakeWidgets.rects = {}
    ui = FakeWidgets("Objectives_Window")
    imgui = Mock()
    imgui.get_style.return_value = SimpleNamespace(font_scale_main=1.0, font_scale_dpi=1.0)
    imgui.begin_child.return_value = child_open
    monkeypatch.setattr(content_module, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(content_module, "imgui", imgui)
    monkeypatch.setattr(content_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(content_module.Prims, "meter", Mock())
    return SimpleNamespace(ui=ui, imgui=imgui, session=session)


def test_render_description_tab_draws_header_campaign_state_and_source_frames(monkeypatch):
    group = SimpleNamespace(x=5, y=10, width=100, height=20)
    ui_state = install_ui(monkeypatch, session=FakeSession(group_rect=group))
    ui_state.ui.rects["frmInner/frmInner/tabInfo/Tab1/frmInner"] = SimpleNamespace(width=400, height=300)
    content = ObjectivesWindowContent()
    campaign = {"scenario_id": "campaign-1", "outcome": "victory", "outcome_reason": "All goals met.",
                "sandbox_continuation": True}
    scenario = {"title": "The Long Campaign", "description": "A detailed scenario."}

    content.render(overview(campaign=campaign, scenario=scenario), "UKR", 120, Mock())

    assert [call[1] for call in FakeWidgets.calls if call[0] == "frame"] == [
        "frmInner", "frmInner/frmInner", "frmInner/frmInner/frmInfo", "frmInner/frmInner/tabInfo",
        "frmInner/frmInner/tabInfo/Tab1/frmInner",
    ]
    assert any(call[2] == "The Long Campaign" for call in FakeWidgets.calls if call[0] == "text_at")
    assert any(call[2] == "UKR" for call in FakeWidgets.calls if call[0] == "text_at")
    ui_state.imgui.text_wrapped.assert_any_call("A detailed scenario.", test_id="objectives.description.text")
    ui_state.imgui.text_colored.assert_called_once()
    ui_state.imgui.text_wrapped.assert_any_call("All goals met.")
    ui_state.imgui.text_disabled.assert_called_once_with("Sandbox continuation is enabled.")
    assert ui_state.imgui.push_font.call_args_list == [((None, 9.0), {}), ((None, 9.0), {})]
    assert ui_state.imgui.pop_font.call_count == 2


def test_render_empty_description_and_absent_campaign_use_explicit_fallbacks(monkeypatch):
    ui_state = install_ui(monkeypatch, session=None)
    ui_state.ui.rects["frmInner/frmInner/tabInfo/Tab1/frmInner"] = SimpleNamespace(width=400, height=300)
    content = ObjectivesWindowContent()

    content.render(overview(), "", 0, Mock())

    texts = [call[2] for call in FakeWidgets.calls if call[0] == "text_at"]
    assert "No active campaign" in texts
    assert "—" in texts
    ui_state.imgui.text_disabled.assert_any_call(
        "No campaign description is available.", test_id="objectives.description.empty",
    )
    ui_state.imgui.text_disabled.assert_any_call("No campaign is active for this country.")
    assert not any(call[0] == "button_at" for call in FakeWidgets.calls)


@pytest.mark.parametrize("active_tab", [1, 2])
def test_render_routes_selected_objectives_and_tips_tabs(monkeypatch, active_tab):
    ui_state = install_ui(monkeypatch, session=None)
    content = ObjectivesWindowContent()
    content._active_tab = active_tab
    content._render_goals_tab = Mock()
    content._render_tips_tab = Mock()
    content._render_description_tab = Mock()
    data = overview()
    advice = Mock()

    content.render(data, "UKR", 42, advice)

    content._render_description_tab.assert_not_called()
    if active_tab == 1:
        content._render_goals_tab.assert_called_once_with(ui_state.ui, data, 42)
        content._render_tips_tab.assert_not_called()
    else:
        content._render_tips_tab.assert_called_once_with(ui_state.ui, advice)
        content._render_goals_tab.assert_not_called()


def test_render_tabs_selects_tab_and_always_restores_button_style(monkeypatch):
    ui_state = install_ui(monkeypatch, session=None)
    content = ObjectivesWindowContent()
    session = FakeSession(group_rect=SimpleNamespace(x=4, y=8, width=100, height=20))
    FakeWidgets.button_results["objectives.tab.goals"] = True

    content._render_tabs(ui_state.ui, session, "tabs", SimpleNamespace(tab_names=("a", "b", "c")))

    assert content._active_tab == 1
    assert len([call for call in FakeWidgets.calls if call[0] == "button_at"]) == 3
    assert ui_state.imgui.push_style_color.call_count == 3
    assert ui_state.imgui.pop_style_color.call_count == 3


@pytest.mark.parametrize(
    ("session", "tab_layout"),
    [
        (FakeSession(group_rect=None), SimpleNamespace(tab_names=("a", "b", "c"))),
        (FakeSession(group_rect=SimpleNamespace(x=0, y=0, width=1, height=1)), SimpleNamespace(tab_names=("a",))),
    ],
)
def test_render_tabs_skips_missing_group_or_incompatible_source_tabs(monkeypatch, session, tab_layout):
    ui_state = install_ui(monkeypatch, session=None)
    content = ObjectivesWindowContent()

    content._render_tabs(ui_state.ui, session, "tabs", tab_layout)

    assert not any(call[0] == "button_at" for call in FakeWidgets.calls)
    ui_state.imgui.push_font.assert_not_called()


def test_render_tabs_skips_individual_missing_tab_rectangles(monkeypatch):
    ui_state = install_ui(monkeypatch, session=None)
    content = ObjectivesWindowContent()
    session = FakeSession(
        group_rect=SimpleNamespace(x=0, y=0, width=100, height=20), missing_tabs=(1,),
    )

    content._render_tabs(ui_state.ui, session, "tabs", SimpleNamespace(tab_names=("a", "b", "c")))

    assert len([call for call in FakeWidgets.calls if call[0] == "button_at"]) == 2
    assert ui_state.imgui.push_style_color.call_count == 2
    assert ui_state.imgui.pop_style_color.call_count == 2


def test_description_tab_closes_child_when_source_geometry_or_visibility_is_missing(monkeypatch):
    ui_state = install_ui(monkeypatch)
    content = ObjectivesWindowContent()
    slot = "frmInner/frmInner/tabInfo/Tab1/frmInner"
    ui_state.ui.rects[slot] = None

    content._render_description_tab(ui_state.ui, overview(scenario={"description": "hidden"}))

    ui_state.imgui.end_child.assert_called_once_with()
    ui_state.imgui.text_wrapped.assert_not_called()

    ui_state.imgui.reset_mock()
    ui_state.imgui.get_style.return_value = SimpleNamespace(font_scale_main=1, font_scale_dpi=1)
    ui_state.ui.rects[slot] = SimpleNamespace(width=100, height=80)
    ui_state.imgui.begin_child.return_value = False
    content._render_description_tab(ui_state.ui, overview(scenario={"description": "hidden"}))
    assert ui_state.imgui.end_child.call_count == 1
    ui_state.imgui.text_wrapped.assert_not_called()


def test_goals_tab_renders_deadline_and_objectives_or_empty_state(monkeypatch):
    ui_state = install_ui(monkeypatch)
    content = ObjectivesWindowContent()
    slot = "frmInner/frmInner/tabInfo/Tab2/frmObjectives/lstGoals"
    ui_state.ui.rects[slot] = SimpleNamespace(width=200, height=100)
    content._render_objective = Mock()
    campaign = {"started_at_minute": 100}
    scenario = {"max_duration_minutes": 300}
    objective_rows = [{"id": "goal-1"}, {"id": "goal-2"}]

    content._render_goals_tab(ui_state.ui, overview(campaign=campaign, scenario=scenario, objectives=objective_rows), 200)

    time_label = [call[2] for call in FakeWidgets.calls if call[0] == "text_at"]
    assert "3h" in time_label
    assert "TIME LIMIT" in time_label
    assert content._render_objective.call_count == 2
    ui_state.imgui.end_child.assert_called_once_with()

    FakeWidgets.calls.clear()
    ui_state.imgui.reset_mock()
    content._render_goals_tab(ui_state.ui, overview(scenario={}, objectives=()), 0)
    time_label = [call[2] for call in FakeWidgets.calls if call[0] == "text_at"]
    assert "NO TIME LIMIT" in time_label
    ui_state.imgui.text_disabled.assert_called_once_with(
        "This campaign has no configured objectives.", test_id="objectives.goals.empty",
    )


def test_goals_tab_closes_child_when_source_child_cannot_be_rendered(monkeypatch):
    ui_state = install_ui(monkeypatch)
    content = ObjectivesWindowContent()
    ui_state.ui.rects["frmInner/frmInner/tabInfo/Tab2/frmObjectives/lstGoals"] = None

    content._render_goals_tab(ui_state.ui, overview(), 0)

    ui_state.imgui.end_child.assert_called_once_with()


def test_tips_tab_calls_advice_only_when_source_child_is_open(monkeypatch):
    ui_state = install_ui(monkeypatch)
    content = ObjectivesWindowContent()
    advice = Mock()
    slot = "frmInner/frmInner/tabInfo/Tab3/frmInner"
    ui_state.ui.rects[slot] = SimpleNamespace(width=100, height=50)

    content._render_tips_tab(ui_state.ui, advice)

    advice.assert_called_once_with()
    ui_state.imgui.text_disabled.assert_called_once_with(
        "No scenario-authored tips are stored in OpenPower.",
        test_id="objectives.tips.unavailable",
    )
    ui_state.imgui.end_child.assert_called_once_with()

    ui_state.imgui.reset_mock()
    ui_state.imgui.begin_child.return_value = False
    advice.reset_mock()
    content._render_tips_tab(ui_state.ui, advice)
    advice.assert_not_called()
    ui_state.imgui.end_child.assert_called_once_with()


def test_source_font_scales_from_style_and_restores_font_when_body_fails(monkeypatch):
    ui_state = install_ui(monkeypatch)
    ui_state.imgui.get_style.return_value = SimpleNamespace(font_scale_main=2.0, font_scale_dpi=1.5)

    with pytest.raises(RuntimeError, match="render failed"):
        with ObjectivesWindowContent._source_font():
            raise RuntimeError("render failed")

    ui_state.imgui.push_font.assert_called_once_with(None, 3.0)
    ui_state.imgui.pop_font.assert_called_once_with()


def test_source_child_requires_layout_rect_and_passes_source_geometry(monkeypatch):
    ui_state = install_ui(monkeypatch)
    ui_state.ui.rects["page"] = None
    assert ObjectivesWindowContent._begin_source_child(ui_state.ui, "page", "page.id") is False
    ui_state.imgui.begin_child.assert_not_called()

    ui_state.ui.rects["page"] = SimpleNamespace(width=120, height=80)
    ui_state.imgui.begin_child.return_value = True
    assert ObjectivesWindowContent._begin_source_child(ui_state.ui, "page", "page.id") is True
    ui_state.imgui.begin_child.assert_called_once_with(
        "##page.id", (120, 80), True, test_id="page.id", gml_id="Objectives_Window/page",
    )


@pytest.mark.parametrize(
    ("campaign", "scenario", "now", "expected"),
    [
        (None, {"max_duration_minutes": 100}, 20, None),
        ({"started_at_minute": 5}, None, 20, None),
        ({"started_at_minute": 5}, {"max_duration_minutes": 0}, 20, None),
        ({"started_at_minute": 5}, {"max_duration_minutes": 10}, 8, 7),
        ({"started_at_minute": 5}, {"max_duration_minutes": 10}, 99, 0),
    ],
)
def test_campaign_minutes_remaining_handles_absent_limits_and_expired_deadlines(campaign, scenario, now, expected):
    assert ObjectivesWindowContent._campaign_minutes_remaining(campaign, scenario, now) == expected


@pytest.mark.parametrize((("minutes", "expected")), [(0, "0h"), (59, "0h"), (60, "1h"), (1500, "1d 1h"), (-1, "0h")])
def test_format_duration_uses_days_and_remaining_hours(minutes, expected):
    assert ObjectivesWindowContent._format_duration(minutes) == expected


def test_objective_renderer_clamps_progress_and_marks_completed_rows(monkeypatch):
    ui_state = install_ui(monkeypatch)
    row = {"id": "goal", "title": "Victory", "status": "completed", "progress": 1.5}

    ObjectivesWindowContent._render_objective(row, now=20)

    ui_state.imgui.checkbox.assert_called_once_with(
        "##objective-complete:goal", True, test_id="objectives.goal.completed.goal",
    )
    content_module.Prims.meter.assert_called_once_with("", 100.0, content_module.GAMETHEME.colors.positive)
    ui_state.imgui.dummy.assert_called_once_with((0.0, 6.0))


def test_completion_indicator_restores_disabled_scope_if_imgui_raises(monkeypatch):
    ui_state = install_ui(monkeypatch)
    ui_state.imgui.checkbox.side_effect = RuntimeError("checkbox failed")

    with pytest.raises(RuntimeError, match="checkbox failed"):
        ObjectivesWindowContent._render_completion_indicator("goal", "COMPLETED")

    ui_state.imgui.begin_disabled.assert_called_once_with()
    ui_state.imgui.end_disabled.assert_called_once_with()


def test_objective_details_render_values_deadline_hold_blocker_and_evidence(monkeypatch):
    ui_state = install_ui(monkeypatch)
    row = {
        "description": "Control the capital.",
        "objective_type": "region_control",
        "current_value": 2,
        "target_value": 3,
        "remaining": 1,
        "deadline_at_minute": 3000,
        "hold_duration_minutes": 60,
        "held_minutes": 20,
        "status": "blocked",
        "missing_data_reason": "Region control is unknown.",
        "evidence_json": '[{"source_table":"regions","game_minute":100,"current_value":2,"target_value":3}]',
    }

    ObjectivesWindowContent._render_objective_details(row, now=120, objective_id="capital")

    ui_state.imgui.push_text_wrap_pos.assert_called_once_with(0.0)
    ui_state.imgui.pop_text_wrap_pos.assert_called_once_with()
    assert any("Current 2.00 / target 3.00; remaining 1.00" in str(call) for call in ui_state.imgui.text_disabled.call_args_list)
    assert any("Deadline: 2 day(s) remaining" in str(call) for call in ui_state.imgui.text_disabled.call_args_list)
    assert any("Held 20 / 60 minute(s)" in str(call) for call in ui_state.imgui.text_disabled.call_args_list)
    ui_state.imgui.text_colored.assert_any_call(
        content_module.GAMETHEME.colors.warning, "Region control is unknown.",
    )
    assert any("Latest evidence: regions at minute 100 (2.00 / 3.00)" in str(call) for call in ui_state.imgui.text_disabled.call_args_list)


def test_optional_objective_details_skip_empty_description_values_dates_holds_and_evidence(monkeypatch):
    ui_state = install_ui(monkeypatch)
    row = {"status": "active", "reason": "Waiting for a new turn.", "evidence_json": "bad json"}

    ObjectivesWindowContent._render_objective_details(row, now=0, objective_id="goal")

    ui_state.imgui.push_text_wrap_pos.assert_not_called()
    ui_state.imgui.text_disabled.assert_called_once_with("Waiting for a new turn.")
    ui_state.imgui.text_colored.assert_not_called()


def test_blocked_reason_uses_default_when_no_reason_is_recorded(monkeypatch):
    ui_state = install_ui(monkeypatch)

    ObjectivesWindowContent._render_blocked_reason({"status": "blocked"})

    ui_state.imgui.text_colored.assert_called_once_with(
        content_module.GAMETHEME.colors.warning, "Required data is missing.",
    )
