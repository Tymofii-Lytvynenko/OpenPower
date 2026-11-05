"""Validation and application for direct constitutional form changes."""

from __future__ import annotations

import polars as pl

from modules.base.systems.politics.government_transition import apply_government_transition
from modules.base.systems.politics.political_policy import DEFAULT_ELECTION_INTERVAL_MINUTES
from modules.base.systems.world.authority_policy import (
    can_change_foreign_government,
    foreign_government_change_restriction,
    player_controls_country,
)
from modules.base.systems.politics.foreign_constitutional_policy import (
    build_foreign_government_effects,
)
from src.shared.actions import ActionSetGovernmentForm
from src.shared.determinism import DeterministicRuntime
from src.shared.events import EventGovernmentFormChanged, EventMartialLawChanged
from src.shared.state import GameState


_ACTIVE_CRISIS_STATUSES = frozenset({"pending", "active", "open", "escalated"})
_MAX_INT64 = 9_223_372_036_854_775_807


def process_government_form_change(
    state: GameState,
    action: ActionSetGovernmentForm,
    now: int,
) -> None:
    """Apply one validated government-form change as a single table batch."""

    country = _tag(action.country_tag)
    reason = _validate_government_form_change(state, action, country, now)
    if reason:
        _record_result(state, action, "rejected", reason, now, country)
        return

    governments = state.tables["country_governments"].to_dicts()
    government = next(row for row in governments if _tag(row.get("country_id")) == country)
    form_rules = state.tables["government_form_rules"].to_dicts()
    target_form = _key(action.target_form_id)
    target_rule = next(
        (row for row in form_rules if _key(row.get("government_form_id")) == target_form),
        None,
    )
    parties = state.tables["political_parties"].to_dicts()
    transitions = state.tables["law_transitions"].to_dicts()
    elections = state.tables["political_elections"].to_dicts()
    previous_form = str(government.get("government_form_id") or "").strip()
    ruling_party = str(government.get("ruling_party_id") or "").strip().casefold()
    form_changed = _key(previous_form) != target_form
    previous_martial_law = bool(government.get("martial_law", False))

    changed: set[str] = set()
    foreign_change = not player_controls_country(state, action.player_id, country)
    foreign_table_updates: dict[str, pl.DataFrame] = {}
    foreign_events = ()
    if form_changed:
        if target_rule is None:
            _record_result(
                state,
                action,
                "rejected",
                "The selected government form is unavailable or ambiguous.",
                now,
                country,
            )
            return
        interval = int(target_rule.get("election_interval_minutes") or 0)
        next_election = (
            now + (interval or DEFAULT_ELECTION_INTERVAL_MINUTES)
            if target_rule.get("election_eligible")
            else 0
        )
        changed = apply_government_transition(
            government,
            target_rule,
            target_form,
            ruling_party,
            next_election,
            now,
            country,
            parties,
            transitions,
            elections,
        )
        if foreign_change:
            foreign_table_updates, foreign_events = build_foreign_government_effects(
                state,
                _player_country_tag(state, action.player_id),
                country,
                now,
            )
            changed.update(foreign_table_updates)
        if "martial_law" in government and bool(government.get("martial_law")):
            target_name = str(target_rule.get("display_name") or target_form).casefold()
            # Older form-change commands preserve the established military-form cleanup rule.
            if action.target_martial_law is None and "military" not in target_form and "military" not in target_name:
                government["martial_law"] = False

    if action.target_martial_law is not None:
        government["martial_law"] = action.target_martial_law

    history = state.tables["political_history"].to_dicts()
    reason = "The government form changed under the selected constitutional rules."
    if form_changed:
        history.append(
            {
                "id": DeterministicRuntime(state.determinism).next_id(
                    "political-history", int(state.globals.get("tick", 0))
                ),
                "country_id": country,
                "event_type": "government_form_changed",
                "source_type": "direct_constitutional_change",
                "source_id": country,
                "game_minute": now,
                "previous_value": previous_form,
                "new_value": target_form,
                "reason": reason,
                "result": "success",
            }
        )

    new_martial_law = bool(government.get("martial_law", False))
    if new_martial_law != previous_martial_law:
        martial_law_reason = (
            "Martial law was declared by the country's government."
            if new_martial_law
            else "Martial law was ended by the country's government."
        )
        history.append(
            {
                "id": DeterministicRuntime(state.determinism).next_id(
                    "political-history", int(state.globals.get("tick", 0))
                ),
                "country_id": country,
                "event_type": "martial_law_changed",
                "source_type": "direct_constitutional_change",
                "source_id": country,
                "game_minute": now,
                "previous_value": "active" if previous_martial_law else "inactive",
                "new_value": "active" if new_martial_law else "inactive",
                "reason": martial_law_reason,
                "result": "success",
            }
        )

    if new_martial_law != previous_martial_law:
        changed.add("country_governments")
        state.events.append(
            EventMartialLawChanged(
                country_id=country,
                previous_status=previous_martial_law,
                new_status=new_martial_law,
                at_minute=now,
                reason=martial_law_reason,
            )
        )

    rows_by_table = {
        "country_governments": governments,
        "political_parties": parties,
        "law_transitions": transitions,
        "political_elections": elections,
        "political_history": history,
    }
    updated_frames = {
        name: (
            foreign_table_updates[name]
            if name in foreign_table_updates
            else pl.DataFrame(rows_by_table[name], schema=state.tables[name].schema, strict=False)
        )
        for name in changed | {"political_history"}
    }
    for name, frame in updated_frames.items():
        state.update_table(name, frame)
    state.events.extend(foreign_events)

    if form_changed:
        state.events.append(
            EventGovernmentFormChanged(
                country_id=country,
                previous_form_id=previous_form,
                new_form_id=target_form,
                ruling_party_id=ruling_party,
                at_minute=now,
                reason=reason,
            )
        )
    result_reason = reason if form_changed else martial_law_reason
    _record_result(state, action, "applied", result_reason, now, country)


def _validate_government_form_change(
    state: GameState,
    action: ActionSetGovernmentForm,
    country: str,
    now: int,
) -> str:
    if not country:
        return "Select a country before changing its government form."

    countries = state.tables.get("countries")
    if countries is None or "id" not in countries.columns or not any(
        _tag(value) == country for value in countries["id"].to_list()
    ):
        return "The selected country is unavailable."
    foreign_change = not player_controls_country(state, action.player_id, country)
    if foreign_change and not can_change_foreign_government(
        state, action.player_id, country, action.confirmed_foreign_change
    ):
        reason = foreign_government_change_restriction(state, action.player_id, country)
        if reason:
            return reason
        return "Confirm this foreign government-form change before applying it."
    governments = state.tables.get("country_governments")
    if governments is None or "country_id" not in governments.columns:
        return "The country's government record is unavailable."
    matching_governments = [
        row for row in governments.iter_rows(named=True)
        if _tag(row.get("country_id")) == country
    ]
    if len(matching_governments) != 1:
        return "The country's government record is missing or ambiguous."
    government = matching_governments[0]
    current_form = _key(government.get("government_form_id"))
    expected_form = _key(action.expected_form_id)
    if not expected_form or expected_form != current_form:
        return "The government form changed after this selection was opened. Review it and try again."

    current_martial_law = bool(government.get("martial_law", False))
    if action.expected_martial_law is not None:
        if type(action.expected_martial_law) is not bool:
            return "The expected martial-law state is invalid."
        if action.expected_martial_law != current_martial_law:
            return "Martial law changed after this selection was opened. Review it and try again."
    if action.target_martial_law is not None and type(action.target_martial_law) is not bool:
        return "The requested martial-law state is invalid."

    target_form = _key(action.target_form_id)
    if not target_form:
        return "Select an available government form."
    form_changed = target_form != current_form
    martial_law_changed = (
        action.target_martial_law is not None
        and action.target_martial_law != current_martial_law
    )
    if foreign_change:
        if not form_changed:
            return "Foreign constitutional changes can only change the government form."
        if martial_law_changed:
            return "Foreign constitutional changes cannot change martial-law status."
        if state.tables.get("countries_treaties") is None or state.tables.get("treaty_effects") is None:
            return "Military-access treaty data is unavailable for the foreign form change."
    if not form_changed and martial_law_changed:
        return ""
    if not form_changed:
        return "The selected government form is already in effect."

    if foreign_change and not _has_relation_pair(state, country, _player_country_tag(state, action.player_id)):
        return "Foreign constitutional relation data is unavailable."

    rules = state.tables.get("government_form_rules")
    if rules is None or "government_form_id" not in rules.columns:
        return "Government-form rules are unavailable."
    matching_rules = [
        row for row in rules.iter_rows(named=True)
        if _key(row.get("government_form_id")) == target_form
    ]
    if len(matching_rules) != 1:
        return "The selected government form is unavailable or ambiguous."
    rule = matching_rules[0]

    if _key(government.get("crisis_status")) not in {"", "none", "resolved"}:
        return "The government form cannot change during a political crisis."
    crises = state.tables.get("political_crises")
    if crises is not None and not crises.is_empty() and {"country_id", "status"}.issubset(crises.columns):
        if any(
            _tag(row.get("country_id")) == country
            and _key(row.get("status")) in _ACTIVE_CRISIS_STATUSES
            for row in crises.iter_rows(named=True)
        ):
            return "The government form cannot change during an active political crisis."

    parties_table = state.tables.get("political_parties")
    if parties_table is None or not {"country_id", "party_id", "eligible"}.issubset(parties_table.columns):
        return "The country's political-party data is unavailable."
    parties = [
        row for row in parties_table.iter_rows(named=True)
        if _tag(row.get("country_id")) == country
    ]
    if not parties:
        return "The country's political-party data is unavailable."
    ruling_party = _key(government.get("ruling_party_id"))
    if not ruling_party or not any(
        _key(row.get("party_id")) == ruling_party and bool(row.get("eligible"))
        for row in parties
    ):
        return "The current ruling party is not eligible under the party data."

    minimum = rule.get("minimum_eligible_parties")
    maximum = rule.get("maximum_eligible_parties")
    if type(minimum) is not int or type(maximum) is not int or minimum < 1 or maximum < 0:
        return "The selected government form has invalid party-count limits."
    eligible_count = sum(bool(row.get("eligible")) for row in parties)
    if eligible_count < minimum or (maximum and eligible_count > maximum):
        return "The eligible party count does not satisfy the selected government's rules."

    election_eligible = rule.get("election_eligible")
    interval = rule.get("election_interval_minutes")
    if type(election_eligible) is not bool or type(interval) is not int or interval < 0:
        return "The selected government form has invalid election rules."
    interval = interval or DEFAULT_ELECTION_INTERVAL_MINUTES
    if election_eligible and now + interval > _MAX_INT64:
        return "The next election date exceeds the supported range."
    return ""


def _record_result(
    state: GameState,
    action: ActionSetGovernmentForm,
    status: str,
    reason: str,
    now: int,
    country: str,
) -> None:
    state.journal.append_command_result(
        {
            "result_id": DeterministicRuntime(state.determinism).next_id(
                "political-command", int(state.globals.get("tick", 0))
            ),
            "action_type": type(action).__name__,
            "player_id": str(action.player_id),
            "status": status,
            "reason": reason,
            "game_minute": now,
            "country_id": country,
            "previous_form_id": str(action.expected_form_id or ""),
            "target_form_id": str(action.target_form_id or ""),
            "previous_martial_law": action.expected_martial_law,
            "target_martial_law": action.target_martial_law,
        }
    )


def _has_relation_pair(state: GameState, left: str, right: str) -> bool:
    relations = state.tables.get("countries_relations")
    if not left or not right or relations is None:
        return False
    if not {"source", "target", "value"}.issubset(relations.columns):
        return False
    pairs = {
        (_tag(row.get("source")), _tag(row.get("target")))
        for row in relations.iter_rows(named=True)
    }
    return (left, right) in pairs and (right, left) in pairs


def _player_country_tag(state: GameState, player_id: object) -> str:
    actor = str(player_id or "").strip()
    mapping = state.globals.get("player_country_map", {})
    if isinstance(mapping, dict):
        mapped = _tag(mapping.get(actor))
        if mapped:
            return mapped
    actor_tag = _tag(actor)
    if actor_tag in {"LOCAL_ADMIN", "LOCAL_PLAYER"}:
        return _tag(state.globals.get("player_tag"))
    return actor_tag


def _tag(value: object) -> str:
    return str(value or "").strip().upper()


def _key(value: object) -> str:
    return str(value or "").strip().casefold()
