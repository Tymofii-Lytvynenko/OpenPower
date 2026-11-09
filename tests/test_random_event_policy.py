import math
from dataclasses import replace

import pytest

import modules.base.systems.world.random_event_policy as random_event_policy

from modules.base.systems.world.random_event_policy import (
    DEFAULT_CATEGORIES,
    EventDefinition,
    EventEffectDefinition,
    EventResponseDefinition,
    EVENT_BY_TYPE,
    EVENT_DEFINITIONS,
    clamp,
    effect_records,
    validate_catalog,
)


def test_catalog_has_stable_unique_types_and_enabled_categories() -> None:
    assert validate_catalog() == ()
    assert len(EVENT_DEFINITIONS) == 10
    assert set(DEFAULT_CATEGORIES) == {"disaster", "economic", "health"}
    assert len(EVENT_BY_TYPE) == len(EVENT_DEFINITIONS)


@pytest.mark.parametrize("value, expected", [(-1.0, 0.0), (0.4, 0.4), (2.0, 1.0)])
def test_clamp_bounds_severity(value: float, expected: float) -> None:
    assert clamp(value, 0.0, 1.0) == expected


def test_epidemic_effects_are_stable_explicit_and_bounded() -> None:
    definition = EVENT_BY_TYPE["epidemic"]
    rows = effect_records(
        event_id="event-42",
        definition=definition,
        severity=1.5,
        region_id=7,
        country_id="AAA",
        starts_at_minute=100,
        expires_at_minute=20_260,
    )

    assert [row["category"] for row in rows] == [
        "infrastructure_utilities",
        "infrastructure_telecom",
        "health",
        "labour",
        "migration",
        "approval",
    ]
    assert [row["id"] for row in rows] == [
        "event-42:region:7:infrastructure_utilities",
        "event-42:region:7:infrastructure_telecom",
        "event-42:region:7:health",
        "event-42:country:AAA:labour",
        "event-42:region:7:migration",
        "event-42:country:AAA:approval",
    ]
    assert rows[2]["magnitude"] == -0.08
    assert all(row["starts_at_minute"] == 100 for row in rows)
    assert all(row["expires_at_minute"] == 20_260 for row in rows)


def test_effect_subject_without_resolved_country_does_not_invent_one() -> None:
    rows = effect_records(
        event_id="event-1",
        definition=EVENT_BY_TYPE["strike"],
        severity=0.5,
        region_id=9,
        country_id="",
        starts_at_minute=0,
        expires_at_minute=4_320,
    )
    assert all(row["subject_type"] == "country" for row in rows)
    assert all(row["subject_id"] == "" for row in rows)


def _valid_definition() -> EventDefinition:
    return EventDefinition(
        event_type="sample",
        label="Sample",
        category="health",
        weight=1.0,
        duration_days=1,
        cooldown_days=0,
        severity_minimum=0.0,
        severity_maximum=1.0,
        eligible_scope="country",
        effects=(
            EventEffectDefinition(
                category="stability",
                subject_scope="country",
                magnitude_per_severity=0.1,
                minimum_magnitude=0.0,
                maximum_magnitude=1.0,
                unit="ratio",
                application_mode="immediate",
            ),
        ),
        responses=(
            EventResponseDefinition(
                response_id="relief",
                authority_scope="region_owner",
                cost=1.0,
                available_after_days=0,
                mitigation=0.5,
                risk=0.1,
                secondary_effects=(("stability", 0.1, "ratio"),),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("event_changes", "response_changes", "effect_changes", "expected_issue"),
    [
        ({"event_type": ""}, None, None, "duplicate or empty event type"),
        ({"duration_days": 0}, None, None, "invalid timing or weight"),
        ({"severity_maximum": 1.1}, None, None, "invalid severity bounds"),
        ({"eligible_scope": "planet"}, None, None, "invalid target scope"),
        (None, {"cost": -1.0}, None, "invalid response cost/timing"),
        (None, {"mitigation": 1.1}, None, "invalid response bounds"),
        (
            None,
            {"secondary_effects": (("stability", math.nan, "ratio"),)},
            None,
            "non-finite secondary effect",
        ),
        (None, None, {"minimum_magnitude": 2.0}, "invalid effect bounds"),
        (None, None, {"application_mode": "unknown"}, "invalid effect mode"),
    ],
)
def test_catalog_validation_reports_invalid_definition_edges(
    monkeypatch,
    event_changes: dict | None,
    response_changes: dict | None,
    effect_changes: dict | None,
    expected_issue: str,
) -> None:
    definition = _valid_definition()
    if response_changes:
        definition = replace(
            definition,
            responses=(replace(definition.responses[0], **response_changes),),
        )
    if effect_changes:
        definition = replace(
            definition,
            effects=(replace(definition.effects[0], **effect_changes),),
        )
    if event_changes:
        definition = replace(definition, **event_changes)
    monkeypatch.setattr(random_event_policy, "EVENT_DEFINITIONS", (definition,))

    issues = validate_catalog()

    assert any(expected_issue in issue for issue in issues)
