"""Authoritative party batches with explicitly confirmed constitutional targets."""
import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.events import EventPoliticalPartyEligibilityChanged, EventGovernmentFormChanged
from src.shared.determinism import DeterministicRuntime
from modules.base.systems.politics.government_transition import apply_government_transition
from modules.base.systems.politics.party_constitution_policy import plan_party_constitution


def _key(value):
    return str(value or "").strip().casefold()


def validate_party_changes(government, rule, parties, action, *, check_count=True, limits_rule=None):
    if not government or not rule or _key(action.expected_government_form) != _key(government.get("government_form_id")):
        return "The inspected government form changed or is unavailable."
    if not rule.get("party_policy_editable"):
        return "This government form has no configured party-policy authority."
    if _key(government.get("crisis_status")) not in {"", "none", "resolved"}:
        return "Party status cannot change during a government crisis."
    if not isinstance(action.changes, dict) or not action.changes or any(not isinstance(k, str) or not k.strip() or type(v) is not bool for k, v in action.changes.items()):
        return "Choose listed parties and boolean eligibility statuses."
    index = {str(row.get("party_id") or ""): row for row in parties}
    if any(key not in index for key in action.changes):
        return "A selected party is missing from this country."
    ruling = str(government.get("ruling_party_id") or "")
    if any(not value and (key == ruling or bool(index[key].get("is_ruling"))) for key, value in action.changes.items()):
        return "The ruling party cannot be prohibited through party-status editing."
    eligible = sum(bool(action.changes.get(key, row.get("eligible", False))) for key, row in index.items())
    bounds = limits_rule if limits_rule is not None else rule
    minimum, maximum = bounds.get("minimum_eligible_parties", 1), bounds.get("maximum_eligible_parties", 0)
    if type(minimum) is not int or type(maximum) is not int or minimum < 1 or maximum < 0 or (maximum and maximum < minimum):
        return "The configured party-count limits are invalid."
    if check_count and (eligible < minimum or (maximum and eligible > maximum)):
        return "This party count requires a configured constitutional transition; the government form has not changed."
    return ""


def process_party_changes(state, action, now):
    country = str(action.country_tag or "").strip().upper()
    rows = state.tables["political_parties"].to_dicts()
    government_rows = state.tables["country_governments"].to_dicts()
    form_rules = state.tables["government_form_rules"].to_dicts()
    parties = [row for row in rows if str(row.get("country_id") or "").upper() == country]
    government = next((row for row in government_rows if str(row.get("country_id") or "").upper() == country), None)
    rule = next((row for row in form_rules if government and _key(row.get("government_form_id")) == _key(government.get("government_form_id"))), None)
    reason, plan = "", None
    if not any(str(row.get("id") or "").upper() == country for row in state.tables["countries"].iter_rows(named=True)):
        reason = "The selected country is unavailable."
    elif not player_controls_country(state, action.player_id, country):
        reason = "The issuer does not control this country's parties."
    elif any(str(row.get("country_id") or "").upper() == country and _key(row.get("status")) in {"pending", "active", "open", "escalated"} for row in state.tables["political_crises"].iter_rows(named=True)):
        reason = "Party status cannot change during an active political crisis."
    else:
        reason = validate_party_changes(government, rule, parties, action, check_count=False)
        if not reason:
            plan, reason = plan_party_constitution(rule, form_rules, parties, action, now)
        if not reason:
            reason = validate_party_changes(government, rule, parties, action,
                                            limits_rule=plan.target_rule if plan else None)
    if not reason:
        _apply_validated_party_changes(state, action, now, country, government, government_rows, rows, parties, plan)
    state.journal.append_command_result(dict(tick=int(state.globals.get("tick", 0)), player_id=str(action.player_id),
        action_type=type(action).__name__, status="rejected" if reason else "applied",
        reason=reason or ("Party statuses and constitutional form updated." if plan else "Party statuses updated."), country_id=country))


def _apply_validated_party_changes(state, action, now, country, government, government_rows, rows, parties, plan):
    changes = {}
    for row in parties:
        party = str(row.get("party_id") or "")
        if party in action.changes and bool(row.get("eligible")) != action.changes[party]:
            row.update(eligible=action.changes[party], updated_at_minute=now)
            changes[party] = action.changes[party]
    updated = {"political_parties": rows} if changes else {}
    events = []
    if plan:
        old_form = str(government["government_form_id"])
        transitions = state.tables["law_transitions"].to_dicts()
        elections = state.tables["political_elections"].to_dicts()
        changed = apply_government_transition(government, plan.target_rule, plan.target_form,
            str(government.get("ruling_party_id") or "").strip().lower(), plan.next_election_at_minute, now,
            country, rows, transitions, elections)
        candidates = dict(country_governments=government_rows, political_parties=rows,
                          law_transitions=transitions, political_elections=elections)
        updated.update({name: candidates[name] for name in changed})
        reason = "The confirmed party policy changed the constitutional form."
        history = state.tables["political_history"].to_dicts()
        history.append(dict(id=DeterministicRuntime(state.determinism).next_id("political-history", int(state.globals.get("tick", 0))),
                            country_id=country, event_type="government_form_changed", source_type="party_policy",
                            source_id=country, game_minute=now, previous_value=old_form, new_value=plan.target_form,
                            reason=reason, result="success"))
        updated["political_history"] = history
        events.append(EventGovernmentFormChanged(country, old_form, plan.target_form,
                                                 str(government["ruling_party_id"]), now, reason))
    if changes:
        events.append(EventPoliticalPartyEligibilityChanged(country, changes, str(government["government_form_id"]), now))
    # Materialize every affected table before publishing any part of the batch.
    frames = {name: pl.DataFrame(data, schema=state.tables[name].schema, strict=False) for name, data in updated.items()}
    for name, frame in frames.items():
        state.update_table(name, frame)
    state.events.extend(events)
