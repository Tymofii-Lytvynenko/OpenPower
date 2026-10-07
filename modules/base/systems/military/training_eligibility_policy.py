"""Pure facility and cost rules shared by AI proposals and training actions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from modules.base.systems.military.capability_catalog import TRAINING_LEVELS


def training_level_steps(current: Any, target: Any) -> int:
    current_level = str(current or "Recruit").strip().title()
    target_level = str(target or "").strip().title()
    try:
        steps = TRAINING_LEVELS.index(target_level) - TRAINING_LEVELS.index(current_level)
    except ValueError:
        return 0
    return steps if steps > 0 else 0


def training_cost(strength: Any, level_steps: int, cost_per_strength: Any) -> float:
    return max(0.0, _finite_number(strength)) * max(0, int(level_steps)) * max(
        0.0, _finite_number(cost_per_strength)
    )


def facility_domains(facility: Mapping[str, Any]) -> set[str]:
    raw_domains = facility.get("supported_domains")
    if isinstance(raw_domains, (list, tuple, set)):
        return {
            str(domain or "").strip().lower()
            for domain in raw_domains
            if str(domain or "").strip()
        }
    try:
        parsed = json.loads(str(raw_domains or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    return {
        str(domain or "").strip().lower()
        for domain in parsed
        if str(domain or "").strip()
    } if isinstance(parsed, list) else set()


def select_training_facility(
    unit: Mapping[str, Any],
    owner: str,
    domain: str,
    facilities: Sequence[Mapping[str, Any]],
    orders: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    region_id = _integer(unit.get("current_region_id"))
    local_sites = [
        site for site in facilities
        if _tag(site.get("country_id")) == _tag(owner)
        and _integer(site.get("region_id")) == region_id
    ]
    if not local_sites:
        return None, "No training facility is configured at the unit's location."

    domain = str(domain or "land").strip().lower()
    compatible_sites = [
        site for site in local_sites
        if domain in facility_domains(site) or "all" in facility_domains(site)
    ]
    if not compatible_sites:
        return None, f"No local training facility supports the {domain} domain."

    enabled_sites = [site for site in compatible_sites if bool(site.get("enabled"))]
    if not enabled_sites:
        return None, "No compatible training facility is enabled at the unit's location."
    staffed_sites = [
        site for site in enabled_sites
        if _integer(site.get("instructor_count")) > 0
    ]
    if not staffed_sites:
        return None, "No eligible instructor is available at a compatible training facility."

    for site in sorted(staffed_sites, key=lambda row: str(row.get("id") or "")):
        slot_limit = min(
            max(0, _integer(site.get("capacity"))),
            max(0, _integer(site.get("instructor_count"))),
        )
        active_orders = sum(
            1 for order in orders
            if str(order.get("facility_id") or "") == str(site.get("id") or "")
            and str(order.get("status") or "") == "active"
        )
        if active_orders < slot_limit:
            return site, ""
    return None, "All compatible training facilities are at capacity."


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _finite_number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0
