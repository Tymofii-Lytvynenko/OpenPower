from types import SimpleNamespace
import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.party_policy_draft import PartyPolicyDraft
from src.shared.actions import ActionSetPartyEligibility
from src.shared.events import EventPoliticalPartyEligibilityChanged
from src.shared.state import GameState


def world():
    state = GameState(tables={
        "countries": pl.DataFrame([dict(id="AAA", money_reserves=100.)]),
        "country_governments": pl.DataFrame([dict(country_id="AAA", government_type="Custom", government_form_id="custom", initialized=True, election_eligible=False, ruling_party_id="r", crisis_status="none")]),
        "government_form_rules": pl.DataFrame([dict(government_form_id="custom", party_policy_editable=True, minimum_eligible_parties=2, maximum_eligible_parties=0)]),
        "political_parties": pl.DataFrame([dict(country_id="AAA", party_id=key, eligible=key != "b", is_ruling=key == "r", support_share=0.4) for key in ["r", "a", "b"]]),
    }, globals={"player_country_map": {"player": "AAA"}})
    ensure_base_tables(state)
    system = PoliticalLifecycleSystem()
    system.update(state, 0.)
    return state, system


def test_atomic_party_swap_updates_state_and_emits_exact_event():
    state, system = world()
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "custom", {"a": False, "b": True})]
    system.update(state, 0.)
    statuses = {r["party_id"]: r["eligible"] for r in state.tables["political_parties"].to_dicts()}
    assert statuses == {"r": True, "a": False, "b": True}
    assert state.journal.command_results[-1]["status"] == "applied"
    event = next(e for e in state.events if isinstance(e, EventPoliticalPartyEligibilityChanged))
    assert event.changes == {"a": False, "b": True}


@pytest.mark.parametrize("case", ["actor", "ruling", "count", "missing", "malformed", "form", "authority", "crisis", "maximum", "invalid_limits", "empty"])
def test_rejected_party_batches_change_no_party(case):
    state, system = world()
    changes = {"a": False, "b": True}
    actor, form = "player", "custom"
    if case == "empty": changes = {}
    if case == "maximum":
        changes = {"b": True}
        state.update_table("government_form_rules", state.tables["government_form_rules"].with_columns(pl.lit(2).alias("maximum_eligible_parties")))
    if case == "invalid_limits": state.update_table("government_form_rules", state.tables["government_form_rules"].with_columns(pl.lit(0).alias("minimum_eligible_parties")))
    if case == "actor": actor = "foreign"
    if case == "ruling": changes = {"r": False, "b": True}
    if case == "count": changes = {"a": False}
    if case == "missing": changes["gone"] = True
    if case == "malformed": changes["b"] = 1
    if case == "form": form = "old form"
    if case == "authority": state.update_table("government_form_rules", state.tables["government_form_rules"].with_columns(pl.lit(False).alias("party_policy_editable")))
    if case == "crisis": state.update_table("country_governments", state.tables["country_governments"].with_columns(pl.lit("active").alias("crisis_status")))
    before = state.tables["political_parties"].clone()
    state.current_actions = [ActionSetPartyEligibility(actor, "AAA", form, changes)]
    system.update(state, 0.)
    assert state.tables["political_parties"].equals(before)
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_party_draft_uses_one_batch_and_keeps_state_unchanged():
    state, system = world()
    draft = PartyPolicyDraft()
    draft.select_country("AAA")
    draft.choose(SimpleNamespace(party_id="a", eligible=True, is_ruling=False), False, "custom")
    draft.choose(SimpleNamespace(party_id="b", eligible=False, is_ruling=False), True, "custom")
    context = PanelRenderContext("AAA", True, net_client=SimpleNamespace(player_id="player"))
    prepared, reason = draft.prepare(state, context)
    assert not reason and len(prepared) == 1
    assert prepared[0].changes == {"a": False, "b": True}
    state.update_table("political_parties", state.tables["political_parties"].filter(pl.col("party_id") != "b"))
    assert draft.prepare(state, context)[1]


def test_party_changes_precede_an_election_due_in_the_same_update():
    state, system = world()
    state.update_table("country_governments", state.tables["country_governments"].with_columns(
        pl.lit(True).alias("election_eligible"), pl.lit(10).alias("next_election_at_minute")))
    state.update_table("government_form_rules", state.tables["government_form_rules"].with_columns(
        pl.lit(True).alias("election_eligible"), pl.lit(100).alias("election_interval_minutes")))
    state.update_table("political_parties", state.tables["political_parties"].with_columns(
        pl.when(pl.col("party_id") == "b").then(pl.lit(.9)).otherwise(pl.lit(.1)).alias("support_share")))
    state.time.total_minutes = 10
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "custom", {"a": False, "b": True})]
    system.update(state, 0.)
    assert state.tables["country_governments"].item(0, "ruling_party_id") == "b"


def test_noop_batch_does_not_emit_a_duplicate_change_event():
    state, system = world()
    state.events.clear()
    before = state.tables["political_parties"].clone()
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "custom", {"a": True})]
    system.update(state, 0.)
    assert state.tables["political_parties"].equals(before)
    assert not any(isinstance(e, EventPoliticalPartyEligibilityChanged) for e in state.events)


def test_legacy_builtin_form_gets_party_metadata_while_explicit_denial_survives():
    from modules.base.systems.politics.political_policy import default_government_form_rules
    rules = pl.DataFrame([
        dict(government_form_id="multi-party democracy", party_policy_editable=None, minimum_eligible_parties=1, maximum_eligible_parties=0),
        dict(government_form_id="centralized republic", party_policy_editable=False, minimum_eligible_parties=1, maximum_eligible_parties=0),
        dict(government_form_id="custom", party_policy_editable=None, minimum_eligible_parties=1, maximum_eligible_parties=0),
    ])
    result = default_government_form_rules(rules)
    builtin = result.filter(pl.col("government_form_id") == "multi-party democracy").row(0, named=True)
    assert builtin["party_policy_editable"] is True
    assert builtin["minimum_eligible_parties"] == 2
    assert result.filter(pl.col("government_form_id") == "centralized republic").item(0, "party_policy_editable") is False
    assert result.filter(pl.col("government_form_id") == "custom").item(0, "party_policy_editable") is None


def test_invalid_party_batch_blocks_other_policy_drafts_before_dispatch():
    from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel
    state, system = world()
    row = dict(country_id="AAA", law_id="speech", value="Old", allowed_values_json='["Old", "New"]')
    state.update_table("country_laws", pl.DataFrame([row]))
    panel = InternalLawsPanel()
    panel._law_draft.select_country("AAA")
    panel._law_draft.choose(row, "New")
    panel._party_draft.select_country("AAA")
    panel._party_draft.choose(SimpleNamespace(party_id="a", eligible=True, is_ruling=False), False, "custom")
    actions = []
    context = PanelRenderContext("AAA", True, net_client=SimpleNamespace(player_id="player", send_action=actions.append))
    assert panel._apply_drafts(state, context)
    assert actions == []
    assert panel._party_draft.pending and panel._law_draft.pending


def transition_world():
    import json
    state, system = world()
    rules = state.tables["government_form_rules"].with_columns(
        pl.when(pl.col("government_form_id") == "custom")
        .then(pl.lit(json.dumps([dict(target_form_id="single-party democracy", minimum=1, maximum=1)])))
        .otherwise(pl.col("party_count_transitions_json")).alias("party_count_transitions_json"))
    state.update_table("government_form_rules", rules)
    return state, system


def test_confirmed_party_transition_changes_form_and_resolves_dependent_schedules():
    from src.shared.events import EventGovernmentFormChanged
    state, system = transition_world()
    state.update_table("law_transitions", pl.DataFrame([
        dict(id="cancel", country_id="AAA", status="scheduled", carry_over_rule="cancel_on_regime_change", effective_at_minute=1000),
        dict(id="carry", country_id="AAA", status="scheduled", carry_over_rule="carry_over", effective_at_minute=1000),
    ]))
    state.update_table("political_elections", pl.DataFrame([dict(id="old", country_id="AAA", status="scheduled", scheduled_at_minute=500)]))
    ensure_base_tables(state)
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "custom", {"a": False}, "single-party democracy")]
    system.update(state, 0.)
    assert state.journal.command_results[-1]["status"] == "applied"
    government = state.tables["country_governments"].row(0, named=True)
    assert government["government_form_id"] == "single-party democracy"
    assert government["ruling_party_id"] == "r"
    assert government["next_election_at_minute"] > state.time.total_minutes
    assert state.tables["political_elections"].filter(pl.col("id") == "old").item(0, "status") == "cancelled"
    assert state.tables["law_transitions"].filter(pl.col("id") == "cancel").item(0, "status") == "cancelled"
    assert state.tables["law_transitions"].filter(pl.col("id") == "carry").item(0, "status") == "scheduled"
    assert any(isinstance(e, EventGovernmentFormChanged) for e in state.events)
    assert state.tables["political_history"].filter(pl.col("source_type") == "party_policy").height == 1
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "single-party democracy", {"a": True}, "multi-party democracy")]
    system.update(state, 0.)
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.tables["country_governments"].item(0, "government_form_id") == "multi-party democracy"


@pytest.mark.parametrize("mode", ["unconfirmed", "wrong", "unrelated", "invalid_schedule", "invalid_target_count"])
def test_constitutional_transition_rejection_is_atomic(mode):
    state, system = transition_world()
    target = "single-party democracy"
    changes = {"a": False}
    if mode == "unconfirmed": target = ""
    if mode == "wrong": target = "another form"
    if mode == "unrelated": changes = {"b": True}
    if mode in {"invalid_schedule", "invalid_target_count"}:
        column = "election_interval_minutes" if mode == "invalid_schedule" else "minimum_eligible_parties"
        value = -1 if mode == "invalid_schedule" else 2
        state.update_table("government_form_rules", state.tables["government_form_rules"].with_columns(
            pl.when(pl.col("government_form_id") == "single-party democracy").then(pl.lit(value))
            .otherwise(pl.col(column)).alias(column)))
    before = {name: state.tables[name].clone() for name in ["political_parties", "country_governments", "law_transitions", "political_elections", "political_history"]}
    state.current_actions = [ActionSetPartyEligibility("player", "AAA", "custom", changes, target)]
    system.update(state, 0.)
    assert state.journal.command_results[-1]["status"] == "rejected"
    for name, frame in before.items():
        assert state.tables[name].equals(frame), name


def test_question_answer_is_one_shot_and_no_restores_the_previous_draft():
    from src.client.ui.components.shared.generic_question_dialog import GenericQuestionDialog
    from src.client.ui.panels.politics.internal_laws_panel import InternalLawsPanel
    state, system = transition_world()
    panel = InternalLawsPanel()
    panel._party_draft.select_country("AAA")
    context = PanelRenderContext("AAA", True, net_client=SimpleNamespace(player_id="player"))
    party = SimpleNamespace(party_id="a", eligible=True, is_ruling=False)
    panel._choose_party(state, context, party, False, "custom")
    assert panel._party_question.is_open
    panel._party_question.answer(False)
    assert not panel._party_draft.pending
    panel._choose_party(state, context, party, False, "custom")
    panel._party_question.answer(True)
    actions, reason = panel._party_draft.prepare(state, context)
    assert not reason and actions[0].confirmed_government_form == "single-party democracy"
    calls = []
    question = GenericQuestionDialog("test")
    question.show("Confirm?", lambda: calls.append(True), lambda: calls.append(False))
    assert not question.show("Replacement?", lambda: calls.append("replacement"), lambda: None)
    question.answer(True)
    question.answer(False)
    assert calls == [True]
