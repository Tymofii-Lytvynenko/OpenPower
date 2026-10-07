from __future__ import annotations

import json
import math
from typing import Any

import polars as pl

from modules.base.systems.politics.law_transition_policy import (
    LawChangeDecision,
    normalize_law_rows,
    validate_law_change,
)
from modules.base.systems.politics.election_policy import (
    resolve_election,
    validate_election_override,
)
from modules.base.systems.politics.political_policy import (
    DEFAULT_ELECTION_INTERVAL_MINUTES,
    default_government_form_rules,
    initialize_country_politics,
    normalize_political_indicators,
)
from modules.base.systems.world.authority_policy import player_controls_country
from modules.base.systems.politics.political_crisis_policy import (
    RegimeChangeAssessment,
    assess_regime_change,
    normalize_regime_change_paths,
)
from src.shared.actions import (
    ActionChangePoliticalLaw,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
)
from src.shared.determinism import DeterministicRuntime
from src.shared.events import (
    EventGovernmentFormChanged,
    EventMessageCreated,
    EventPoliticalCrisisChanged,
    EventPoliticalElectionOverrideApplied,
    EventPoliticalElectionResolved,
    EventPoliticalLawTransitionResolved,
    EventPoliticalLawTransitionScheduled,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE


class PoliticalLifecycleSystem(ISystem):
    """Own normalized political state and effective-dated law transitions."""

    runtime_state_contract = {
        "_last_revisions": SYSTEM_STATE_CACHE,
        "_last_law_revision": SYSTEM_STATE_CACHE,
        "_last_transition_revision": SYSTEM_STATE_CACHE,
        "_next_law_deadline": SYSTEM_STATE_CACHE,
        "_last_election_revisions": SYSTEM_STATE_CACHE,
        "_next_election_deadline": SYSTEM_STATE_CACHE,
    }

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "country_governments",
                "government_form_rules",
                "political_parties",
                "country_laws",
                "law_transitions",
                "political_crises",
                "countries_relations",
                "political_elections",
                "political_history",
                "political_effects",
                "messages",
                "news_items",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "country_governments",
                "government_form_rules",
                "political_parties",
                "country_laws",
                "law_transitions",
                "political_effects",
                "political_history",
                "political_elections",
                "political_crises",
                "countries_relations",
                "messages",
                "news_items",
            }
        ),
        handles=frozenset(
            {ActionChangePoliticalLaw, ActionSetElectionOverride, ActionResolvePoliticalCrisis}
        ),
        phase=SystemPhase.POLITICS,
    )

    def __init__(self) -> None:
        self._last_revisions: tuple[object, ...] | None = None
        self._last_law_revision = -1
        self._last_transition_revision = -1
        self._next_law_deadline = -1
        self._last_election_revisions: tuple[object, ...] | None = None
        self._next_election_deadline = -1

    @property
    def id(self) -> str:
        return "base.political_lifecycle"

    @property
    def dependencies(self) -> list[str]:
        return ["base.bootstrap", "base.politics"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {
            "countries",
            "country_governments",
            "government_form_rules",
            "political_parties",
            "country_laws",
            "law_transitions",
            "political_crises",
            "political_elections",
            "political_effects",
            "political_history",
            "messages",
            "news_items",
        }
        if not required.issubset(state.tables):
            return

        countries = state.tables["countries"]
        if countries.is_empty() or "id" not in countries.columns:
            return

        self._initialize_political_state(state, countries)
        if self._last_law_revision != state.table_revisions.get("country_laws", 0):
            laws = normalize_law_rows(state.tables["country_laws"])
            self._update_if_changed(state, "country_laws", laws)
            self._last_law_revision = state.table_revisions.get("country_laws", 0)

        now = max(0, int(state.time.total_minutes))
        transition_revision = state.table_revisions.get("law_transitions", 0)
        if transition_revision != self._last_transition_revision:
            self._refresh_next_law_deadline(state)
        actions = [
            action
            for action in state.current_actions
            if isinstance(action, ActionChangePoliticalLaw)
        ]
        if actions:
            self._process_law_actions(state, actions, now)
            self._refresh_next_law_deadline(state)

        election_override_actions = [
            action
            for action in state.current_actions
            if isinstance(action, ActionSetElectionOverride)
        ]
        if election_override_actions:
            self._process_election_override_actions(state, election_override_actions, now)

        regime_change_actions = [
            action
            for action in state.current_actions
            if isinstance(action, ActionResolvePoliticalCrisis)
        ]
        if regime_change_actions:
            self._process_regime_change_actions(state, regime_change_actions, now)

        if self._next_law_deadline >= 0 and now >= self._next_law_deadline:
            self._resolve_due_law_transitions(state, now)
        self._refresh_next_law_deadline(state)

        if self._election_revision_key(state) != self._last_election_revisions:
            self._ensure_scheduled_elections(state, now)
            self._refresh_next_election_deadline(state)
        if self._next_election_deadline >= 0 and now >= self._next_election_deadline:
            self._resolve_due_elections(state, now)
            self._ensure_scheduled_elections(state, now)
        self._refresh_next_election_deadline(state)
        self._last_law_revision = state.table_revisions.get("country_laws", 0)

    def _process_regime_change_actions(
        self,
        state: GameState,
        actions: list[ActionResolvePoliticalCrisis],
        now: int,
    ) -> None:
        table_names = (
            "countries",
            "country_governments",
            "government_form_rules",
            "political_parties",
            "country_laws",
            "law_transitions",
            "political_crises",
            "political_elections",
            "political_history",
            "political_effects",
            "messages",
            "news_items",
        )
        rows = {name: state.tables[name].to_dicts() for name in table_names}
        relations_frame = state.tables.get("countries_relations")
        relations = relations_frame.to_dicts() if relations_frame is not None else None
        countries = rows["countries"]
        governments = rows["country_governments"]
        form_rules = rows["government_form_rules"]
        parties = rows["political_parties"]
        laws = rows["country_laws"]
        transitions = rows["law_transitions"]
        crises = rows["political_crises"]
        elections = rows["political_elections"]
        history = rows["political_history"]
        effects = rows["political_effects"]
        messages = rows["messages"]
        news = rows["news_items"]
        country_index = {self._tag(row.get("id")): row for row in countries}
        government_index = {self._tag(row.get("country_id")): row for row in governments}
        crisis_index = {str(row.get("id") or ""): row for row in crises}
        changed: set[str] = set()
        relations_changed = False
        runtime = DeterministicRuntime(state.determinism)

        for action in actions:
            country_id = self._tag(action.country_tag)
            crisis_id = str(action.crisis_id or "").strip()
            country = country_index.get(country_id)
            government = government_index.get(country_id)
            crisis = crisis_index.get(crisis_id)
            reason = ""
            if country is None or government is None or crisis is None:
                reason = "The country, government, or requested political crisis is unavailable."
            elif self._tag(crisis.get("country_id")) != country_id:
                reason = "The requested political crisis belongs to another country."
            elif not player_controls_country(state, action.player_id, country_id):
                reason = "The actor does not control this country."

            current_form = self._form_id(government.get("government_form_id")) if government else ""
            current_rule = next(
                (
                    row
                    for row in form_rules
                    if self._form_id(row.get("government_form_id")) == current_form
                ),
                None,
            )
            if not reason and current_rule is None:
                reason = "The current government form has no regime-change rules."

            assessment: RegimeChangeAssessment | None = None
            if not reason and current_rule and country and government and crisis:
                assessment, reason = assess_regime_change(
                    paths=normalize_regime_change_paths(
                        current_rule.get("regime_change_paths_json")
                    ),
                    path_id=action.decision,
                    crisis=crisis,
                    current_form_id=current_form,
                    government=government,
                    country=country,
                    form_rules=form_rules,
                    parties=parties,
                    laws=laws,
                    countries=countries,
                    relations=relations,
                    now_minute=now,
                )

            if reason or assessment is None or country is None or government is None or crisis is None:
                reason = reason or "The regime-change decision could not be validated."
                self._record_regime_change_result(
                    state, action, "rejected", reason, now, country_id, crisis_id
                )
                notified, news_added = self._notify_regime_change_actor(
                    state,
                    messages,
                    news,
                    action,
                    country_id,
                    "Regime change rejected",
                    reason,
                    now,
                )
                if notified or news_added:
                    if notified:
                        changed.add("messages")
                    if news_added:
                        changed.add("news_items")
                continue

            path = assessment.path
            old_form = current_form
            old_party = self._party_id(government.get("ruling_party_id"))
            outcome = "success" if assessment.success else "failed"
            deltas = (
                (path.approval_delta, path.stability_delta, path.corruption_delta)
                if assessment.success
                else (
                    path.failure_approval_delta,
                    path.failure_stability_delta,
                    path.failure_corruption_delta,
                )
            )
            for column, delta, fallback in zip(
                ("gvt_approval", "gvt_stability", "gvt_corruption"),
                deltas,
                (50.0, 50.0, 10.0),
            ):
                if delta == 0.0:
                    continue
                current = self._finite(country.get(column), fallback)
                if 0.0 <= current <= 1.0:
                    current *= 100.0
                country[column] = min(100.0, max(0.0, current + delta))
                changed.add("countries")

            if assessment.success:
                target_rule = next(
                    row
                    for row in form_rules
                    if self._form_id(row.get("government_form_id"))
                    == assessment.government_form_id
                )
                government.update(
                    {
                        "government_form_id": assessment.government_form_id,
                        "government_type": str(
                            target_rule.get("display_name") or assessment.government_form_id
                        ),
                        "ruling_party_id": assessment.ruling_party_id,
                        "succession_party_id": assessment.ruling_party_id,
                        "election_eligible": bool(target_rule.get("election_eligible", False)),
                        "next_election_at_minute": assessment.next_election_at_minute,
                        "updated_at_minute": now,
                    }
                )
                changed.add("country_governments")
                for party in parties:
                    if self._tag(party.get("country_id")) != country_id:
                        continue
                    is_ruling = self._party_id(party.get("party_id")) == assessment.ruling_party_id
                    if bool(party.get("is_ruling")) != is_ruling:
                        party["is_ruling"] = is_ruling
                        party["updated_at_minute"] = now
                        changed.add("political_parties")

                for law, target_value in self._validated_law_updates(
                    laws, country_id, path.law_values
                ):
                    if str(law.get("value") or "") == target_value:
                        continue
                    law["value"] = target_value
                    law["last_changed_at_minute"] = now
                    law["cooldown_until_minute"] = now + max(
                        0, int(law.get("cooldown_minutes") or 0)
                    )
                    changed.add("country_laws")
                    declared_by_value = self._decode_effects_by_value(
                        law.get("effects_by_value_json")
                    )
                    declared_effects = self._decode_effects(
                        declared_by_value.get(target_value, [])
                    )
                    for index, declared in enumerate(declared_effects):
                        domain = str(declared.get("domain") or "").strip().casefold()
                        effect_name = str(declared.get("effect") or "").strip().casefold()
                        value = self._finite(declared.get("value"), 0.0)
                        if not domain or not effect_name or value == 0.0:
                            continue
                        effects.append(
                            {
                                "id": f"{crisis_id}:law:{self._law_id(law.get('law_id'))}:{index}",
                                "country_id": country_id,
                                "source_type": "regime_change",
                                "source_id": crisis_id,
                                "domain": domain,
                                "effect": effect_name,
                                "value": min(1.0, max(-1.0, value)),
                                "effective_at_minute": now,
                                "expires_at_minute": 0,
                                "status": "active",
                                "reason": assessment.reason,
                            }
                        )
                        changed.add("political_effects")

                for transition in transitions:
                    if (
                        self._tag(transition.get("country_id")) == country_id
                        and str(transition.get("status") or "") == "scheduled"
                        and str(transition.get("carry_over_rule") or "")
                        == "cancel_on_regime_change"
                    ):
                        transition.update(
                            {
                                "status": "cancelled",
                                "reason": "The regime change cancelled this pending law transition.",
                            }
                        )
                        changed.add("law_transitions")
                for election in elections:
                    if (
                        self._tag(election.get("country_id")) == country_id
                        and str(election.get("status") or "") == "scheduled"
                    ):
                        election.update(
                            {
                                "status": "cancelled",
                                "resolved_at_minute": now,
                                "reason": "The regime change replaced the existing election schedule.",
                            }
                        )
                        changed.add("political_elections")

                if relations is not None:
                    for relation_effect in path.relation_effects:
                        directions = [(country_id, relation_effect.target_country_id)]
                        if relation_effect.reciprocal:
                            directions.append((relation_effect.target_country_id, country_id))
                        for source, target in directions:
                            relation = next(
                                row
                                for row in relations
                                if self._tag(row.get("source")) == source
                                and self._tag(row.get("target")) == target
                            )
                            relation["value"] = min(
                                100.0,
                                max(-100.0, self._finite(relation.get("value")) + relation_effect.delta),
                            )
                            relations_changed = True

            active_crises = [
                row
                for row in crises
                if self._tag(row.get("country_id")) == country_id
                and row is not crisis
                and self._text(row.get("status")).casefold()
                in {"pending", "active", "open", "escalated"}
            ]
            crisis.update(
                {
                    "status": "resolved",
                    "outcome": outcome,
                    "resolved_at_minute": now,
                    "reason": assessment.reason,
                }
            )
            changed.add("political_crises")
            if active_crises:
                selected = max(
                        active_crises,
                        key=lambda row: (
                            int(row.get("created_at_minute") or 0),
                            str(row.get("crisis_type") or "").strip(),
                            str(row.get("id") or "").strip(),
                        ),
                    )
                government["crisis_status"] = str(selected.get("crisis_type") or "none").strip()
            else:
                government["crisis_status"] = "none"
            government["updated_at_minute"] = now
            changed.add("country_governments")
            history.append(
                {
                    "id": runtime.next_id("political-history", int(state.globals.get("tick", 0))),
                    "country_id": country_id,
                    "event_type": "regime_change_resolved",
                    "source_type": "regime_change_path",
                    "source_id": crisis_id,
                    "game_minute": now,
                    "previous_value": f"{old_form}|{old_party}",
                    "new_value": (
                        f"{assessment.government_form_id}|{assessment.ruling_party_id}"
                        if assessment.success
                        else f"{old_form}|{old_party}"
                    ),
                    "reason": assessment.reason,
                    "result": outcome,
                }
            )
            changed.add("political_history")
            state.events.append(
                EventPoliticalCrisisChanged(
                    country_id=country_id,
                    crisis_id=crisis_id,
                    crisis_type=str(crisis.get("crisis_type") or "").strip(),
                    status="resolved",
                    reason=assessment.reason,
                    at_minute=now,
                )
            )
            if assessment.success and old_form != assessment.government_form_id:
                state.events.append(
                    EventGovernmentFormChanged(
                        country_id=country_id,
                        previous_form_id=old_form,
                        new_form_id=assessment.government_form_id,
                        ruling_party_id=assessment.ruling_party_id,
                        at_minute=now,
                        reason=assessment.reason,
                    )
                )
            self._record_regime_change_result(
                state, action, outcome, assessment.reason, now, country_id, crisis_id
            )
            notified, news_added = self._notify(
                state,
                messages,
                news,
                country_id,
                "Regime change " + ("succeeded" if assessment.success else "failed"),
                assessment.reason,
                now,
                crisis_id + ":regime-change-resolved",
            )
            if notified:
                changed.add("messages")
            if news_added:
                changed.add("news_items")

        for table_name in table_names:
            if table_name in changed:
                self._store_rows(state, table_name, rows[table_name])
        if relations_changed and relations is not None and relations_frame is not None:
            self._update_if_changed(
                state,
                "countries_relations",
                pl.DataFrame(relations, schema=relations_frame.schema, strict=False),
            )

    @staticmethod
    def _validated_law_updates(
        laws: list[dict[str, Any]], country_id: str, law_values: tuple[tuple[str, str], ...]
    ) -> list[tuple[dict[str, Any], str]]:
        index = {
            (
                str(row.get("country_id") or "").strip().upper(),
                str(row.get("law_id") or "").strip().casefold(),
            ): row
            for row in laws
        }
        validated: list[tuple[dict[str, Any], str]] = []
        for law_id, target_value in law_values:
            law = index[(country_id, law_id)]
            try:
                allowed = json.loads(str(law.get("allowed_values_json") or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                allowed = []
            canonical = next(
                (
                    value
                    for value in allowed
                    if isinstance(value, str) and value.casefold() == target_value.casefold()
                ),
                target_value,
            )
            validated.append((law, canonical))
        return validated

    @staticmethod
    def _decode_effects_by_value(value: Any) -> dict[str, Any]:
        try:
            parsed = value if isinstance(value, dict) else json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _record_regime_change_result(
        self,
        state: GameState,
        action: ActionResolvePoliticalCrisis,
        status: str,
        reason: str,
        now: int,
        country_id: str,
        crisis_id: str,
    ) -> None:
        runtime = DeterministicRuntime(state.determinism)
        state.journal.append_command_result(
            {
                "result_id": runtime.next_id("political-command", int(state.globals.get("tick", 0))),
                "action_type": type(action).__name__,
                "player_id": str(action.player_id),
                "status": status,
                "reason": reason,
                "game_minute": now,
                "country_id": country_id,
                "crisis_id": crisis_id,
                "decision": str(action.decision),
                "decision_reason": str(getattr(action, "decision_reason", "") or ""),
            }
        )

    def _notify_regime_change_actor(
        self,
        state: GameState,
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        action: ActionResolvePoliticalCrisis,
        requested_country_id: str,
        subject: str,
        body: str,
        now: int,
    ) -> tuple[bool, bool]:
        mapping = state.globals.get("player_country_map", {})
        actor_country = self._tag(mapping.get(str(action.player_id))) if isinstance(mapping, dict) else ""
        if not actor_country and self._tag(action.player_id) in {"SERVER", "AI", "AI_SYSTEM"}:
            actor_country = requested_country_id
        if not actor_country:
            return False, False
        return self._notify(
            state,
            messages,
            news,
            actor_country,
            subject,
            body,
            now,
            f"political-crisis-rejection:{int(state.globals.get('tick', 0))}:{action.player_id}:{action.crisis_id}",
        )

    def _initialize_political_state(self, state: GameState, countries: pl.DataFrame) -> None:
        country_ids = tuple(countries["id"].to_list())
        political_revisions = tuple(
            state.table_revisions.get(name, 0)
            for name in (
                "country_governments",
                "government_form_rules",
                "political_parties",
            )
        )
        revision_key = (country_ids, political_revisions)
        if revision_key == self._last_revisions:
            return

        normalized_countries = normalize_political_indicators(countries)
        governments, parties, rules = initialize_country_politics(
            normalized_countries,
            state.tables.get("country_governments", pl.DataFrame()),
            state.tables.get("political_parties", pl.DataFrame()),
            default_government_form_rules(state.tables.get("government_form_rules", pl.DataFrame())),
            int(state.time.total_minutes),
        )
        self._update_if_changed(state, "government_form_rules", rules)
        self._update_if_changed(state, "political_parties", parties)
        self._update_if_changed(state, "country_governments", governments)
        self._update_if_changed(state, "countries", normalized_countries)
        self._last_revisions = (
            country_ids,
            tuple(
                state.table_revisions.get(name, 0)
                for name in (
                    "country_governments",
                    "government_form_rules",
                    "political_parties",
                )
            ),
        )

    def _process_law_actions(
        self,
        state: GameState,
        actions: list[ActionChangePoliticalLaw],
        now: int,
    ) -> None:
        country_rows = state.tables["countries"].to_dicts()
        government_rows = state.tables["country_governments"].to_dicts()
        form_rows = state.tables["government_form_rules"].to_dicts()
        law_rows = state.tables["country_laws"].to_dicts()
        transition_rows = state.tables["law_transitions"].to_dicts()
        crisis_rows = state.tables["political_crises"].to_dicts()
        history_rows = state.tables["political_history"].to_dicts()
        messages = state.tables["messages"].to_dicts()
        news = state.tables["news_items"].to_dicts()
        changed_laws = changed_transitions = changed_countries = changed_history = False
        changed_messages = changed_news = False
        country_index = {self._tag(row.get("id")): row for row in country_rows}
        government_index = {
            self._tag(row.get("country_id")): row for row in government_rows
        }
        form_index = {
            self._form_id(row.get("government_form_id")): row for row in form_rows
        }
        law_index = {
            (self._tag(row.get("country_id")), self._law_id(row.get("law_id"))): row
            for row in law_rows
        }
        pending = {
            (self._tag(row.get("country_id")), self._law_id(row.get("law_id")))
            for row in transition_rows
            if str(row.get("status") or "") == "scheduled"
        }
        active_crises = {
            self._tag(row.get("country_id"))
            for row in crisis_rows
            if str(row.get("status") or "").lower() in {"pending", "active", "open"}
        }

        for action in actions:
            country_id = self._tag(action.country_tag)
            law_id = self._law_id(action.law_id)
            country = country_index.get(country_id)
            government = government_index.get(country_id)
            law = law_index.get((country_id, law_id))
            form_rule = (
                form_index.get(self._form_id(government.get("government_form_id")))
                if government is not None
                else None
            )
            reason = ""
            if country is None or government is None or law is None or form_rule is None:
                reason = "The country, government, or requested law is unavailable."
            elif not player_controls_country(state, action.player_id, country_id):
                reason = "The actor does not control this country."

            decision: LawChangeDecision | None = None
            if not reason and law is not None and government is not None and form_rule is not None:
                decision, reason = validate_law_change(
                    law=law,
                    government=government,
                    form_rule=form_rule,
                    target_value=action.target_value,
                    now_minute=now,
                    treasury=country.get("money_reserves") if country is not None else None,
                    has_pending_transition=(country_id, law_id) in pending,
                    crisis_active=country_id in active_crises,
                )

            if reason or decision is None or law is None or government is None or country is None:
                reason = reason or "The law change could not be validated."
                self._record_command_result(state, action, "rejected", reason, now, country_id, law_id)
                notified, news_added = self._notify_actor(
                    state, messages, news, action, country_id, "Law change rejected", reason, now
                )
                changed_messages |= notified
                changed_news |= news_added
                continue

            runtime = DeterministicRuntime(state.determinism)
            transition_id = runtime.next_id("political-law", int(state.globals.get("tick", 0)))
            effective_at = now + decision.transition_minutes
            cooldown_until = effective_at + decision.cooldown_minutes
            transition = {
                "id": transition_id,
                "country_id": country_id,
                "law_id": law_id,
                "player_id": str(action.player_id),
                "government_form_id": self._form_id(government.get("government_form_id")),
                "previous_value": str(law.get("value") or ""),
                "target_value": decision.target_value,
                "transition_cost": decision.change_cost,
                "legal_authority": decision.legal_authority,
                "created_at_minute": now,
                "effective_at_minute": effective_at,
                "cooldown_until_minute": cooldown_until,
                "carry_over_rule": decision.carry_over_rule,
                "effects_json": self._json(list(decision.effects)),
                "status": "scheduled",
                "reason": "Authorized change scheduled for its configured effective minute.",
            }
            transition_rows.append(transition)
            pending.add((country_id, law_id))
            changed_transitions = True

            country["money_reserves"] = self._finite(country.get("money_reserves")) - decision.change_cost
            changed_countries = changed_countries or decision.change_cost > 0.0
            law["cooldown_until_minute"] = cooldown_until
            changed_laws = True
            history_rows.append(
                {
                    "id": runtime.next_id("political-history", int(state.globals.get("tick", 0))),
                    "country_id": country_id,
                    "event_type": "law_transition_scheduled",
                    "source_type": "action",
                    "source_id": transition_id,
                    "game_minute": now,
                    "previous_value": transition["previous_value"],
                    "new_value": decision.target_value,
                    "reason": transition["reason"],
                    "result": "scheduled",
                }
            )
            changed_history = True
            state.events.append(
                EventPoliticalLawTransitionScheduled(
                    country_id=country_id,
                    law_id=law_id,
                    transition_id=transition_id,
                    effective_at_minute=effective_at,
                )
            )
            self._record_command_result(
                state,
                action,
                "applied",
                transition["reason"],
                now,
                country_id,
                law_id,
                transition_id,
            )
            notified, news_added = self._notify(
                state,
                messages,
                news,
                country_id,
                "Law change scheduled",
                f"{law.get('title') or law_id} will change to {decision.target_value} at game minute {effective_at}.",
                now,
                transition_id,
            )
            changed_messages |= notified
            changed_news |= news_added

        if changed_countries:
            self._store_rows(state, "countries", country_rows)
        if changed_laws:
            self._store_rows(state, "country_laws", law_rows)
        if changed_transitions:
            self._store_rows(state, "law_transitions", transition_rows)
        if changed_history:
            self._store_rows(state, "political_history", history_rows)
        if changed_messages:
            self._store_rows(state, "messages", messages)
        if changed_news:
            self._store_rows(state, "news_items", news)

    def _resolve_due_law_transitions(self, state: GameState, now: int) -> None:
        transitions = state.tables["law_transitions"].to_dicts()
        due = sorted(
            (
                row
                for row in transitions
                if str(row.get("status") or "") == "scheduled"
                and int(row.get("effective_at_minute") or 0) <= now
            ),
            key=lambda row: (int(row.get("effective_at_minute") or 0), str(row.get("id") or "")),
        )
        if not due:
            return

        countries = state.tables["countries"].to_dicts()
        governments = state.tables["country_governments"].to_dicts()
        laws = state.tables["country_laws"].to_dicts()
        history = state.tables["political_history"].to_dicts()
        effects = state.tables["political_effects"].to_dicts()
        messages = state.tables["messages"].to_dicts()
        news = state.tables["news_items"].to_dicts()
        country_index = {self._tag(row.get("id")): row for row in countries}
        government_index = {self._tag(row.get("country_id")): row for row in governments}
        law_index = {
            (self._tag(row.get("country_id")), self._law_id(row.get("law_id"))): row
            for row in laws
        }
        transition_index = {str(row.get("id") or ""): row for row in transitions}
        runtime = DeterministicRuntime(state.determinism)
        laws_changed = history_changed = effects_changed = False
        messages_changed = news_changed = False

        for transition in due:
            transition_id = str(transition.get("id") or "")
            country_id = self._tag(transition.get("country_id"))
            law_id = self._law_id(transition.get("law_id"))
            government = government_index.get(country_id)
            law = law_index.get((country_id, law_id))
            reason = ""
            outcome = "effective"
            current_form = self._form_id(government.get("government_form_id")) if government else ""
            previous_form = self._form_id(transition.get("government_form_id"))
            if law is None or country_id not in country_index:
                outcome, reason = "rejected", "The country or law no longer exists."
            elif (
                transition.get("carry_over_rule") == "cancel_on_regime_change"
                and previous_form
                and current_form != previous_form
            ):
                outcome, reason = "cancelled", "The government form changed before the law became effective."
            elif str(law.get("value") or "") != str(transition.get("previous_value") or ""):
                outcome, reason = "cancelled", "The law changed after this request was scheduled."

            transition_row = transition_index[transition_id]
            transition_row["status"] = outcome
            transition_row["reason"] = reason or "The law became effective at its scheduled game minute."
            if outcome == "effective" and law is not None:
                old_value = str(law.get("value") or "")
                new_value = str(transition.get("target_value") or "")
                law["value"] = new_value
                law["last_changed_at_minute"] = now
                law["cooldown_until_minute"] = int(transition.get("cooldown_until_minute") or now)
                laws_changed = True
                for declared in self._decode_effects(transition.get("effects_json")):
                    value = self._finite(declared.get("value"))
                    if not math.isfinite(value):
                        continue
                    effects.append(
                        {
                            "id": runtime.next_id("political-effect", int(state.globals.get("tick", 0))),
                            "country_id": country_id,
                            "source_type": "law_transition",
                            "source_id": transition_id,
                            "domain": str(declared.get("domain") or ""),
                            "effect": str(declared.get("effect") or ""),
                            "value": min(1.0, max(-1.0, value)),
                            "effective_at_minute": now,
                            "expires_at_minute": 0,
                            "status": "active",
                            "reason": transition_row["reason"],
                        }
                    )
                    effects_changed = True
                history.append(
                    {
                        "id": runtime.next_id("political-history", int(state.globals.get("tick", 0))),
                        "country_id": country_id,
                        "event_type": "law_changed",
                        "source_type": "law_transition",
                        "source_id": transition_id,
                        "game_minute": now,
                        "previous_value": old_value,
                        "new_value": new_value,
                        "reason": transition_row["reason"],
                        "result": "effective",
                    }
                )
                history_changed = True

            state.events.append(
                EventPoliticalLawTransitionResolved(
                    country_id=country_id,
                    law_id=law_id,
                    transition_id=transition_id,
                    status=outcome,
                    reason=transition_row["reason"],
                    at_minute=now,
                )
            )
            notified, news_added = self._notify(
                state,
                messages,
                news,
                country_id,
                "Law change " + ("effective" if outcome == "effective" else outcome),
                transition_row["reason"],
                now,
                transition_id + ":resolved",
            )
            messages_changed |= notified
            news_changed |= news_added

        self._store_rows(state, "law_transitions", transitions)
        if laws_changed:
            self._store_rows(state, "country_laws", laws)
        if history_changed:
            self._store_rows(state, "political_history", history)
        if effects_changed:
            self._store_rows(state, "political_effects", effects)
        if messages_changed:
            self._store_rows(state, "messages", messages)
        if news_changed:
            self._store_rows(state, "news_items", news)

    def _record_command_result(
        self,
        state: GameState,
        action: ActionChangePoliticalLaw,
        status: str,
        reason: str,
        now: int,
        country_id: str,
        law_id: str,
        transition_id: str = "",
    ) -> None:
        runtime = DeterministicRuntime(state.determinism)
        state.journal.append_command_result(
            {
                "result_id": runtime.next_id("political-command", int(state.globals.get("tick", 0))),
                "action_type": type(action).__name__,
                "player_id": str(action.player_id),
                "status": status,
                "reason": reason,
                "game_minute": now,
                "country_id": country_id,
                "law_id": law_id,
                "target_value": str(action.target_value),
                "transition_id": transition_id,
                "decision_reason": str(getattr(action, "decision_reason", "") or ""),
            }
        )

    def _notify_actor(
        self,
        state: GameState,
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        action: ActionChangePoliticalLaw,
        requested_country_id: str,
        subject: str,
        body: str,
        now: int,
    ) -> tuple[bool, bool]:
        mapping = state.globals.get("player_country_map", {})
        actor_country = self._tag(mapping.get(str(action.player_id))) if isinstance(mapping, dict) else ""
        if not actor_country and str(action.player_id).strip().upper() in {"SERVER", "AI", "AI_SYSTEM"}:
            actor_country = requested_country_id
        if not actor_country:
            return False, False
        return self._notify(
            state,
            messages,
            news,
            actor_country,
            subject,
            body,
            now,
            f"political-rejection:{int(state.globals.get('tick', 0))}:{action.player_id}:{action.law_id}",
        )

    def _notify(
        self,
        state: GameState,
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        country_id: str,
        subject: str,
        body: str,
        now: int,
        source_id: str,
    ) -> tuple[bool, bool]:
        message_id = f"{source_id}:message:{country_id}"
        changed_message = message_id not in {str(row.get("id") or "") for row in messages}
        if changed_message:
            messages.append(
                {
                    "id": message_id,
                    "country_id": country_id,
                    "category": "politics",
                    "subject": subject,
                    "body": body,
                    "is_read": False,
                    "created_at": str(state.time.date_str),
                }
            )
            state.events.append(
                EventMessageCreated(message_id=message_id, country_tag=country_id, category="politics")
            )
        news_id = f"{source_id}:news"
        changed_news = news_id not in {str(row.get("id") or "") for row in news}
        if changed_news:
            news.append(
                {
                    "id": news_id,
                    "headline": subject,
                    "body": body,
                    "category": "politics",
                    "severity": "info",
                    "related_country_id": country_id,
                    "created_at": str(state.time.date_str),
                }
            )
        return changed_message, changed_news

    def _refresh_next_law_deadline(self, state: GameState) -> None:
        transitions = state.tables["law_transitions"]
        scheduled = transitions.filter(pl.col("status") == "scheduled")
        self._next_law_deadline = (
            int(scheduled["effective_at_minute"].min()) if not scheduled.is_empty() else -1
        )
        self._last_transition_revision = state.table_revisions.get("law_transitions", 0)

    @staticmethod
    def _election_revision_key(state: GameState) -> tuple[int, ...]:
        return tuple(
            state.table_revisions.get(name, 0)
            for name in (
                "country_governments",
                "government_form_rules",
                "political_parties",
                "political_elections",
            )
        )

    def _process_election_override_actions(
        self,
        state: GameState,
        actions: list[ActionSetElectionOverride],
        now: int,
    ) -> None:
        countries = state.tables["countries"].to_dicts()
        governments = state.tables["country_governments"].to_dicts()
        form_rules = state.tables["government_form_rules"].to_dicts()
        parties = state.tables["political_parties"].to_dicts()
        elections = state.tables["political_elections"].to_dicts()
        crises = state.tables["political_crises"].to_dicts()
        effects = state.tables["political_effects"].to_dicts()
        history = state.tables["political_history"].to_dicts()
        messages = state.tables["messages"].to_dicts()
        news = state.tables["news_items"].to_dicts()
        country_index = {self._tag(row.get("id")): row for row in countries}
        government_index = {self._tag(row.get("country_id")): row for row in governments}
        rule_index = {self._form_id(row.get("government_form_id")): row for row in form_rules}
        parties_by_country: dict[str, list[dict[str, Any]]] = {}
        for party in parties:
            parties_by_country.setdefault(self._tag(party.get("country_id")), []).append(party)

        changed = False
        messages_changed = False
        news_changed = False
        runtime = DeterministicRuntime(state.determinism)

        for action in actions:
            country_id = self._tag(action.country_tag)
            country = country_index.get(country_id)
            government = government_index.get(country_id)
            form_rule = (
                rule_index.get(self._form_id(government.get("government_form_id")))
                if government is not None
                else None
            )
            scheduled = sorted(
                (
                    row
                    for row in elections
                    if self._tag(row.get("country_id")) == country_id
                    and str(row.get("status") or "") == "scheduled"
                ),
                key=lambda row: (
                    int(row.get("scheduled_at_minute") or 0),
                    str(row.get("id") or ""),
                ),
            )
            reason = ""
            if country is None or government is None or form_rule is None:
                reason = "The country, government, or scheduled election is unavailable."
            elif not player_controls_country(state, action.player_id, country_id):
                reason = "The actor does not control this country."

            last_override = max(
                (
                    int(row.get("game_minute") or 0)
                    for row in history
                    if self._tag(row.get("country_id")) == country_id
                    and str(row.get("event_type") or "") == "election_override_applied"
                ),
                default=None,
            )
            active_crisis = any(
                self._tag(row.get("country_id")) == country_id
                and str(row.get("status") or "").strip().casefold()
                in {"pending", "active", "open"}
                for row in crises
            )
            decision = None
            if not reason and country is not None and government is not None and form_rule is not None:
                decision, reason = validate_election_override(
                    override_type=action.override_type,
                    duration_days=action.duration_days,
                    now_minute=now,
                    current_election_minute=(
                        scheduled[0].get("scheduled_at_minute")
                        if scheduled
                        else government.get("next_election_at_minute")
                    ),
                    form_rule=form_rule,
                    government=government,
                    treasury=country.get("money_reserves"),
                    last_override_at_minute=last_override,
                    party_ids=(row.get("party_id") for row in parties_by_country.get(country_id, [])),
                    crisis_active=active_crisis,
                )

            if reason or decision is None or country is None or government is None:
                reason = reason or "The election override could not be validated."
                self._record_election_override_result(
                    state, action, "rejected", reason, now, country_id
                )
                notified, news_added = self._notify_election_override_actor(
                    state,
                    messages,
                    news,
                    action,
                    country_id,
                    "Election override rejected",
                    reason,
                    now,
                )
                messages_changed |= notified
                news_changed |= news_added
                continue

            election = scheduled[0] if scheduled else None
            previous_date = int(
                (election or {}).get("scheduled_at_minute")
                or government.get("next_election_at_minute")
                or 0
            )
            previous_ruling = self._party_id(government.get("ruling_party_id"))
            override_id = runtime.next_id(
                "political-election-override", int(state.globals.get("tick", 0))
            )
            reason = (
                f"The {decision.override_type} election override was authorized; "
                f"the next legal election is at game minute {decision.next_election_at_minute}."
            )

            country["money_reserves"] = self._finite(country.get("money_reserves")) - decision.cost
            government.update(
                {
                    "next_election_at_minute": decision.next_election_at_minute,
                    "updated_at_minute": now,
                }
            )
            successor = previous_ruling
            if decision.successor_party_id:
                successor = self._party_id(decision.successor_party_id)
                government["ruling_party_id"] = successor
                government["succession_party_id"] = successor
                for party in parties_by_country.get(country_id, []):
                    party_id = self._party_id(party.get("party_id"))
                    party["is_ruling"] = party_id == successor
                    if party_id == successor:
                        party["updated_at_minute"] = now

            if election is None:
                election = {
                    "id": (
                        f"election-{country_id.lower()}-"
                        f"{decision.next_election_at_minute:012d}-{override_id}"
                    ),
                    "country_id": country_id,
                    "government_form_id": self._form_id(
                        government.get("government_form_id")
                    ),
                    "scheduled_at_minute": decision.next_election_at_minute,
                    "resolved_at_minute": 0,
                    "eligible_party_ids": [],
                    "coalition_party_ids": [],
                    "support_snapshot_json": "{}",
                    "results_json": "{}",
                    "turnout": 0.0,
                    "winner_party_id": "",
                    "override_type": decision.override_type,
                    "status": "scheduled",
                    "reason": reason,
                }
                elections.append(election)
            else:
                election.update(
                    {
                        "scheduled_at_minute": decision.next_election_at_minute,
                        "override_type": decision.override_type,
                        "reason": reason,
                    }
                )
            history.append(
                {
                    "id": runtime.next_id(
                        "political-history", int(state.globals.get("tick", 0))
                    ),
                    "country_id": country_id,
                    "event_type": "election_override_applied",
                    "source_type": "action",
                    "source_id": override_id,
                    "game_minute": now,
                    "previous_value": str(previous_date),
                    "new_value": str(decision.next_election_at_minute),
                    "reason": reason,
                    "result": "applied",
                }
            )
            for effect_name, value in (
                ("approval_delta", decision.approval_delta),
                ("stability_delta", decision.stability_delta),
            ):
                if value == 0.0:
                    continue
                effects.append(
                    {
                        "id": f"{override_id}:{effect_name}",
                        "country_id": country_id,
                        "source_type": "election_override",
                        "source_id": override_id,
                        "domain": "override",
                        "effect": effect_name,
                        "value": value,
                        "effective_at_minute": now,
                        "expires_at_minute": 0,
                        "status": "pending",
                        "reason": reason,
                    }
                )

            state.events.append(
                EventPoliticalElectionOverrideApplied(
                    country_id=country_id,
                    override_id=override_id,
                    override_type=decision.override_type,
                    next_election_at_minute=decision.next_election_at_minute,
                    at_minute=now,
                    ruling_party_id=successor,
                )
            )
            self._record_election_override_result(
                state, action, "applied", reason, now, country_id, override_id
            )
            notified, news_added = self._notify_election_override_actor(
                state,
                messages,
                news,
                action,
                country_id,
                "Election override applied",
                reason,
                now,
            )
            messages_changed |= notified
            news_changed |= news_added
            changed = True

        if changed:
            self._store_rows(state, "countries", countries)
            self._store_rows(state, "country_governments", governments)
            self._store_rows(state, "political_parties", parties)
            self._store_rows(state, "political_elections", elections)
            self._store_rows(state, "political_effects", effects)
            self._store_rows(state, "political_history", history)
        if messages_changed:
            self._store_rows(state, "messages", messages)
        if news_changed:
            self._store_rows(state, "news_items", news)

    def _record_election_override_result(
        self,
        state: GameState,
        action: ActionSetElectionOverride,
        status: str,
        reason: str,
        now: int,
        country_id: str,
        override_id: str = "",
    ) -> None:
        runtime = DeterministicRuntime(state.determinism)
        state.journal.append_command_result(
            {
                "result_id": runtime.next_id(
                    "political-command", int(state.globals.get("tick", 0))
                ),
                "action_type": type(action).__name__,
                "player_id": str(action.player_id),
                "status": status,
                "reason": reason,
                "game_minute": now,
                "country_id": country_id,
                "override_type": str(action.override_type),
                "duration_days": action.duration_days,
                "override_id": override_id,
                "decision_reason": str(getattr(action, "decision_reason", "") or ""),
            }
        )

    def _notify_election_override_actor(
        self,
        state: GameState,
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        action: ActionSetElectionOverride,
        requested_country_id: str,
        subject: str,
        body: str,
        now: int,
    ) -> tuple[bool, bool]:
        mapping = state.globals.get("player_country_map", {})
        actor_country = self._tag(mapping.get(str(action.player_id))) if isinstance(mapping, dict) else ""
        if not actor_country and str(action.player_id).strip().upper() in {
            "SERVER",
            "AI",
            "AI_SYSTEM",
        }:
            actor_country = requested_country_id
        if not actor_country:
            return False, False
        source_id = (
            f"election-override:{int(state.globals.get('tick', 0))}:"
            f"{action.player_id}:{requested_country_id}:{action.override_type}"
        )
        return self._notify(
            state,
            messages,
            news,
            actor_country,
            subject,
            body,
            now,
            source_id,
        )

    def _ensure_scheduled_elections(self, state: GameState, now: int) -> None:
        election_rows = state.tables["political_elections"].to_dicts()
        governments = state.tables["country_governments"].to_dicts()
        rules = {
            self._form_id(row.get("government_form_id")): row
            for row in state.tables["government_form_rules"].to_dicts()
        }
        scheduled_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in election_rows:
            if str(row.get("status") or "") == "scheduled":
                scheduled_by_country.setdefault(self._tag(row.get("country_id")), []).append(row)

        changed = False
        for government in sorted(governments, key=lambda row: self._tag(row.get("country_id"))):
            country_id = self._tag(government.get("country_id"))
            if not country_id:
                continue
            form_id = self._form_id(government.get("government_form_id"))
            rule = rules.get(form_id, {})
            scheduled_at = max(0, int(government.get("next_election_at_minute") or 0))
            electoral = bool(government.get("election_eligible")) and bool(
                rule.get("election_eligible", False)
            )
            existing = sorted(
                scheduled_by_country.get(country_id, []),
                key=lambda row: (int(row.get("scheduled_at_minute") or 0), str(row.get("id") or "")),
            )
            if not electoral or scheduled_at <= 0:
                for row in existing:
                    row["status"] = "cancelled"
                    row["resolved_at_minute"] = now
                    row["reason"] = "The current government has no scheduled election."
                    changed = True
                continue

            matching = [
                row for row in existing
                if int(row.get("scheduled_at_minute") or 0) == scheduled_at
            ]
            keep = matching[0] if matching else None
            for row in existing:
                if row is keep:
                    if self._form_id(row.get("government_form_id")) != form_id:
                        row["government_form_id"] = form_id
                        changed = True
                    continue
                row["status"] = "superseded"
                row["resolved_at_minute"] = now
                row["reason"] = "The canonical government election date changed."
                changed = True
            if keep is None:
                election_rows.append(
                    {
                        "id": f"election-{country_id.lower()}-{scheduled_at:012d}",
                        "country_id": country_id,
                        "government_form_id": form_id,
                        "scheduled_at_minute": scheduled_at,
                        "resolved_at_minute": 0,
                        "eligible_party_ids": [],
                        "coalition_party_ids": [],
                        "support_snapshot_json": "{}",
                        "results_json": "{}",
                        "turnout": 0.0,
                        "winner_party_id": "",
                        "override_type": "",
                        "status": "scheduled",
                        "reason": "Election is scheduled by the current government rules.",
                    }
                )
                changed = True

        if changed:
            self._store_rows(state, "political_elections", election_rows)

    def _resolve_due_elections(self, state: GameState, now: int) -> None:
        election_rows = state.tables["political_elections"].to_dicts()
        due = sorted(
            (
                row
                for row in election_rows
                if str(row.get("status") or "") == "scheduled"
                and int(row.get("scheduled_at_minute") or 0) <= now
            ),
            key=lambda row: (
                int(row.get("scheduled_at_minute") or 0),
                self._tag(row.get("country_id")),
                str(row.get("id") or ""),
            ),
        )
        if not due:
            return

        countries = state.tables["countries"].to_dicts()
        governments = state.tables["country_governments"].to_dicts()
        parties = state.tables["political_parties"].to_dicts()
        form_rules = state.tables["government_form_rules"].to_dicts()
        history = state.tables["political_history"].to_dicts()
        messages = state.tables["messages"].to_dicts()
        news = state.tables["news_items"].to_dicts()
        country_index = {self._tag(row.get("id")): row for row in countries}
        government_index = {self._tag(row.get("country_id")): row for row in governments}
        rule_index = {self._form_id(row.get("government_form_id")): row for row in form_rules}
        party_index: dict[str, list[dict[str, Any]]] = {}
        for party in parties:
            party_index.setdefault(self._tag(party.get("country_id")), []).append(party)
        election_index = {str(row.get("id") or ""): row for row in election_rows}
        runtime = DeterministicRuntime(state.determinism)
        changed_governments = changed_parties = changed_history = False
        messages_changed = news_changed = False

        for election in due:
            country_id = self._tag(election.get("country_id"))
            election_id = str(election.get("id") or "")
            government = government_index.get(country_id)
            country = country_index.get(country_id)
            form_id = self._form_id(government.get("government_form_id")) if government else ""
            rule = rule_index.get(form_id, {})
            election_row = election_index[election_id]
            if (
                government is None
                or country is None
                or not bool(government.get("election_eligible"))
                or not bool(rule.get("election_eligible", False))
            ):
                election_row["status"] = "cancelled"
                election_row["resolved_at_minute"] = now
                election_row["reason"] = "The government is no longer eligible to hold this election."
                continue

            country_parties = party_index.get(country_id, [])
            outcome = resolve_election(
                country_parties,
                ruling_party_id=government.get("ruling_party_id"),
                succession_party_id=government.get("succession_party_id"),
                approval=country.get("gvt_approval"),
                stability=country.get("gvt_stability"),
                form_rule=rule,
            )
            winner = outcome.winner_party_id
            election_row.update(
                {
                    "government_form_id": form_id,
                    "resolved_at_minute": now,
                    "eligible_party_ids": list(outcome.eligible_party_ids),
                    "coalition_party_ids": list(outcome.coalition_party_ids),
                    "support_snapshot_json": outcome.support_snapshot_json,
                    "results_json": outcome.results_json,
                    "turnout": outcome.turnout,
                    "winner_party_id": winner,
                    "status": "resolved",
                    "reason": "Election results were resolved from the captured eligible-party support snapshot.",
                }
            )
            interval = max(
                0,
                int(rule.get("election_interval_minutes") or DEFAULT_ELECTION_INTERVAL_MINUTES),
            ) or DEFAULT_ELECTION_INTERVAL_MINUTES
            previous_ruling = str(government.get("ruling_party_id") or "")
            government.update(
                {
                    "ruling_party_id": winner,
                    "succession_party_id": winner,
                    "last_election_id": election_id,
                    "next_election_at_minute": now + interval,
                    "updated_at_minute": now,
                }
            )
            changed_governments = True
            for party in country_parties:
                party_id = self._party_id(party.get("party_id"))
                is_ruling = party_id == winner
                if bool(party.get("is_ruling")) != is_ruling:
                    party["is_ruling"] = is_ruling
                    party["updated_at_minute"] = now
                    changed_parties = True
            if not any(self._party_id(row.get("party_id")) == winner for row in country_parties):
                parties.append(
                    {
                        "country_id": country_id,
                        "party_id": winner,
                        "display_name": "Incumbent",
                        "support_share": 1.0,
                        "organization": 0.5,
                        "policy_positions_json": "{}",
                        "eligible": True,
                        "is_ruling": True,
                        "updated_at_minute": now,
                    }
                )
                changed_parties = True

            history.append(
                {
                    "id": runtime.next_id("political-history", int(state.globals.get("tick", 0))),
                    "country_id": country_id,
                    "event_type": "election_resolved",
                    "source_type": "election",
                    "source_id": election_id,
                    "game_minute": now,
                    "previous_value": previous_ruling,
                    "new_value": winner,
                    "reason": election_row["reason"],
                    "result": "resolved",
                }
            )
            changed_history = True
            state.events.append(
                EventPoliticalElectionResolved(
                    country_id=country_id,
                    election_id=election_id,
                    winner_party_id=winner,
                    turnout=outcome.turnout,
                    at_minute=now,
                    coalition_party_ids=outcome.coalition_party_ids,
                )
            )
            coalition_text = (
                f" The governing coalition is {', '.join(outcome.coalition_party_ids)}."
                if len(outcome.coalition_party_ids) > 1
                else ""
            )
            notified, news_added = self._notify(
                state,
                messages,
                news,
                country_id,
                "Election results",
                f"{winner} won the election with turnout of {outcome.turnout:.1%}.{coalition_text} The next election is scheduled at game minute {now + interval}.",
                now,
                election_id + ":resolved",
            )
            messages_changed |= notified
            news_changed |= news_added

        self._store_rows(state, "political_elections", election_rows)
        if changed_governments:
            self._store_rows(state, "country_governments", governments)
        if changed_parties:
            self._store_rows(state, "political_parties", parties)
        if changed_history:
            self._store_rows(state, "political_history", history)
        if messages_changed:
            self._store_rows(state, "messages", messages)
        if news_changed:
            self._store_rows(state, "news_items", news)

    def _refresh_next_election_deadline(self, state: GameState) -> None:
        elections = state.tables["political_elections"]
        scheduled = elections.filter(pl.col("status") == "scheduled")
        self._next_election_deadline = (
            int(scheduled["scheduled_at_minute"].min()) if not scheduled.is_empty() else -1
        )
        self._last_election_revisions = self._election_revision_key(state)

    @staticmethod
    def _store_rows(state: GameState, table_name: str, rows: list[dict[str, Any]]) -> None:
        current = state.tables[table_name]
        updated = pl.DataFrame(rows, schema=current.schema, strict=False) if rows else current.clear()
        if not updated.equals(current):
            state.update_table(table_name, updated)

    @staticmethod
    def _update_if_changed(state: GameState, table_name: str, updated: pl.DataFrame) -> None:
        current = state.tables.get(table_name)
        if current is None or not current.equals(updated):
            state.update_table(table_name, updated)

    @staticmethod
    def _decode_effects(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            parsed = value
        else:
            try:
                parsed = json.loads(str(value or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _finite(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return number if math.isfinite(number) else default

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _law_id(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _form_id(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _party_id(value: Any) -> str:
        return str(value or "").strip().lower()
