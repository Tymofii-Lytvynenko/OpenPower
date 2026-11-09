from types import SimpleNamespace
import polars as pl

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.identity_policy_draft import (
    IdentityPolicyDraft,
    recognized,
)
from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel


def setup():
    rows = [dict(country_id="UKR", identity_type="language", identity_id="a", legal_status="legal", population_share=60., is_other_bucket=False),
            dict(country_id="UKR", identity_type="language", identity_id="b", legal_status="illegal", population_share=40., is_other_bucket=False)]
    draft = IdentityPolicyDraft()
    draft.select_country("UKR")
    state = SimpleNamespace(tables={"country_identity_groups": pl.DataFrame(rows)})
    actions = []
    context = PanelRenderContext("UKR", True, net_client=SimpleNamespace(player_id="player", send_action=actions.append))
    return rows, draft, state, context, actions


def test_swap_preserves_recognition_and_dispatches_expansion_first():
    rows, draft, state, context, actions = setup()
    assert draft.choose(rows, rows[0], "illegal")
    assert not draft.pending
    assert draft.choose(rows, rows[1], "legal") == ""
    assert draft.choose(rows, rows[0], "illegal") == ""
    assert draft.choose(rows, rows[1], "illegal")
    prepared, reason = draft.prepare(state, context)
    assert not reason
    assert [(a.identity_id, a.status) for a in prepared] == [("b", "legal"), ("a", "illegal")]
    assert not actions
    assert state.tables["country_identity_groups"].item(0, "legal_status") == "legal"


def test_identity_staleness_prevents_civil_law_dispatch_too():
    rows, draft, state, context, actions = setup()
    draft.choose(rows, rows[1], "legal")
    panel = InternalLawsPanel()
    panel._law_draft.select_country("UKR")
    panel._law_draft.choose(dict(law_id="speech", value="Old", allowed_values_json='["Old", "New"]'), "New")
    state.tables["country_laws"] = pl.DataFrame([dict(country_id="UKR", law_id="speech", value="Old", allowed_values_json='["Old", "New"]')])
    panel._identity_draft = draft
    state.tables.pop("country_identity_groups")
    assert panel._apply_drafts(state, context)
    assert not actions
    assert panel._law_draft.pending and draft.pending


def test_country_selection_and_aggregate_restrictions():
    rows, draft, state, context, actions = setup()
    assert draft.choose(rows, {**rows[1], "is_other_bucket": True}, "legal")
    assert draft.choose(rows, rows[1], "legal") == ""
    draft.select_country("POL")
    assert not draft.pending
    draft.select_country("UKR")
    assert draft.pending
    assert draft.prepare(state, PanelRenderContext("UKR", False, net_client=context.net_client))[1]


def test_recognition_rejects_unparseable_population_share():
    assert not recognized({"population_share": "not-a-number", "legal_status": "legal"})


def test_restoring_original_status_removes_the_pending_change():
    rows, draft, _state, _context, _actions = setup()

    assert draft.choose(rows, rows[1], "legal") == ""
    assert draft.pending
    assert draft.choose(rows, rows[1], "illegal") == ""
    assert not draft.pending


def test_prepare_rechecks_that_another_group_remains_recognized():
    rows, draft, state, context, _actions = setup()
    assert draft.choose(rows, rows[1], "legal") == ""
    assert draft.choose(rows, rows[0], "illegal") == ""

    rows[1]["population_share"] = "not-a-number"
    state.tables["country_identity_groups"] = pl.DataFrame(rows, strict=False)

    prepared, reason = draft.prepare(state, context)

    assert prepared == []
    assert reason == "At least one group of each edited identity type must remain legally recognized."
