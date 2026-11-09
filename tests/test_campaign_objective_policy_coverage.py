from __future__ import annotations

import polars as pl

from modules.base.systems.world.campaign_objective_policy import _rows, measure_objective
from src.shared.state import GameState


def _state(**tables: list[dict]) -> GameState:
    return GameState(tables={name: pl.DataFrame(rows) for name, rows in tables.items()})


def _measure(state: GameState, objective_type: str, **fields):
    return measure_objective(state, {"objective_type": objective_type, **fields})


def test_control_region_reports_missing_records_and_falls_back_to_owner() -> None:
    missing_table = _measure(GameState(), "control_region", actor_id="USA", target_id="1")
    no_target = _measure(
        _state(regions=[{"id": 1, "owner": "USA"}]),
        "control_region",
        actor_id="USA",
        target_id="",
    )
    missing_region = _measure(
        _state(regions=[{"id": 1, "owner": "USA"}]),
        "control_region",
        actor_id="USA",
        target_id="2",
    )
    owner_fallback = _measure(
        _state(regions=[{"id": 1, "owner": "USA"}]),
        "control_region",
        actor_id="USA",
        target_id="1",
        control_field="governor",
    )
    missing_owner = _measure(
        _state(regions=[{"id": 1}]),
        "control_region",
        actor_id="USA",
        target_id="1",
    )

    assert all(not result.available for result in (missing_table, no_target, missing_region, missing_owner))
    assert owner_fallback.available and owner_fallback.value == 1.0


def test_treaty_membership_accepts_delimited_members_and_handles_missing_records() -> None:
    state = _state(countries_treaties=[{
        "id": "pact",
        "members": "CAN; usa",
        "side_a": None,
        "side_b": None,
        "status": "active",
    }])

    membership = _measure(state, "treaty_membership", actor_id="USA", target_id="pact")
    missing_table = _measure(GameState(), "treaty_membership", actor_id="USA", target_id="pact")
    missing_treaty = _measure(state, "treaty_membership", actor_id="USA", target_id="unknown")

    assert membership.available and membership.value == 1.0
    assert not missing_table.available
    assert not missing_treaty.available


def test_resource_measurements_handle_empty_inputs_and_non_positive_totals() -> None:
    no_resource = _measure(GameState(), "resource_quantity", actor_id="USA")
    no_matching_resource = _measure(
        _state(domestic_production=[{
            "country_id": "CAN", "game_resource_id": "oil", "domestic_production": 5.0,
        }]),
        "resource_quantity",
        actor_id="USA",
        target_resource_id="oil",
    )
    no_share_source = _measure(
        _state(domestic_production=[]),
        "resource_share",
        actor_id="USA",
        target_resource_id="",
    )
    zero_world_production = _measure(
        _state(domestic_production=[{
            "country_id": "USA", "game_resource_id": "oil", "domestic_production": 0.0,
        }]),
        "resource_share",
        actor_id="USA",
        target_resource_id="oil",
    )

    assert not no_resource.available
    assert not no_matching_resource.available
    assert not no_share_source.available
    assert not zero_world_production.available


def test_gdp_per_capita_uses_explicit_and_region_derived_population() -> None:
    explicit = _measure(
        _state(countries=[{"id": "USA", "gdp_per_capita": 12.5}]),
        "gdp_per_capita",
        actor_id="USA",
    )
    regional_population = _measure(
        _state(
            countries=[{"id": "USA", "gdp": 350.0, "population": None}],
            regions=[{
                "id": 1, "owner": "USA", "pop_14": 10.0, "pop_15_64": 20.0, "pop_65": 5.0,
            }],
        ),
        "gdp_per_capita",
        actor_id="USA",
    )
    missing_country = _measure(
        _state(countries=[{"id": "CAN", "gdp": 100.0, "population": 10.0}]),
        "gdp_per_capita",
        actor_id="USA",
    )
    incomplete_source = _measure(
        _state(countries=[{"id": "USA", "gdp": None, "population": None}]),
        "gdp_per_capita",
        actor_id="USA",
    )

    assert explicit.available and explicit.value == 12.5
    assert regional_population.available and regional_population.value == 10.0
    assert not missing_country.available
    assert not incomplete_source.available


def test_population_and_development_report_missing_actor_and_derive_population() -> None:
    missing_actor_population = _measure(
        _state(countries=[{"id": "CAN", "population": 50.0}]),
        "population",
        actor_id="USA",
    )
    regional_population = _measure(
        _state(
            countries=[{"id": "USA", "population": None}],
            regions=[{
                "id": 1, "owner": "USA", "pop_14": 10.0, "pop_15_64": 20.0, "pop_65": 5.0,
            }],
        ),
        "population",
        actor_id="USA",
    )
    missing_actor_development = _measure(
        _state(countries=[{"id": "CAN", "human_dev": 0.7}]),
        "development",
        actor_id="USA",
    )

    assert not missing_actor_population.available
    assert regional_population.available and regional_population.value == 35.0
    assert not missing_actor_development.available


def test_conquest_measurement_handles_invalid_ids_and_control_field_gaps() -> None:
    unavailable_regions = _measure(
        GameState(), "conquer_country", actor_id="USA", target_id="CAN"
    )
    invalid_ids_use_owner_identity = _measure(
        _state(regions=[{"id": 1, "owner": "CAN"}]),
        "conquer_country",
        actor_id="USA",
        target_id="CAN",
        target_ids_json="{invalid",
    )
    explicit_ids = _measure(
        _state(regions=[{"id": 1, "owner": "USA", "controller": "USA"}]),
        "country_conquest",
        actor_id="USA",
        target_id="CAN",
        target_ids_json='["1"]',
    )
    no_target_regions = _measure(
        _state(regions=[{"id": 1, "owner": "USA"}]),
        "conquer_country",
        actor_id="USA",
        target_id="CAN",
    )
    missing_control_field = _measure(
        _state(regions=[{"id": 1, "owner": "CAN"}]),
        "conquer_country",
        actor_id="USA",
        target_id="CAN",
        control_field="controller",
    )

    assert not unavailable_regions.available
    assert invalid_ids_use_owner_identity.available and invalid_ids_use_owner_identity.value == 0.0
    assert explicit_ids.available and explicit_ids.value == 1.0
    assert not no_target_regions.available
    assert not missing_control_field.available


def test_weapon_and_research_measurements_report_unavailable_sources() -> None:
    missing_weapons = _measure(GameState(), "strategic_weapon_construction", actor_id="USA")
    missing_launches = _measure(GameState(), "strategic_weapon_use", actor_id="USA")
    missing_tracks = _measure(GameState(), "research_level", actor_id="USA")
    unmatched_track = _measure(
        _state(research_tracks=[{"country_id": "CAN", "branch": "strategic", "research_level": 1}]),
        "research_level",
        actor_id="USA",
    )
    unsupported = _measure(GameState(), "unrecognized_objective", actor_id="USA")

    assert not missing_weapons.available
    assert not missing_launches.available
    assert not missing_tracks.available
    assert not unmatched_track.available
    assert "unrecognized_objective" in unsupported.reason


def test_rows_reads_tables_without_a_measurement_context() -> None:
    state = _state(countries=[{"id": "USA"}])

    assert _rows(state, "countries") == [{"id": "USA"}]
    assert _rows(state, "regions") is None
