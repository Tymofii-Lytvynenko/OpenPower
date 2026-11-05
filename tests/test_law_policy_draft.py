import json
from types import SimpleNamespace

import polars as pl
import pytest

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.law_policy_draft import LawPolicyDraft, law_choices


def setup():
    row = dict(country_id="UKR", law_id="speech", value="Permitted", allowed_values_json=json.dumps(["Permitted", "Restricted"]))
    state = SimpleNamespace(tables={"country_laws": pl.DataFrame([row])})
    actions = []
    context = PanelRenderContext("UKR", True, net_client=SimpleNamespace(player_id="player", send_action=actions.append))
    draft = LawPolicyDraft()
    draft.select_country("UKR")
    return row, state, context, draft, actions


def test_law_drafts_dispatch_only_on_apply_and_once():
    row, state, context, draft, actions = setup()
    assert draft.choose(row, "Restricted")
    assert not actions
    assert draft.apply(state, context) == ""
    assert actions[0].target_value == "Restricted"
    assert actions[0].country_tag == "UKR"
    assert draft.apply(state, context) == ""
    assert len(actions) == 1
    assert state.tables["country_laws"].item(0, "value") == "Permitted"


@pytest.mark.parametrize("change", ["removed", "value", "choices", "scheduled", "foreign"])
def test_stale_or_unauthorized_law_draft_dispatches_nothing(change):
    row, state, context, draft, actions = setup()
    draft.choose(row, "Restricted")
    if change == "removed":
        state.tables.clear()
    elif change == "value":
        state.tables["country_laws"] = pl.DataFrame([{**row, "value": "Restricted"}])
    elif change == "choices":
        state.tables["country_laws"] = pl.DataFrame([{**row, "allowed_values_json": "[]"}])
    elif change == "scheduled":
        state.tables["law_transitions"] = pl.DataFrame([dict(country_id="UKR", law_id="speech", status="scheduled")])
    else:
        context = PanelRenderContext("UKR", False, net_client=context.net_client)
    assert draft.apply(state, context)
    assert not actions
    assert draft.pending


def test_drafts_survive_country_selection_and_can_be_reverted():
    row, state, context, draft, actions = setup()
    draft.choose(row, "Restricted")
    draft.select_country("POL")
    assert not draft.pending
    draft.select_country("UKR")
    assert draft.pending
    draft.choose(row, "Permitted")
    assert not draft.pending


@pytest.mark.parametrize("value", ["broken", "{}", "null", '[1, false]'])
def test_unknown_law_choices_are_not_invented(value):
    assert law_choices({"allowed_values_json": value}) == ()


def test_changed_second_law_prevents_dispatch_of_first_draft():
    row, state, context, draft, actions = setup()
    second = {**row, "law_id": "assembly"}
    state.tables["country_laws"] = pl.DataFrame([row, second])
    draft.choose(row, "Restricted")
    draft.choose(second, "Restricted")
    state.tables["country_laws"] = pl.DataFrame([row, {**second, "value": "Restricted"}])
    assert draft.apply(state, context)
    assert actions == []


@pytest.mark.parametrize("decision", ["apply", "discard", "stale"])
def test_panel_close_only_finishes_when_draft_is_applied_or_discarded(decision):
    from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
    from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel
    row, state, context, draft, actions = setup()
    panel = InternalLawsPanel()
    panel._law_draft = draft
    draft.choose(row, "Restricted")
    if decision == "stale":
        state.tables.clear()
    result = panel._finish_close(CloseDecision.DISCARD if decision == "discard" else CloseDecision.APPLY, state, context)
    assert result is (decision == "stale")
    assert len(actions) == int(decision == "apply")
    assert bool(draft.pending) is (decision == "stale")
    assert panel._law_notice.is_open is (decision == "stale")
