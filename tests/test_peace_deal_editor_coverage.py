from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.panels.military import peace_deal_editor as editor_module
from src.client.ui.panels.military.peace_deal_editor import PeaceDealEditor
from src.shared.actions import ActionRespondPeaceDeal, ActionSubmitPeaceDeal


def install_imgui(monkeypatch, *, combo_values=None, input_values=None, buttons=()):
    imgui = Mock()
    combo_values = combo_values or {}
    input_values = input_values or {}
    buttons = set(buttons)

    def combo(_label, current, _items, *, test_id):
        index = combo_values.get(test_id, current)
        return index != current, index

    def input_float(_label, current, *_args, test_id, **_kwargs):
        value = input_values.get(test_id, current)
        return value != current, value

    imgui.combo.side_effect = combo
    imgui.input_float.side_effect = input_float
    imgui.button.side_effect = lambda _label, *args, **kwargs: kwargs.get("test_id") in buttons
    monkeypatch.setattr(editor_module, "imgui", imgui)

    @contextmanager
    def region(*_args, **_kwargs):
        yield

    monkeypatch.setattr(editor_module, "semantic_region", region)
    return imgui


def war(**updates):
    result = {
        "id": "war-1",
        "side_a": ["USA", "FRA"],
        "side_b": ["CAN", "MEX"],
        "leader_a": "USA",
        "leader_b": "CAN",
    }
    result.update(updates)
    return result


def state(**tables):
    return SimpleNamespace(tables=tables, journal=SimpleNamespace(command_results=[]))


def test_render_resets_drafts_for_a_new_war_and_ignores_missing_war(monkeypatch):
    imgui = install_imgui(monkeypatch)
    editor = PeaceDealEditor()
    editor._render_proposal_builder = Mock()
    editor._render_responses = Mock()
    editor._offered = [{"type": "old"}]
    editor._requested = [{"type": "old-request"}]
    editor._pending_submission = ("old-war", "USA", "player-1")
    editor._submission_feedback = "old feedback"
    editor._submission_rejected = False

    editor.render(state(), None, "USA", True, None)
    editor._render_proposal_builder.assert_not_called()

    editor.render(state(), war(), "USA", True, None)

    assert editor._war_id == "war-1"
    assert editor._offered == []
    assert editor._requested == []
    assert editor._pending_submission is None
    assert editor._submission_feedback == ""
    editor._render_proposal_builder.assert_called_once()
    editor._render_responses.assert_called_once()
    imgui.text.assert_called_once_with("STRUCTURED PEACE PACKAGE", test_id="war_list.peace.heading")


def test_render_feedback_is_shown_only_for_non_rejected_results(monkeypatch):
    imgui = install_imgui(monkeypatch)
    editor = PeaceDealEditor()
    editor._render_proposal_builder = Mock()
    editor._render_responses = Mock()
    editor._war_id = "war-1"
    editor._submission_feedback = "Package submitted"

    editor.render(state(), war(), "USA", True, None)
    imgui.text_disabled.assert_called_once_with(
        "Package submitted", test_id="war_list.peace.submission_feedback",
    )

    imgui.text_disabled.reset_mock()
    editor._submission_rejected = True
    editor.render(state(), war(), "USA", True, None)
    imgui.text_disabled.assert_not_called()


def test_builder_enforces_war_leaders_and_builds_a_submitted_reparations_package(monkeypatch):
    imgui = install_imgui(
        monkeypatch,
        input_values={
            "war_list.peace.amount": 2_500_000.0,
            "war_list.peace.duration_months": 18.0,
        },
        buttons={"war_list.peace.add_clause", "war_list.peace.submit"},
    )
    editor = PeaceDealEditor()
    editor._clause_type = 1
    editor._direction = 1
    client = Mock()
    client.player_id = "player-1"

    editor._render_proposal_builder(state(), war(), "MEX", True, client)
    imgui.text_disabled.assert_called_once_with(
        "Only a war leader can submit a package.",
        test_id="war_list.peace.leader_restriction",
    )
    assert imgui.combo.call_count == 0

    editor._render_proposal_builder(state(), war(), "USA", True, client)

    assert editor._offered == [{
        "type": "war_reparations",
        "payer_country_id": "USA",
        "recipient_country_id": "CAN",
        "amount": 2_500_000.0,
        "duration_months": 18,
    }]
    client.send_action.assert_called_once()
    action = client.send_action.call_args.args[0]
    assert isinstance(action, ActionSubmitPeaceDeal)
    assert action.player_id == "player-1"
    assert action.war_id == "war-1"
    assert action.proposer_country_id == "USA"
    assert editor._pending_submission == ("war-1", "USA", "player-1")
    assert editor._submission_feedback == "Submitting peace package..."
    assert editor._submission_rejected is False
    assert imgui.end_disabled.call_count == 5


def test_builder_clear_and_disabled_submission_paths(monkeypatch):
    imgui = install_imgui(
        monkeypatch,
        buttons={
            "war_list.peace.clear", "war_list.peace.add_clause", "war_list.peace.submit",
        },
    )
    editor = PeaceDealEditor()
    editor._clause_type = 0
    editor._offered = [{"type": "old"}]
    editor._requested = [{"type": "old"}]
    editor._render_proposal_builder(state(), war(), "USA", False, None)

    assert editor._offered == []
    assert editor._requested == []
    assert editor._pending_submission is None
    assert imgui.begin_disabled.call_args_list[0].args == (False,)
    assert imgui.begin_disabled.call_args_list[1].args == (True,)
    assert imgui.begin_disabled.call_args_list[-1].args == (True,)
    assert imgui.text_disabled.call_args_list[0].args[0] == "An empty package requests a white peace."
    assert imgui.text_disabled.call_args_list[-2].args[0] == "Offered: none"
    assert imgui.text_disabled.call_args_list[-1].args[0] == "Requested: none"


def test_clause_fields_create_white_peace_reparations_and_demilitarization(monkeypatch):
    imgui = install_imgui(
        monkeypatch,
        input_values={
            "war_list.peace.amount": -2.0,
            "war_list.peace.duration_months": 500.0,
            "war_list.peace.maximum_strength": -5.0,
            "war_list.peace.duration_days": 5000.0,
        },
    )
    editor = PeaceDealEditor()
    sides = ({"USA"}, {"CAN"})

    assert editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN") is None
    assert imgui.text_disabled.call_args.kwargs["test_id"] == "war_list.peace.white_peace_help"

    editor._clause_type = 1
    editor._direction = 0
    reparations = editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN")
    assert reparations == {
        "type": "war_reparations", "payer_country_id": "CAN", "recipient_country_id": "USA",
        "amount": 1.0, "duration_months": 360,
    }
    editor._direction = 1
    reparations = editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN")
    assert reparations["payer_country_id"] == "USA"
    assert reparations["recipient_country_id"] == "CAN"

    editor._clause_type = 4
    editor._direction = 0
    demilitarization = editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN")
    assert demilitarization == {
        "type": "demilitarization", "country_id": "CAN",
        "maximum_strength": 0, "duration_days": 3650,
    }
    editor._direction = 1
    demilitarization = editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN")
    assert demilitarization["country_id"] == "USA"


def test_territory_clause_filters_participant_regions_and_handles_empty_options(monkeypatch):
    imgui = install_imgui(monkeypatch, combo_values={"war_list.peace.region": 0})
    editor = PeaceDealEditor()
    editor._clause_type = 2
    sides = ({"USA"}, {"CAN"})

    unavailable = editor._render_clause_fields(
        state(regions=pl.DataFrame({"id": [1], "owner": ["MEX"], "controller": ["MEX"]})),
        *sides, "USA", "USA", "CAN",
    )
    assert unavailable is None
    assert imgui.text_disabled.call_args.kwargs["test_id"] == "war_list.peace.region_unavailable"

    regions = pl.DataFrame({
        "id": [0, 2, 1, 3, 4],
        "owner": ["USA", "CAN", "CAN", "MEX", "USA"],
        "controller": ["USA", "USA", "CAN", "CAN", "CAN"],
    })
    clause = editor._render_clause_fields(state(regions=regions), *sides, "USA", "USA", "CAN")
    assert clause == {"type": "territory_transfer", "region_id": 1, "new_owner_country_id": "USA"}
    assert imgui.combo.call_args.kwargs["test_id"] == "war_list.peace.region"

    editor._direction = 1
    clause = editor._render_clause_fields(state(regions=regions), *sides, "USA", "USA", "CAN")
    assert clause["new_owner_country_id"] == "CAN"


def test_treaty_annulment_requires_active_treaty_between_war_sides(monkeypatch):
    imgui = install_imgui(monkeypatch, combo_values={"war_list.peace.treaty": 0})
    editor = PeaceDealEditor()
    editor._clause_type = 3
    sides = ({"USA"}, {"CAN"})

    assert editor._render_clause_fields(state(), *sides, "USA", "USA", "CAN") is None
    assert imgui.text_disabled.call_args.kwargs["test_id"] == "war_list.peace.treaty_unavailable"

    treaties = pl.DataFrame({
        "id": ["inactive", "one-side", "t1"],
        "name": ["Inactive", "One side", "Mutual pact"],
        "status": ["ended", "active", "active"],
        "members": [["USA", "CAN"], ["USA"], ["USA", "CAN"]],
    })
    clause = editor._render_clause_fields(
        state(countries_treaties=treaties), *sides, "USA", "USA", "CAN",
    )
    assert clause == {"type": "treaty_annulment", "treaty_id": "t1"}


def test_select_id_clamps_combo_indices_and_preserves_selected_values(monkeypatch):
    imgui = install_imgui(monkeypatch, combo_values={"pick": 9})
    editor = PeaceDealEditor()

    assert editor._select_id("Item", "b", [("a", "A"), ("b", "B")], test_id="pick") == "b"
    assert imgui.combo.call_args.args[1] == 1
    imgui.combo.side_effect = lambda _label, _index, _items, *, test_id: (True, -8)
    assert editor._select_id("Item", "missing", [("a", "A"), ("b", "B")], test_id="pick") == "a"


def test_pending_peace_deal_responses_accept_reject_and_respect_eligibility(monkeypatch):
    imgui = install_imgui(monkeypatch, buttons={"war_list.peace.response.accept.d1"})
    editor = PeaceDealEditor()
    deals = pl.DataFrame({
        "id": ["wrong-war", "accepted", "not-required", "d1"],
        "war_id": ["w2", "war-1", "war-1", "war-1"],
        "status": ["pending", "pending", "pending", "pending"],
        "responding_side": [["USA"], ["USA"], ["CAN"], ["USA", "MEX"]],
        "accepted_responses": [[], ["USA"], [], ["MEX"]],
        "offered_clauses_json": ["[]", "[]", "[]", "invalid"],
        "requested_clauses_json": ["[]", "[]", "[]", '[{"type":"white_peace"}]'],
        "proposer_country_id": ["CAN", "CAN", "CAN", "CAN"],
    })
    client = Mock()
    client.player_id = "player-1"
    editor._render_responses(state(peace_deals=deals), war(), "usa", True, client)

    client.send_action.assert_called_once()
    action = client.send_action.call_args.args[0]
    assert isinstance(action, ActionRespondPeaceDeal)
    assert action.accept is True
    assert action.deal_id == "d1"
    assert imgui.text_wrapped.call_count == 1
    assert "offered none; requested white_peace" in imgui.text_wrapped.call_args.args[0]

    imgui.button.side_effect = lambda _label, *args, **kwargs: kwargs.get("test_id") == "war_list.peace.response.reject.d1"
    editor._render_responses(state(peace_deals=deals), war(), "USA", True, client)
    assert client.send_action.call_count == 2
    assert client.send_action.call_args.args[0].accept is False


def test_response_table_absence_empty_and_non_owned_country_do_not_send_actions(monkeypatch):
    imgui = install_imgui(monkeypatch, buttons={
        "war_list.peace.response.accept.d1", "war_list.peace.response.reject.d1",
    })
    editor = PeaceDealEditor()
    editor._render_responses(state(), war(), "USA", True, Mock())
    editor._render_responses(state(peace_deals=pl.DataFrame()), war(), "USA", True, Mock())
    deals = pl.DataFrame({
        "id": ["d1"], "war_id": ["war-1"], "status": ["pending"],
        "responding_side": [["USA"]], "accepted_responses": [[]],
        "offered_clauses_json": ["{}"], "requested_clauses_json": ["[1]"],
        "proposer_country_id": [None],
    })
    client = Mock()
    editor._render_responses(state(peace_deals=deals), war(), "USA", False, client)
    client.send_action.assert_not_called()
    assert imgui.begin_disabled.call_args.args == (True,)


def test_submission_result_cursor_filters_identity_and_uses_failure_fallbacks():
    editor = PeaceDealEditor()
    empty_state = SimpleNamespace()
    editor._consume_submission_results(empty_state)
    assert editor._journal_cursor is not None
    editor._journal_cursor = Mock()
    editor._journal_cursor.consume.return_value = []
    editor._consume_submission_results(empty_state)
    editor._journal_cursor.consume.assert_called_once_with(())

    editor._pending_submission = ("war-1", "USA", "player-1")
    editor._journal_cursor.consume.return_value = [
        {"action_type": "Other", "actor_id": "player-1", "status": "failed"},
        {"action_type": "ActionSubmitPeaceDeal", "actor_id": "another", "status": "failed"},
        {"action_type": "ActionSubmitPeaceDeal", "player_id": "player-1", "status": "applied",
         "war_id": "war-2", "country_id": "USA"},
        {"action_type": "ActionSubmitPeaceDeal", "actor_id": "player-1", "status": "applied"},
        {"action_type": "ActionSubmitPeaceDeal", "player_id": "player-1", "status": "failed",
         "message": "Transport failed"},
    ]
    editor._offered = [{"type": "white_peace"}]
    editor._consume_submission_results(empty_state)
    assert editor._pending_submission is None
    assert editor._submission_feedback == "Transport failed"
    assert editor._submission_rejected is True
    assert editor._offered == [{"type": "white_peace"}]


def test_submission_result_applied_fallback_clears_draft_and_ignores_nonterminal_status():
    editor = PeaceDealEditor()
    editor._journal_cursor = Mock()
    editor._journal_cursor.consume.return_value = [
        {"action_type": "ActionSubmitPeaceDeal", "actor_id": "player-1", "status": "queued",
         "war_id": "war-1", "country_id": "USA"},
        {"action_type": "ActionSubmitPeaceDeal", "actor_id": "player-1", "status": "applied",
         "war_id": "war-1", "country_id": "usa"},
    ]
    editor._pending_submission = ("war-1", "USA", "player-1")
    editor._offered = [{"type": "treaty_annulment"}]
    editor._requested = [{"type": "demilitarization"}]

    editor._consume_submission_results(SimpleNamespace())

    assert editor._pending_submission is None
    assert editor._offered == []
    assert editor._requested == []
    assert editor._submission_feedback == "Peace package submitted."
    assert editor._submission_rejected is False


def test_clause_helpers_normalize_values_and_reject_invalid_json():
    assert PeaceDealEditor._decode(None) == []
    assert PeaceDealEditor._decode("not-json") == []
    assert PeaceDealEditor._decode('{"type":"white_peace"}') == []
    assert PeaceDealEditor._decode('[{"type":"white_peace"}, 1]') == []
    assert PeaceDealEditor._decode('[{"type":"white_peace"}]') == [{"type": "white_peace"}]
    assert PeaceDealEditor._summarize([]) == ""
    assert PeaceDealEditor._summarize([{}, {"type": "territory_transfer"}]) == "clause; territory_transfer"
    assert PeaceDealEditor._tag(None) == ""
    assert PeaceDealEditor._tag(" usa ") == "USA"
    assert PeaceDealEditor._tags(" usa, ,can ") == {"USA", "CAN"}
    assert PeaceDealEditor._tags(["usa", "", "can"]) == {"USA", "CAN"}
    assert PeaceDealEditor._tags(42) == set()
