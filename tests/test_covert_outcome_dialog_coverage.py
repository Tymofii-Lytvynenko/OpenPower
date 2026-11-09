from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.components.shared.covert_outcome_dialog as outcome_module
from src.client.ui.components.shared.covert_outcome_dialog import CovertOutcomeDialog


def _install_ui(monkeypatch, *, opened=True, content_visible=True, exit_clicked=False):
    imgui = Mock()
    imgui.WindowFlags_ = SimpleNamespace(no_scrollbar=1, no_scroll_with_mouse=2, no_title_bar=4)
    imgui.get_io.return_value = SimpleNamespace(display_size=SimpleNamespace(x=800, y=600))
    ui = Mock()
    ui.path.side_effect = lambda slot: f"outcome/{slot}"
    ui.button.return_value = exit_clicked
    windows = []
    frames = []

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield opened

    @contextmanager
    def child_frame(*args, **kwargs):
        frames.append((args, kwargs))
        yield content_visible

    monkeypatch.setattr(outcome_module, "imgui", imgui)
    monkeypatch.setattr(outcome_module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(outcome_module, "GMLWidgets", Mock(return_value=ui))
    monkeypatch.setattr(outcome_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(outcome_module, "center_window", Mock(return_value=(123.0, 45.0)))
    return imgui, ui, windows, frames


def _mission(**changes):
    mission = {
        "id": "mission-1",
        "owner_country_id": "UKR",
        "target_country_id": "POL",
        "mission_type": "civilian_sabotage",
        "target_sector": "civilian",
        "target_resource_id": "oil",
        "target_unit_category": None,
        "cell_id": "cell-1",
        "complexity": "high",
        "framed_country_id": None,
        "result": "partial_success",
        "_viewer_role": "owner",
    }
    mission.update(changes)
    return mission


def _dialog(mission):
    dialog = CovertOutcomeDialog()
    dialog._presenter.covert_missions_for_country = Mock(return_value=[mission])
    dialog.show(mission["id"], "ukr")
    return dialog


def _state(*, cells=None, incidents=None):
    tables = {}
    if cells is not None:
        tables["covert_cells"] = SimpleNamespace(to_dicts=lambda: cells)
    if incidents is not None:
        tables["covert_incidents"] = SimpleNamespace(to_dicts=lambda: incidents)
    return SimpleNamespace(tables=tables)


def test_render_skips_closed_or_stale_outcomes():
    dialog = CovertOutcomeDialog()
    state = _state()
    dialog.render(state)
    assert dialog._mission_id == ""

    mission = _mission(result="")
    dialog = _dialog(mission)
    dialog.render(state)
    assert dialog._mission_id == ""


def test_own_outcome_renders_cell_mission_summary_and_civilian_resource(monkeypatch):
    imgui, ui, windows, frames = _install_ui(monkeypatch)
    mission = _mission()
    dialog = _dialog(mission)
    state = _state(
        cells=[
            {"id": "other", "country_id": "UKR", "cell_name": "Other cell"},
            {"id": "cell-1", "country_id": "POL", "cell_name": "Foreign cell"},
            {"id": "cell-1", "country_id": "UKR", "cell_name": "Harbor cell"},
        ],
        incidents=[
            {"mission_id": "mission-1", "audience_country_ids": ["UKR"], "summary": "Warehouse damaged."},
            {"mission_id": "mission-1", "audience_country_ids": ["POL"], "summary": "Private report."},
        ],
    )

    dialog.render(state)

    assert dialog._mission_id == "mission-1"
    assert windows[0][1]["test_id"] == "covert.outcome.own"
    assert windows[0][1]["gml_template"] == "Covert_Actions_Mission_Outcome"
    assert (windows[0][1]["x"], windows[0][1]["y"], windows[0][1]["w"], windows[0][1]["h"]) == (
        123.0, 45.0, 451, 252,
    )
    assert any(call.args == ("txtCellName", "Harbor cell",) for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtMissionType", "Sabotage") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtSector", "Civilian") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtResourceUnit", outcome_module.resource_label("oil")) for call in ui.text.call_args_list)
    assert imgui.text_wrapped.call_args.args[0] == "Partial Success\nWarehouse damaged."
    assert frames[0][0] == ("outcome/txtResult",)


def test_own_outcome_uses_fallback_values_and_respects_hidden_result_frame(monkeypatch):
    imgui, ui, _windows, _frames = _install_ui(monkeypatch, content_visible=False)
    mission = _mission(
        mission_type="unknown_operation",
        target_sector=None,
        target_resource_id=None,
        target_unit_category=None,
        complexity=None,
        cell_id=None,
    )
    dialog = _dialog(mission)
    dialog.render(_state())

    assert any(call.args[:2] == ("txtCellName", "Unavailable") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtSector", "Not recorded") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtComplexity", "Not Recorded") for call in ui.text.call_args_list)
    assert imgui.text_wrapped.called is False


def test_attacked_outcome_discloses_target_description_and_close_action(monkeypatch):
    imgui, ui, windows, _frames = _install_ui(monkeypatch, exit_clicked=True)
    category, label = outcome_module.UNIT_CATEGORY_OPTIONS[0]
    mission = _mission(
        owner_country_id="POL",
        target_country_id="UKR",
        mission_type="military_disruption",
        target_sector="military",
        target_resource_id=None,
        target_unit_category=category,
        _viewer_role="target",
        result="failed",
    )
    dialog = _dialog(mission)
    state = _state(incidents=[
        {"mission_id": "mission-1", "audience_country_ids": ["UKR"], "summary": "Operation discovered."},
    ])

    dialog.render(state)

    assert windows[0][1]["test_id"] == "covert.outcome.attacked"
    assert windows[0][1]["gml_template"] == "Covert_Actions_Mission_Outcome_Attacked"
    assert windows[0][1]["flags"] == (
        imgui.WindowFlags_.no_scrollbar
        | imgui.WindowFlags_.no_scroll_with_mouse
        | imgui.WindowFlags_.no_title_bar
    )
    assert any(call.args == ("lblTitle", "DISCOVERED OPERATION") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtMission", "Disruption") for call in ui.text.call_args_list)
    assert any(call.args[:2] == ("txtOutcome", "Failed") for call in ui.text.call_args_list)
    assert imgui.text_wrapped.call_args.args[0] == f"Operation discovered.\nTarget: Military · {label}"
    assert dialog._mission_id == ""


def test_framed_outcome_hides_discoverable_details_and_uses_implication_copy(monkeypatch):
    imgui, ui, windows, _frames = _install_ui(monkeypatch)
    mission = _mission(
        owner_country_id="POL",
        target_country_id="UKR",
        framed_country_id="DEU",
        _viewer_role="framed",
    )
    dialog = _dialog(mission)

    dialog.render(_state())

    assert windows[0][1]["w"] == 401
    assert windows[0][1]["h"] == 105
    assert any(call.args == ("lblTitle", "YOUR COUNTRY WAS FRAMED") for call in ui.text.call_args_list)
    assert not any(call.args[0] == "lblOutcome" for call in ui.text.call_args_list)
    assert any(call.args == ("lblEffect", "IMPLICATION") for call in ui.text.call_args_list)
    assert imgui.text_wrapped.call_args.args[0] == "Your country was implicated in a covert operation."


def test_closed_window_clears_active_mission_and_target_descriptions_are_safe(monkeypatch):
    _install_ui(monkeypatch, opened=False)
    dialog = _dialog(_mission())
    dialog.render(_state())
    assert dialog._mission_id == ""

    assert CovertOutcomeDialog._target_description(
        {"target_resource_id": "oil"}, "civilian",
    ) == f"Civilian · {outcome_module.resource_label('oil')}"
    category, label = outcome_module.UNIT_CATEGORY_OPTIONS[0]
    assert CovertOutcomeDialog._target_description(
        {"target_unit_category": category}, "military",
    ) == f"Military · {label}"
    assert CovertOutcomeDialog._target_description(
        {"target_unit_category": "unknown"}, "military",
    ) == ""
    assert CovertOutcomeDialog._target_description({}, "unknown") == ""
