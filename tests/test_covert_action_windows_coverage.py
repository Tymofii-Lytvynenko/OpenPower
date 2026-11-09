from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.panels.military import covert_action_windows as covert_ui
from src.shared.actions import ActionCreateCovertCell, ActionStartCovertMission, ActionTrainCovertCell


class FakeImgui:
    class StyleVar_:
        frame_padding = "frame_padding"

    def __init__(self, *, clicks=(), inputs=None, combos=None, slider_values=None):
        self.clicks = set(clicks)
        self.inputs = inputs or {}
        self.combos = combos or {}
        self.slider_values = slider_values or {}
        self.calls = []
        self.disabled_stack = []
        self.style_depth = 0

    def get_current_context(self):
        return object()

    def open_popup(self, popup_id):
        self.calls.append(("open_popup", popup_id))

    def close_current_popup(self):
        self.calls.append(("close_current_popup",))

    def push_style_var(self, *_args):
        self.style_depth += 1

    def pop_style_var(self):
        self.style_depth -= 1

    def text_disabled(self, value, **kwargs):
        self.calls.append(("text_disabled", value, kwargs))

    def text(self, value, **kwargs):
        self.calls.append(("text", value, kwargs))

    def input_text(self, _label, current, _length, *, test_id, **_kwargs):
        value = self.inputs.get(test_id, current)
        return value != current, value

    def combo(self, _label, current, items, *, test_id, **kwargs):
        self.calls.append(("combo", test_id, list(items), kwargs))
        selected = self.combos.get(test_id, current)
        return selected != current, selected

    def slider_float(self, _label, current, _minimum, _maximum, _format, *, test_id, **_kwargs):
        value = self.slider_values.get(test_id, current)
        return value != current, value

    def begin_disabled(self, disabled):
        self.disabled_stack.append(bool(disabled) or any(self.disabled_stack))

    def end_disabled(self):
        self.disabled_stack.pop()

    def button(self, _label, *, test_id, **_kwargs):
        self.calls.append(("button", test_id, any(self.disabled_stack)))
        return test_id in self.clicks and not any(self.disabled_stack)


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def state(*, countries=("UKR", "POL", "USA"), resources=None):
    country_rows = [{"id": tag, "name": f"{tag} name"} for tag in countries]
    tables = {"countries": pl.DataFrame(country_rows)}
    if resources is not None:
        tables["resource_ledger"] = pl.DataFrame(
            [{"country_id": tag, "game_resource_id": resource} for tag, resource in resources]
        )
    return SimpleNamespace(tables=tables)


def context(client=None, *, own=True, tag="UKR"):
    return SimpleNamespace(is_own_country=own, target_tag=tag, net_client=client)


def cell(cell_id="cell-1", *, target="POL", status="active", name="Cell"):
    return {"id": cell_id, "target_country_id": target, "status": status, "cell_name": name}


def install_ui(monkeypatch, ui=None, *, popup_open=True):
    fake = ui or FakeImgui()

    @contextmanager
    def popup(*_args, **_kwargs):
        yield popup_open

    monkeypatch.setattr(covert_ui, "imgui", fake)
    monkeypatch.setattr(covert_ui, "gml_popup_modal", popup)
    return fake


def presenter_with(cells):
    presenter = Mock()
    presenter.covert_cells_for_country.return_value = cells
    return presenter


def test_open_deduplicates_cell_ids_and_resets_transient_form_state():
    windows = covert_ui.CovertActionWindows()
    windows.open("train", "fallback", cell_ids=("a", "a", "", "b"))
    assert windows._training_cell_ids == ("a", "b")
    assert windows._training_cell == "a"

    windows._mission_category = "terrorism"
    windows._mission_cover_country = "USA"
    windows.open("mission", cell_ids=("b", "b"))
    assert windows._mission_cell_ids == ("b",)
    assert windows._mission_category == covert_ui.MISSION_CATEGORY_OPTIONS[0][0]
    assert windows._mission_sector == "military"
    assert windows._mission_complexity == "medium"
    assert windows._mission_target == "ground"
    assert windows._mission_cover_country == ""

    windows.open("create")
    assert windows._cell_name == ""
    assert windows._create_quote is None
    assert windows._create_quote_key is None


def test_render_unknown_window_is_a_noop_and_closed_popup_clears_form(monkeypatch):
    ui = install_ui(monkeypatch, popup_open=False)
    windows = covert_ui.CovertActionWindows()
    windows.open("create")
    windows.render(state(), context(), presenter_with([]))
    assert windows._active_window == ""
    assert windows._popup_requested is False
    assert any(call[0] == "open_popup" for call in ui.calls)

    windows.open("unknown")
    windows.render(state(), context(), presenter_with([]))
    assert windows._active_window == "unknown"


def test_create_cell_quotes_once_then_sends_normalized_action(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(
        clicks={"covert.cell_creation.submit"},
        inputs={"covert.cell_creation.name": "  Field Office  "},
        combos={"covert.cell_creation.target": 1, "covert.cell_creation.training_level": 2},
    ))
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    quote = SimpleNamespace(
        setup_cost=1200, daily_upkeep=17.5, deployment_minutes=1500, rejection_reason=""
    )
    windows._covert_operations.quote_cell_creation = Mock(return_value=quote)
    windows.open("create")

    game_state = state()
    windows.render(game_state, context(client), presenter_with([]))
    assert windows._active_window == ""
    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionCreateCovertCell)
    assert action.country_tag == "UKR"
    assert action.target_country_tag == "USA"
    assert action.cell_name == "Field Office"
    assert action.training_level == covert_ui.SKILL_LEVELS[2]
    windows._covert_operations.quote_cell_creation.assert_called_once_with(
        game_state, "UKR", "USA", covert_ui.SKILL_LEVELS[2]
    )
    assert windows._cell_name == "New covert cell"
    assert windows._create_quote is quote
    assert any(call[0] == "text" and call[1] == "1 d 1 h" for call in ui.calls)


def test_create_without_targets_disables_submit_and_cancel_closes(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(clicks={"covert.cell_creation.submit", "covert.cell_creation.cancel"}))
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    windows._covert_operations.quote_cell_creation = Mock(
        return_value=SimpleNamespace(
            setup_cost=0, daily_upkeep=0, deployment_minutes=None, rejection_reason=""
        )
    )
    windows.open("create")
    windows.render(state(countries=("UKR",)), context(client), presenter_with([]))
    assert not client.actions
    assert windows._active_window == ""
    assert any(
        call[0] == "text_disabled" and "No target countries" in call[1]
        for call in ui.calls
    )


def test_create_quote_cache_invalidates_when_target_or_training_changes(monkeypatch):
    ui = install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows._covert_operations.quote_cell_creation = Mock(
        return_value=SimpleNamespace(
            setup_cost=1, daily_upkeep=2, deployment_minutes=None, rejection_reason="blocked"
        )
    )
    windows.open("create")
    windows.render(state(), context(), presenter_with([]))
    windows.render(state(), context(), presenter_with([]))
    assert windows._covert_operations.quote_cell_creation.call_count == 1
    ui.combos["covert.cell_creation.target"] = 1
    windows.render(state(), context(), presenter_with([]))
    assert windows._covert_operations.quote_cell_creation.call_count == 2
    assert any(call[0] == "text" and call[1] == "No legal route" for call in ui.calls)


def test_training_single_selection_filters_status_and_sends_adjusted_points(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(
        clicks={"covert.cell_training.submit"},
        combos={"covert.cell_training.cell": 1},
        slider_values={"covert.cell_training.points": 37.0},
    ))
    client = FakeClient()
    rows = [cell("inactive", status="captured"), cell("cell-1"), cell("cell-2", name="Second")]
    windows = covert_ui.CovertActionWindows()
    windows.open("train", "cell-2")
    windows.render(state(), context(client), presenter_with(rows))

    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionTrainCovertCell)
    assert action.cell_id == "cell-2"
    assert action.training_points == 37.0
    assert windows._training_cell == "cell-2"
    assert windows._active_window == ""


def test_training_empty_and_stale_selections_show_feedback_without_sending(monkeypatch):
    ui = install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows.open("train", "removed")
    windows.render(state(), context(FakeClient()), presenter_with([cell(status="captured")]))
    assert any(call[0] == "text_disabled" and "No active covert cell" in call[1] for call in ui.calls)

    ui.calls.clear()
    windows.open("train", "removed")
    client = FakeClient()
    windows.render(state(), context(client), presenter_with([cell("cell-1")]))
    assert not client.actions
    assert any(
        call[0] == "text_disabled" and call[2].get("test_id") == "covert.cell_training.stale_selection"
        for call in ui.calls
    )


def test_training_multiple_selection_sends_one_action_per_cell_and_detects_stale_member(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(clicks={"covert.cell_training.submit"}))
    rows = [cell("a"), cell("b", target="USA")]
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    windows.open("train", cell_ids=("a", "b"))
    windows.render(state(), context(client), presenter_with(rows))
    assert [action.cell_id for action in client.actions] == ["a", "b"]
    assert all(isinstance(action, ActionTrainCovertCell) for action in client.actions)

    ui.calls.clear()
    client = FakeClient()
    windows.open("train", cell_ids=("a", "missing"))
    windows.render(state(), context(client), presenter_with(rows))
    assert not client.actions
    assert any("One or more selected cells" in call[1] for call in ui.calls if call[0] == "text_disabled")


def test_mission_military_prepare_selects_default_cell_and_sends_typed_action(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(clicks={"covert.new_mission.submit"}))
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    windows.open("mission")
    windows.render(state(), context(client), presenter_with([cell()]))

    assert len(client.actions) == 1
    action = client.actions[0]
    assert isinstance(action, ActionStartCovertMission)
    assert action.cell_id == "cell-1"
    assert action.mission_type == "military_espionage"
    assert action.target_country_tag == "POL"
    assert action.target_sector == "military"
    assert action.target_unit_category == "ground"
    assert action.target_resource_id is None
    assert action.requires_execution_confirmation is True
    assert windows._mission_cell_ids == ("cell-1",)
    assert windows._active_window == ""
    assert any(call[0] == "combo" and call[1] == "covert.new_mission.cover_country" for call in ui.calls)


def test_mission_civilian_target_uses_resources_shared_by_selected_countries(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(
        clicks={"covert.new_mission.submit"},
        combos={"covert.new_mission.sector": 0},
    ))
    client = FakeClient()
    rows = [cell("a", target="POL"), cell("b", target="USA")]
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", cell_ids=("a", "b"))
    game_state = state(resources=[
        ("POL", "fossil_fuels"), ("POL", "minerals"), ("USA", "fossil_fuels")
    ])
    windows.render(game_state, context(client), presenter_with(rows))

    assert windows._mission_cell_ids == ("a", "b")
    assert windows._mission_target == "fossil_fuels"
    assert covert_ui.country_resource_ids(game_state, "POL") == ("fossil_fuels", "minerals")
    assert covert_ui.country_resource_ids(game_state, "USA") == ("fossil_fuels",)
    submit_states = [call for call in ui.calls if call[0] == "button" and call[1] == "covert.new_mission.submit"]
    assert submit_states == [("button", "covert.new_mission.submit", False)], submit_states
    assert [action.target_resource_id for action in client.actions] == ["fossil_fuels", "fossil_fuels"]
    assert [action.target_sector for action in client.actions] == ["civilian", "civilian"]
    assert all(action.target_unit_category is None for action in client.actions)
    assert any(
        call[0] == "combo" and call[1] == "covert.new_mission.target" and call[2] == ["Fossil Fuels"]
        for call in ui.calls
    )


def test_mission_assassination_omits_sector_and_coup_is_filtered_for_self_target(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(
        clicks={"covert.new_mission.submit"},
        combos={"covert.new_mission.type": 2},
    ))
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", "self")
    windows.render(state(), context(client), presenter_with([cell("self", target="UKR")]))
    action = client.actions[0]
    assert action.mission_type == "assassination"
    assert action.target_sector is None
    categories = next(call[2] for call in ui.calls if call[0] == "combo" and call[1] == "covert.new_mission.type")
    assert "Coup d'Etat" not in categories
    sector_call = next(call for call in ui.calls if call[0] == "combo" and call[1] == "covert.new_mission.sector")
    assert sector_call[3]["gml_enabled"] is False


def test_mission_coup_forces_high_complexity_and_empty_or_stale_rosters_do_not_submit(monkeypatch):
    ui = install_ui(monkeypatch, FakeImgui(
        clicks={"covert.new_mission.submit"},
        combos={"covert.new_mission.type": 4},
    ))
    client = FakeClient()
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", "cell-1")
    windows.render(state(), context(client), presenter_with([cell()]))
    assert client.actions[0].mission_type == "coup_attempt"
    assert client.actions[0].complexity == "high"

    ui.calls.clear()
    client = FakeClient()
    windows.open("mission")
    windows.render(state(), context(client), presenter_with([]))
    assert not client.actions
    assert any("No active covert cell" in call[1] for call in ui.calls if call[0] == "text_disabled")

    ui.calls.clear()
    windows.open("mission", "removed")
    windows.render(state(), context(client), presenter_with([cell()]))
    assert not client.actions
    assert any(
        call[0] == "text" and call[2].get("test_id") == "covert.new_mission.target_country"
        and call[1] == "Unavailable"
        for call in ui.calls
    )


def test_foreign_context_closes_popup_and_reconciles_active_window(monkeypatch):
    ui = install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows.open("mission")
    windows.render(state(), context(own=False), presenter_with([]))
    assert windows._active_window == ""
    assert windows._popup_requested is False
    assert any(call[0] == "close_current_popup" for call in ui.calls)


def test_country_and_deployment_helpers_cover_missing_data_and_time_ranges():
    assert covert_ui.CovertActionWindows._country_tags(state(), "UKR") == ["POL", "USA"]
    assert covert_ui.CovertActionWindows._country_tags(state(), "UKR", include_own=True) == ["POL", "UKR", "USA"]
    assert covert_ui.CovertActionWindows._country_tags(SimpleNamespace(tables={}), "UKR") == []
    assert covert_ui.CovertActionWindows._format_deployment_time(None) == "Unavailable"
    assert covert_ui.CovertActionWindows._format_deployment_time(None, "blocked") == "No legal route"
    assert covert_ui.CovertActionWindows._format_deployment_time(0) == "Immediate"
    assert covert_ui.CovertActionWindows._format_deployment_time(65) == "1 h 5 m"
    assert covert_ui.CovertActionWindows._format_deployment_time(45) == "45 min"
    assert covert_ui.CovertActionWindows._format_deployment_time(1500) == "1 d 1 h"


def test_compact_control_style_is_restored_even_when_rendering_raises(monkeypatch):
    ui = install_ui(monkeypatch)
    try:
        with covert_ui._compact_gml_controls():
            assert ui.style_depth == 1
            raise RuntimeError("simulated control failure")
    except RuntimeError:
        pass
    assert ui.style_depth == 0


def test_create_resets_unknown_training_level_before_render(monkeypatch):
    install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows._covert_operations.quote_cell_creation = Mock(
        return_value=SimpleNamespace(
            setup_cost=0,
            daily_upkeep=0,
            deployment_minutes=0,
            rejection_reason="",
        )
    )
    windows.open("create")
    windows._create_training_level = "unknown"

    windows.render(state(), context(), presenter_with([]))

    assert windows._create_training_level == covert_ui.SKILL_LEVELS[0]


def test_closed_training_and_mission_popups_clear_active_window(monkeypatch):
    install_ui(monkeypatch, popup_open=False)
    windows = covert_ui.CovertActionWindows()

    windows.open("train", "cell-1")
    windows.render(state(), context(), presenter_with([cell()]))
    assert windows._active_window == ""

    windows.open("mission", "cell-1")
    windows.render(state(), context(), presenter_with([cell()]))
    assert windows._active_window == ""


def test_training_cancel_closes_modal(monkeypatch):
    install_ui(monkeypatch, FakeImgui(clicks={"covert.cell_training.cancel"}))
    windows = covert_ui.CovertActionWindows()
    windows.open("train", "cell-1")

    windows.render(state(), context(), presenter_with([cell()]))

    assert windows._active_window == ""


def test_mission_form_repairs_unknown_category_and_sector(monkeypatch):
    install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", "cell-1")
    windows._mission_category = "unknown"
    windows._mission_sector = "unknown"

    windows.render(state(), context(), presenter_with([cell()]))

    assert windows._mission_category == covert_ui.MISSION_CATEGORY_OPTIONS[0][0]
    assert windows._mission_sector == "military"


def test_stale_civilian_mission_resets_unavailable_target_and_cover(monkeypatch):
    ui = install_ui(monkeypatch)
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", "removed")
    windows._mission_sector = "civilian"
    windows._mission_cover_country = "MISSING"

    windows.render(state(), context(), presenter_with([cell()]))

    target_call = next(
        call for call in ui.calls
        if call[0] == "combo" and call[1] == "covert.new_mission.target"
    )
    assert target_call[2] == ["Unavailable"]
    assert windows._mission_target == ""
    assert windows._mission_cover_country == ""


def test_mission_cancel_closes_modal(monkeypatch):
    install_ui(monkeypatch, FakeImgui(clicks={"covert.new_mission.cancel"}))
    windows = covert_ui.CovertActionWindows()
    windows.open("mission", "cell-1")

    windows.render(state(), context(), presenter_with([cell()]))

    assert windows._active_window == ""
