from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.politics.election_policy import validate_election_override
from modules.base.systems.politics.law_transition_policy import validate_law_change
from modules.base.systems.politics.political_crisis_policy import (
    assess_regime_change,
    normalize_regime_change_paths,
)
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import (
    ActionChangePoliticalLaw,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
    GameAction,
)


_POLITICAL_TABLES = frozenset(
    {
        "countries",
        "country_governments",
        "government_form_rules",
        "political_parties",
        "country_laws",
        "law_transitions",
        "political_elections",
        "political_crises",
        "political_history",
    }
)
_ACTIVE_CRISIS = frozenset({"pending", "active", "open", "escalated"})
_AI_ACTOR = "AI_SYSTEM"
_EXTRA_SCHEMA = {
    "decision_reason": pl.Utf8,
    "country_tag": pl.Utf8,
    "law_id": pl.Utf8,
    "target_value": pl.Utf8,
    "override_type": pl.Utf8,
    "duration_days": pl.Int64,
    "crisis_id": pl.Utf8,
    "path_id": pl.Utf8,
}


class PoliticalLawPolicy:
    """Suggests legal, bounded law transitions for non-player governments."""

    id = "political_law"
    required_tables = _POLITICAL_TABLES
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        if context.day_ordinal % self.cadence_days:
            return empty_candidates(_EXTRA_SCHEMA)
        bundle = _political_rows(context)
        if bundle is None:
            return empty_candidates(_EXTRA_SCHEMA)
        countries, governments, forms, parties, laws, transitions, _, _, _ = bundle
        government_index = {_tag(row.get("country_id")): row for row in governments}
        form_index = {_form(row.get("government_form_id")): row for row in forms}
        active_countries = _active_crisis_countries(bundle[7])
        pending_laws = {
            (_tag(row.get("country_id")), _law(row.get("law_id")))
            for row in transitions
            if _text(row.get("status")).casefold() == "scheduled"
        }
        parties_by_country: dict[str, list[dict[str, Any]]] = {}
        for party in parties:
            parties_by_country.setdefault(_tag(party.get("country_id")), []).append(party)
        laws_by_country: dict[str, list[dict[str, Any]]] = {}
        for law in laws:
            laws_by_country.setdefault(_tag(law.get("country_id")), []).append(law)

        candidates = []
        for country in sorted(countries, key=lambda row: _tag(row.get("id"))):
            country_id = _tag(country.get("id"))
            if not _is_ai_country(context, country_id):
                continue
            government = government_index.get(country_id)
            if government is None or country_id in active_countries:
                continue
            form_rule = form_index.get(_form(government.get("government_form_id")))
            if form_rule is None:
                continue
            approval = _percent(country.get("gvt_approval"), 50.0)
            stability = _percent(country.get("gvt_stability"), 50.0)
            best: tuple[float, str, str, str] | None = None
            for law in sorted(laws_by_country.get(country_id, []), key=lambda row: _law(row.get("law_id"))):
                law_id = _law(law.get("law_id"))
                if (country_id, law_id) in pending_laws:
                    continue
                allowed = _string_list(law.get("allowed_values_json"))
                current_value = _text(law.get("value"))
                for target in allowed:
                    if target.casefold() == current_value.casefold():
                        continue
                    decision, _ = validate_law_change(
                        law=law,
                        government=government,
                        form_rule=form_rule,
                        target_value=target,
                        now_minute=context.total_minutes,
                        treasury=country.get("money_reserves"),
                        has_pending_transition=False,
                        crisis_active=False,
                    )
                    if decision is None:
                        continue
                    score, reason = _law_value_utility(
                        law,
                        current_value,
                        decision.target_value,
                        approval,
                        stability,
                    )
                    if score <= 0.05:
                        continue
                    choice = (score, law_id, decision.target_value, reason)
                    if best is None or choice[:3] > best[:3]:
                        best = choice
            if best is None:
                continue
            score, law_id, target_value, rationale = best
            candidates.append(
                _candidate(
                    self.id,
                    country_id,
                    score,
                    "law_change",
                    f"political-action:{country_id}",
                    "law_change",
                    f"improve_{rationale}",
                    decision_reason=(
                        f"Selected {law_id}={target_value} because its declared effects "
                        f"address this country's political conditions."
                    ),
                    country_tag=country_id,
                    law_id=law_id,
                    target_value=target_value,
                )
            )
        return _candidate_frame(candidates)

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "law_change":
            return None
        country = _tag(row.get("country_tag"))
        law_id = _law(row.get("law_id"))
        target = _text(row.get("target_value"))
        if not country or not law_id or not target:
            return None
        return ActionChangePoliticalLaw(
            _AI_ACTOR,
            country,
            law_id,
            target,
            decision_reason=_text(row.get("decision_reason")),
        )


class PoliticalElectionPolicy:
    """Uses government-configured election overrides when their political rationale is clear."""

    id = "political_election"
    required_tables = _POLITICAL_TABLES
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        if context.day_ordinal % self.cadence_days:
            return empty_candidates(_EXTRA_SCHEMA)
        bundle = _political_rows(context)
        if bundle is None:
            return empty_candidates(_EXTRA_SCHEMA)
        countries, governments, forms, parties, _, _, elections, crises, history = bundle
        government_index = {_tag(row.get("country_id")): row for row in governments}
        form_index = {_form(row.get("government_form_id")): row for row in forms}
        countries_by_id = {_tag(row.get("id")): row for row in countries}
        parties_by_country: dict[str, list[dict[str, Any]]] = {}
        for party in parties:
            parties_by_country.setdefault(_tag(party.get("country_id")), []).append(party)
        scheduled_by_country: dict[str, list[dict[str, Any]]] = {}
        for election in elections:
            if _text(election.get("status")).casefold() == "scheduled":
                scheduled_by_country.setdefault(_tag(election.get("country_id")), []).append(election)
        history_by_country: dict[str, list[dict[str, Any]]] = {}
        for record in history:
            history_by_country.setdefault(_tag(record.get("country_id")), []).append(record)
        active_countries = _active_crisis_countries(crises)
        terms = context.globals.get("political_ai_terms", {})
        terms = terms if isinstance(terms, dict) else {}
        low_approval = _bounded(terms.get("postpone_below_approval"), 0.0, 100.0, 35.0)
        high_approval = _bounded(terms.get("accelerate_above_approval"), 0.0, 100.0, 75.0)
        high_stability = _bounded(terms.get("accelerate_above_stability"), 0.0, 100.0, 65.0)

        candidates = []
        for country_id, country in sorted(countries_by_id.items()):
            if not _is_ai_country(context, country_id) or country_id in active_countries:
                continue
            government = government_index.get(country_id)
            if government is None or not bool(government.get("election_eligible")):
                continue
            form_rule = form_index.get(_form(government.get("government_form_id")))
            if form_rule is None:
                continue
            scheduled = sorted(
                scheduled_by_country.get(country_id, []),
                key=lambda row: (int(row.get("scheduled_at_minute") or 0), _text(row.get("id"))),
            )
            current_election = scheduled[0] if scheduled else None
            current_date = (
                current_election.get("scheduled_at_minute")
                if current_election is not None
                else government.get("next_election_at_minute")
            )
            approval = _percent(country.get("gvt_approval"), 50.0)
            stability = _percent(country.get("gvt_stability"), 50.0)
            ruling = _party(_text(government.get("ruling_party_id")))
            country_parties = parties_by_country.get(country_id, [])
            ruling_party = next(
                (party for party in country_parties if _party(party.get("party_id")) == ruling),
                None,
            )
            last_override = max(
                (
                    int(row.get("game_minute") or 0)
                    for row in history_by_country.get(country_id, [])
                    if _text(row.get("event_type")) == "election_override_applied"
                ),
                default=None,
            )
            options = _json_records(form_rule.get("election_overrides_json"))
            for rule in options:
                override_type = _text(rule.get("type")).casefold()
                if override_type == "postpone" and approval > low_approval:
                    continue
                if override_type == "accelerate" and not (
                    approval >= high_approval and stability >= high_stability
                ):
                    continue
                if override_type == "succession" and not (
                    ruling_party is None or not bool(ruling_party.get("eligible", False))
                ):
                    continue
                if override_type not in {"postpone", "accelerate", "succession"}:
                    continue
                duration = _bounded_int(rule.get("minimum_duration_days"), 1, 36_500, 1)
                decision, _ = validate_election_override(
                    override_type=override_type,
                    duration_days=duration,
                    now_minute=context.total_minutes,
                    current_election_minute=current_date,
                    form_rule=form_rule,
                    government=government,
                    treasury=country.get("money_reserves"),
                    last_override_at_minute=last_override,
                    party_ids=(row.get("party_id") for row in country_parties),
                    crisis_active=False,
                )
                if decision is None:
                    continue
                if override_type == "postpone":
                    utility = 0.65 + max(0.0, low_approval - approval) / 100.0
                    rationale = f"approval {approval:.1f} is below {low_approval:.1f}"
                elif override_type == "accelerate":
                    utility = 0.65 + (approval + stability) / 200.0
                    rationale = "approval and stability satisfy the configured early-election mandate"
                else:
                    utility = 1.5
                    rationale = "the incumbent is ineligible and a configured successor is available"
                candidates.append(
                    _candidate(
                        self.id,
                        country_id,
                        utility,
                        "election_override",
                        f"political-action:{country_id}",
                        "election_override",
                        f"{override_type}_election_{rationale.split()[0]}",
                        decision_reason=f"Selected {override_type} because {rationale}.",
                        country_tag=country_id,
                        override_type=override_type,
                        duration_days=duration,
                    )
                )
        return _candidate_frame(candidates)

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "election_override":
            return None
        country = _tag(row.get("country_tag"))
        override_type = _text(row.get("override_type"))
        duration = _bounded_int(row.get("duration_days"), 1, 36_500, 1)
        if not country or not override_type:
            return None
        return ActionSetElectionOverride(
            _AI_ACTOR,
            country,
            override_type,
            duration,
            decision_reason=_text(row.get("decision_reason")),
        )


class PoliticalCrisisPolicy:
    """Resolves active crises only when one configured transition currently meets every threshold."""

    id = "political_crisis"
    required_tables = _POLITICAL_TABLES
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        bundle = _political_rows(context)
        if bundle is None:
            return empty_candidates(_EXTRA_SCHEMA)
        countries, governments, forms, parties, laws, _, _, crises, _ = bundle
        country_index = {_tag(row.get("id")): row for row in countries}
        government_index = {_tag(row.get("country_id")): row for row in governments}
        form_index = {_form(row.get("government_form_id")): row for row in forms}
        parties_by_country: dict[str, list[dict[str, Any]]] = {}
        laws_by_country: dict[str, list[dict[str, Any]]] = {}
        crises_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in parties:
            parties_by_country.setdefault(_tag(row.get("country_id")), []).append(row)
        for row in laws:
            laws_by_country.setdefault(_tag(row.get("country_id")), []).append(row)
        for row in crises:
            if _text(row.get("status")).casefold() in _ACTIVE_CRISIS:
                crises_by_country.setdefault(_tag(row.get("country_id")), []).append(row)
        relation_frame = context.tables.get("countries_relations")
        relations = relation_frame.to_dicts() if relation_frame is not None else None

        candidates = []
        for country_id, country in sorted(country_index.items()):
            if not _is_ai_country(context, country_id):
                continue
            government = government_index.get(country_id)
            if government is None:
                continue
            form_rule = form_index.get(_form(government.get("government_form_id")))
            if form_rule is None:
                continue
            paths = normalize_regime_change_paths(
                form_rule.get("regime_change_paths_json")
            )
            if not paths:
                continue
            for crisis in sorted(
                crises_by_country.get(country_id, []),
                key=lambda row: (
                    int(row.get("deadline_at_minute") or 0),
                    _text(row.get("id")),
                ),
            ):
                matches = []
                for path in paths:
                    if _text(crisis.get("crisis_type")).casefold() not in path.crisis_types:
                        continue
                    assessment, _ = assess_regime_change(
                        paths=(path,),
                        path_id=path.path_id,
                        crisis=crisis,
                        current_form_id=_form(government.get("government_form_id")),
                        government=government,
                        country=country,
                        form_rules=forms,
                        parties=parties_by_country.get(country_id, []),
                        laws=laws_by_country.get(country_id, []),
                        countries=countries,
                        relations=relations,
                        now_minute=context.total_minutes,
                    )
                    if assessment is not None and assessment.success:
                        matches.append((path.path_id, assessment))
                if not matches:
                    continue
                path_id, assessment = min(matches, key=lambda item: item[0])
                candidates.append(
                    _candidate(
                        self.id,
                        country_id,
                        1.5 + _bounded(_finite(crisis.get("support"), 0.0), 0.0, 1.0, 0.0),
                        "regime_change",
                        f"political-action:{country_id}",
                        "resolve_crisis",
                        f"resolve_{_text(crisis.get('crisis_type')).casefold()}",
                        decision_reason=(
                            f"Selected path {path_id} because its configured support, approval, "
                            "stability, and target-state checks currently pass."
                        ),
                        country_tag=country_id,
                        crisis_id=_text(crisis.get("id")),
                        path_id=path_id,
                    )
                )
        return _candidate_frame(candidates)

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "resolve_crisis":
            return None
        country = _tag(row.get("country_tag"))
        crisis_id = _text(row.get("crisis_id"))
        path_id = _text(row.get("path_id"))
        if not country or not crisis_id or not path_id:
            return None
        return ActionResolvePoliticalCrisis(
            _AI_ACTOR,
            country,
            crisis_id,
            path_id,
            decision_reason=_text(row.get("decision_reason")),
        )


def _political_rows(context: AITableContext) -> tuple[list[dict[str, Any]], ...] | None:
    if not _POLITICAL_TABLES.issubset(context.tables):
        return None
    return tuple(context.tables[name].to_dicts() for name in (
        "countries",
        "country_governments",
        "government_form_rules",
        "political_parties",
        "country_laws",
        "law_transitions",
        "political_elections",
        "political_crises",
        "political_history",
    ))


def _is_ai_country(context: AITableContext, country_id: str) -> bool:
    if not country_id:
        return False
    delegated_authority = context.delegated_domains.get(country_id, frozenset())
    political_authority = "politics" in delegated_authority
    if country_id == _tag(context.player_tag) and not political_authority:
        return False
    mapping = context.globals.get("player_country_map", {})
    if (
        isinstance(mapping, dict)
        and country_id in {_tag(value) for value in mapping.values()}
        and not political_authority
    ):
        return False
    controlled = context.globals.get("ai_controlled_countries")
    if isinstance(controlled, (list, tuple, set, frozenset)):
        return country_id in {_tag(value) for value in controlled}
    return True


def _active_crisis_countries(crises: list[dict[str, Any]]) -> set[str]:
    return {
        _tag(row.get("country_id"))
        for row in crises
        if _text(row.get("status")).casefold() in _ACTIVE_CRISIS
    }


def _law_value_utility(
    law: dict[str, Any], current_value: str, target_value: str, approval: float, stability: float
) -> tuple[float, str]:
    by_value = _json_object(law.get("effects_by_value_json"))
    current = _effect_totals(by_value.get(current_value, []))
    target = _effect_totals(by_value.get(target_value, []))
    score = 0.0
    causes: list[str] = []
    for (domain, effect), target_value in target.items():
        difference = target_value - current.get((domain, effect), 0.0)
        if difference <= 0.0:
            continue
        if domain == "rights":
            score += difference * max(0.0, (80.0 - approval) / 50.0)
            causes.append("public_rights_for_approval")
        elif (domain, effect) == ("stability", "stability_modifier"):
            score += difference * max(0.0, (75.0 - stability) / 50.0)
            causes.append("stability_support")
        elif domain == "economy":
            score += difference * 0.35
            causes.append("economic_resilience")
    reason = min(causes) if causes else ""
    return score, reason


def _effect_totals(value: Any) -> dict[tuple[str, str], float]:
    if not isinstance(value, list):
        return {}
    totals: dict[tuple[str, str], float] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        key = (_text(item.get("domain")).casefold(), _text(item.get("effect")).casefold())
        magnitude = _finite(item.get("value"), 0.0)
        if key[0] and key[1]:
            totals[key] = totals.get(key, 0.0) + magnitude
    return totals


def _candidate(
    policy_id: str,
    country_id: str,
    utility: float,
    domain: str,
    conflict_key: str,
    action_kind: str,
    reason_code: str,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "country_id": country_id,
        "domain": "politics",
        "utility": float(utility),
        "conflict_key": conflict_key,
        "action_kind": action_kind,
        "reason_code": reason_code,
        "quota": 1,
        **payload,
    }


def _candidate_frame(candidates: list[dict[str, Any]]) -> pl.LazyFrame:
    if not candidates:
        return empty_candidates(_EXTRA_SCHEMA)
    return pl.DataFrame(candidates, infer_schema_length=None).lazy()


def _json_records(value: Any) -> list[dict[str, Any]]:
    try:
        parsed = value if isinstance(value, (dict, list)) else json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("rules", [])
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = value if isinstance(value, dict) else json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: Any) -> list[str]:
    try:
        parsed = value if isinstance(value, list) else json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _percent(value: Any, default: float) -> float:
    result = _finite(value, default)
    if 0.0 <= result <= 1.0:
        result *= 100.0
    return min(100.0, max(0.0, result))


def _bounded(value: Any, minimum: float, maximum: float, default: float) -> float:
    return min(maximum, max(minimum, _finite(value, default)))


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(maximum, max(minimum, number))


def _finite(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tag(value: Any) -> str:
    return _text(value).upper()


def _form(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _law(value: Any) -> str:
    return _text(value).casefold()


def _party(value: Any) -> str:
    return _text(value).casefold()
