import pytest

from modules.base.systems.world.random_event_policy import (
    DEFAULT_CATEGORIES,
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
