"""Deterministic covert-mission outcome and discovery policy."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.covert_mission_profiles import MISSION_PROFILES
from modules.base.systems.military.covert_policy import (
    SKILL_LEVELS,
    domestic_security_coverage,
    skill_profile,
)
from src.shared.covert_mission_options import mission_success_modifier


@dataclass(frozen=True, slots=True)
class MissionResolutionServices:
    normalize_tag: Callable[[Any], str]
    finite_number: Callable[[Any], float]
    metric_count: Callable[..., int]
    metric_value: Callable[..., Any]
    country_population: Callable[[Any, str], float]
    relation_value: Callable[[Sequence[dict[str, Any]], str, str], float]
    target_regional_telecom_capacity: Callable[
        [Any, Mapping[str, Any], Mapping[str, Any]], float
    ]
    table_value_by_key: Callable[[Any, str, Any, str, Any], Any]
    intelligence_snapshot: Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _ResolutionProbabilities:
    success: float
    detection: float


@dataclass(frozen=True, slots=True)
class _OutcomeRoll:
    result: str
    discovered: bool
    detection_roll: float


@dataclass(frozen=True, slots=True)
class _IntelligenceConfidence:
    value: float
    target_telecom: float
    factors: dict[str, Any]


def resolve_mission(
    state: Any,
    cell: Mapping[str, Any],
    mission: Mapping[str, Any],
    target: Mapping[str, Any],
    all_cells: Sequence[dict[str, Any]],
    relation_rows: Sequence[dict[str, Any]],
    security_cell_counts: pl.DataFrame | None = None,
    espionage_cell_counts: pl.DataFrame | None = None,
    population_by_country: pl.DataFrame | None = None,
    *,
    services: MissionResolutionServices,
) -> tuple[str, bool, bool, float, dict[str, Any]]:
    mission_type = str(mission.get("mission_type"))
    base_risk, base_detection, _ = MISSION_PROFILES[mission_type]
    profile = skill_profile(cell.get("skill_level"))
    probabilities = _resolution_probabilities(
        state,
        cell,
        mission,
        target,
        all_cells,
        relation_rows,
        base_risk,
        base_detection,
        profile,
        security_cell_counts,
        population_by_country,
        services,
    )
    outcome = _roll_outcome(state, mission, probabilities)
    intelligence = _intelligence_confidence(
        state,
        cell,
        mission,
        target,
        all_cells,
        espionage_cell_counts,
        services,
    )
    output = _intelligence_output(
        state,
        mission,
        target,
        outcome.result,
        intelligence,
        population_by_country,
        services,
    )
    discovered_during_resolution = (
        outcome.discovered
        and outcome.detection_roll < probabilities.detection * 0.65
    )
    return (
        outcome.result,
        outcome.discovered,
        discovered_during_resolution,
        intelligence.value,
        output,
    )


def _resolution_probabilities(
    state: Any,
    cell: Mapping[str, Any],
    mission: Mapping[str, Any],
    target: Mapping[str, Any],
    all_cells: Sequence[dict[str, Any]],
    relation_rows: Sequence[dict[str, Any]],
    base_risk: float,
    base_detection: float,
    profile: Any,
    security_cell_counts: pl.DataFrame | None,
    population_by_country: pl.DataFrame | None,
    services: MissionResolutionServices,
) -> _ResolutionProbabilities:
    target_id = services.normalize_tag(target.get("id"))
    target_security = min(
        0.7,
        max(
            0.0,
            services.finite_number(target.get("security_upkeep"))
            / max(1.0, services.finite_number(target.get("gdp")) * 0.02),
        ),
    )
    security_cell_count = _security_cell_count(
        all_cells, target_id, security_cell_counts, services
    )
    population = (
        services.metric_value(
            population_by_country, "population", country_id=target_id
        )
        if population_by_country is not None
        else services.country_population(state, target_id)
    )
    coverage = domestic_security_coverage(
        security_cell_count, population, state.globals
    )
    concealment = min(0.9, max(0.0, services.finite_number(cell.get("concealment"))))
    relation = services.relation_value(
        relation_rows,
        services.normalize_tag(mission.get("owner_country_id")),
        services.normalize_tag(target.get("id")),
    )
    scrutiny = max(0.0, -relation) / 100.0 * 0.12
    detection_probability = min(
        0.92,
        max(0.02, base_detection + target_security + coverage + scrutiny - concealment * 0.55),
    )
    preparation_quality = min(
        0.2, services.finite_number(mission.get("preparation_required")) / 10080.0
    )
    communications_factor = (
        1.0 if bool(cell.get("communications_ready", True)) else 0.55
    )
    mission_type = str(mission.get("mission_type") or "")
    has_specific_target = bool(
        str(mission.get("target_resource_id") or "").strip()
        or str(mission.get("target_unit_category") or "").strip()
    )
    # These multipliers follow the source constants in
    # .codex/reference-hdm-full-reference/includes/common_lib/reference_covert_actions_cell.h;
    # retain OpenPower's security and concealment inputs alongside them.
    resolution_modifier = mission_success_modifier(
        mission_type,
        str(mission.get("complexity") or "medium"),
        has_specific_target=has_specific_target,
    )
    success_probability = min(
        0.92,
        max(
            0.05,
            (1.0 - base_risk + profile.success_bonus + concealment * 0.15 + preparation_quality - target_security * 0.4)
            * communications_factor
            * resolution_modifier,
        ),
    )
    return _ResolutionProbabilities(success_probability, detection_probability)


def _security_cell_count(
    all_cells: Sequence[dict[str, Any]],
    target_id: str,
    security_cell_counts: pl.DataFrame | None,
    services: MissionResolutionServices,
) -> int:
    if security_cell_counts is not None:
        return services.metric_count(security_cell_counts, country_id=target_id)
    return sum(
        1
        for row in all_cells
        if services.normalize_tag(row.get("country_id")) == target_id
        and row.get("assignment") == "domestic_security"
        and row.get("status") == "active"
        and services.normalize_tag(row.get("location_country_id")) == target_id
    )


def _roll_outcome(
    state: Any,
    mission: Mapping[str, Any],
    probabilities: _ResolutionProbabilities,
) -> _OutcomeRoll:
    seed = f"{state.determinism.seed}:{mission['id']}:{mission['resolves_at_minute']}"
    roll = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16) / float(
        0xFFFFFFFFFFFFFFFF
    )
    detection_roll = int(
        hashlib.sha256((seed + ":detection").encode("utf-8")).hexdigest()[:16], 16
    ) / float(0xFFFFFFFFFFFFFFFF)
    discovered = detection_roll < probabilities.detection
    partial_threshold = min(0.98, probabilities.success + 0.12)
    result = (
        "captured"
        if discovered
        and not roll < partial_threshold
        and detection_roll < probabilities.detection * 0.35
        else "success"
        if roll < probabilities.success
        else "partial_success"
        if roll < partial_threshold
        else "failure"
    )
    return _OutcomeRoll(result, discovered, detection_roll)


def _intelligence_confidence(
    state: Any,
    cell: Mapping[str, Any],
    mission: Mapping[str, Any],
    target: Mapping[str, Any],
    all_cells: Sequence[dict[str, Any]],
    espionage_cell_counts: pl.DataFrame | None,
    services: MissionResolutionServices,
) -> _IntelligenceConfidence:
    skill_index = SKILL_LEVELS.index(str(cell.get("skill_level") or "Recruit"))
    communications_factor = (
        1.0 if bool(cell.get("communications_ready", True)) else 0.55
    )
    target_telecom = services.target_regional_telecom_capacity(state, cell, target)
    confidence = min(
        0.95,
        max(
            0.1,
            (0.35 + skill_index * 0.16 + services.finite_number(cell.get("readiness")) * 0.15)
            * communications_factor,
        ),
    )
    confidence *= 0.75 + 0.25 * target_telecom
    confidence_factors: dict[str, Any] = {}
    if str(mission.get("mission_type") or "") == "military_espionage":
        owner_id = services.normalize_tag(mission.get("owner_country_id"))
        target_id = services.normalize_tag(target.get("id"))
        countries = state.tables.get("countries")
        observer_budget = services.table_value_by_key(
            countries, "id", owner_id, "budget_telecom_ratio", 0.5
        )
        telecom_budget = min(1.0, max(0.0, services.finite_number(observer_budget)))
        active_coverage = _espionage_cell_count(
            all_cells, owner_id, target_id, espionage_cell_counts, services
        )
        diminishing_coverage = 1.0 - (0.72 ** active_coverage)
        confidence *= 0.7 + 0.2 * telecom_budget + 0.1 * diminishing_coverage
        confidence = min(0.95, max(0.1, confidence))
        confidence_factors = {
            "observer_telecom": telecom_budget,
            "target_telecom": target_telecom,
            "intelligence_coverage": _coverage_band(active_coverage),
        }
    return _IntelligenceConfidence(confidence, target_telecom, confidence_factors)


def _espionage_cell_count(
    all_cells: Sequence[dict[str, Any]],
    owner_id: str,
    target_id: str,
    espionage_cell_counts: pl.DataFrame | None,
    services: MissionResolutionServices,
) -> int:
    if espionage_cell_counts is not None:
        return services.metric_count(
            espionage_cell_counts,
            country_id=owner_id,
            target_country_id=target_id,
        )
    return sum(
        1
        for row in all_cells
        if services.normalize_tag(row.get("country_id")) == owner_id
        and services.normalize_tag(row.get("target_country_id")) == target_id
        and str(row.get("assignment") or "") == "espionage"
        and str(row.get("status") or "") in {"active", "preparing"}
    )


def _coverage_band(active_coverage: int) -> str:
    if active_coverage == 0:
        return "none"
    if active_coverage == 1:
        return "limited"
    if active_coverage <= 3:
        return "sustained"
    return "dense"


def _intelligence_output(
    state: Any,
    mission: Mapping[str, Any],
    target: Mapping[str, Any],
    result: str,
    intelligence: _IntelligenceConfidence,
    population_by_country: pl.DataFrame | None,
    services: MissionResolutionServices,
) -> dict[str, Any]:
    if result not in {"success", "partial_success"}:
        return {}
    if "espionage" not in str(mission.get("mission_type")):
        return {}
    output = services.intelligence_snapshot(
        state,
        target,
        mission,
        intelligence.value,
        intelligence.factors,
        population_by_country,
    )
    if output:
        output["information_freshness"] = 0.5 + 0.5 * intelligence.target_telecom
    return output
