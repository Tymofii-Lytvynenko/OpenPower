"""Static random-event definitions and bounded policy helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EventEffectDefinition:
    category: str
    subject_scope: str
    magnitude_per_severity: float
    minimum_magnitude: float
    maximum_magnitude: float
    unit: str
    application_mode: str


@dataclass(frozen=True, slots=True)
class EventResponseDefinition:
    response_id: str
    authority_scope: str
    cost: float
    available_after_days: int
    mitigation: float
    risk: float
    secondary_effects: tuple[tuple[str, float, str], ...] = ()


@dataclass(frozen=True, slots=True)
class EventDefinition:
    event_type: str
    label: str
    category: str
    weight: float
    duration_days: int
    cooldown_days: int
    severity_minimum: float
    severity_maximum: float
    eligible_scope: str
    effects: tuple[EventEffectDefinition, ...]
    responses: tuple[EventResponseDefinition, ...]


def _infrastructure_effects(
    **factors: float,
) -> tuple[EventEffectDefinition, ...]:
    return tuple(
        EventEffectDefinition(
            f"infrastructure_{category}",
            "region",
            magnitude,
            0.0,
            min(1.0, magnitude * 1.5),
            "ratio",
            "immediate",
        )
        for category, magnitude in factors.items()
    )


def _disaster_effects(
    *,
    health: float,
    production: float,
    migration: float,
    approval: float,
    budget_pressure: float,
    **infrastructure: float,
) -> tuple[EventEffectDefinition, ...]:
    """Keep each disaster connected to its regional and national consequences."""
    return (
        *_infrastructure_effects(**infrastructure),
        EventEffectDefinition("health", "region", -health, -health * 1.5, 0.0, "index", "recurring"),
        EventEffectDefinition("production", "country", -production, -production * 1.5, 0.0, "ratio", "recurring"),
        EventEffectDefinition("migration", "region", migration, 0.0, migration * 1.5, "ratio", "recurring"),
        EventEffectDefinition("approval", "country", -approval, -approval * 1.5, 0.0, "index", "recurring"),
        EventEffectDefinition("budget_pressure", "country", budget_pressure, 0.0, budget_pressure * 1.5, "ratio", "recurring"),
    )


_DISASTER_RESPONSE = (
    EventResponseDefinition(
        "emergency_relief", "region_owner", 10_000.0, 0, 0.25, 0.02,
        (("approval", -0.02, "index"),),
    ),
)
_HEALTH_RESPONSE = (
    EventResponseDefinition(
        "public_health_response", "region_owner", 15_000.0, 0, 0.35, 0.04,
        (("labour", -0.02, "ratio"),),
    ),
)
_ECONOMIC_RESPONSE = (
    EventResponseDefinition(
        "stabilization_package", "region_owner", 12_500.0, 0, 0.30, 0.03,
        (("budget_pressure", 0.02, "ratio"),),
    ),
)


EVENT_DEFINITIONS: tuple[EventDefinition, ...] = (
    EventDefinition("earthquake", "🌍 Earthquake", "disaster", 1.0, 3, 45, 0.2, 1.0, "region", _disaster_effects(health=0.04, production=0.04, migration=0.03, approval=0.02, budget_pressure=0.03, transport=0.16, utilities=0.18, industrial=0.08, telecom=0.10), _DISASTER_RESPONSE),
    EventDefinition("flood", "🌊 Flood", "disaster", 1.2, 4, 30, 0.2, 1.0, "region", _disaster_effects(health=0.05, production=0.04, migration=0.04, approval=0.02, budget_pressure=0.04, transport=0.14, utilities=0.16, industrial=0.08), _DISASTER_RESPONSE),
    EventDefinition("wildfire", "🔥 Wildfire", "disaster", 1.0, 5, 30, 0.2, 1.0, "region", _disaster_effects(health=0.05, production=0.04, migration=0.03, approval=0.02, budget_pressure=0.03, utilities=0.10, industrial=0.14, telecom=0.05), _DISASTER_RESPONSE),
    EventDefinition("tornado", "🌪️ Tornado", "disaster", 0.8, 2, 30, 0.2, 1.0, "region", _disaster_effects(health=0.03, production=0.03, migration=0.02, approval=0.015, budget_pressure=0.025, transport=0.12, utilities=0.12, telecom=0.06), _DISASTER_RESPONSE),
    EventDefinition("volcanic_eruption", "🌋 Eruption", "disaster", 0.4, 7, 90, 0.2, 1.0, "region", _disaster_effects(health=0.06, production=0.05, migration=0.04, approval=0.025, budget_pressure=0.05, transport=0.12, utilities=0.14, industrial=0.10, telecom=0.10), _DISASTER_RESPONSE),
    EventDefinition("drought", "☀️ Drought", "disaster", 0.9, 10, 45, 0.2, 1.0, "region", _disaster_effects(health=0.03, production=0.06, migration=0.03, approval=0.02, budget_pressure=0.04, utilities=0.10, industrial=0.06), _DISASTER_RESPONSE),
    EventDefinition("epidemic", "🦠 Epidemic", "health", 0.6, 14, 90, 0.2, 1.0, "region", (
        *_infrastructure_effects(utilities=0.06, telecom=0.04),
        EventEffectDefinition("health", "region", -0.08, -0.10, 0.0, "index", "recurring"),
        EventEffectDefinition("labour", "country", -0.04, -0.05, 0.0, "ratio", "recurring"),
        EventEffectDefinition("migration", "region", 0.03, 0.0, 0.05, "ratio", "recurring"),
        EventEffectDefinition("approval", "country", -0.03, -0.05, 0.0, "index", "recurring"),
    ), _HEALTH_RESPONSE),
    EventDefinition("economic_boom", "📈 Economic Boom", "economic", 0.7, 7, 90, 0.2, 1.0, "region", (
        EventEffectDefinition("production", "country", 0.04, 0.0, 0.05, "ratio", "recurring"),
        EventEffectDefinition("employment", "country", 0.02, 0.0, 0.03, "ratio", "recurring"),
        EventEffectDefinition("demand", "country", 0.03, 0.0, 0.04, "ratio", "recurring"),
        EventEffectDefinition("approval", "country", 0.02, 0.0, 0.03, "index", "recurring"),
    ), _ECONOMIC_RESPONSE),
    EventDefinition("strike", "✊ Strike", "economic", 0.8, 3, 45, 0.2, 1.0, "region", (
        EventEffectDefinition("production", "country", -0.08, -0.10, 0.0, "ratio", "recurring"),
        EventEffectDefinition("employment", "country", -0.03, -0.04, 0.0, "ratio", "recurring"),
        EventEffectDefinition("demand", "country", -0.03, -0.04, 0.0, "ratio", "recurring"),
        EventEffectDefinition("approval", "country", -0.02, -0.04, 0.0, "index", "recurring"),
        EventEffectDefinition("political_pressure", "country", 0.04, 0.0, 0.05, "index", "recurring"),
    ), _ECONOMIC_RESPONSE),
    EventDefinition("tsunami", "🌊 Tsunami", "disaster", 0.3, 4, 90, 0.2, 1.0, "region", _disaster_effects(health=0.06, production=0.04, migration=0.04, approval=0.025, budget_pressure=0.05, transport=0.16, utilities=0.15, industrial=0.06, telecom=0.12), _DISASTER_RESPONSE),
)

EVENT_BY_TYPE = {definition.event_type: definition for definition in EVENT_DEFINITIONS}
EVENT_CATALOG: list[dict[str, Any]] = [
    {
        "type": definition.event_type,
        "label": definition.label,
        "weight": definition.weight,
        "duration_days": definition.duration_days,
    }
    for definition in EVENT_DEFINITIONS
]

DEFAULT_DAILY_CHANCE = 0.35
DEFAULT_MAX_ACTIVE_EVENTS = 5
MIN_FREQUENCY_MULTIPLIER = 0.0
MAX_FREQUENCY_MULTIPLIER = 4.0
MAX_ACTIVE_EVENTS_LIMIT = 100_000
MINUTES_PER_DAY = 1440
DEFAULT_CATEGORIES = tuple(sorted({definition.category for definition in EVENT_DEFINITIONS}))


def clamp(value: float, lower: float, upper: float) -> float:
    """Keep policy magnitudes inside their declared bounds."""
    return min(upper, max(lower, float(value)))


def validate_catalog() -> tuple[str, ...]:
    """Return catalog defects so startup and tests can reject invalid policy."""
    issues: list[str] = []
    seen: set[str] = set()
    for definition in EVENT_DEFINITIONS:
        if not definition.event_type or definition.event_type in seen:
            issues.append(f"duplicate or empty event type: {definition.event_type!r}")
        seen.add(definition.event_type)
        if not 0.0 <= definition.weight or definition.duration_days <= 0 or definition.cooldown_days < 0:
            issues.append(f"invalid timing or weight: {definition.event_type}")
        if not 0.0 <= definition.severity_minimum <= definition.severity_maximum <= 1.0:
            issues.append(f"invalid severity bounds: {definition.event_type}")
        if definition.eligible_scope not in {"region", "country", "global"}:
            issues.append(f"invalid target scope: {definition.event_type}")
        for response in definition.responses:
            if response.cost < 0.0 or response.available_after_days < 0:
                issues.append(f"invalid response cost/timing: {definition.event_type}/{response.response_id}")
            if not 0.0 <= response.mitigation <= 1.0 or not 0.0 <= response.risk <= 1.0:
                issues.append(f"invalid response bounds: {definition.event_type}/{response.response_id}")
            if any(not math.isfinite(magnitude) for _, magnitude, _ in response.secondary_effects):
                issues.append(f"non-finite secondary effect: {definition.event_type}/{response.response_id}")
        for effect in definition.effects:
            if effect.minimum_magnitude > effect.maximum_magnitude:
                issues.append(f"invalid effect bounds: {definition.event_type}/{effect.category}")
            if effect.application_mode not in {"immediate", "recurring", "recoverable"}:
                issues.append(f"invalid effect mode: {definition.event_type}/{effect.category}")
    return tuple(issues)


def effect_records(
    *,
    event_id: str,
    definition: EventDefinition,
    severity: float,
    region_id: int,
    country_id: str,
    starts_at_minute: int,
    expires_at_minute: int,
) -> list[dict[str, Any]]:
    """Materialize stable, bounded effect rows for an event instance."""
    bounded_severity = clamp(severity, 0.0, 1.0)
    rows: list[dict[str, Any]] = []
    for effect in definition.effects:
        subject_type = effect.subject_scope
        subject_id = (
            str(region_id) if subject_type == "region"
            else country_id if subject_type == "country"
            else "world"
        )
        magnitude = clamp(
            bounded_severity * effect.magnitude_per_severity,
            effect.minimum_magnitude,
            effect.maximum_magnitude,
        )
        rows.append(
            {
                "id": f"{event_id}:{subject_type}:{subject_id}:{effect.category}",
                "event_id": event_id,
                "category": effect.category,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "magnitude": magnitude,
                "unit": effect.unit,
                "application_mode": effect.application_mode,
                "starts_at_minute": max(0, int(starts_at_minute)),
                "expires_at_minute": max(0, int(expires_at_minute)),
                "last_applied_at_minute": 0,
                "status": "pending",
                "mitigation_pending": False,
                "recovery_state_json": "{}",
            }
        )
    return rows
