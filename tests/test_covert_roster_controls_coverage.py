from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.panels.military import covert_roster_controls as controls_module
from src.shared.actions import ActionRetargetCovertCell, ActionSetCovertCellActivity


class _RecordingImgui:
    HoveredFlags_ = SimpleNamespace(allow_when_disabled=1)

    def __init__(self, combos, *, hovered=False):
        self.combos = list(combos)
        self.hovered = hovered
        self.disabled_states = []
        self.combo_calls = []
        self.tooltips = []

    def begin_disabled(self, disabled):
        self.disabled_states.append(disabled)

    def combo(self, *args, **kwargs):
        self.combo_calls.append((args, kwargs))
        return self.combos.pop(0)

    def end_disabled(self):
        pass

    def is_item_hovered(self, _flags):
        return self.hovered

    def set_tooltip(self, message):
        self.tooltips.append(message)


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, *, named):
        assert named is True
        return iter(self.rows)


def _row(**overrides):
    row = {
        "id": "cell-1",
        "country_id": "UKR",
        "target_country_id": "POL",
        "status": "active",
        "communications_ready": True,
    }
    row.update(overrides)
    return row


def _context(**overrides):
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    context = {
        "target_tag": "UKR",
        "is_own_country": True,
        "net_client": client,
    }
    context.update(overrides)
    return SimpleNamespace(**context)


def test_render_submits_country_change_and_blocks_second_pending_edit(monkeypatch):
    options = [SimpleNamespace(tag="DEU", name="Germany"), SimpleNamespace(tag="FRA", name="France")]
    monkeypatch.setattr(controls_module, "country_options_from_state", lambda _state: options)
    imgui = _RecordingImgui([(True, 1), (True, 1)])
    monkeypatch.setattr(controls_module, "imgui", imgui)
    controls = controls_module.CovertRosterControls()
    context = _context()
    on_select = Mock()

    controls.render(
        SimpleNamespace(path=lambda name: f"row/{name}"),
        _row(),
        None,
        object(),
        context,
        on_select,
    )

    assert imgui.combo_calls[0][0][:3] == (
        "##assigned_country",
        0,
        ["POL", "Germany", "France"],
    )
    assert imgui.combo_calls[0][1] == {
        "test_id": "covert_ops.cell.cell-1.country",
        "gml_id": "row/cboCountry",
    }
    assert imgui.disabled_states == [False, True]
    assert on_select.call_count == 1
    context.net_client.send_action.assert_called_once_with(
        ActionRetargetCovertCell("player-1", "cell-1", "DEU", "POL", "active")
    )
    assert controls.pending["cell-1"] == ("UKR", "POL", "active")


def test_render_submits_activity_change_and_formats_unlisted_status(monkeypatch):
    options = [SimpleNamespace(tag="DEU", name="Germany")]
    monkeypatch.setattr(controls_module, "country_options_from_state", lambda _state: options)
    imgui = _RecordingImgui([(False, 0), (True, 1)])
    monkeypatch.setattr(controls_module, "imgui", imgui)
    controls = controls_module.CovertRosterControls()
    context = _context()
    on_select = Mock()

    controls.render(
        SimpleNamespace(path=lambda name: name),
        _row(status="training", target_country_id=""),
        None,
        object(),
        context,
        on_select,
    )

    assert imgui.combo_calls[0][0][:3] == ("##assigned_country", 0, ["Unknown", "Germany"])
    assert imgui.combo_calls[1][0][:3] == ("##cell_activity", 0, ["Training", "Active", "Dormant"])
    assert imgui.disabled_states == [True, True]
    on_select.assert_not_called()
    context.net_client.send_action.assert_not_called()

    imgui = _RecordingImgui([(False, 0), (True, 1)])
    monkeypatch.setattr(controls_module, "imgui", imgui)
    controls.render(
        SimpleNamespace(path=lambda name: name),
        _row(status="idle"),
        None,
        object(),
        context,
        on_select,
    )

    assert imgui.combo_calls[1][0][:3] == ("##cell_activity", 0, ["Active", "Dormant"])
    context.net_client.send_action.assert_called_once_with(
        ActionSetCovertCellActivity("player-1", "cell-1", False, "POL", "idle")
    )
    assert on_select.call_count == 1


def test_render_disables_busy_controls_and_explains_pending_or_blocked_state(monkeypatch):
    options = [SimpleNamespace(tag="POL", name="Poland")]
    monkeypatch.setattr(controls_module, "country_options_from_state", lambda _state: options)
    controls = controls_module.CovertRosterControls()
    controls.pending["cell-1"] = ("UKR", "POL", "active")
    context = _context()
    imgui = _RecordingImgui([(False, 0), (False, 0)], hovered=True)
    monkeypatch.setattr(controls_module, "imgui", imgui)

    controls.render(
        SimpleNamespace(path=lambda name: name),
        _row(),
        None,
        object(),
        context,
        Mock(),
    )

    assert imgui.disabled_states == [True, True]
    assert imgui.tooltips == ["Awaiting server reply."]

    controls.pending.clear()
    imgui = _RecordingImgui([(False, 0), (False, 0)], hovered=True)
    monkeypatch.setattr(controls_module, "imgui", imgui)
    controls.render(
        SimpleNamespace(path=lambda name: name),
        _row(communications_ready=False),
        {"status": "ready"},
        object(),
        context,
        Mock(),
    )

    assert imgui.disabled_states == [True, True]
    assert imgui.tooltips == [
        "Finish or cancel the current operation and restore communications before editing."
    ]


def test_update_reconciles_pending_signatures_and_clears_missing_or_changed_rows():
    controls = controls_module.CovertRosterControls()
    context = _context()
    state = SimpleNamespace(
        journal=SimpleNamespace(command_results=[]),
        tables={"covert_cells": _Table([_row()])},
    )
    controls.update(state, context)
    controls.pending["cell-1"] = ("UKR", "POL", "active")

    controls.update(state, context)
    assert controls.pending["cell-1"] == ("UKR", "POL", "active")

    state.tables["covert_cells"] = _Table([_row(status="dormant")])
    controls.update(state, context)
    assert controls.pending == {}

    controls.pending["cell-1"] = ("UKR", "POL", "active")
    state.tables["covert_cells"] = None
    controls.update(state, context)
    assert controls.pending == {}
