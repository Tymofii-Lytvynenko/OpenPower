from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from src.client.ui.panels.politics import treaties_live
from src.client.ui.panels.politics.treaties_live import (
    LiveTreatiesPanel,
    _format_ratio_condition,
    _selectable_table_entry,
)
from src.shared.actions import ActionRespondTreaty
from src.shared.mod_api import ClientPresentationKeys
from tests.test_support.client_presentation import client_state, presentation_values


class Table:
    def __init__(self, rows, columns=None):
        self.rows = rows
        self.columns = set(columns if columns is not None else (rows[0].keys() if rows else ()))

    def is_empty(self):
        return not self.rows

    def to_dicts(self):
        return self.rows


class Imgui:
    def __init__(self, *, clicked=False, available_width=150.0):
        self.clicked = clicked
        self.available_width = available_width
        self.cursor_x = 10.0
        self.selectables = []
        self.tooltips = []
        self.wrapped = []

    def get_cursor_pos_x(self):
        return self.cursor_x

    def set_cursor_pos_x(self, value):
        self.cursor_x = value

    def get_content_region_avail(self):
        return SimpleNamespace(x=self.available_width)

    def selectable(self, label, selected, *, size, test_id):
        self.selectables.append((label, selected, size, test_id))
        return self.clicked, False

    def set_item_tooltip(self, tooltip):
        self.tooltips.append(tooltip)

    def text_wrapped(self, value, *, test_id):
        self.wrapped.append((value, test_id))


def _panel(**kwargs):
    instance = LiveTreatiesPanel(**kwargs)
    factory = presentation_values()[ClientPresentationKeys.TREATY_ELIGIBILITY_QUERY_SERVICE_FACTORY]
    instance._diplomacy = factory()
    return instance


class Ui:
    def __init__(self, *, clicked=()):
        self.clicked = set(clicked)
        self.frames = []
        self.texts = []
        self.text_at_calls = []
        self.combos = []
        self.meters = []
        self.buttons = []
        self.toggles = []

    def frame(self, slot):
        self.frames.append(slot)

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def text_at(self, *args, **kwargs):
        self.text_at_calls.append((args, kwargs))

    def combo_at(self, *args, **kwargs):
        self.combos.append((args, kwargs))

    def meter(self, *args, **kwargs):
        self.meters.append((args, kwargs))

    @staticmethod
    def path(slot):
        return f"gml/{slot}"

    def button(self, slot, label, test_id, **kwargs):
        self.buttons.append((slot, label, test_id, kwargs))
        return test_id in self.clicked and kwargs.get("enabled", True)

    def toggle(self, *args, **kwargs):
        self.toggles.append((args, kwargs))


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


class ParticipantDialog:
    def __init__(self):
        self.ineligible = []
        self.results = []
        self.dismissed = 0

    def mark_ineligible(self, tags):
        self.ineligible.append(tags)

    def resolve_result(self, *, applied):
        self.results.append(applied)

    def dismiss(self):
        self.dismissed += 1


def install_imgui(monkeypatch, **kwargs):
    fake = Imgui(**kwargs)
    monkeypatch.setattr(treaties_live, "imgui", fake)
    return fake


@pytest.mark.parametrize(
    "value,expected",
    [(None, "No limit"), ("bad", "No limit"), (-1, "No limit"), (0, "No limit"), (1, "≤ 1.00×"), (2.5, "≤ 2.50×")],
)
def test_ratio_condition_formats_bounded_and_unbounded_values(value, expected):
    assert _format_ratio_condition(value) == expected


def test_selectable_table_entry_offsets_and_limits_hitbox_width(monkeypatch):
    fake = install_imgui(monkeypatch, clicked=True, available_width=180.0)

    assert _selectable_table_entry("Long treaty name", False, "treaty.id", "details") is True
    assert fake.cursor_x == 15.0
    assert fake.selectables == [("Long treaty name", False, (180.0, 0.0), "treaty.id")]
    assert fake.tooltips == ["details"]

    fake.available_width = 0.0
    fake.clicked = False
    assert _selectable_table_entry("Compact", True, "treaty.other") is False
    assert fake.selectables[-1][2] == (1.0, 0.0)
    assert fake.tooltips == ["details"]


def test_treaty_lookup_and_effect_lookup_handle_missing_tables_and_filter_ids():
    state = SimpleNamespace(tables={
        "countries_treaties": Table([{"id": "T1"}, {"id": "T2"}]),
        "treaty_effects": Table([
            {"treaty_id": "T1", "effect": "trade"},
            {"treaty_id": "T2", "effect": "migration"},
        ]),
    })

    assert LiveTreatiesPanel._find_row(SimpleNamespace(tables={}), "countries_treaties", "T1") is None
    assert LiveTreatiesPanel._find_row(SimpleNamespace(tables={"countries_treaties": Table([])}), "countries_treaties", "T1") is None
    assert LiveTreatiesPanel._find_row(state, "countries_treaties", "") is None
    assert LiveTreatiesPanel._find_row(state, "countries_treaties", "T2") == {"id": "T2"}
    assert LiveTreatiesPanel._find_effects(SimpleNamespace(tables={}), "T1") == []
    assert LiveTreatiesPanel._find_effects(SimpleNamespace(tables={"treaty_effects": Table([], columns={"treaty_id"})}), "T1") == []
    assert LiveTreatiesPanel._find_effects(SimpleNamespace(tables={"treaty_effects": Table([{"value": 1}], columns={"value"})}), "T1") == []
    assert LiveTreatiesPanel._find_effects(state, "T1") == [{"treaty_id": "T1", "effect": "trade"}]


def test_external_selection_opens_active_or_pending_treaty_and_ignores_unknown_id():
    panel = _panel()
    state = client_state(
        tables={
            "countries_treaties": Table([{"id": "active"}]),
            "pending_treaties": Table([{"id": "proposal"}]),
        },
        journal=SimpleNamespace(domain_events=[{
            "event_type": "EventTreatyLifecycleChanged",
            "payload": {"proposal_id": "proposal", "transition": "activated"},
        }]),
    )

    assert panel.show_treaty(state, "active") is True
    assert panel._selected_treaty_id == "active"
    assert panel._selected_pending_id == ""
    assert panel._show_details is True
    assert panel._details_needs_focus is True
    assert panel._detail_lifecycle.proposal is False

    assert panel.show_treaty(state, "proposal") is True
    assert panel._selected_treaty_id == ""
    assert panel._selected_pending_id == "proposal"
    assert panel._detail_lifecycle.proposal is True
    assert panel._detail_lifecycle.update({"id": "proposal", "status": "pending"}, state.journal.domain_events) == ""

    assert panel.show_treaty(state, "missing") is False


@pytest.mark.parametrize(
    "treaty,context,expected",
    [
        ({"type": "mobility_agreement", "source_country_id": "USA"}, SimpleNamespace(net_client=Client(), is_own_country=True, target_tag=" usa "), True),
        ({"type": "mobility_agreement", "source_country_id": "CAN"}, SimpleNamespace(net_client=Client(), is_own_country=True, target_tag="USA"), False),
        ({"type": "mobility_agreement", "source_country_id": "USA", "status": "ended"}, SimpleNamespace(net_client=Client(), is_own_country=True, target_tag="USA"), False),
        ({"type": "unknown", "source_country_id": "USA"}, SimpleNamespace(net_client=Client(), is_own_country=True, target_tag="USA"), False),
        ({"type": "mobility_agreement", "source_country_id": "USA"}, SimpleNamespace(net_client=None, is_own_country=True, target_tag="USA"), False),
        ({"type": "mobility_agreement", "source_country_id": "USA"}, SimpleNamespace(net_client=Client(), is_own_country=False, target_tag="USA"), False),
    ],
)
def test_participant_edit_permission_requires_active_sponsor_and_local_client(treaty, context, expected):
    assert LiveTreatiesPanel._can_edit_participants(treaty, context) is expected


def test_conditions_render_saved_values_as_read_only_source_options():
    ui = Ui()
    treaty = {
        "conditions_json": '{"allow_members_at_war": true, "minimum_relation": 25, "maximum_geographic_distance_km": 1200, "government_type": "parliamentary_republic", "max_economic_strength_ratio": 1.5, "max_military_strength_ratio": 0, "max_research_ratio": 2}',
    }

    LiveTreatiesPanel._render_conditions(ui, treaty)

    assert ui.frames == ["frmConditions"]
    assert len(ui.texts) == 6
    assert ui.texts[0][0] == ("frmConditions/lblTitle", "CONDITIONS")
    assert ui.texts[0][1]["tooltip"].endswith("Current value: Yes.")
    assert ui.text_at_calls[0][0][:2] == ("frmConditions/lblGeographicProximity", "GEOGRAPHIC PROXIMITY")
    assert [call[0][3] for call in ui.combos] == [
        ["≥ 25"], ["≤ 1200 km"], ["Parliamentary Republic"], ["≤ 1.50×"], ["No limit"], ["≤ 2.00×"],
    ]
    assert all(call[1]["enabled"] is False for call in ui.combos)


def test_proposal_response_actions_send_accept_and_reject_only_for_required_country(monkeypatch):
    panel = _panel()
    client = Client()
    ui = Ui(clicked={"treaties.details.accept", "treaties.details.reject"})
    context = SimpleNamespace(target_tag=" usa ", is_own_country=True, net_client=client)

    panel._render_proposal_response_actions(
        ui,
        {"id": "P1", "required_responses": ["USA", "CAN"]},
        context,
    )

    assert [action.accept for action in client.actions] == [True, False]
    assert all(isinstance(action, ActionRespondTreaty) for action in client.actions)
    assert all(action.treaty_id == "P1" and action.responder_country_tag == "USA" for action in client.actions)

    for restricted in (
        SimpleNamespace(target_tag="USA", is_own_country=False, net_client=client),
        SimpleNamespace(target_tag="MEX", is_own_country=True, net_client=client),
        SimpleNamespace(target_tag="USA", is_own_country=True, net_client=None),
    ):
        untouched = Ui(clicked={"treaties.details.accept"})
        panel._render_proposal_response_actions(untouched, {"id": "P2", "required_responses": ["USA"]}, restricted)
        assert untouched.buttons == []


def test_pressure_fallback_preserves_slots_without_reporting_pressure(monkeypatch):
    fake = install_imgui(monkeypatch)
    ui = Ui()

    @contextmanager
    def opened_child(*args, **kwargs):
        yield True

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)
    LiveTreatiesPanel._render_pressure_fallback(ui)

    assert ui.frames == ["frmPressure"]
    assert any(call[0][1] == "N/A" for call in ui.texts)
    assert ui.meters[0][0][1] == 0.0
    assert ui.buttons[0][2] == "treaties.details.sponsor.unavailable"
    assert ui.buttons[0][3]["enabled"] is False
    assert fake.wrapped == [(
        "OpenPower does not track REFERENCE treaty pressure-country totals.",
        "treaties.details.pressure.unavailable",
    )]


def participant_state(*, results=(), treaty=None):
    rows = [] if treaty is None else [treaty]
    return client_state(
        tables={"countries_treaties": Table(rows)},
        journal=SimpleNamespace(command_results=list(results)),
    )


def test_participant_result_cursor_ignores_unrelated_result_and_marks_rejected_members(monkeypatch):
    panel = _panel()
    dialog = ParticipantDialog()
    panel._participant_dialog = dialog
    panel._editing_treaty_id = "T1"
    panel._pending_participant_sides = (frozenset({"USA", "MEX"}), frozenset({"CAN"}))
    panel._diplomacy.ineligible_treaty_members = lambda state, proposed: {
        tag for tag in proposed["members"] if tag == "MEX"
    }
    treaty = {"id": "T1", "side_a": ["USA"], "side_b": ["CAN"], "members": ["USA", "CAN"]}
    state = participant_state(treaty=treaty)
    context = SimpleNamespace(net_client=SimpleNamespace(player_id="player-1"))

    panel._resolve_participant_update(state, context)
    state.journal.command_results.extend([
        {"action_type": "ActionUpdateTreatyParticipants", "player_id": "other", "status": "rejected"},
        {"action_type": "ActionCreateTreaty", "player_id": "player-1", "status": "rejected"},
    ])
    panel._resolve_participant_update(state, context)
    assert panel._pending_participant_sides is not None
    assert dialog.results == []

    state.journal.command_results.append({
        "action_type": "ActionUpdateTreatyParticipants",
        "actor_id": "player-1",
        "status": "FAILED",
    })
    panel._resolve_participant_update(state, context)

    assert dialog.ineligible == [{"MEX"}]
    assert dialog.results == [False]
    assert panel._pending_participant_sides is None


@pytest.mark.parametrize("status", ["accepted", "applied", "succeeded"])
def test_participant_result_acceptance_resolves_pending_dialog(status):
    panel = _panel()
    dialog = ParticipantDialog()
    panel._participant_dialog = dialog
    panel._editing_treaty_id = "T1"
    panel._pending_participant_sides = (frozenset({"USA"}), frozenset({"CAN"}))
    state = participant_state()
    context = SimpleNamespace(net_client=SimpleNamespace(player_id="player-1"))
    panel._resolve_participant_update(state, context)
    state.journal.command_results.append({
        "action_type": "ActionUpdateTreatyParticipants",
        "player_id": "player-1",
        "status": status,
    })

    panel._resolve_participant_update(state, context)

    assert dialog.results == [True]
    assert panel._pending_participant_sides is None


def test_participant_snapshot_match_resolves_without_command_result():
    panel = _panel()
    dialog = ParticipantDialog()
    panel._participant_dialog = dialog
    panel._editing_treaty_id = "T1"
    panel._pending_participant_sides = (frozenset({"USA", "GBR"}), frozenset({"CAN"}))
    treaty = {"id": "T1", "side_a": [" usa ", "gbr"], "side_b": ["can"]}
    state = participant_state(treaty=treaty)
    context = SimpleNamespace(net_client=SimpleNamespace(player_id="player-1"))
    panel._resolve_participant_update(state, context)
    panel._resolve_participant_update(state, context)

    assert dialog.results == [True]
    assert panel._pending_participant_sides is None


def test_detail_lifecycle_notifies_once_and_acknowledges_only_current_treaty():
    panel = _panel()
    panel._show_details = True
    panel._selected_treaty_id = "missing"
    panel._editing_treaty_id = "T-old"
    panel._participant_dialog = ParticipantDialog()
    notices = []
    context = SimpleNamespace(on_notice=lambda *args, **kwargs: notices.append((args, kwargs)))

    panel._update_detail_lifecycle(client_state(tables={}, journal=SimpleNamespace(domain_events=[])), context)

    assert panel._participant_dialog.dismissed == 1
    assert panel._editing_treaty_id == ""
    assert notices[0][0] == ("Treaty details", "The treaty is no longer available.")

    old_acknowledge = notices[0][1]["on_acknowledge"]
    panel._detail_lifecycle = object()
    panel._show_details = True
    old_acknowledge()
    assert panel._show_details is True


def test_render_closes_list_and_dismisses_participant_dialog_when_window_is_closed(monkeypatch):
    panel = _panel()
    dialog = SimpleNamespace(is_open=False, dismiss=Mock(), render=Mock(return_value=None))
    panel._participant_dialog = dialog
    panel._resolve_participant_update = Mock()
    panel._update_detail_lifecycle = Mock()
    monkeypatch.setattr(treaties_live, "main_pillar_position", lambda _name: (10, 20))

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(treaties_live.WindowManager, "window", closed_window)
    context = SimpleNamespace(target_tag="USA", net_client=None, is_own_country=True)

    assert panel.render(client_state(tables={}), context) is False

    dialog.dismiss.assert_called_once()
    dialog.render.assert_not_called()
    panel._resolve_participant_update.assert_called_once()
    panel._update_detail_lifecycle.assert_called_once()


def test_render_resolves_requested_treaty_and_sends_participant_changes(monkeypatch):
    panel = _panel()
    panel.request_treaty("T1")
    panel._editing_treaty_id = "T1"
    panel._resolve_participant_update = Mock()
    panel._update_detail_lifecycle = Mock()
    panel._render_details_window = Mock()
    panel._diplomacy.ineligible_treaty_members = Mock(return_value={"MEX"})
    updated_sides = ({"USA", "MEX"}, {"CAN"})
    dialog = SimpleNamespace(
        is_open=False,
        render=Mock(return_value=updated_sides),
        dismiss=Mock(),
    )
    panel._participant_dialog = dialog
    client = Client()
    context = SimpleNamespace(target_tag="USA", net_client=client, is_own_country=True)
    state = client_state(
        tables={
            "countries_treaties": Table([{"id": "T1", "members": ["USA", "CAN"]}]),
            "pending_treaties": Table([]),
        },
        journal=SimpleNamespace(domain_events=[]),
    )

    assert panel.render(state, context) is True

    assert panel._requested_treaty_id == ""
    assert panel._selected_treaty_id == "T1"
    assert panel._show_details is True
    panel._render_details_window.assert_called_once_with(state, context)
    panel._diplomacy.ineligible_treaty_members.assert_called_once()
    assert panel._pending_participant_sides == (frozenset({"USA", "MEX"}), frozenset({"CAN"}))
    action = client.actions[0]
    assert action.treaty_id == "T1"
    assert action.side_a_country_tags == ["MEX", "USA"]
    assert action.side_b_country_tags == ["CAN"]


def test_content_renders_filters_sections_and_new_treaty_controls(monkeypatch):
    panel = _panel(open_editor_cb=Mock())
    panel._selected_treaty_id = "T1"
    panel._filter_member_tag = "OLD"
    panel._filter_type_key = "old_type"
    active = [{"id": "T1"}]
    pending = [{"id": "P1"}]
    panel._presenter.active_treaties_for_country = Mock(return_value=active)
    panel._presenter.pending_treaties_for_country = Mock(return_value=pending)
    panel._render_active_table = Mock()
    panel._render_pending_table = Mock()
    panel._render_actions = Mock()
    panel._render_recognition = Mock()
    ui = Ui(clicked={"treaties.new_treaty", "treaties.view_selected"})
    monkeypatch.setattr(treaties_live, "draw_required_tables", lambda *_args: True)
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(treaties_live, "_treaty_filter_options", lambda *_args: (
        [("USA", "United States")], [("alliance", "Alliance")],
    ))
    monkeypatch.setattr(treaties_live, "_matches_treaty_filter", lambda *_args: True)
    values = presentation_values()
    values[ClientPresentationKeys.COUNTRY_DIPLOMACY_RESTRICTION] = lambda *_args: None

    @contextmanager
    def opened_child(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)
    fake_imgui = MagicMock()
    fake_imgui.combo.side_effect = [(False, 0), (False, 0)]
    fake_imgui.begin_tab_bar.return_value = True
    fake_imgui.begin_tab_item.side_effect = [(True, None), (True, None)]
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)
    state = client_state(
        client_presentation=values,
        tables={"countries_treaties": Table([]), "pending_treaties": Table([])},
    )
    context = SimpleNamespace(target_tag="usa", is_own_country=True, on_notice=None)

    panel._render_content(state, context)

    assert panel._filter_member_tag == ""
    assert panel._filter_type_key == ""
    panel._presenter.active_treaties_for_country.assert_called_once_with(state, "USA")
    panel._render_active_table.assert_called_once_with(active)
    panel._render_pending_table.assert_called_once_with(pending)
    panel._render_actions.assert_called_once_with(state, context, "USA", active, pending)
    panel._render_recognition.assert_called_once_with(state, context, "USA")
    panel._open_editor_cb.assert_called_once()
    assert panel._show_details is True
    assert panel._details_needs_focus is True


def test_active_and_pending_tables_select_rows_and_show_response_counts(monkeypatch):
    panel = _panel()
    ui = MagicMock()
    ui.TableFlags_.borders_inner = 1
    ui.TableFlags_.row_bg = 2
    ui.TableColumnFlags_.width_stretch = 1
    ui.TableColumnFlags_.width_fixed = 2
    ui.begin_table.return_value = True
    selectable = Mock(return_value=True)
    empty_state = Mock()
    monkeypatch.setattr(treaties_live, "imgui", ui)
    monkeypatch.setattr(treaties_live, "_selectable_table_entry", selectable)
    monkeypatch.setattr(treaties_live, "draw_empty_state", empty_state)

    panel._render_active_table([{"id": "T1", "name": "Alliance", "type": "mutual_defense", "members_count": 3}])
    assert panel._selected_treaty_id == "T1"
    assert panel._selected_pending_id == ""
    assert panel._detail_lifecycle is None
    assert ui.text.call_args_list[0].args[0] == "Mutual Defense"
    assert ui.text.call_args_list[1].args[0] == "3"

    panel._render_pending_table([{
        "id": "P1",
        "title": "New pact",
        "treaty_type": "trade_agreement",
        "accepted_members": [" usa ", "CAN"],
        "required_responses": ["USA", "CAN", "MEX"],
    }])
    assert panel._selected_pending_id == "P1"
    assert panel._selected_treaty_id == ""
    assert ui.text.call_args_list[-2].args[0] == "Trade Agreement"
    assert ui.text.call_args_list[-1].args[0] == "2/4"
    assert ui.end_table.call_count == 2

    panel._render_active_table([])
    panel._render_pending_table([])
    assert [call.args[0] for call in empty_state.call_args_list] == [
        "No active treaties involve the selected country.",
        "No treaty proposal is awaiting a response.",
    ]


def test_active_treaty_actions_dispatch_leave_and_join_commands(monkeypatch):
    panel = _panel()
    panel._selected_treaty_id = "T1"
    ui = MagicMock()
    ui.button.side_effect = [True, True]
    ui.same_line = Mock()
    monkeypatch.setattr(treaties_live, "imgui", ui)
    client = Client()
    context = SimpleNamespace(net_client=client, is_own_country=True)

    panel._render_actions(
        SimpleNamespace(tables={}),
        context,
        "USA",
        [{"id": "T1", "open_to_new_members": True}],
        [],
    )

    assert len(client.actions) == 2
    assert client.actions[0].treaty_id == "T1"
    assert client.actions[1].treaty_id == "T1"
    ui.same_line.assert_called_once()


def test_details_window_renders_active_treaty_and_closes_on_request(monkeypatch):
    panel = _panel()
    panel._show_details = True
    panel._details_needs_focus = True
    panel._selected_treaty_id = "T1"
    row = {
        "id": "T1",
        "name": "Regional Compact",
        "type": "trade_agreement",
        "status": "active",
        "members": ["USA", "CAN"],
        "side_a": ["USA"],
        "side_b": ["CAN"],
        "conditions_json": "{}",
        "terms": "Reduce tariffs",
        "open_to_new_members": False,
    }
    state = SimpleNamespace(tables={
        "countries_treaties": Table([row]),
        "pending_treaties": Table([]),
        "treaty_effects": Table([{"treaty_id": "T1", "effect": "tariff_reduction", "value": 15}]),
    })
    panel._detail_lifecycle = SimpleNamespace(message="", last_row=row)
    panel._render_conditions = Mock()
    panel._render_details_member_list = Mock()
    panel._render_eligibility_list = Mock()
    panel._render_pressure_fallback = Mock()
    ui = Ui(clicked={"treaties.details.close"})
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(treaties_live, "draw_required_tables", lambda *_args: True)
    monkeypatch.setattr(treaties_live, "main_pillar_position", lambda _name: (100, 50))

    @contextmanager
    def opened_child(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)

    @contextmanager
    def opened_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live.WindowManager, "window", opened_window)
    fake_imgui = MagicMock()
    fake_imgui.get_io.return_value.display_size = SimpleNamespace(x=1280, y=720)
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)
    context = SimpleNamespace(target_tag="USA", is_own_country=True, net_client=Client())

    panel._render_details_window(state, context)

    assert panel._details_needs_focus is False
    assert panel._show_details is False
    fake_imgui.set_next_window_focus.assert_called_once()
    assert ui.text_at_calls[0][0][1] == "Regional Compact"
    assert any("TERMS" in call[0][0] and "tariff_reduction (15)" in call[0][0] for call in fake_imgui.text_wrapped.call_args_list)
    assert panel._render_conditions.call_args.args == (ui, row)
    assert panel._render_details_member_list.call_count == 2
    panel._render_eligibility_list.assert_called_once_with(row, state, context)
    panel._render_pressure_fallback.assert_called_once_with(ui)


def test_details_window_skips_missing_row_when_lifecycle_is_not_initialized():
    panel = _panel()
    panel._show_details = True
    panel._detail_lifecycle = None

    panel._render_details_window(SimpleNamespace(tables={}), SimpleNamespace())

    assert panel._show_details is True


def test_details_member_list_handles_populated_empty_and_closed_slots(monkeypatch):
    panel = _panel()
    panel._flags.draw_flag = Mock()
    ui = Ui()
    fake_imgui = MagicMock()
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)
    monkeypatch.setattr(treaties_live, "resolve_country_name", lambda _state, tag: f"Name {tag}")
    opened_states = iter((True, True, False))

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield next(opened_states)

    monkeypatch.setattr(treaties_live, "gml_child_frame", child_frame)
    state = SimpleNamespace(tables={})

    panel._render_details_member_list(ui, state, "lstA", ["CAN", "USA"])
    panel._render_details_member_list(ui, state, "lstEmpty", [])
    panel._render_details_member_list(ui, state, "lstClosed", ["MEX"])

    assert [call.args for call in panel._flags.draw_flag.call_args_list] == [
        ("CAN", 22.0, 13.0), ("USA", 22.0, 13.0),
    ]
    assert fake_imgui.same_line.call_count == 2
    assert [call.args[0] for call in fake_imgui.text.call_args_list] == [
        "Name CAN (CAN)", "Name USA (USA)",
    ]
    fake_imgui.text_disabled.assert_called_once_with("No members recorded.")


def test_participant_editor_preserves_two_sides_and_protects_sponsor():
    panel = _panel()
    dialog = Mock()
    panel._participant_dialog = dialog
    panel._diplomacy.ineligible_treaty_members = Mock(return_value={"MEX"})
    state = SimpleNamespace(tables={})
    treaty = {
        "id": "T1",
        "type": "mobility_agreement",
        "members": ["usa", "mex", "can"],
        "side_a": ["usa", "mex"],
        "side_b": ["can"],
        "source_country_id": "usa",
    }

    panel._open_participant_editor(treaty, state, remove_ineligible=True)

    dialog.open.assert_called_once_with(
        side_a={"USA", "MEX"},
        side_b={"CAN"},
        two_sided=True,
        protected_a={"USA"},
        protected_b=set(),
        ineligible_tags={"MEX"},
    )
    dialog.remove_ineligible.assert_called_once_with()
    assert panel._editing_treaty_id == "T1"


def test_participant_editor_places_one_sided_members_on_side_a():
    panel = _panel()
    panel._participant_dialog = Mock()
    panel._diplomacy.ineligible_treaty_members = Mock(return_value=set())

    panel._open_participant_editor(
        {
            "id": "T2",
            "type": "alliance",
            "members": ["USA", "CAN"],
            "side_a": [],
            "side_b": [],
            "source_country_id": "USA",
        },
        SimpleNamespace(tables={}),
    )

    panel._participant_dialog.open.assert_called_once_with(
        side_a={"USA", "CAN"},
        side_b=set(),
        two_sided=False,
        protected_a={"USA"},
        protected_b=set(),
        ineligible_tags=set(),
    )


def test_eligibility_list_renders_sorted_rows_and_removes_ineligible_members(monkeypatch):
    panel = _panel()
    ui = Ui(clicked={"treaties.details.remove_ineligible"})
    row_ui = MagicMock()
    notices = []
    panel._diplomacy.eligible_treaty_countries = Mock(
        return_value={"USA", "CAN", "MEX", "GBR", "FRA", "DEU"}
    )
    panel._diplomacy.ineligible_treaty_members = Mock(return_value={"MEX"})
    panel._open_participant_editor = Mock()
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(treaties_live, "resolve_country_name", lambda _state, tag: f"Name {tag}")

    @contextmanager
    def opened_child(*_args, **_kwargs):
        yield True

    @contextmanager
    def row(*_args, **_kwargs):
        yield row_ui

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)
    monkeypatch.setattr(treaties_live, "gml_row", row)
    treaty = {
        "id": "T1",
        "type": "mobility_agreement",
        "status": "active",
        "source_country_id": "USA",
    }
    state = SimpleNamespace(tables={})
    context = SimpleNamespace(
        target_tag="USA",
        is_own_country=True,
        net_client=Client(),
        on_notice=lambda *args: notices.append(args),
    )

    panel._render_eligibility_list(treaty, state, context)

    assert row_ui.picture.call_count == 6
    assert [call.args[1] for call in row_ui.text.call_args_list] == [
        "CAN", "DEU", "FRA", "GBR", "MEX", "USA",
    ]
    assert row_ui.text.call_args_list[0].kwargs == {
        "tooltip": "Name CAN", "test_id": "treaties.eligible.CAN",
    }
    button = next(call for call in ui.buttons if call[2] == "treaties.details.remove_ineligible")
    assert button[3]["enabled"] is True
    assert button[3]["dynamic_enabled"] is True
    panel._open_participant_editor.assert_called_once_with(treaty, state, remove_ineligible=True)
    assert notices == [(
        "Treaty eligibility",
        "Removed ineligible members from the draft: MEX. Apply the participant changes to save.",
    )]


def test_eligibility_list_handles_no_rows_and_disables_read_only_removal(monkeypatch):
    panel = _panel()
    ui = Ui(clicked={"treaties.details.remove_ineligible"})
    panel._diplomacy.eligible_treaty_countries = Mock(return_value=set())
    panel._diplomacy.ineligible_treaty_members = Mock(return_value={"USA"})
    panel._open_participant_editor = Mock()
    fake_imgui = MagicMock()
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)

    @contextmanager
    def opened_child(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)
    treaty = {"id": "T1", "type": "mobility_agreement", "source_country_id": "USA"}
    panel._render_eligibility_list(
        treaty,
        SimpleNamespace(tables={}),
        SimpleNamespace(target_tag="USA", is_own_country=False, net_client=Client(), on_notice=None),
    )
    panel._render_eligibility_list(None, SimpleNamespace(tables={}), SimpleNamespace())

    fake_imgui.text_disabled.assert_called_once_with("No eligible countries.")
    button = next(call for call in ui.buttons if call[2] == "treaties.details.remove_ineligible")
    assert button[3]["enabled"] is False
    panel._open_participant_editor.assert_not_called()


def test_recognition_panel_shows_empty_state_when_there_are_no_cases(monkeypatch):
    panel = _panel()
    panel._recognition_presenter.cases_for_country = Mock(return_value=[])
    empty_state = Mock()
    monkeypatch.setattr(treaties_live, "draw_empty_state", empty_state)
    imgui = MagicMock()
    monkeypatch.setattr(treaties_live, "imgui", imgui)

    panel._render_recognition(SimpleNamespace(tables={}), SimpleNamespace(), "USA")

    imgui.text.assert_called_once_with("UN RECOGNITION COUNCIL")
    empty_state.assert_called_once_with(
        "No completed annexation is awaiting or has received a recognition vote."
    )


def test_recognition_panel_dispatches_votes_and_renders_case_status(monkeypatch):
    panel = _panel()
    cases = [
        {
            "id": "C1", "region_id": "R1", "claimant_id": "USA", "former_owner_id": "CAN",
            "status": "pending", "yes_votes": 1, "no_votes": 0, "abstain_votes": 0,
            "eligible_voters": ["USA", "CAN"], "my_status": "", "my_vote": "",
            "days_remaining": 3, "reason": "",
        },
        {
            "id": "C2", "region_id": "R2", "claimant_id": "MEX", "former_owner_id": "USA",
            "status": "approved", "yes_votes": 2, "no_votes": 0, "abstain_votes": 1,
            "eligible_voters": ["USA", "CAN"], "my_status": "recognized", "my_vote": "",
            "days_remaining": 0, "reason": "",
        },
        {
            "id": "C3", "region_id": "R3", "claimant_id": "CAN", "former_owner_id": "MEX",
            "status": "pending", "yes_votes": 0, "no_votes": 1, "abstain_votes": 0,
            "eligible_voters": ["CAN"], "my_status": "", "my_vote": "no",
            "days_remaining": 0, "reason": "Voting period ended.",
        },
    ]
    panel._recognition_presenter.cases_for_country = Mock(return_value=cases)
    imgui = MagicMock()
    imgui.small_button.side_effect = [True, False, True]
    monkeypatch.setattr(treaties_live, "imgui", imgui)
    client = Client()
    context = SimpleNamespace(net_client=client, is_own_country=True)

    panel._render_recognition(SimpleNamespace(tables={}), context, "USA")

    assert len(client.actions) == 2
    assert [action.vote for action in client.actions] == ["yes", "abstain"]
    assert [action.case_id for action in client.actions] == ["C1", "C1"]
    assert all(action.country_tag == "USA" for action in client.actions)
    assert imgui.same_line.call_count == 2
    assert imgui.push_id.call_count == 3
    assert imgui.pop_id.call_count == 3
    rendered = [call.args[0] for call in imgui.text.call_args_list]
    assert any("Your country's status: Recognized" in text for text in rendered)
    assert any("Your current vote: No" in text for text in rendered)
    assert any("Voting deadline: 3 game days remaining" in text for text in rendered)
    imgui.text_disabled.assert_called_once_with("Voting period ended.")


def test_render_handles_missing_requested_treaty_and_list_branch(monkeypatch):
    panel = _panel()
    panel.request_treaty("missing")
    panel._resolve_participant_update = Mock()
    panel._update_detail_lifecycle = Mock()
    panel._render_content = Mock()
    panel._render_details_window = Mock()
    panel._participant_dialog = SimpleNamespace(
        is_open=False,
        dismiss=Mock(),
        render=Mock(return_value=None),
    )
    state = SimpleNamespace(
        tables={"countries_treaties": Table([]), "pending_treaties": Table([])}
    )
    context = SimpleNamespace(target_tag="USA", net_client=None, is_own_country=True)
    monkeypatch.setattr(treaties_live, "main_pillar_position", lambda _name: (10, 20))

    @contextmanager
    def opened_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live.WindowManager, "window", opened_window)

    assert panel.render(state, context) is True
    assert panel._selected_treaty_id == "missing"
    assert panel._selected_pending_id == ""
    assert panel._show_details is True
    assert panel._detail_lifecycle is None
    assert panel._requested_treaty_id == ""
    panel._render_details_window.assert_called_once_with(state, context)

    panel._show_details = False
    panel._render_details_window.reset_mock()
    assert panel.render(state, context) is True
    panel._render_content.assert_called_once_with(state, context)


def test_participant_update_and_detail_lifecycle_skip_missing_or_hidden_records():
    panel = _panel()
    panel._editing_treaty_id = "missing"
    panel._pending_participant_sides = (frozenset({"USA"}), frozenset({"CAN"}))
    state = participant_state()
    context = SimpleNamespace(net_client=Client())

    panel._resolve_participant_update(state, context)
    panel._resolve_participant_update(state, context)

    assert panel._pending_participant_sides is not None
    panel._update_detail_lifecycle(state, context)
    assert panel._detail_lifecycle is None


def test_content_returns_for_missing_tables_and_notifies_when_creation_is_restricted(monkeypatch):
    panel = _panel(open_editor_cb=Mock())
    context = SimpleNamespace(
        target_tag="USA",
        is_own_country=True,
        on_notice=Mock(),
    )
    values = presentation_values()
    values[ClientPresentationKeys.COUNTRY_DIPLOMACY_RESTRICTION] = (
        lambda *_args: "This country cannot initiate treaties."
    )
    state = client_state(client_presentation=values, tables={})
    monkeypatch.setattr(treaties_live, "draw_required_tables", lambda *_args: False)
    panel._render_content(state, context)

    ui = Ui(clicked={"treaties.new_treaty"})
    panel._presenter.active_treaties_for_country = Mock(return_value=[])
    panel._presenter.pending_treaties_for_country = Mock(return_value=[])
    panel._render_active_table = Mock()
    panel._render_pending_table = Mock()
    panel._render_actions = Mock()
    panel._render_recognition = Mock()
    monkeypatch.setattr(treaties_live, "draw_required_tables", lambda *_args: True)
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(treaties_live, "_treaty_filter_options", lambda *_args: ([], []))
    monkeypatch.setattr(treaties_live, "_matches_treaty_filter", lambda *_args: True)
    fake_imgui = MagicMock()
    fake_imgui.combo.side_effect = [(False, 0), (False, 0)]
    fake_imgui.begin_tab_bar.return_value = True
    fake_imgui.begin_tab_item.side_effect = [(True, None), (False, None)]
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)

    @contextmanager
    def opened_child(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(treaties_live, "gml_child_frame", opened_child)
    panel._render_content(state, context)

    context.on_notice.assert_called_once_with(
        "New treaty", "This country cannot initiate treaties."
    )
    panel._open_editor_cb.assert_not_called()


def test_action_and_details_methods_return_for_nonlocal_or_hidden_views(monkeypatch):
    panel = _panel()
    panel._render_actions(
        SimpleNamespace(),
        SimpleNamespace(net_client=None, is_own_country=True),
        "USA",
        [{"id": "T1"}],
        [],
    )
    panel._show_details = False
    panel._render_details_window(SimpleNamespace(tables={}), SimpleNamespace())


def _install_details_window(monkeypatch, *, opened, tables_available=True, ui=None):
    ui = ui or Ui()
    monkeypatch.setattr(treaties_live, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(
        treaties_live, "draw_required_tables", lambda *_args: tables_available
    )
    monkeypatch.setattr(treaties_live, "main_pillar_position", lambda _name: (100, 50))

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield True

    @contextmanager
    def details_window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(treaties_live, "gml_child_frame", child_frame)
    monkeypatch.setattr(treaties_live.WindowManager, "window", details_window)
    fake_imgui = MagicMock()
    fake_imgui.get_io.return_value.display_size = SimpleNamespace(x=1280, y=720)
    monkeypatch.setattr(treaties_live, "imgui", fake_imgui)
    return ui, fake_imgui


def test_details_window_closes_or_skips_when_window_or_tables_are_unavailable(monkeypatch):
    panel = _panel()
    panel._show_details = True
    panel._detail_lifecycle = SimpleNamespace(message="", last_row={})
    state = SimpleNamespace(tables={})
    context = SimpleNamespace(target_tag="USA", is_own_country=False, net_client=None)

    _install_details_window(monkeypatch, opened=False)
    panel._render_details_window(state, context)
    assert panel._show_details is False

    panel._show_details = True
    _install_details_window(monkeypatch, opened=True, tables_available=False)
    panel._render_details_window(state, context)
    assert panel._show_details is True


def test_details_window_renders_lifecycle_fallback_proposal_and_edit_paths(monkeypatch):
    panel = _panel()
    panel._render_conditions = Mock()
    panel._render_details_member_list = Mock()
    panel._render_eligibility_list = Mock()
    panel._render_pressure_fallback = Mock()
    panel._render_proposal_response_actions = Mock()
    panel._open_participant_editor = Mock()
    ui = Ui(clicked={"treaties.details.edit_participants"})
    _, fake_imgui = _install_details_window(monkeypatch, opened=True, ui=ui)
    context = SimpleNamespace(
        target_tag="USA",
        is_own_country=True,
        net_client=Client(),
    )

    cached_row = {
        "id": "removed",
        "members": ["USA"],
        "side_a": [],
        "side_b": [],
    }
    panel._show_details = True
    panel._selected_treaty_id = "removed"
    panel._selected_pending_id = ""
    panel._detail_lifecycle = SimpleNamespace(
        message="The treaty has been accepted.",
        last_row=cached_row,
    )
    cached_state = SimpleNamespace(
        tables={"countries_treaties": Table([]), "pending_treaties": Table([])}
    )
    panel._render_details_window(
        cached_state,
        context,
    )
    assert any(
        call[0][:2] == ("frmMain/txtStatus", "Accepted")
        for call in ui.text_at_calls
    )
    panel._render_details_member_list.assert_any_call(
        ui,
        cached_state,
        "lstCountriesA",
        ["USA"],
    )
    assert any(
        "The treaty has been accepted." in call.args[0]
        for call in fake_imgui.text_wrapped.call_args_list
    )

    active_row = {
        "id": "active",
        "type": "mobility_agreement",
        "source_country_id": "USA",
        "status": "active",
        "members": ["USA", "CAN"],
        "side_a": ["USA"],
        "side_b": ["CAN"],
    }
    active_state = SimpleNamespace(
        tables={
            "countries_treaties": Table([active_row]),
            "pending_treaties": Table([]),
            "treaty_effects": Table([]),
        }
    )
    panel._selected_treaty_id = "active"
    panel._detail_lifecycle = SimpleNamespace(message="", last_row=active_row)
    panel._render_details_window(active_state, context)
    panel._open_participant_editor.assert_called_once_with(active_row, active_state)
    assert any(
        call.args[0] == "No additional treaty details are recorded."
        for call in fake_imgui.text_wrapped.call_args_list
    )

    proposal = {
        "id": "pending",
        "treaty_type": "alliance",
        "status": "pending",
        "members": ["USA", "CAN"],
        "side_a": ["USA"],
        "side_b": ["CAN"],
    }
    pending_state = SimpleNamespace(
        tables={
            "countries_treaties": Table([]),
            "pending_treaties": Table([proposal]),
            "treaty_effects": Table([]),
        }
    )
    panel._selected_treaty_id = ""
    panel._selected_pending_id = "pending"
    panel._detail_lifecycle = SimpleNamespace(message="", last_row=proposal)
    panel._render_details_window(pending_state, context)
    panel._render_proposal_response_actions.assert_called_once_with(
        ui, proposal, context
    )
