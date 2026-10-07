from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from collections.abc import Iterable, Mapping
from typing import Any


MINUTES_PER_YEAR = 365 * 24 * 60


@dataclass(frozen=True)
class InfrastructureCategoryPolicy:
    """Configurable limits and lifecycle rates for one infrastructure category."""

    category: str
    baseline: float
    maximum: float
    construction_cost_per_level: float
    construction_minutes_per_level: int
    maintenance_cost_per_level_month: float
    annual_depreciation: float
    legacy_level_column: str | None = None
    legacy_condition_column: str | None = None
    damage_response: Mapping[str, float] = field(default_factory=dict)


DEFAULT_CATEGORY_POLICIES: dict[str, InfrastructureCategoryPolicy] = {
    "transport": InfrastructureCategoryPolicy(
        "transport", 0.25, 1.0, 100_000.0, 43_200, 1_000.0, 0.025,
        "infrastructure", "infrastructure_health",
    ),
    "utilities": InfrastructureCategoryPolicy(
        "utilities", 0.30, 1.0, 125_000.0, 50_400, 1_250.0, 0.03,
        "health_capacity", "infrastructure_health",
    ),
    "industrial": InfrastructureCategoryPolicy(
        "industrial", 0.20, 1.0, 150_000.0, 57_600, 1_500.0, 0.035,
        "industrial_access", "infrastructure_health",
    ),
    "telecom": InfrastructureCategoryPolicy(
        "telecom", 0.20, 1.0, 90_000.0, 36_000, 900.0, 0.04,
        "communications", "infrastructure_health",
    ),
}


def configured_category_policies(
    raw: Any,
) -> dict[str, InfrastructureCategoryPolicy]:
    """Apply scenario overrides without allowing incomplete policies to leak in."""

    policies = dict(DEFAULT_CATEGORY_POLICIES)
    if not isinstance(raw, Mapping):
        return policies

    for category, values in raw.items():
        key = str(category).strip().lower()
        if not key or not isinstance(values, Mapping):
            continue
        current = policies.get(key)
        if current is None:
            required = {
                "baseline",
                "maximum",
                "construction_cost_per_level",
                "construction_minutes_per_level",
                "maintenance_cost_per_level_month",
                "annual_depreciation",
            }
            if not required.issubset(values):
                continue
            try:
                candidate = InfrastructureCategoryPolicy(
                    category=key,
                    baseline=values["baseline"],
                    maximum=values["maximum"],
                    construction_cost_per_level=values["construction_cost_per_level"],
                    construction_minutes_per_level=values["construction_minutes_per_level"],
                    maintenance_cost_per_level_month=values["maintenance_cost_per_level_month"],
                    annual_depreciation=values["annual_depreciation"],
                    legacy_level_column=values.get("legacy_level_column"),
                    legacy_condition_column=values.get("legacy_condition_column"),
                    damage_response=_normalize_damage_response(
                        values.get("damage_response", {})
                    ),
                )
            except (TypeError, ValueError):
                continue
            if _valid_policy(candidate):
                policies[key] = candidate
            continue
        accepted: dict[str, Any] = {}
        for field_name in (
            "baseline",
            "maximum",
            "construction_cost_per_level",
            "construction_minutes_per_level",
            "maintenance_cost_per_level_month",
            "annual_depreciation",
            "legacy_level_column",
            "legacy_condition_column",
            "damage_response",
        ):
            if field_name in values:
                accepted[field_name] = values[field_name]
        if "damage_response" in accepted:
            try:
                accepted["damage_response"] = _normalize_damage_response(
                    accepted["damage_response"]
                )
            except (TypeError, ValueError, OverflowError):
                continue
        try:
            candidate = replace(current, **accepted)
        except (TypeError, ValueError):
            continue
        if _valid_policy(candidate):
            policies[key] = candidate
    return policies


def _normalize_damage_response(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        raise TypeError("damage_response must map source names to multipliers")
    normalized: dict[str, float] = {}
    for source, multiplier in raw.items():
        key = str(source).strip().lower()
        if not key:
            raise ValueError("damage_response keys cannot be empty")
        normalized[key] = float(multiplier)
    return normalized


def _valid_policy(policy: InfrastructureCategoryPolicy) -> bool:
    numeric = (
        policy.baseline,
        policy.maximum,
        policy.construction_cost_per_level,
        policy.construction_minutes_per_level,
        policy.maintenance_cost_per_level_month,
        policy.annual_depreciation,
    )
    try:
        baseline, maximum, construction_cost, construction_minutes, maintenance_cost, depreciation = (
            float(value) for value in numeric
        )
    except (TypeError, ValueError, OverflowError):
        return False
    response = policy.damage_response
    if not isinstance(response, Mapping):
        return False
    try:
        response_values = [float(value) for value in response.values()]
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        all(math.isfinite(value) for value in (baseline, maximum, construction_cost, construction_minutes, maintenance_cost, depreciation))
        and 0.0 <= baseline <= maximum <= 1.0
        and construction_cost >= 0.0
        and construction_minutes > 0
        and maintenance_cost >= 0.0
        and 0.0 <= depreciation <= 1.0
        and (policy.legacy_level_column is None or isinstance(policy.legacy_level_column, str))
        and (policy.legacy_condition_column is None or isinstance(policy.legacy_condition_column, str))
        and all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in response_values)
    )


def bounded_ratio(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = default
    if not math.isfinite(number):
        number = default
    return max(0.0, min(1.0, number))


def quote_infrastructure_cost(
    category: str,
    current_level: float,
    target_level: float,
    *,
    regional_scale: float = 1.0,
    policies: Mapping[str, InfrastructureCategoryPolicy] = DEFAULT_CATEGORY_POLICIES,
) -> float:
    """Calculate a deterministic project quote from server-owned policy."""

    policy = policies.get(str(category).strip().lower())
    if policy is None:
        raise ValueError(f"Unsupported infrastructure category: {category!r}.")
    current = float(current_level)
    target = float(target_level)
    scale = float(regional_scale)
    if not all(math.isfinite(number) for number in (current, target, scale)):
        raise ValueError("Infrastructure quote inputs must be finite.")
    if not 0.0 <= current < target <= policy.maximum:
        raise ValueError("Target level must exceed the current level and stay within the category maximum.")
    if scale <= 0.0:
        raise ValueError("Regional scale must be positive.")
    return (target - current) * policy.construction_cost_per_level * scale


def quote_infrastructure_duration(
    category: str,
    current_level: float,
    target_level: float,
    *,
    regional_scale: float = 1.0,
    policies: Mapping[str, InfrastructureCategoryPolicy] = DEFAULT_CATEGORY_POLICIES,
) -> int:
    policy = policies.get(str(category).strip().lower())
    if policy is None:
        raise ValueError(f"Unsupported infrastructure category: {category!r}.")
    current = float(current_level)
    target = float(target_level)
    scale = float(regional_scale)
    if not all(math.isfinite(number) for number in (current, target, scale)):
        raise ValueError("Infrastructure duration inputs must be finite.")
    if not 0.0 <= current < target <= policy.maximum or scale <= 0.0:
        raise ValueError("Infrastructure duration inputs are outside the valid range.")
    return max(1, int(math.ceil((target - current) * policy.construction_minutes_per_level * scale)))


def calculate_infrastructure_capacity(level: float, condition: float, maximum: float) -> float:
    max_level = max(0.0, float(maximum))
    if not math.isfinite(max_level) or max_level <= 0.0:
        return 0.0
    return bounded_ratio(level / max_level) * bounded_ratio(condition)


def depreciate_infrastructure_condition(
    condition: float,
    elapsed_minutes: int,
    *,
    annual_rate: float,
    maintenance_ratio: float,
    use_factor: float = 0.0,
) -> float:
    rate = max(0.0, min(1.0, float(annual_rate)))
    elapsed = max(0, int(elapsed_minutes))
    maintenance = bounded_ratio(maintenance_ratio)
    use = max(0.0, min(2.0, float(use_factor)))
    effective_loss = rate * (elapsed / MINUTES_PER_YEAR) * (1.0 + use) * (1.0 - maintenance)
    return max(0.0, bounded_ratio(condition) - effective_loss)


def aggregate_weighted_values(values: Iterable[float], weights: Iterable[float]) -> float:
    pairs = [
        (bounded_ratio(value), float(weight))
        for value, weight in zip(values, weights)
        if math.isfinite(float(weight)) and float(weight) > 0.0
    ]
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0.0:
        return 0.0
    return sum(value * weight for value, weight in pairs) / total_weight


def apply_infrastructure_damage(
    profile: Mapping[str, Any],
    *,
    source_id: str,
    source_type: str,
    severity: float,
    now_minute: int,
    existing_source_ids: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Apply a source once and return the restoration ceiling with its record."""

    current = dict(profile)
    source = str(source_id).strip()
    if (
        not source
        or source == str(current.get("last_source_id") or "")
        or source in set(existing_source_ids)
    ):
        return current, None
    impact = bounded_ratio(severity)
    level = bounded_ratio(current.get("level"))
    condition = bounded_ratio(current.get("condition"), 1.0)
    capacity = calculate_infrastructure_capacity(
        level, condition, current.get("maximum", 1.0)
    )
    current.update(
        condition=max(0.0, condition * (1.0 - impact)),
        capacity=calculate_infrastructure_capacity(
            level, condition * (1.0 - impact), current.get("maximum", 1.0)
        ),
        last_change_minute=int(now_minute),
        last_source_type=str(source_type),
        last_source_id=source,
    )
    record = {
        "source_id": source,
        "source_type": str(source_type),
        "severity": impact,
        "pre_damage_level": level,
        "pre_damage_condition": condition,
        "restoration_ceiling": capacity,
        "damaged_at_minute": int(now_minute),
    }
    return current, record


def reconstruct_infrastructure_capacity(
    current_capacity: float,
    repair_amount: float,
    *,
    restoration_ceiling: float,
) -> float:
    current = bounded_ratio(current_capacity)
    repair = max(0.0, float(repair_amount))
    ceiling = bounded_ratio(restoration_ceiling)
    if not math.isfinite(repair):
        repair = 0.0
    return min(ceiling, current + repair)


def build_initial_profiles(
    region_rows: Iterable[Mapping[str, Any]],
    *,
    policies: Mapping[str, InfrastructureCategoryPolicy] = DEFAULT_CATEGORY_POLICIES,
    now_minute: int = 0,
) -> list[dict[str, Any]]:
    """Seed additive category rows while preserving legacy regional values."""

    profiles: list[dict[str, Any]] = []
    for region in region_rows:
        region_id = int(region.get("id", 0) or 0)
        for category, policy in policies.items():
            level = _legacy_ratio(region.get(policy.legacy_level_column)) if policy.legacy_level_column else None
            if level is None:
                level = policy.baseline
            condition = _legacy_ratio(region.get(policy.legacy_condition_column)) if policy.legacy_condition_column else None
            if condition is None:
                condition = 1.0
            level = min(policy.maximum, level)
            profiles.append(
                {
                    "region_id": region_id,
                    "category": category,
                    "level": level,
                    "condition": condition,
                    "capacity": calculate_infrastructure_capacity(level, condition, policy.maximum),
                    "baseline": policy.baseline,
                    "maximum": policy.maximum,
                    "maintenance_level": 0.0,
                    "maintenance_cost_per_level_month": policy.maintenance_cost_per_level_month,
                    "last_change_minute": int(now_minute),
                    "last_source_type": "legacy" if policy.legacy_level_column in region else "baseline",
                    "last_source_id": "legacy-seed" if policy.legacy_level_column in region else "scenario-default",
                }
            )
    return profiles


def _legacy_ratio(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0.0, min(1.0, number)) if math.isfinite(number) else None
