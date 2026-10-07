"""Pure threshold and recovery policies for domestic political crises."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


_SUPPORTED_TYPES = frozenset({"protest", "strike", "paralysis", "government_crisis"})
_METRICS = {
    "approval": "gvt_approval",
    "stability": "gvt_stability",
    "corruption": "gvt_corruption",
}


@dataclass(frozen=True, slots=True)
class CrisisRule:
    rule_id: str
    crisis_type: str
    metric: str
    threshold: float
    direction: str
    recovery_threshold: float
    recovery_direction: str
    priority: int
    approval_delta: float
    stability_delta: float
    corruption_delta: float


@dataclass(frozen=True, slots=True)
class CrisisTransition:
    rule: CrisisRule
    status: str
    metric_value: float
    reason: str


@dataclass(frozen=True, slots=True)
class RegimeRelationEffect:
    target_country_id: str
    delta: float
    reciprocal: bool


@dataclass(frozen=True, slots=True)
class RegimeChangePath:
    path_id: str
    crisis_types: frozenset[str]
    minimum_support: float
    minimum_approval: float
    minimum_stability: float
    government_form_id: str
    ruling_party_id: str
    law_values: tuple[tuple[str, str], ...]
    approval_delta: float
    stability_delta: float
    corruption_delta: float
    failure_approval_delta: float
    failure_stability_delta: float
    failure_corruption_delta: float
    relation_effects: tuple[RegimeRelationEffect, ...]


@dataclass(frozen=True, slots=True)
class RegimeChangeAssessment:
    path: RegimeChangePath
    success: bool
    government_form_id: str
    ruling_party_id: str
    next_election_at_minute: int
    reason: str


def normalize_crisis_rules(value: Any) -> tuple[CrisisRule, ...]:
    """Normalize configured thresholds, ignoring malformed or ambiguous records."""

    records = _decode_records(value)
    rules: list[CrisisRule] = []
    seen_ids: set[str] = set()
    for record in records:
        crisis_type = _text(record.get("type", record.get("crisis_type"))).casefold()
        metric = _text(record.get("metric")).casefold()
        metric_column = _METRICS.get(metric)
        threshold = _finite(record.get("threshold"))
        direction = _text(record.get("direction"), "below").casefold()
        if (
            crisis_type not in _SUPPORTED_TYPES
            or metric_column is None
            or threshold is None
            or not 0.0 <= threshold <= 100.0
            or direction not in {"below", "above"}
        ):
            continue

        default_recovery = (
            min(100.0, threshold + 5.0)
            if direction == "below"
            else max(0.0, threshold - 5.0)
        )
        recovery_threshold = _finite(record.get("recovery_threshold", default_recovery))
        recovery_direction = _text(
            record.get("recovery_direction"), "above" if direction == "below" else "below"
        ).casefold()
        if (
            recovery_threshold is None
            or not 0.0 <= recovery_threshold <= 100.0
            or recovery_direction not in {"below", "above"}
            or (
                direction == "below"
                and (recovery_direction != "above" or recovery_threshold <= threshold)
            )
            or (
                direction == "above"
                and (recovery_direction != "below" or recovery_threshold >= threshold)
            )
        ):
            continue

        priority = _integer(record.get("priority", 0))
        if priority is None or not 0 <= priority <= 100_000:
            continue
        rule_id = _text(record.get("id", record.get("rule_id")))
        if not rule_id:
            rule_id = f"{crisis_type}-{metric}-{threshold:g}-{priority}"
        rule_id = rule_id.casefold()
        if rule_id in seen_ids:
            continue
        seen_ids.add(rule_id)

        deltas = {
            name: _finite(record.get(name, 0.0))
            for name in ("approval_delta", "stability_delta", "corruption_delta")
        }
        if any(value is None for value in deltas.values()):
            continue
        rules.append(
            CrisisRule(
                rule_id=rule_id,
                crisis_type=crisis_type,
                metric=metric_column,
                threshold=threshold,
                direction=direction,
                recovery_threshold=recovery_threshold,
                recovery_direction=recovery_direction,
                priority=priority,
                approval_delta=_bounded(deltas["approval_delta"], -100.0, 100.0),
                stability_delta=_bounded(deltas["stability_delta"], -100.0, 100.0),
                corruption_delta=_bounded(deltas["corruption_delta"], -100.0, 100.0),
            )
        )
    return tuple(sorted(rules, key=lambda rule: (rule.priority, rule.crisis_type, rule.rule_id)))


def evaluate_crisis_transitions(
    rules: tuple[CrisisRule, ...],
    country: dict[str, Any],
    existing_crises: list[dict[str, Any]],
) -> tuple[CrisisTransition, ...]:
    """Return deterministic opens/recoveries without changing the supplied records."""

    active_by_rule = {
        _text(row.get("trigger")).casefold(): row
        for row in existing_crises
        if _text(row.get("status")).casefold() in {"pending", "active", "open", "escalated"}
    }
    transitions: list[CrisisTransition] = []
    for rule in rules:
        value = _finite(country.get(rule.metric))
        if value is None:
            continue
        active = active_by_rule.get(rule.rule_id)
        if active is not None:
            if _crossed(value, rule.recovery_threshold, rule.recovery_direction):
                transitions.append(
                    CrisisTransition(
                        rule=rule,
                        status="resolved",
                        metric_value=value,
                        reason=(
                            f"{rule.crisis_type.title()} recovered: {rule.metric} is "
                            f"{value:.1f}, past the {rule.recovery_threshold:.1f} recovery threshold."
                        ),
                    )
                )
            continue
        if _crossed(value, rule.threshold, rule.direction):
            transitions.append(
                CrisisTransition(
                    rule=rule,
                    status="active",
                    metric_value=value,
                    reason=(
                        f"{rule.crisis_type.title()} triggered: {rule.metric} is {value:.1f}, "
                        f"{rule.direction} the {rule.threshold:.1f} threshold."
                    ),
                )
            )
    return tuple(transitions)


def normalize_regime_change_paths(value: Any) -> tuple[RegimeChangePath, ...]:
    """Normalize declared regime paths into bounded, deterministic records."""

    records = _decode_path_records(value)
    paths: list[RegimeChangePath] = []
    seen_ids: set[str] = set()
    for record in records:
        path_id = _text(record.get("id", record.get("path_id"))).casefold()
        if not path_id or path_id in seen_ids:
            continue
        outcome = record.get("outcome")
        outcome = outcome if isinstance(outcome, dict) else {}
        crisis_types_value = record.get("crisis_types", record.get("crisis_type", ()))
        if isinstance(crisis_types_value, str):
            crisis_types = {crisis_types_value.strip().casefold()} if crisis_types_value.strip() else set()
        elif isinstance(crisis_types_value, (list, tuple, set)):
            crisis_types = {
                str(item).strip().casefold()
                for item in crisis_types_value
                if str(item).strip()
            }
        else:
            crisis_types = set()
        support = _finite(record.get("minimum_support", 0.0))
        approval = _finite(record.get("minimum_approval", 0.0))
        stability = _finite(record.get("minimum_stability", 0.0))
        if (
            not crisis_types
            or any(len(value) > 80 for value in crisis_types)
            or support is None
            or not 0.0 <= support <= 1.0
            or approval is None
            or not 0.0 <= approval <= 100.0
            or stability is None
            or not 0.0 <= stability <= 100.0
        ):
            continue

        raw_law_values = record.get("law_values", outcome.get("law_values", {}))
        if not isinstance(raw_law_values, dict):
            continue
        law_values: list[tuple[str, str]] = []
        for law_id, target_value in sorted(raw_law_values.items(), key=lambda item: str(item[0]).casefold()):
            law_key = str(law_id or "").strip().casefold()
            target = str(target_value or "").strip()
            if not law_key or not target or len(law_key) > 120 or len(target) > 240:
                law_values = []
                break
            law_values.append((law_key, target))
        if raw_law_values and not law_values:
            continue

        raw_relations = record.get("relation_effects", outcome.get("relation_effects", []))
        if not isinstance(raw_relations, list):
            continue
        relation_effects: list[RegimeRelationEffect] = []
        relation_keys: set[tuple[str, bool]] = set()
        relations_valid = True
        for declared in raw_relations:
            if not isinstance(declared, dict):
                relations_valid = False
                break
            target = _text(declared.get("target_country_id", declared.get("target"))).upper()
            delta = _finite(declared.get("delta"))
            reciprocal = bool(declared.get("reciprocal", False))
            key = (target, reciprocal)
            if not target or len(target) > 16 or delta is None or key in relation_keys:
                relations_valid = False
                break
            relation_keys.add(key)
            relation_effects.append(
                RegimeRelationEffect(
                    target_country_id=target,
                    delta=_bounded(delta, -100.0, 100.0),
                    reciprocal=reciprocal,
                )
            )
        if not relations_valid:
            continue

        failure = record.get("failure_effects")
        failure = failure if isinstance(failure, dict) else {}
        values = {
            name: _finite(outcome.get(name, record.get(name, 0.0)))
            for name in ("approval_delta", "stability_delta", "corruption_delta")
        }
        for name in ("approval_delta", "stability_delta", "corruption_delta"):
            values[f"failure_{name}"] = _finite(
                failure.get(name, failure.get(f"failure_{name}", 0.0))
            )
        if any(number is None for number in values.values()):
            continue

        paths.append(
            RegimeChangePath(
                path_id=path_id,
                crisis_types=frozenset(crisis_types),
                minimum_support=support,
                minimum_approval=approval,
                minimum_stability=stability,
                government_form_id=_text(
                    outcome.get("government_form_id", record.get("government_form_id"))
                ).casefold(),
                ruling_party_id=_text(
                    outcome.get("ruling_party_id", record.get("ruling_party_id"))
                ).casefold(),
                law_values=tuple(law_values),
                approval_delta=_bounded(values["approval_delta"], -100.0, 100.0),
                stability_delta=_bounded(values["stability_delta"], -100.0, 100.0),
                corruption_delta=_bounded(values["corruption_delta"], -100.0, 100.0),
                failure_approval_delta=_bounded(values["failure_approval_delta"], -100.0, 100.0),
                failure_stability_delta=_bounded(values["failure_stability_delta"], -100.0, 100.0),
                failure_corruption_delta=_bounded(values["failure_corruption_delta"], -100.0, 100.0),
                relation_effects=tuple(relation_effects),
            )
        )
        seen_ids.add(path_id)
    return tuple(sorted(paths, key=lambda path: path.path_id))


def assess_regime_change(
    *,
    paths: tuple[RegimeChangePath, ...],
    path_id: Any,
    crisis: dict[str, Any],
    current_form_id: str,
    government: dict[str, Any],
    country: dict[str, Any],
    form_rules: list[dict[str, Any]],
    parties: list[dict[str, Any]],
    laws: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None,
    now_minute: int,
) -> tuple[RegimeChangeAssessment | None, str]:
    """Check every declared target before deciding if the crisis attempt succeeds."""

    selected_id = _text(path_id).casefold()
    path = next((record for record in paths if record.path_id == selected_id), None)
    if path is None:
        return None, "The selected regime-change path is not configured for this government form."
    if _text(crisis.get("status")).casefold() not in {"pending", "active", "open", "escalated"}:
        return None, "The political crisis is no longer active."
    if _text(crisis.get("crisis_type")).casefold() not in path.crisis_types:
        return None, "This regime-change path does not apply to the active crisis type."
    deadline = _integer(crisis.get("deadline_at_minute", 0))
    if deadline is None or (deadline > 0 and deadline <= now_minute):
        return None, "The political crisis decision deadline has passed."

    target_form = path.government_form_id or _text(crisis.get("proposed_form_id")).casefold() or current_form_id
    form_index = {_form_id(row.get("government_form_id")): row for row in form_rules}
    target_form_rule = form_index.get(_form_id(target_form))
    if target_form_rule is None:
        return None, "The configured target government form is unavailable."

    country_id = _text(country.get("id")).upper()
    party_id = path.ruling_party_id or _text(crisis.get("proposed_ruling_party_id")).casefold()
    party_rows = [
        row for row in parties
        if _text(row.get("country_id")).upper() == country_id
    ]
    if party_id:
        party = next((row for row in party_rows if _party_id(row.get("party_id")) == party_id), None)
        if party is None:
            return None, "The configured ruling party does not exist in this country."
        if not bool(party.get("eligible", False)):
            return None, "The configured ruling party is not eligible to govern."
    else:
        party_id = _party_id(government.get("ruling_party_id"))
        if not any(_party_id(row.get("party_id")) == party_id for row in party_rows):
            return None, "The crisis has no valid successor or ruling party."

    law_index: dict[str, dict[str, Any]] = {}
    for law in laws:
        if _text(law.get("country_id")).upper() != country_id:
            continue
        law_key = _text(law.get("law_id")).casefold()
        if law_key in law_index:
            return None, "The country has ambiguous duplicate law records."
        law_index[law_key] = law
    canonical_laws: list[tuple[dict[str, Any], str]] = []
    for law_id, target_value in path.law_values:
        law = law_index.get(law_id)
        if law is None:
            return None, f"The configured law '{law_id}' is unavailable."
        allowed = _decode_string_list(law.get("allowed_values_json"))
        canonical = next((value for value in allowed if _text(value).casefold() == target_value.casefold()), None)
        if canonical is None:
            return None, f"The configured value is not allowed for law '{law_id}'."
        canonical_laws.append((law, canonical))

    country_ids = {_text(row.get("id")).upper() for row in countries}
    relation_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in relations or []:
        key = (_text(row.get("source")).upper(), _text(row.get("target")).upper())
        relation_index.setdefault(key, []).append(row)
    for effect in path.relation_effects:
        target = effect.target_country_id
        if target == country_id or target not in country_ids:
            return None, f"The relation-effect target '{target}' is unavailable."
        directions = [(country_id, target)]
        if effect.reciprocal:
            directions.append((target, country_id))
        for direction in directions:
            matches = relation_index.get(direction, [])
            if len(matches) != 1:
                return None, "A configured relation effect requires one unambiguous existing relation in each direction."
            if _finite(matches[0].get("value")) is None:
                return None, "A configured relation effect targets a non-numeric relation value."

    approval = _percentage(country.get("gvt_approval"), 50.0)
    stability = _percentage(country.get("gvt_stability"), 50.0)
    support = _finite(crisis.get("support"))
    if support is None:
        support = 0.0
    support = _bounded(support, 0.0, 1.0)
    success = (
        support >= path.minimum_support
        and approval >= path.minimum_approval
        and stability >= path.minimum_stability
    )
    if success:
        try:
            election_eligible = bool(target_form_rule.get("election_eligible", False))
            interval = _integer(target_form_rule.get("election_interval_minutes", 0)) or 0
            if interval < 0 or interval > 2_147_483_647:
                return None, "The target government's election interval is invalid."
            next_election = now_minute + (interval or 4 * 365 * 24 * 60) if election_eligible else 0
            if next_election > 9_223_372_036_854_775_807:
                return None, "The target government's election date exceeds the supported game-time range."
        except (OverflowError, TypeError, ValueError):
            return None, "The target government's election schedule is invalid."
    else:
        next_election = int(government.get("next_election_at_minute") or 0)

    reasons = []
    if support < path.minimum_support:
        reasons.append(f"support {support:.3f} is below {path.minimum_support:.3f}")
    if approval < path.minimum_approval:
        reasons.append(f"approval {approval:.1f} is below {path.minimum_approval:.1f}")
    if stability < path.minimum_stability:
        reasons.append(f"stability {stability:.1f} is below {path.minimum_stability:.1f}")
    result_reason = (
        f"Regime-change path '{path.path_id}' succeeded."
        if success
        else f"Regime-change attempt failed because " + ", ".join(reasons) + "."
    )
    return (
        RegimeChangeAssessment(
            path=path,
            success=success,
            government_form_id=_form_id(target_form),
            ruling_party_id=party_id,
            next_election_at_minute=next_election,
            reason=result_reason,
        ),
        "",
    )


def _decode_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("rules", parsed.get("thresholds", []))
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _decode_path_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if isinstance(parsed, dict):
        parsed = parsed.get("paths", [])
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _decode_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return [str(item) for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _percentage(value: Any, default: float) -> float:
    number = _finite(value)
    if number is None:
        return default
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return _bounded(number, 0.0, 100.0)


def _form_id(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _party_id(value: Any) -> str:
    return str(value or "").strip().casefold()


def _crossed(value: float, threshold: float, direction: str) -> bool:
    return value < threshold if direction == "below" else value > threshold


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return number


def _bounded(value: float | None, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, float(value or 0.0)))


def _text(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()
