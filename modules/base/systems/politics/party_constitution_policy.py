"""Preflight voluntary constitutional transitions caused by party-count changes."""
from dataclasses import dataclass
from src.shared.party_policy import party_count_transitions
from modules.base.systems.politics.political_policy import DEFAULT_ELECTION_INTERVAL_MINUTES


@dataclass(frozen=True)
class PartyConstitutionPlan:
    target_form: str
    target_rule: dict
    next_election_at_minute: int


def plan_party_constitution(rule, form_rules, parties, action, now):
    count = sum(bool(action.changes.get(str(row.get("party_id") or ""), row.get("eligible"))) for row in parties)
    minimum, maximum = rule.get("minimum_eligible_parties", 1), rule.get("maximum_eligible_parties", 0)
    required = count < minimum or (maximum and count > maximum)
    confirmed = str(action.confirmed_government_form or "").strip().casefold()
    if not required:
        return (None, "An unrelated constitutional transition cannot accompany this party batch.") if confirmed else (None, "")
    matches = [item for item in party_count_transitions(rule) if item.matches(count)]
    if len(matches) != 1:
        return None, "This party count requires one unambiguous configured constitutional transition."
    target = matches[0].target_form_id
    if confirmed != target:
        return None, "Explicit confirmation of the configured constitutional transition is required."
    if target == str(rule.get("government_form_id") or "").strip().casefold():
        return None, "The constitutional transition must select another government form."
    targets = [row for row in form_rules if str(row.get("government_form_id") or "").strip().casefold() == target]
    if len(targets) != 1:
        return None, "The configured constitutional target is unavailable or ambiguous."
    target_rule = targets[0]
    interval = target_rule.get("election_interval_minutes", 0)
    if type(interval) is not int or interval < 0 or interval > 2_147_483_647:
        return None, "The target government's election interval is invalid."
    next_election = now + (interval or DEFAULT_ELECTION_INTERVAL_MINUTES) if target_rule.get("election_eligible") else 0
    if next_election > 9_223_372_036_854_775_807:
        return None, "The target government's election date exceeds the supported range."
    return PartyConstitutionPlan(target, target_rule, next_election), ""
