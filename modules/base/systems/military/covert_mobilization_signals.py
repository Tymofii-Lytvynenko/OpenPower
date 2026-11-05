"""Build deterministic, privacy-preserving findings from readiness changes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.covert_mobilization import MobilizationFactors
from modules.base.systems.military.covert_policy import (
    SKILL_LEVELS,
    domestic_security_coverage,
)
from src.shared.events import EventUnitReadinessStarted
from src.shared.state import GameState


TagNormalizer = Callable[[Any], str]
FiniteNumber = Callable[[Any], float]
RegionalTelecomCapacity = Callable[[GameState, Mapping[str, Any], Mapping[str, Any]], float]
CountryPopulation = Callable[[GameState, str], float]

_READINESS_RANK = {"parked": 0, "ready": 1, "fortified": 2}


@dataclass(frozen=True, slots=True)
class _SignalContext:
    state: GameState
    cells: Sequence[Mapping[str, Any]]
    countries_by_id: Mapping[str, Mapping[str, Any]]
    units_by_id: Mapping[str, Mapping[str, Any]]
    designs_by_id: Mapping[str, Mapping[str, Any]]
    now: int
    normalize_tag: TagNormalizer
    finite_number: FiniteNumber
    regional_telecom_capacity: RegionalTelecomCapacity
    country_population: CountryPopulation


@dataclass(frozen=True, slots=True)
class _SignalRows:
    units_by_id: Mapping[str, Mapping[str, Any]]
    designs_by_id: Mapping[str, Mapping[str, Any]]
    existing_ids: set[str]


@dataclass(frozen=True, slots=True)
class _ResolvedObservation:
    unit: Mapping[str, Any]
    target_id: str
    target: Mapping[str, Any]
    best_observer: Mapping[str, Any]
    observer_id: str
    observer: Mapping[str, Any]
    observer_count: int


def mobilization_observers(
    cells: Sequence[Mapping[str, Any]],
    target_id: str,
    *,
    normalize_tag: TagNormalizer,
    finite_number: FiniteNumber,
) -> list[Mapping[str, Any]]:
    eligible = [
        cell
        for cell in cells
        if _is_eligible_observer(cell, target_id, normalize_tag)
    ]
    return sorted(eligible, key=lambda cell: _observer_priority(cell, finite_number))


def _is_eligible_observer(
    cell: Mapping[str, Any], target_id: str, normalize_tag: TagNormalizer
) -> bool:
    if normalize_tag(cell.get("country_id")) == target_id:
        return False
    if not _observes_target_in_place(cell, target_id, normalize_tag):
        return False
    return _is_connected_espionage_cell(cell)


def _observes_target_in_place(
    cell: Mapping[str, Any], target_id: str, normalize_tag: TagNormalizer
) -> bool:
    return (
        normalize_tag(cell.get("target_country_id")) == target_id
        and normalize_tag(cell.get("location_country_id")) == target_id
    )


def _is_connected_espionage_cell(cell: Mapping[str, Any]) -> bool:
    assignment = str(cell.get("assignment") or "").strip().lower()
    status = str(cell.get("status") or "").strip().lower()
    return (
        assignment == "espionage"
        and status in {"active", "idle", "preparing"}
        and bool(cell.get("communications_ready", True))
    )


def _observer_priority(
    cell: Mapping[str, Any], finite_number: FiniteNumber
) -> tuple[int, float, str]:
    skill_level = str(cell.get("skill_level") or "Recruit")
    skill_rank = SKILL_LEVELS.index(skill_level) if skill_level in SKILL_LEVELS else 0
    return (
        -skill_rank,
        -finite_number(cell.get("readiness")),
        str(cell.get("id") or ""),
    )


def record_mobilization_signals(
    state: GameState,
    cells: Sequence[Mapping[str, Any]],
    countries_by_id: Mapping[str, Mapping[str, Any]],
    findings: list[dict[str, Any]],
    now: int,
    *,
    normalize_tag: TagNormalizer,
    finite_number: FiniteNumber,
    regional_telecom_capacity: RegionalTelecomCapacity,
    country_population: CountryPopulation,
) -> None:
    readiness_events = _readiness_escalations(state.events)
    if not readiness_events:
        return

    rows = _signal_rows_for_events(state, readiness_events)
    if rows is None:
        return

    context = _SignalContext(
        state=state,
        cells=cells,
        countries_by_id=countries_by_id,
        units_by_id=rows.units_by_id,
        designs_by_id=rows.designs_by_id,
        now=now,
        normalize_tag=normalize_tag,
        finite_number=finite_number,
        regional_telecom_capacity=regional_telecom_capacity,
        country_population=country_population,
    )

    for event in readiness_events:
        finding = _finding_for_readiness_event(event, context, rows.existing_ids)
        if finding is None:
            continue
        findings.append(finding)
        rows.existing_ids.add(finding["id"])


def _signal_rows_for_events(
    state: GameState, events: Sequence[EventUnitReadinessStarted]
) -> _SignalRows | None:
    units_table = state.tables.get("units")
    if units_table is None or units_table.is_empty() or "id" not in units_table.columns:
        return None

    unit_ids = {str(event.unit_id or "") for event in events if str(event.unit_id or "")}
    units_by_id = _rows_by_id(units_table, unit_ids)
    if not units_by_id:
        return None

    design_ids = {
        str(row.get("design_id") or "")
        for row in units_by_id.values()
        if str(row.get("design_id") or "")
    }
    designs_by_id = _rows_by_id(state.tables.get("unit_designs"), design_ids)
    existing_ids = _mobilization_finding_ids(state.tables.get("covert_findings"))
    return _SignalRows(units_by_id, designs_by_id, existing_ids)


def _readiness_escalations(events: Sequence[Any]) -> list[EventUnitReadinessStarted]:
    return [
        event
        for event in events
        if _is_readiness_escalation(event)
    ]


def _is_readiness_escalation(event: Any) -> bool:
    if not isinstance(event, EventUnitReadinessStarted):
        return False
    from_rank = _READINESS_RANK.get(str(event.from_status or "").strip().lower(), -1)
    target_rank = _READINESS_RANK.get(str(event.target_status or "").strip().lower(), -1)
    return target_rank > from_rank


def _rows_by_id(table: pl.DataFrame | None, ids: set[str]) -> dict[str, dict[str, Any]]:
    if table is None or not ids:
        return {}
    if table.is_empty() or "id" not in table.columns:
        return {}

    matched_rows = table.filter(pl.col("id").cast(pl.Utf8).is_in(sorted(ids)))
    return {str(row.get("id") or ""): row for row in matched_rows.to_dicts()}


def _mobilization_finding_ids(table: pl.DataFrame | None) -> set[str]:
    if table is None or table.is_empty() or "id" not in table.columns:
        return set()

    return set(
        table.filter(pl.col("id").cast(pl.Utf8).str.starts_with("mobilization-"))
        .get_column("id")
        .cast(pl.Utf8)
        .to_list()
    )


def _finding_for_readiness_event(
    event: EventUnitReadinessStarted,
    context: _SignalContext,
    existing_ids: set[str],
) -> dict[str, Any] | None:
    observation = _resolve_observation(event, context)
    if observation is None:
        return None

    factors = _detection_factors(context, observation)
    deterministic_seed = _deterministic_seed(event, context, observation)
    if not _is_detected(deterministic_seed, factors):
        return None

    observation_id = _observation_id(deterministic_seed)
    if observation_id in existing_ids:
        return None

    return _finding_row(
        observation_id,
        event,
        context,
        observation,
        factors,
    )


def _resolve_observation(
    event: EventUnitReadinessStarted, context: _SignalContext
) -> _ResolvedObservation | None:
    unit = context.units_by_id.get(str(event.unit_id or ""))
    if unit is None:
        return None

    target_id = context.normalize_tag(unit.get("owner"))
    target = context.countries_by_id.get(target_id)
    if not target_id or target is None:
        return None

    observers = mobilization_observers(
        context.cells,
        target_id,
        normalize_tag=context.normalize_tag,
        finite_number=context.finite_number,
    )
    if not observers:
        return None

    best_observer = observers[0]
    observer_id = context.normalize_tag(best_observer.get("country_id"))
    observer = context.countries_by_id.get(observer_id)
    if observer is None:
        return None

    return _ResolvedObservation(
        unit, target_id, target, best_observer, observer_id, observer, len(observers)
    )


def _deterministic_seed(
    event: EventUnitReadinessStarted,
    context: _SignalContext,
    observation: _ResolvedObservation,
) -> str:
    identity = f"{event.transition_id}:{observation.observer_id}:{observation.target_id}"
    return f"{context.state.determinism.seed}:mobilization:{identity}"


def _is_detected(seed: str, factors: MobilizationFactors) -> bool:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    detection_roll = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
    return detection_roll < factors.detection_probability()


def _observation_id(seed: str) -> str:
    digest = hashlib.sha256(f"{seed}:finding".encode("utf-8")).hexdigest()
    return f"mobilization-{digest[:24]}"


def _detection_factors(
    context: _SignalContext,
    observation: _ResolvedObservation,
) -> MobilizationFactors:
    finite = context.finite_number
    observer_telecom = min(
        1.0, max(0.0, finite(observation.observer.get("budget_telecom_ratio", 0.5)))
    )
    target_telecom = context.regional_telecom_capacity(
        context.state, observation.best_observer, observation.target
    )
    target_security = min(
        0.7,
        max(
            0.0,
            finite(observation.target.get("security_upkeep"))
            / max(1.0, finite(observation.target.get("gdp")) * 0.02),
        ),
    )
    domestic_security_count = _domestic_security_count(
        context.cells, observation.target_id, context.normalize_tag
    )
    domestic_coverage = domestic_security_coverage(
        domestic_security_count,
        context.country_population(context.state, observation.target_id),
        context.state.globals,
    )
    observer_cell = observation.best_observer
    skill_index = SKILL_LEVELS.index(str(observer_cell.get("skill_level") or "Recruit"))
    return MobilizationFactors(
        skill_index=skill_index,
        readiness=min(1.0, max(0.0, finite(observer_cell.get("readiness")))),
        observer_telecom=observer_telecom,
        target_telecom=target_telecom,
        signal_coverage=1.0 - (0.72**observation.observer_count),
        target_security=target_security,
        domestic_coverage=domestic_coverage,
    )


def _domestic_security_count(
    cells: Sequence[Mapping[str, Any]],
    target_id: str,
    normalize_tag: TagNormalizer,
) -> int:
    return sum(
        1
        for cell in cells
        if _is_domestic_security_cell(cell, target_id, normalize_tag)
    )


def _is_domestic_security_cell(
    cell: Mapping[str, Any], target_id: str, normalize_tag: TagNormalizer
) -> bool:
    if normalize_tag(cell.get("country_id")) != target_id:
        return False
    if str(cell.get("assignment") or "") != "domestic_security":
        return False
    if str(cell.get("status") or "") != "active":
        return False
    return normalize_tag(cell.get("location_country_id")) == target_id


def _finding_row(
    observation_id: str,
    event: EventUnitReadinessStarted,
    context: _SignalContext,
    observation: _ResolvedObservation,
    factors: MobilizationFactors,
) -> dict[str, Any]:
    design = context.designs_by_id.get(str(observation.unit.get("design_id") or ""), {})
    domain = str(
        design.get("domain") or observation.unit.get("unit_domain") or "land"
    ).strip().lower()
    confidence_factors = {
        "observer_telecom": factors.observer_telecom,
        "target_telecom": factors.target_telecom,
        "intelligence_coverage": _coverage_label(observation.observer_count),
    }
    output = {
        "signal_type": "mobilization",
        "domain": domain,
        "from_readiness": str(event.from_status or "").strip().lower(),
        "to_readiness": str(event.target_status or "").strip().lower(),
        "confidence_factors": confidence_factors,
    }
    lifetime = min(
        365 * 24 * 60,
        max(
            24 * 60,
            int(context.finite_number(
                context.state.globals.get("covert_mobilization_signal_lifetime_minutes", 30 * 24 * 60)
            )),
        ),
    )
    return {
        "id": observation_id,
        "owner_country_id": observation.observer_id,
        "target_country_id": observation.target_id,
        "category": "military_mobilization",
        "value_json": json.dumps(output, sort_keys=True, separators=(",", ":")),
        "confidence": factors.confidence(),
        "freshness": 1.0,
        "discovered_at_minute": context.now,
        "expires_at_minute": context.now + lifetime,
    }


def _coverage_label(observer_count: int) -> str:
    if observer_count == 1:
        return "limited"
    if observer_count <= 3:
        return "sustained"
    return "dense"
