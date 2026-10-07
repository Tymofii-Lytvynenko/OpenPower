"""Pure deterministic policies for regional population movement."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

import polars as pl


MOBILITY_ACCESS_EFFECTS = frozenset(
    {"migration_mobility_access", "mobility_access", "free_movement", "movement_access"}
)
MOVEMENT_RESTRICTION_EFFECTS = frozenset(
    {"migration_mobility_restriction", "movement_restriction", "mobility_sanction"}
)
HOSTILE_RELATION_THRESHOLD = -60.0


@dataclass(frozen=True, slots=True)
class BorderAccessDecision:
    eligible: bool
    reason_code: str
    access_rate: float = 0.0
    mobility_agreement: bool = False


@dataclass(frozen=True, slots=True)
class DestinationCapacity:
    eligible: bool
    available_people: int
    total_capacity: int
    reason_code: str


def build_route_index(adjacency: pl.DataFrame | None) -> dict[int, tuple[int, ...]]:
    """Build a stable bidirectional index from the authoritative adjacency table."""

    neighbors: dict[int, set[int]] = {}
    if adjacency is None or adjacency.is_empty():
        return {}

    required = {"region_id", "neighbor_region_id"}
    if not required.issubset(adjacency.columns):
        return {}

    for row in adjacency.select("region_id", "neighbor_region_id").iter_rows(named=True):
        try:
            left = int(row["region_id"])
            right = int(row["neighbor_region_id"])
        except (TypeError, ValueError, OverflowError):
            continue
        if left == right:
            continue
        neighbors.setdefault(left, set()).add(right)
        neighbors.setdefault(right, set()).add(left)
    return {region_id: tuple(sorted(values)) for region_id, values in sorted(neighbors.items())}


def calculate_migrant_cohorts(
    population_count: int,
    source_cohorts: Mapping[str, Any],
    skilled_worker_preference: float = 0.0,
    family_reunification_rate: float = 1.0,
) -> tuple[int, int, int]:
    """Allocate an exact integer population total by source cohort proportions."""

    total_source = sum(
        max(0, _integer(source_cohorts.get(column)))
        for column in ("pop_14", "pop_15_64", "pop_65")
    )
    requested = min(max(0, _integer(population_count)), total_source)
    if requested == 0 or total_source == 0:
        return (0, 0, 0)

    source = [
        max(0, _integer(source_cohorts.get(column)))
        for column in ("pop_14", "pop_15_64", "pop_65")
    ]
    family_rate = _bounded_ratio(family_reunification_rate, default=1.0)
    dependent_limit = int(math.floor(source[0] * family_rate + 0.5))
    requested = min(requested, dependent_limit + source[1] + source[2])
    if requested == 0:
        return (0, 0, 0)

    weights = [value / total_source for value in source]
    preference = _bounded_ratio(skilled_worker_preference)
    if source[1] > 0 and preference > 0.0:
        added_working_share = (1.0 - weights[1]) * preference * 0.15
        other_share = weights[0] + weights[2]
        if other_share > 0.0:
            reduction = added_working_share / other_share
            weights[0] *= 1.0 - reduction
            weights[2] *= 1.0 - reduction
            weights[1] += added_working_share

    if requested > 0 and weights[0] * requested > dependent_limit:
        weights[0] = dependent_limit / requested
        other_total = weights[1] + weights[2]
        if other_total > 0.0:
            weights[1] = (1.0 - weights[0]) * weights[1] / other_total
            weights[2] = (1.0 - weights[0]) * weights[2] / other_total

    allocated = [0, 0, 0]
    remaining = requested
    while remaining > 0:
        eligible = [index for index in range(3) if allocated[index] < source[index]]
        if 0 in eligible and allocated[0] >= dependent_limit:
            eligible.remove(0)
        if not eligible:
            break
        eligible_weight = sum(weights[index] for index in eligible)
        if eligible_weight <= 0.0:
            shares = {index: 1.0 / len(eligible) for index in eligible}
        else:
            shares = {index: weights[index] / eligible_weight for index in eligible}
        exact = {index: remaining * shares[index] for index in eligible}
        assigned_now = {
            index: min(
                source[index] - allocated[index],
                dependent_limit - allocated[index] if index == 0 else remaining,
                math.floor(exact[index]),
            )
            for index in eligible
        }
        for index, amount in assigned_now.items():
            allocated[index] += amount
        assigned_count = sum(assigned_now.values())
        remaining -= assigned_count
        if remaining <= 0:
            break
        # Stable cohort-index tie-breaking preserves deterministic largest-remainder allocation.
        remainders = sorted(
            eligible,
            key=lambda index: (-(exact[index] - math.floor(exact[index])), index),
        )
        for index in remainders:
            limit = min(source[index], dependent_limit if index == 0 else source[index])
            if allocated[index] >= limit:
                continue
            allocated[index] += 1
            remaining -= 1
            if remaining == 0:
                break
        if assigned_count == 0 and not remainders:
            break
    return (allocated[0], allocated[1], allocated[2])


def assess_destination_capacity(
    region: Mapping[str, Any],
    *,
    current_population: int,
    reserved_population: int = 0,
) -> DestinationCapacity:
    """Return conservative remaining capacity without admitting unsupported empty regions."""

    current = max(0, _integer(current_population))
    reserved = max(0, _integer(reserved_population))
    housing = _capacity_value(region, "housing_capacity")
    employment = _capacity_value(region, "employment_capacity")
    services = _capacity_value(region, "service_capacity")
    transport_capacity = _capacity_value(region, "transport_capacity")
    transport = _bounded_ratio(region.get("transport_access"), default=1.0)

    if current == 0 and min(housing, employment, services) <= 0:
        return DestinationCapacity(False, 0, 0, "no_destination_capacity")
    if current == 0 and transport <= 0.0:
        return DestinationCapacity(False, 0, 0, "no_destination_capacity")

    if current > 0:
        # Legacy worlds have no absolute capacity fields; these bounded proxies avoid a hard stop.
        housing = housing or current + max(1, int(current * 0.15))
        employment = employment or current + max(1, int(current * 0.10))
        services = services or current + max(1, int(current * 0.10))
        # Explicit transport limits must remain authoritative as population changes between due flows.
        transport_capacity = transport_capacity or current + max(1, int(current * 0.25 * transport))
    else:
        if transport_capacity <= 0:
            transport_capacity = min(housing, employment, services)

    total_capacity = min(housing, employment, services, transport_capacity)
    available = max(0, total_capacity - current - reserved)
    return DestinationCapacity(
        eligible=available > 0,
        available_people=available,
        total_capacity=max(0, total_capacity),
        reason_code="eligible_capacity" if available > 0 else "no_destination_capacity",
    )


def evaluate_border_access(
    origin_country_id: str,
    destination_country_id: str,
    origin_policy: Mapping[str, Any],
    destination_policy: Mapping[str, Any],
    *,
    relations: pl.DataFrame | None = None,
    wars: pl.DataFrame | None = None,
    treaty_effects: pl.DataFrame | None = None,
) -> BorderAccessDecision:
    """Apply explicit border, relation, war, treaty, and movement-sanction rules."""

    origin = _tag(origin_country_id)
    destination = _tag(destination_country_id)
    if not origin or not destination:
        return BorderAccessDecision(False, "unknown_country")
    if origin == destination:
        return BorderAccessDecision(
            True,
            "eligible_domestic",
            _combined_rate(origin_policy, destination_policy, include_border=False),
        )
    if _at_war(origin, destination, wars):
        return BorderAccessDecision(False, "at_war")
    if _has_effect_for_pair(
        treaty_effects,
        MOVEMENT_RESTRICTION_EFFECTS,
        origin,
        destination,
    ):
        return BorderAccessDecision(False, "sanction_restricted")

    agreement = _has_effect_for_pair(
        treaty_effects,
        MOBILITY_ACCESS_EFFECTS,
        origin,
        destination,
    )
    border_closed = any(
        str(policy.get("border_policy") or "managed").strip().lower() == "closed"
        for policy in (origin_policy, destination_policy)
    )
    if border_closed and not agreement:
        return BorderAccessDecision(False, "border_closed")

    hostile = _minimum_relation(origin, destination, relations) <= HOSTILE_RELATION_THRESHOLD
    if hostile and not agreement:
        return BorderAccessDecision(False, "hostile_relations")

    access_rate = _combined_rate(
        origin_policy,
        destination_policy,
        include_border=True,
        mobility_agreement=agreement,
    )
    if access_rate <= 0.0:
        origin_rate = _bounded_ratio(origin_policy.get("exit_rate"))
        reason = "exit_restricted" if origin_rate <= 0.0 else "entry_restricted"
        return BorderAccessDecision(False, reason)
    reason = "eligible_mobility_agreement" if agreement else "eligible_international"
    return BorderAccessDecision(True, reason, access_rate, agreement)


def estimate_migration_count(
    origin_region: Mapping[str, Any],
    destination_region: Mapping[str, Any],
    origin_country: Mapping[str, Any],
    destination_country: Mapping[str, Any],
    *,
    access_rate: float,
    source_available: int,
    destination_available: int,
) -> tuple[int, float]:
    """Estimate a bounded deterministic route count from relative living conditions."""

    source = max(0, _integer(source_available))
    capacity = max(0, _integer(destination_available))
    if source == 0 or capacity == 0:
        return 0, 0.0

    origin_score = _attractiveness(origin_region, origin_country)
    destination_score = _attractiveness(destination_region, destination_country)
    advantage = destination_score - origin_score
    pressure = _bounded_ratio(origin_country.get("migration_pressure"))
    opportunity = max(0.0, advantage) + pressure * 0.25
    rate = min(0.02, opportunity * 0.02) * _bounded_ratio(access_rate)
    count = min(source, capacity, int(math.floor(source * rate + 0.5)))
    return max(0, count), _bounded_ratio(opportunity)


def _attractiveness(region: Mapping[str, Any], country: Mapping[str, Any]) -> float:
    employment = _bounded_ratio(country.get("employment_rate"), 0.5)
    development = _bounded_ratio(country.get("human_dev"), 0.5)
    health = _bounded_ratio(country.get("economic_health"), 0.5)
    transport = _bounded_ratio(region.get("transport_access"), 0.5)
    services = _bounded_ratio(region.get("health_capacity"), 0.5)
    return _bounded_ratio(
        (employment * 0.25)
        + (development * 0.25)
        + (health * 0.20)
        + (transport * 0.15)
        + (services * 0.15)
    )


def _combined_rate(
    origin_policy: Mapping[str, Any],
    destination_policy: Mapping[str, Any],
    *,
    include_border: bool,
    mobility_agreement: bool = False,
) -> float:
    rate = min(
        _bounded_ratio(origin_policy.get("exit_rate"), 0.5),
        _bounded_ratio(destination_policy.get("entry_rate"), 0.5),
    )
    posture_multipliers = {"open": 1.0, "managed": 0.75, "restricted": 0.25}
    rate *= min(
        posture_multipliers.get(str(policy.get("migration_policy") or "managed").lower(), 0.5)
        for policy in (origin_policy, destination_policy)
    )
    if include_border and not mobility_agreement:
        rate *= min(
            1.0 if str(policy.get("border_policy") or "managed").lower() == "open" else 0.75
            for policy in (origin_policy, destination_policy)
        )
    return _bounded_ratio(rate)


def _minimum_relation(origin: str, destination: str, relations: pl.DataFrame | None) -> float:
    if relations is None or relations.is_empty():
        return 0.0
    if not {"source", "target", "value"}.issubset(relations.columns):
        return 0.0
    values = [
        _finite(row.get("value"), 0.0)
        for row in relations.to_dicts()
        if (
            (_tag(row.get("source")), _tag(row.get("target"))) in {
                (origin, destination), (destination, origin)
            }
        )
    ]
    return min(values) if values else 0.0


def _at_war(origin: str, destination: str, wars: pl.DataFrame | None) -> bool:
    if wars is None or wars.is_empty():
        return False
    for row in wars.to_dicts():
        status = str(row.get("status") or "active").strip().lower()
        if status not in {"active", "ongoing", "in_progress"}:
            continue
        side_a = _country_tags(row.get("side_a"))
        side_b = _country_tags(row.get("side_b"))
        if not side_a:
            side_a = {_tag(row.get("attacker_tag"))}
        if not side_b:
            side_b = {_tag(row.get("defender_tag"))}
        if (origin in side_a and destination in side_b) or (
            destination in side_a and origin in side_b
        ):
            return True
    return False


def _has_effect_for_pair(
    effects: pl.DataFrame | None,
    names: frozenset[str],
    origin: str,
    destination: str,
) -> bool:
    if effects is None or effects.is_empty():
        return False
    if not {"country_id", "effect"}.issubset(effects.columns):
        return False
    for row in effects.to_dicts():
        if str(row.get("effect") or "").strip().lower() not in names:
            continue
        if _finite(row.get("value"), 1.0) <= 0.0:
            continue
        country = _tag(row.get("country_id"))
        if country not in {origin, destination}:
            continue
        targets = _detail_tags(row.get("detail"))
        if not targets or destination in targets or origin in targets:
            return True
    return False


def _detail_tags(value: Any) -> set[str]:
    raw = str(value or "").strip()
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = [part for part in raw.replace(";", ",").split(",") if part.strip()]
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, (list, tuple, set)):
        return set()
    return {_tag(item) for item in parsed if _tag(item)}


def _country_tags(value: Any) -> set[str]:
    if isinstance(value, str):
        values = _detail_tags(value)
    elif isinstance(value, (list, tuple, set)):
        values = {_tag(item) for item in value if _tag(item)}
    else:
        values = set()
    return values


def _capacity_value(region: Mapping[str, Any], name: str) -> int:
    value = _finite(region.get(name), 0.0)
    return max(0, int(math.floor(value)))


def _integer(value: Any) -> int:
    number = _finite(value, 0.0)
    return int(number) if number > 0.0 else 0


def _finite(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _bounded_ratio(value: Any, default: float = 0.0) -> float:
    return min(1.0, max(0.0, _finite(value, default)))


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
