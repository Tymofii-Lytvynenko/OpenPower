"""Pure validation and normalization rules for effective-dated domestic laws."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import polars as pl


DEFAULT_LAW_TRANSITION_MINUTES = 30 * 24 * 60

_LAW_CATALOG: dict[str, dict[str, Any]] = {
    "religion_policy": {
        "values": ["Plural framework", "Monitored practice", "State religion", "Secular administration"],
        "effects": {
            "Plural framework": [{"domain": "rights", "effect": "religious_freedom", "value": 0.1}],
            "Monitored practice": [{"domain": "rights", "effect": "religious_freedom", "value": -0.05}],
            "State religion": [{"domain": "rights", "effect": "religious_freedom", "value": -0.2}],
            "Secular administration": [{"domain": "rights", "effect": "religious_freedom", "value": 0.15}],
        },
    },
    "language_policy": {
        "values": ["Minority protection", "State-first administration", "Multilingual administration", "Single official language"],
        "effects": {
            "Minority protection": [{"domain": "rights", "effect": "language_access", "value": 0.1}],
            "State-first administration": [{"domain": "rights", "effect": "language_access", "value": -0.05}],
            "Multilingual administration": [{"domain": "rights", "effect": "language_access", "value": 0.15}],
            "Single official language": [{"domain": "rights", "effect": "language_access", "value": -0.1}],
        },
    },
    "party_system": {
        "values": ["Competitive", "Managed competition", "Single-party", "Open registration", "Restricted funding"],
        "effects": {
            "Competitive": [{"domain": "rights", "effect": "political_competition", "value": 0.1}],
            "Managed competition": [{"domain": "rights", "effect": "political_competition", "value": -0.05}],
            "Single-party": [{"domain": "rights", "effect": "political_competition", "value": -0.2}],
            "Open registration": [{"domain": "rights", "effect": "political_competition", "value": 0.15}],
            "Restricted funding": [{"domain": "rights", "effect": "political_competition", "value": -0.1}],
        },
    },
    "civil_rights": {
        "values": ["Judicial review", "Administrative controls", "Protected", "Under pressure", "Restricted"],
        "effects": {
            "Judicial review": [{"domain": "rights", "effect": "public_rights", "value": 0.1}],
            "Administrative controls": [{"domain": "rights", "effect": "public_rights", "value": -0.1}],
            "Protected": [{"domain": "rights", "effect": "public_rights", "value": 0.2}],
            "Under pressure": [{"domain": "rights", "effect": "public_rights", "value": -0.1}],
            "Restricted": [{"domain": "rights", "effect": "public_rights", "value": -0.2}],
        },
    },
    "migration_policy": {
        "values": ["Quota system", "Tight restrictions", "Managed entry", "Open entry"],
        "effects": {
            "Quota system": [{"domain": "migration", "effect": "entry_rate", "value": 0.0}],
            "Tight restrictions": [{"domain": "migration", "effect": "entry_rate", "value": -0.2}],
            "Managed entry": [{"domain": "migration", "effect": "entry_rate", "value": 0.05}],
            "Open entry": [{"domain": "migration", "effect": "entry_rate", "value": 0.2}],
        },
    },
    "border_policy": {
        "values": ["Trade corridors open", "Priority checkpoints", "Open borders", "Closed borders"],
        "effects": {
            "Trade corridors open": [{"domain": "migration", "effect": "enforcement_strength", "value": -0.05}],
            "Priority checkpoints": [{"domain": "migration", "effect": "enforcement_strength", "value": 0.1}],
            "Open borders": [{"domain": "migration", "effect": "enforcement_strength", "value": -0.2}],
            "Closed borders": [{"domain": "migration", "effect": "enforcement_strength", "value": 0.2}],
        },
    },
}


@dataclass(frozen=True)
class LawChangeDecision:
    target_value: str
    transition_minutes: int
    change_cost: float
    cooldown_minutes: int
    legal_authority: str
    carry_over_rule: str
    effects: tuple[dict[str, Any], ...]


def normalize_law_rows(frame: pl.DataFrame) -> pl.DataFrame:
    """Enrich legacy law seeds once while preserving scenario-provided rules."""

    if frame.is_empty():
        return frame
    rows = []
    for original in frame.iter_rows(named=True):
        row = dict(original)
        law_id = _text(row.get("law_id")).lower()
        current_value = _text(row.get("value"))
        catalog = _LAW_CATALOG.get(law_id, {})
        raw_allowed = row.get("allowed_values_json")
        allowed = _decode_string_list(raw_allowed)
        if raw_allowed is None or not str(raw_allowed).strip():
            allowed = [str(value) for value in catalog.get("values", ())]
        if current_value and not any(_key(value) == _key(current_value) for value in allowed):
            allowed.append(current_value)

        raw_effects = row.get("effects_by_value_json")
        configured_effects = _decode_object(raw_effects)
        if raw_effects is None or not str(raw_effects).strip():
            configured_effects = dict(catalog.get("effects", {}))
        row.update(
            {
                "source_seed_id": _text(row.get("source_seed_id")) or f"base:{law_id}",
                "allowed_values_json": _json(allowed),
                "transition_minutes": _non_negative_int(
                    row.get("transition_minutes"), DEFAULT_LAW_TRANSITION_MINUTES
                ),
                "legal_authority": _text(row.get("legal_authority")) or "government",
                "change_cost": _finite_or_default(row.get("change_cost"), 0.0),
                "cooldown_minutes": _non_negative_int(row.get("cooldown_minutes")),
                "cooldown_until_minute": _non_negative_int(row.get("cooldown_until_minute")),
                "last_changed_at_minute": _non_negative_int(row.get("last_changed_at_minute")),
                "carry_over_rule": _text(row.get("carry_over_rule")) or "cancel_on_regime_change",
                "effects_by_value_json": _json(configured_effects),
            }
        )
        rows.append(row)
    return pl.DataFrame(rows, schema=frame.schema, strict=False)


def validate_law_change(
    *,
    law: dict[str, Any],
    government: dict[str, Any],
    form_rule: dict[str, Any],
    target_value: Any,
    now_minute: int,
    treasury: Any,
    has_pending_transition: bool,
    crisis_active: bool,
) -> tuple[LawChangeDecision | None, str]:
    """Return a canonical transition decision or a user-readable rejection reason."""

    law_id = _text(law.get("law_id")).lower()
    if not law_id:
        return None, "The requested law does not exist."
    if has_pending_transition:
        return None, "A transition for this law is already pending."
    if crisis_active or _text(government.get("crisis_status"), "none").lower() not in {"", "none", "resolved"}:
        return None, "Law changes are unavailable during an active government crisis."

    authority = _text(law.get("legal_authority"), "government").lower()
    if authority != "government":
        return None, f"The configured legal authority '{authority}' is not available for this action."
    permissions = _decode_string_list(form_rule.get("law_permissions_json"))
    if not any(_key(permission) in {"*", law_id} for permission in permissions):
        return None, "The current government form is not permitted to change this law."

    target_text = _text(target_value)
    allowed = _decode_string_list(law.get("allowed_values_json"))
    canonical_target = next((value for value in allowed if _key(value) == _key(target_text)), None)
    if canonical_target is None:
        return None, "The requested value is not allowed for this law."
    if _key(canonical_target) == _key(law.get("value")):
        return None, "The law already has the requested value."

    cooldown_until = _non_negative_int(law.get("cooldown_until_minute"))
    if cooldown_until > now_minute:
        return None, f"The law change cooldown ends at game minute {cooldown_until}."

    cost = _finite_number(law.get("change_cost"))
    funds = _finite_number(treasury)
    if cost is None or cost < 0.0:
        return None, "The configured law-change cost is invalid."
    if funds is None or funds < cost:
        return None, "The country lacks funds for this law change cost."

    effects_by_value = _decode_object(law.get("effects_by_value_json"))
    configured_effects = effects_by_value.get(canonical_target, [])
    effects = tuple(_normalize_effects(configured_effects))
    transition_minutes = _non_negative_int(
        law.get("transition_minutes"), DEFAULT_LAW_TRANSITION_MINUTES
    )
    cooldown_minutes = _non_negative_int(law.get("cooldown_minutes"))
    carry_over_rule = _text(law.get("carry_over_rule"), "cancel_on_regime_change")
    if carry_over_rule not in {"carry_over", "cancel_on_regime_change"}:
        carry_over_rule = "cancel_on_regime_change"
    return (
        LawChangeDecision(
            target_value=canonical_target,
            transition_minutes=transition_minutes,
            change_cost=cost,
            cooldown_minutes=cooldown_minutes,
            legal_authority=authority,
            carry_over_rule=carry_over_rule,
            effects=effects,
        ),
        "",
    )


def _normalize_effects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for effect in value:
        if not isinstance(effect, dict):
            continue
        domain = _text(effect.get("domain")).lower()
        name = _text(effect.get("effect")).lower()
        magnitude = _finite_number(effect.get("value"))
        if not domain or not name or magnitude is None:
            continue
        normalized.append(
            {
                "domain": domain,
                "effect": name,
                "value": min(1.0, max(-1.0, magnitude)),
            }
        )
    return normalized


def _decode_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _decode_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _key(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _finite_or_default(value: Any, default: float) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(default))
