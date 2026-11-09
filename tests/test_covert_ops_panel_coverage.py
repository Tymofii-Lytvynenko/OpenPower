from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.panels.military import covert_ops_panel as panel_module
from src.client.ui.panels.military.covert_ops_panel import CovertOpsPanel
from src.shared.actions import ActionCancelCovertMission, ActionExecuteCovertMission, ActionRetireCovertCell


class FakeUI:
    results = {}
    calls = []

    def __init__(self, root="root"):
        self.root = root

    def path(self, slot):
        return f"{self.root}/{slot}"

    def text(self, slot, value, **kwargs):
        self.calls.append(("text", self.root, slot, value, kwargs))

    def text_at(self, slot, value, **kwargs):
        self.calls.append(("text_at", self.root, slot, value, kwargs))

    def button(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.calls.append(("button", self.root, slot, label, test_id, enabled, kwargs))
        return bool(enabled and self.results.get(test_id, False))

    def button_at(self, slot, label, test_id, *, enabled=True, **kwargs):
        self.calls.append(("button_at", self.root, slot, label, test_id, enabled, kwargs))
        return bool(enabled and self.results.get(test_id, False))


class FakeRowUI(FakeUI):
    def meter(self, slot, fraction, color, **kwargs):
        self.calls.append(("meter", self.root, slot, fraction, color, kwargs))


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def cell(cell_id="cell-1", *, country="UKR", status="active", **overrides):
    row = {
        "id": cell_id, "country_id": country, "status": status, "cell_name": cell_id.title(),
        "skill_level": "Veteran", "upkeep": 12.5, "readiness": 0.6,
        "assignment": "foreign_intelligence", "location_country_id": "POL",
        "training_progress": 0.0, "training_required": 0.0,
    }
    row.update(overrides)
    return row


def mission(mission_id="mission-1", *, cell_id="cell-1", owner="UKR", status="preparation", **overrides):
    row = {
        "id": mission_id, "cell_id": cell_id, "owner_country_id": owner,
        "status": status, "mission_type": "civilian_espionage", "target_sector": "civilian",
        "target_resource_id": "fossil_fuels", "target_unit_category": None,
        "framed_country_id": "POL", "complexity": "high", "preparation_progress": 0.55,
    }
    row.update(overrides)
    return row


def context(*, own=True, tag="UKR", client=None, notice=None):
    return SimpleNamespace(
        is_own_country=own, target_tag=tag, net_client=client, on_notice=notice,
    )


def install_panel_ui(monkeypatch, *, window_open=True, child_visible=True, row_clicked=False):
    native = SimpleNamespace(
        is_item_clicked=Mock(return_value=row_clicked),
        get_io=lambda: SimpleNamespace(key_ctrl=False, key_shift=False),
        set_scroll_here_y=Mock(),
        text_wrapped=Mock(),
    )
    FakeUI.results = {}
    FakeUI.calls = []
    FakeRowUI.calls = FakeUI.calls
    monkeypatch.setattr(panel_module, "imgui", native)
    monkeypatch.setattr(panel_module, "GMLWidgets", FakeUI)

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_open

    @contextmanager
    def child(_path, **_kwargs):
        yield child_visible

    @contextmanager
    def row(_template, _key):
        yield FakeRowUI("row")

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    monkeypatch.setattr(panel_module, "gml_child_frame", child)
    monkeypatch.setattr(panel_module, "gml_row", row)
    return native


def state_with(*, regions=None, countries=None):
    tables = {}
    if regions is not None:
        tables["regions"] = pl.DataFrame(regions)
    if countries is not None:
        tables["countries"] = pl.DataFrame(countries)
    return SimpleNamespace(tables=tables, globals={})


def test_render_respects_closed_window_and_composes_child_dialogs_when_open(monkeypatch):
    install_panel_ui(monkeypatch, window_open=False)
    panel = CovertOpsPanel()
    panel._render_content = Mock()
    panel._action_windows.render = Mock()
    assert panel.render(state_with(), context()) is False
    panel._render_content.assert_not_called()
    panel._action_windows.render.assert_not_called()

    install_panel_ui(monkeypatch, window_open=True)
    panel = CovertOpsPanel()
    panel._render_content = Mock()
    panel._action_windows.render = Mock()
    panel._intelligence.render = Mock()
    panel._notice.render = Mock()
    assert panel.render(state_with(), context()) is True
    panel._render_content.assert_called_once()
    panel._action_windows.render.assert_called_once()
    panel._intelligence.render.assert_called_once()
    panel._notice.render.assert_called_once()


def test_request_cell_forwards_exact_cell_and_mission_ids():
    panel = CovertOpsPanel()
    panel.request_cell("cell-7", "mission-3")
    assert panel._selection._requested == ("cell-7", "mission-3")


def test_content_filters_private_roster_and_shows_foreign_scope_notice(monkeypatch):
    native = install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    panel._presenter.covert_cells_for_country = Mock(return_value=[cell(country="POL")])
    panel._presenter.covert_missions_for_country = Mock(return_value=[mission(owner="POL")])
    panel._render_actions = Mock()
    panel._render_mission = Mock()
    panel._roster_controls.update = Mock()
    panel._protection_coverage = Mock()

    game_state = state_with()
    panel_context = context(own=False, tag="POL")
    panel._render_content(game_state, panel_context)

    panel._presenter.covert_cells_for_country.assert_not_called()
    panel._presenter.covert_missions_for_country.assert_not_called()
    panel._protection_coverage.assert_not_called()
    panel._render_actions.assert_called_once_with(panel._render_actions.call_args.args[0], [], {}, panel_context)
    native.text_wrapped.assert_called_once_with(
        "Covert cell details are available only for your country.", test_id="covert_ops.cells.empty"
    )
    assert any(
        item[0] == "text" and item[2] == "frmUpkeep/txtProtection" and item[3] == "Unknown"
        for item in FakeUI.calls
    )


def test_content_reconciles_requested_cell_filters_retired_and_foreign_rows_and_scrolls(monkeypatch):
    native = install_panel_ui(monkeypatch, row_clicked=True)
    panel = CovertOpsPanel()
    active = cell("cell-1", status="active")
    panel._presenter.covert_cells_for_country = Mock(return_value=[
        active, cell("retired", status="retired"), cell("foreign", country="POL"),
    ])
    expected_mission = mission()
    panel._presenter.covert_missions_for_country = Mock(return_value=[
        expected_mission, mission("foreign-mission", owner="POL"),
    ])
    panel._roster_controls.update = Mock()
    panel._roster_controls.render = Mock()
    panel._render_actions = Mock()
    panel._render_mission = Mock()
    panel._protection_coverage = Mock(return_value=0.42)
    panel.request_cell("cell-1")
    FakeUI.results["covert_ops.open_intelligence"] = True

    game_state = state_with()
    panel._render_content(game_state, context())

    assert panel._selection.selected_cell_ids == ("cell-1",)
    assert panel._scroll_cell == ""
    native.set_scroll_here_y.assert_called_once_with(0.5)
    panel._presenter.covert_cells_for_country.assert_called_once_with(game_state, "UKR")
    assert panel._roster_controls.render.call_count == 1
    panel._render_actions.assert_called_once()
    assert panel._render_mission.call_args.args[2:] == (active, expected_mission, 1)
    assert panel._intelligence.is_open is True
    assert any(
        item[0] == "text_at" and item[3] == "PROGRESS"
        for item in FakeUI.calls
    )
    assert any(
        item[0] == "text" and item[2] == "frmUpkeep/txtProtection" and item[3] == "42.0%"
        for item in FakeUI.calls
    )


def test_content_reports_stale_requested_cell_to_notice_callback(monkeypatch):
    install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    panel._presenter.covert_cells_for_country = Mock(return_value=[])
    panel._presenter.covert_missions_for_country = Mock(return_value=[])
    panel._render_actions = Mock()
    panel._render_mission = Mock()
    notice = Mock()
    panel.request_cell("gone", "old-mission")

    panel._render_content(state_with(), context(notice=notice))

    notice.assert_called_once_with(
        "Covert operations", "The requested cell or ready mission is no longer available.", severity="warning"
    )


def test_progress_clamps_mission_training_readiness_and_invalid_values():
    assert CovertOpsPanel._progress(cell(), mission(status="preparation", preparation_progress=0.4),) == 0.4
    assert CovertOpsPanel._progress(cell(), mission(status="ready", preparation_progress=1.5)) == 1.0
    assert CovertOpsPanel._progress(cell(status="training", training_progress=25, training_required=50), None) == 0.5
    assert CovertOpsPanel._progress(cell(status="training", training_progress=25, training_required=0), None) == 0.0
    assert CovertOpsPanel._progress(cell(readiness=-1), None) == 0.0
    assert CovertOpsPanel._progress(cell(readiness=float("inf")), None) == 0.0
    assert CovertOpsPanel._progress(cell(readiness="bad"), None) == 0.0


def test_protection_coverage_returns_unknown_for_missing_population_data(monkeypatch):
    no_tables = state_with()
    assert CovertOpsPanel._protection_coverage(no_tables, "UKR", []) is None
    assert CovertOpsPanel._protection_coverage(state_with(regions={"id": [1]}), "UKR", []) is None
    assert CovertOpsPanel._protection_coverage(
        state_with(regions={"owner": ["UKR"], "region_name": ["Kyiv"]}), "UKR", []
    ) is None
    assert CovertOpsPanel._protection_coverage(
        state_with(regions={"owner": ["POL"], "population": [100]}), "UKR", []
    ) is None
    assert CovertOpsPanel._protection_coverage(
        state_with(regions={"owner": ["UKR"], "population": [0]}), "UKR", []
    ) is None
    assert CovertOpsPanel._protection_coverage(
        state_with(regions={"owner": ["UKR"], "population": [float("nan")]}), "UKR", []
    ) is None


def test_protection_coverage_counts_only_active_domestic_security_cells(monkeypatch):
    coverage = Mock(return_value=0.62)
    monkeypatch.setattr(panel_module, "domestic_security_coverage", coverage)
    state = state_with(regions={"owner": [" ukr ", "UKR", "POL"], "population": [1000, 2000, 5000]})
    cells = [
        cell(assignment="domestic_security", status="active", location_country_id="UKR"),
        cell(assignment="domestic_security", status="idle", location_country_id="UKR"),
        cell(assignment="foreign_intelligence", status="active", location_country_id="UKR"),
        cell(assignment="domestic_security", status="active", location_country_id="POL"),
    ]

    assert CovertOpsPanel._protection_coverage(state, "ukr", cells) == 0.62
    coverage.assert_called_once_with(1, 3000.0, state.globals)


def test_actions_open_forms_retire_cells_execute_ready_missions_and_cancel_pending(monkeypatch):
    install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    client = FakeClient()
    panel._action_windows.open = Mock()
    panel._roster_controls.pending = set()
    ui = FakeUI("root")
    active = cell("active", status="active")
    FakeUI.results.update({
        "covert_ops.open_cell_creation": True,
        "covert_ops.open_cell_training": True,
        "covert_ops.retire": True,
        "covert_ops.open_new_mission": True,
    })
    panel._render_actions(ui, [active], {}, context(client=client))
    assert panel._action_windows.open.call_count == 3
    panel._action_windows.open.assert_any_call("create")
    panel._action_windows.open.assert_any_call("train", cell_ids=("active",))
    panel._action_windows.open.assert_any_call("mission", cell_ids=("active",))
    assert isinstance(client.actions[0], ActionRetireCovertCell)
    assert client.actions[0].cell_id == "active"

    panel._action_windows.open.reset_mock()
    client.actions.clear()
    ready = cell("ready", status="ready")
    ready_mission = mission("ready-mission", cell_id="ready", status="ready")
    FakeUI.results = {"covert_ops.execute": True, "covert_ops.cancel_mission": True}
    panel._render_actions(ui, [ready], {"ready": ready_mission}, context(client=client))
    assert [type(action) for action in client.actions] == [ActionExecuteCovertMission, ActionCancelCovertMission]
    assert client.actions[0].mission_id == "ready-mission"
    assert client.actions[1].mission_id == "ready-mission"


def test_actions_disable_commands_for_foreign_context_and_pending_cells(monkeypatch):
    install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    panel._action_windows.open = Mock()
    panel._roster_controls.pending = {"cell-1"}
    ui = FakeUI()
    FakeUI.results = {"covert_ops.open_cell_creation": True, "covert_ops.open_cell_training": True}
    client = FakeClient()
    panel._render_actions(ui, [cell()], {}, context(own=False, client=client))
    panel._render_actions(ui, [cell()], {}, context(client=client))
    assert client.actions == []
    panel._action_windows.open.assert_called_once_with("create")
    assert any(call[0] == "button" and call[4] == "covert_ops.open_cell_training" and not call[5] for call in FakeUI.calls)


def test_mission_summary_renders_resource_unit_and_framed_country_labels(monkeypatch):
    install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    ui = FakeUI("root")
    selected = cell("cell-1", cell_name="Station")
    selected_mission = mission(
        mission_type="military_sabotage", target_sector="military",
        target_resource_id=None, target_unit_category="ground",
    )
    state = state_with(countries={"id": ["POL"], "name": ["Poland"]})

    panel._render_mission(ui, state, selected, selected_mission, 1)

    rendered = {(call[2], call[3]) for call in FakeUI.calls if call[0] == "text"}
    assert ("frmMission/lblTitle", "MISSION · Station") in rendered
    assert ("frmMission/txtMission", "Military Sabotage") in rendered
    assert ("frmMission/txtSector", "Military") in rendered
    assert ("frmMission/txtResourceUnit", "Ground") in rendered
    assert ("frmMission/txtFramedCountry", "Poland") in rendered

    FakeUI.calls.clear()
    panel._render_mission(ui, state, selected, mission(), 1)
    assert any(call[2] == "frmMission/txtResourceUnit" and call[3] == "Fossil Fuels" for call in FakeUI.calls)

    FakeUI.calls.clear()
    panel._render_mission(ui, state, None, None, 3)
    assert any(call[2] == "frmMission/lblTitle" and call[3] == "MISSION · 3 CELLS SELECTED" for call in FakeUI.calls)
    assert any(call[3] == "—" for call in FakeUI.calls if call[0] == "text")


def test_mission_summary_defaults_unknown_fields_and_framed_country(monkeypatch):
    install_panel_ui(monkeypatch)
    panel = CovertOpsPanel()
    ui = FakeUI("root")
    panel._render_mission(ui, state_with(), None, mission(
        mission_type="terrorism", target_sector=None, target_resource_id=None,
        target_unit_category="unknown", framed_country_id=None, complexity=None,
    ), 1)
    rendered = [call[3] for call in FakeUI.calls if call[0] == "text"]
    assert "Political" in rendered
    assert "Not Recorded" in rendered
    assert "None" in rendered
