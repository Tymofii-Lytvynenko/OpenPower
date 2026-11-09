from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import polars as pl
import pytest

from src.client.ui.panels.military import unit_reorganization_windows as windows_module
from src.client.ui.panels.military.unit_reorganization_windows import UnitReorganizationWindows
from src.shared.actions import ActionListUsedUnit, ActionMergeUnits, ActionSplitUnit, ActionWithdrawUsedUnitListing


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


class FakeWidgets:
    results = {}
    calls = []

    def __init__(self, root):
        self.root = root

    def path(self, slot):
        return f"{self.root}/{slot}"

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def button(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, enabled, kwargs))
        return bool(enabled and self.results.get(test_id, False))


def setup(monkeypatch, *, window_open=True, child_visible=True):
    client = FakeClient()
    native = MagicMock()
    native.Col_.button = "button"
    native.StyleVar_.window_border_size = "border_size"
    native.WindowFlags_.no_title_bar = 1
    native.WindowFlags_.no_scrollbar = 2
    native.WindowFlags_.no_scroll_with_mouse = 4
    native.get_io.return_value.display_size = SimpleNamespace(x=1000, y=800)
    native.get_content_region_avail.return_value.x = 100.0
    native.selectable.return_value = (False, False)
    native.checkbox.return_value = (False, False)
    native.button.return_value = False
    native.input_int.side_effect = [(False, 0), (False, 0)]
    native.slider_int.return_value = (False, 0)
    monkeypatch.setattr(windows_module, "imgui", native)
    FakeWidgets.results = {}
    FakeWidgets.calls = []
    monkeypatch.setattr(windows_module, "GMLWidgets", FakeWidgets)

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_open

    @contextmanager
    def child(_path, **_kwargs):
        yield child_visible

    monkeypatch.setattr(windows_module.WindowManager, "window", window)
    monkeypatch.setattr(windows_module, "gml_child_frame", child)
    windows = UnitReorganizationWindows(client, "UKR")
    windows._training.render = Mock()
    return windows, client, native


def game_state(rows, *, listings=None):
    tables = {"units": pl.DataFrame(rows)} if rows is not None else {}
    if listings is not None:
        tables["unit_market_listings"] = pl.DataFrame(listings)
    return SimpleNamespace(tables=tables)


def unit(unit_id="u1", *, owner="UKR", strength=10, region=1, **overrides):
    value = {
        "id": unit_id, "owner": owner, "strength": strength, "equipment_quantity": 5,
        "unit_type": "infantry", "type": "division", "current_region_id": region,
        "unit_lifecycle": "available", "readiness_transition_id": None,
        "is_moving": False, "engagement_mode": None, "training_state": "idle",
        "design_id": "d1", "unit_domain": "land", "readiness_status": "ready",
        "training_level": "trained", "combat_posture": "defensive",
        "latitude": 10.0, "longitude": 20.0,
    }
    value.update(overrides)
    return value


def test_open_methods_reset_mode_and_selection_state_and_available_checks_lifecycle(monkeypatch):
    windows, _client, _native = setup(monkeypatch)
    windows.open_unit_list("u2")
    assert windows._list_unit_id == "u2"
    windows.open_split("u1")
    windows._detached = 3
    windows._direct_split = True
    windows._quantity_direction = "right"
    windows.open_split("u2")
    assert (windows._unit_id, windows._mode, windows._detached, windows._direct_split) == ("u2", "split", 0, False)
    assert windows._quantity_direction == ""

    windows._merge_sources.update({"a", "b"})
    windows.open_merge("u3")
    assert (windows._unit_id, windows._mode, windows._merge_sources) == ("u3", "merge", set())
    assert UnitReorganizationWindows._available(unit()) is True
    for changes in (
        {"is_moving": True}, {"unit_lifecycle": "destroyed"},
        {"readiness_transition_id": "transition"}, {"engagement_mode": "battle"},
        {"training_state": "queued"}, {"training_state": "training"},
        {"training_state": "in_progress"}, {"training_state": "blocked"},
    ):
        assert UnitReorganizationWindows._available(unit(**changes)) is False


def test_training_request_delegates_and_render_reconciles_missing_or_foreign_unit(monkeypatch):
    windows, _client, _native = setup(monkeypatch)
    accepted = Mock()
    state = game_state([unit()])
    windows._training.request_many = Mock(return_value=True)
    assert windows.open_training(state, ["u1"], on_accept=accepted) is True
    windows._training.request_many.assert_called_once_with(state, ["u1"], on_accept=accepted)

    notify = Mock()
    windows._notify = notify
    windows.open_split("missing")
    windows.render(game_state([unit()]))
    assert windows._mode == ""
    notify.assert_called_once_with(
        "Unit reorganization", "The selected unit is unavailable or is not owned by you.", severity="warning"
    )

    notify.reset_mock()
    windows.open_merge("foreign")
    windows._unit_id = "foreign"
    windows.render(game_state([unit("foreign", owner="POL")]))
    assert windows._mode == ""
    assert notify.call_count == 1
    assert windows._rows(SimpleNamespace(tables={})) == []


def test_render_dispatches_split_quantity_and_merge_modes(monkeypatch):
    windows, _client, _native = setup(monkeypatch)
    rows = [unit()]
    windows.open_split("u1")
    windows._split = Mock()
    windows._quantity_window = Mock()
    windows._quantity_direction = "right"
    windows.render(game_state(rows))
    windows._split.assert_called_once_with(rows[0])
    windows._quantity_window.assert_called_once()

    windows._mode = "merge"
    windows._merge = Mock()
    windows.render(game_state(rows))
    windows._merge.assert_called_once_with(rows[0], rows)
    windows._mode = ""
    windows._split.reset_mock()
    windows.render(game_state(rows))
    windows._split.assert_not_called()


def test_render_keeps_legacy_list_and_training_surfaces_active_without_reorganization(monkeypatch):
    windows, _client, _native = setup(monkeypatch)
    windows._list_unit_id = "u1"
    windows._legacy_list = Mock()

    windows.render(game_state([unit()]))

    windows._legacy_list.assert_called_once()
    windows._training.render.assert_called_once()


def test_split_dialog_equal_split_and_apply_action(monkeypatch):
    windows, client, native = setup(monkeypatch)
    FakeWidgets.results.update({"unit.split.equally": True, "unit.split.apply": True})
    native.selectable.return_value = (False, True)
    windows.open_split("u1")

    windows._split(unit(strength=9, equipment_quantity=4))

    assert windows._detached == 4
    assert windows._mode == ""
    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionSplitUnit)
    assert action.unit_id == "u1"
    assert action.detached_strength == 4
    assert native.selectable.call_count == 2
    assert any(call.args[0] == "Equipment: 4" for call in native.text.call_args_list)


def test_split_dialog_handles_closed_window_unavailable_unit_and_boundary_controls(monkeypatch):
    windows, client, _native = setup(monkeypatch, window_open=False)
    windows.open_split("u1")
    windows._split(unit())
    assert windows._mode == ""

    windows, client, _native = setup(monkeypatch)
    windows._detached = 5
    FakeWidgets.results["unit.split.apply"] = True
    windows._split(unit(is_moving=True))
    assert not client.actions
    assert windows._detached == 5
    assert any(
        call[0] == "button" and call[4] == "unit.split.apply" and not call[5]
        for call in FakeWidgets.calls
    )


def test_split_dialog_opens_right_and_left_quantity_popups(monkeypatch):
    windows, _client, _native = setup(monkeypatch)
    windows.open_split("u1")
    FakeWidgets.results["unit.split.to_new"] = True
    windows._split(unit())
    assert windows._quantity_direction == "right"
    assert windows._quantity_capacity == 10

    windows.open_split("u1")
    windows._detached = 4
    FakeWidgets.results["unit.split.to_new"] = False
    FakeWidgets.results["unit.split.to_original"] = True
    windows._split(unit())
    assert windows._quantity_direction == "left"
    assert windows._quantity_capacity == 4


def test_quantity_dialog_clamps_inputs_adjusts_one_person_and_closes_direct_split(monkeypatch):
    windows, client, native = setup(monkeypatch)
    windows.open_split("u1")
    windows._direct_split = True
    windows._open_quantity("right", 10)
    native.input_int.side_effect = [(True, 8), (True, 12)]
    native.slider_int.return_value = (False, 9)
    FakeWidgets.results.update({"unit.split.quantity.down": True, "unit.split.quantity.up": True,
                                "unit.split.quantity.close": True})

    windows._quantity_window()

    assert windows._quantity == 9
    assert windows._detached == 9
    assert windows._mode == ""
    assert any(isinstance(action, ActionSplitUnit) and action.detached_strength == 9 for action in client.actions)
    assert native.push_style_color.call_count == 1
    native.pop_style_var.assert_called_once()
    native.pop_style_color.assert_called_once()


def test_quantity_dialog_cancel_path_and_left_transfer(monkeypatch):
    windows, _client, native = setup(monkeypatch, window_open=False)
    windows.open_split("u1")
    windows._detached = 6
    windows._direct_split = False
    windows._open_quantity("left", 6)
    windows._quantity = 2
    native.slider_int.return_value = (False, 2)
    windows._quantity_window()
    assert windows._detached == 4
    assert windows._quantity_direction == ""


def test_legacy_list_handles_missing_closed_foreign_and_hidden_regions(monkeypatch):
    windows, _client, native = setup(monkeypatch)
    notify = Mock()
    windows._notify = notify
    windows.open_unit_list("missing")
    windows._legacy_list(game_state([unit()]))
    assert windows._list_unit_id == ""
    notify.assert_called_once()

    windows.open_unit_list("u1")
    windows._legacy_list(game_state([unit(owner="POL")]))
    assert any("authorized intelligence" in str(call) for call in native.text_wrapped.call_args_list)
    assert any(call[0] == "text" and call[2] == "frmInformationAccuracy/lblTitle" for call in FakeWidgets.calls)

    windows, _client, _native = setup(monkeypatch, window_open=False)
    windows.open_unit_list("u1")
    windows._legacy_list(game_state([unit()]))
    assert windows._list_unit_id == ""

    windows, _client, _native = setup(monkeypatch, child_visible=False)
    windows.open_unit_list("u1")
    windows._legacy_list(game_state([unit()]))
    assert not native.selectable.called


def test_legacy_list_selects_owned_same_region_units_and_sells_or_withdraws(monkeypatch):
    windows, client, native = setup(monkeypatch)
    windows.open_unit_list("u1")
    rows = [unit("u1"), unit("u2"), unit("foreign", owner="POL"), unit("far", region=2)]
    native.selectable.side_effect = [(False, False), (True, True)]
    FakeWidgets.results["unit.group.sell"] = True
    windows._legacy_list(game_state(rows))
    assert native.selectable.call_count == 2
    assert windows._list_unit_id == "u2"
    assert any(isinstance(action, ActionListUsedUnit) for action in client.actions)

    windows.open_unit_list("u1")
    listings = [{"id": "listing-1", "unit_id": "u1", "status": "listed"}]
    native.selectable.side_effect = None
    native.selectable.return_value = (False, False)
    windows._legacy_list(game_state(rows, listings=listings))
    assert any(isinstance(action, ActionWithdrawUsedUnitListing) for action in client.actions)
    assert any(call[0] == "button" and call[3] == "Withdraw" for call in FakeWidgets.calls)


def test_legacy_list_actions_route_to_split_merge_training_and_listings(monkeypatch):
    windows, client, native = setup(monkeypatch)
    windows._training.request = Mock()
    monkeypatch.setattr(windows_module, "training_offer", lambda *_args: object())
    monkeypatch.setattr(windows_module, "training_unavailable_reason", lambda *_args: "unavailable")
    FakeWidgets.results.update({
        "unit.group.split": True, "unit.group.merge": True, "unit.group.train": True,
        "unit.group.sell": False,
    })
    windows.open_unit_list("u1")
    windows._legacy_list(game_state([unit()]))
    assert (windows._mode, windows._direct_split, windows._quantity_direction) == ("merge", True, "right")
    windows._training.request.assert_called_once()


def test_merge_selects_only_compatible_available_units_and_sends_sorted_sources(monkeypatch):
    windows, client, native = setup(monkeypatch)
    windows.open_merge("u1")
    windows._merge_sources.add("source-a")

    def checkbox(label, _selected, **_kwargs):
        if label.startswith("source-a"):
            return True, False
        if label.startswith("source-b"):
            return True, True
        return False, False

    native.checkbox.side_effect = checkbox
    native.button.return_value = True
    source = unit("source-b", strength=4)
    selected = unit("source-a", strength=5)
    incompatible = unit("wrong-location", latitude=11.0)
    unavailable = unit("moving", is_moving=True)
    rows = [unit(strength=8), source, selected, incompatible, unavailable]
    windows.open_merge("u1")

    windows._merge(rows[0], rows)

    assert native.checkbox.call_count == 2
    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionMergeUnits)
    assert action.target_unit_id == "u1"
    assert action.source_unit_ids == ["source-b"]
    assert windows._mode == ""


def test_merge_clears_stale_sources_and_reports_empty_candidate_set(monkeypatch):
    windows, client, native = setup(monkeypatch)
    windows._merge_sources.add("stale")
    windows.open_merge("u1")
    windows._merge(unit(), [unit(), unit("other", owner="POL")])
    assert windows._merge_sources == set()
    assert not client.actions
    native.text_wrapped.assert_any_call("No compatible units share this location and status.")

    windows, _client, _native = setup(monkeypatch, window_open=False)
    windows._mode = "merge"
    windows._merge(unit(), [unit()])
    assert windows._mode == ""
