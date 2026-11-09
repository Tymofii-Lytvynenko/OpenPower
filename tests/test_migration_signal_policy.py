from modules.base.systems.demographics.migration_signal_policy import (
    DeterministicMigrationSignalCalculator,
)


def test_migration_signals_ignore_invalid_flows_regions_and_policy_values():
    calculator = DeterministicMigrationSignalCalculator()
    projection = calculator.calculate(
        current_records=[],
        country_ids=["aaa", "bbb"],
        region_records=[
            {"id": "r1", "owner": "AAA", "pop_15_64": 100, "service_capacity": 0},
            {"id": "unowned", "owner": "", "pop_15_64": 100, "service_capacity": 25},
        ],
        completed_flows=[
            {
                "origin_country_id": "AAA",
                "destination_country_id": "BBB",
                "population_count": 10,
                "working_age_count": 4,
            },
            {
                "origin_country_id": "AAA",
                "destination_country_id": "BBB",
                "population_count": -1,
                "working_age_count": 100,
            },
        ],
        policies={
            "AAA": {"enforcement_strength": "invalid"},
            "BBB": {"enforcement_strength": float("inf")},
        },
        health_effects={("region", "r1", "health"): -1.0},
        political_effects={("country", "AAA", "political_pressure"): 0.5},
        now=121,
        window_minutes=60,
    )

    rows = {row["country_id"]: row for row in projection.changed_records}
    assert rows["AAA"]["gross_outflow"] == 10
    assert rows["AAA"]["working_age_delta"] == -4
    assert rows["AAA"]["political_pressure"] == 1.0
    assert rows["AAA"]["law_pressure"] == 0.5
    assert rows["AAA"]["service_pressure"] == 0.5
    assert rows["BBB"]["gross_inflow"] == 10
    assert rows["BBB"]["working_age_delta"] == 4
    assert rows["BBB"]["law_pressure"] == 0.5
    assert rows["BBB"]["service_pressure"] == 1.0
    assert len(projection.events) == 2


def test_unchanged_migration_signal_projection_emits_no_duplicate_events():
    calculator = DeterministicMigrationSignalCalculator()
    inputs = {
        "country_ids": ["AAA"],
        "region_records": [
            {"id": "r1", "owner": "AAA", "pop_15_64": 100, "service_capacity": 10}
        ],
        "completed_flows": [],
        "policies": {"AAA": {"enforcement_strength": 0.5}},
        "health_effects": {},
        "political_effects": {},
        "now": 121,
        "window_minutes": 60,
    }
    first = calculator.calculate(current_records=[], **inputs)

    second = calculator.calculate(current_records=first.changed_records, **inputs)

    assert second.changed_records == ()
    assert second.events == ()
