"""Deterministic election snapshots and vote-share resolution."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable


MAX_OVERRIDE_DURATION_DAYS = 36_500
MAX_GAME_MINUTE = (1 << 63) - 1


@dataclass(frozen=True)
class ElectionResult:
    eligible_party_ids: tuple[str, ...]
    coalition_party_ids: tuple[str, ...]
    support_snapshot_json: str
    results_json: str
    turnout: float
    winner_party_id: str


@dataclass(frozen=True)
class ElectionOverrideDecision:
    override_type: str
    next_election_at_minute: int
    cost: float
    approval_delta: float
    stability_delta: float
    cooldown_until_minute: int
    successor_party_id: str = ""


def validate_election_override(
    *,
    override_type: Any,
    duration_days: Any,
    now_minute: int,
    current_election_minute: Any,
    form_rule: dict[str, Any],
    government: dict[str, Any],
    treasury: Any,
    last_override_at_minute: Any = None,
    party_ids: Iterable[Any] = (),
    crisis_active: bool = False,
) -> tuple[ElectionOverrideDecision | None, str]:
    """Validate one government-configured election override without mutating state."""

    override_key = str(override_type or "").strip().casefold()
    if override_key not in {"postpone", "accelerate", "suspend", "succession"}:
        return None, "The requested election override type is not supported."
    if not bool(government.get("election_eligible", False)) or not bool(
        form_rule.get("election_eligible", False)
    ):
        return None, "The current government does not hold scheduled elections."

    rules = _decode_override_rules(form_rule.get("election_overrides_json"))
    matching_rules = [
        rule
        for rule in rules
        if str(rule.get("type", rule.get("override_type", ""))).strip().casefold()
        == override_key
    ]
    if len(matching_rules) != 1:
        return None, "The current government has no unique rule for this election override."
    rule = matching_rules[0]
    if rule.get("enabled", True) is False:
        return None, "This election override is disabled by the current government rules."
    authority = str(rule.get("legal_authority", rule.get("authority", "government"))).strip().casefold()
    if authority != "government":
        return None, f"The configured election authority '{authority}' is not available."
    if crisis_active or str(government.get("crisis_status") or "none").strip().casefold() not in {
        "",
        "none",
        "resolved",
    }:
        return None, "Election overrides are unavailable during an active government crisis."

    duration = _strict_int(duration_days)
    minimum_duration = _strict_int(rule.get("minimum_duration_days", 1))
    maximum_duration = _strict_int(rule.get("maximum_duration_days", 365))
    if (
        duration is None
        or minimum_duration is None
        or maximum_duration is None
        or minimum_duration <= 0
        or maximum_duration < minimum_duration
        or maximum_duration > MAX_OVERRIDE_DURATION_DAYS
        or duration < minimum_duration
        or duration > maximum_duration
    ):
        return None, "The requested override duration is outside the configured date bounds."

    now = _strict_int(now_minute)
    scheduled = _strict_int(current_election_minute)
    if (
        now is None
        or now < 0
        or now > MAX_GAME_MINUTE
        or scheduled is None
        or scheduled <= 0
        or scheduled > MAX_GAME_MINUTE
    ):
        return None, "The current election date is unavailable or invalid."

    minimum_notice_days = _strict_int(rule.get("minimum_notice_days", 1))
    cooldown_days = _strict_int(rule.get("cooldown_days", 0))
    if (
        minimum_notice_days is None
        or minimum_notice_days < 0
        or minimum_notice_days > MAX_OVERRIDE_DURATION_DAYS
        or cooldown_days is None
        or cooldown_days < 0
        or cooldown_days > MAX_OVERRIDE_DURATION_DAYS
    ):
        return None, "The configured election override dates are invalid."
    last_override = _strict_int(last_override_at_minute) if last_override_at_minute is not None else None
    if last_override is None and last_override_at_minute is not None:
        return None, "The previous election override date is invalid."
    if last_override is not None and now < last_override + cooldown_days * 1_440:
        cooldown_ends_at = last_override + cooldown_days * 1_440
        return None, f"The election override cooldown ends at game minute {cooldown_ends_at}."

    cost = _finite_optional(rule.get("cost", 0.0))
    funds = _finite_optional(treasury)
    if cost is None or cost < 0.0:
        return None, "The configured election override cost is invalid."
    if funds is None or funds < cost:
        return None, "The country lacks funds for this election override."

    approval_delta = _finite_optional(rule.get("approval_delta", 0.0))
    stability_delta = _finite_optional(rule.get("stability_delta", 0.0))
    if approval_delta is None or stability_delta is None:
        return None, "The configured election override consequences are invalid."
    approval_delta = min(100.0, max(-100.0, approval_delta))
    stability_delta = min(100.0, max(-100.0, stability_delta))

    duration_minutes = duration * 1_440
    successor_party_id = ""
    if override_key == "postpone":
        next_election = scheduled + duration_minutes
    elif override_key == "accelerate":
        legal_floor = now + max(1, minimum_notice_days) * 1_440
        next_election = max(legal_floor, scheduled - duration_minutes)
        if next_election >= scheduled:
            return None, "The election cannot be accelerated within the configured legal date bounds."
    elif override_key == "suspend":
        next_election = max(scheduled, now + duration_minutes)
        if next_election == scheduled:
            return None, "The requested suspension would not change the next election date."
    else:
        successor_party_id = str(government.get("succession_party_id") or "").strip()
        known_parties = {str(party_id or "").strip().casefold() for party_id in party_ids}
        if not successor_party_id or successor_party_id.casefold() not in known_parties:
            return None, "The configured succession party is unavailable."
        next_election = now + duration_minutes

    cooldown_until = now + cooldown_days * 1_440
    if next_election <= 0 or next_election > MAX_GAME_MINUTE or cooldown_until > MAX_GAME_MINUTE:
        return None, "The configured election override would exceed the supported game-date range."

    return (
        ElectionOverrideDecision(
            override_type=override_key,
            next_election_at_minute=next_election,
            cost=cost,
            approval_delta=approval_delta,
            stability_delta=stability_delta,
            cooldown_until_minute=cooldown_until,
            successor_party_id=successor_party_id,
        ),
        "",
    )


def resolve_election(
    parties: Iterable[dict[str, Any]],
    *,
    ruling_party_id: Any,
    succession_party_id: Any = "",
    approval: Any,
    stability: Any,
    form_rule: dict[str, Any],
) -> ElectionResult:
    """Capture eligible support and compute turnout, vote shares, and a stable winner."""

    party_rows = [dict(row) for row in parties]
    incumbent = _party_id(ruling_party_id)
    successor = _party_id(succession_party_id)
    eligible = [
        dict(row)
        for row in party_rows
        if bool(row.get("eligible", False)) and _party_id(row.get("party_id"))
    ]
    if not eligible:
        fallback_id = (
            successor
            if str(form_rule.get("succession_rule") or "").strip().lower() == "configured_successor"
            and successor
            else incumbent
        )
        fallback = next(
            (dict(row) for row in party_rows if _party_id(row.get("party_id")) == fallback_id),
            None,
        )
        eligible = [
            {
                **(fallback or {}),
                "party_id": fallback_id or "incumbent",
                "support_share": 1.0,
                "organization": 0.5,
                "eligible": True,
            }
        ]

    eligible.sort(key=lambda row: _party_id(row.get("party_id")))
    support = {
        _party_id(row.get("party_id")): {
            "support_share": _ratio(row.get("support_share")),
            "organization": _ratio(row.get("organization")),
            "policy_positions_json": str(row.get("policy_positions_json") or "{}"),
            "is_incumbent": _party_id(row.get("party_id")) == incumbent,
        }
        for row in eligible
    }
    approval_percent = _percent(approval, 50.0)
    stability_percent = _percent(stability, 50.0)
    weights = {
        party_id: values["support_share"] * (0.5 + 0.5 * values["organization"])
        for party_id, values in support.items()
    }
    incumbent_bonus = _bounded(_finite(form_rule.get("incumbent_advantage"), 0.1), 0.0, 0.5)
    if incumbent in weights:
        approval_adjustment = (approval_percent - 50.0) / 50.0
        weights[incumbent] *= _bounded(1.0 + incumbent_bonus * approval_adjustment, 0.5, 1.5)
    weight_total = sum(weights.values())
    if weight_total <= 0.0:
        weights = {party_id: 1.0 for party_id in support}
        weight_total = float(len(weights))

    base_turnout = _bounded(_finite(form_rule.get("election_turnout_base"), 0.65), 0.1, 1.0)
    approval_weight = _bounded(
        _finite(form_rule.get("election_turnout_approval_weight"), 0.003), 0.0, 0.01
    )
    stability_weight = _bounded(
        _finite(form_rule.get("election_turnout_stability_weight"), 0.002), 0.0, 0.01
    )
    turnout = _bounded(
        base_turnout
        + ((approval_percent - 50.0) * approval_weight)
        + ((stability_percent - 50.0) * stability_weight),
        0.1,
        1.0,
    )
    vote_shares = {party_id: weight / weight_total for party_id, weight in weights.items()}
    vote_order = sorted(vote_shares, key=lambda party_id: (-vote_shares[party_id], party_id))
    coalition_threshold = _bounded(_finite(form_rule.get("coalition_threshold"), 0.5), 0.0, 1.0)
    coalition: list[str] = []
    coalition_share = 0.0
    for party_id in vote_order:
        coalition.append(party_id)
        coalition_share += vote_shares[party_id]
        if coalition_share >= coalition_threshold:
            break
    winner = coalition[0] if coalition else vote_order[0]
    result_payload = {
        party_id: {
            "vote_share": vote_shares[party_id],
            "turnout_weighted_share": vote_shares[party_id] * turnout,
        }
        for party_id in sorted(vote_shares)
    }
    return ElectionResult(
        eligible_party_ids=tuple(sorted(support)),
        coalition_party_ids=tuple(coalition),
        support_snapshot_json=_json(support),
        results_json=_json(result_payload),
        turnout=turnout,
        winner_party_id=winner,
    )


def _ratio(value: Any) -> float:
    ratio = _finite(value, 0.0)
    if ratio > 1.0:
        ratio /= 100.0
    return _bounded(ratio, 0.0, 1.0)


def _percent(value: Any, default: float) -> float:
    percent = _finite(value, default)
    if 0.0 <= percent <= 1.0:
        percent *= 100.0
    return _bounded(percent, 0.0, 100.0)


def _finite(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _party_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_override_rules(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return number


def _finite_optional(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None
