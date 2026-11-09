from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.infrastructure_policy import (
    configured_category_policies,
)
from modules.base.systems.world.infrastructure_system import (
    EVENT_INFRASTRUCTURE_CATEGORIES,
    InfrastructureSystem,
)
from src.shared.actions import (
    ActionCancelInfrastructureProject,
    ActionInvestRegionalInfrastructure,
)
from src.shared.events import EventRandomEventTriggered
from src.shared.state import GameState
from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


def _prepared_state():
    state = build_infrastructure_state()
    ensure_base_tables(state)
    system = InfrastructureSystem()
    system.update(state, 0.0)
    policies = configured_category_policies(
        state.globals.get("infrastructure_category_policies")
    )
    return state, system, policies


def _event_effect(
    event_id: str,
    *,
    status: str = "pending",
    mitigation_pending: bool = False,
    subject_id: int = 101,
) -> dict[str, object]:
    category = next(
        name
        for name, infrastructure_category in EVENT_INFRASTRUCTURE_CATEGORIES.items()
        if infrastructure_category == "transport"
    )
    return {
        "id": "effect-1",
        "event_id": event_id,
        "category": category,
        "subject_type": "region",
        "subject_id": subject_id,
        "status": status,
        "starts_at_minute": 0,
        "expires_at_minute": 100,
        "magnitude": 0.4,
        "mitigation_pending": mitigation_pending,
        "last_applied_at_minute": 0,
    }


def test_infrastructure_guards_handle_missing_tables_and_incomplete_profiles() -> None:
    system = InfrastructureSystem()
    assert system.id == "base.infrastructure"
    assert system.dependencies == ["base.time", "base.bootstrap", "base.strategic_warfare"]
    system.update(GameState(), 0.0)
    assert InfrastructureSystem._region_rows(GameState()) == {}
    assert InfrastructureSystem._country_rows(GameState()) == {}
    assert InfrastructureSystem._project_regions_by_id(GameState(), [{"region_id": 1}]) == {}

    state, system, policies = _prepared_state()
    assert system._project_regions_by_id(state, []) == {}
    assert (
        InfrastructureSystem._has_complete_profile_coverage(
            pl.DataFrame({"region_id": [999] * len(policies), "category": list(policies)}),
            pl.DataFrame({"id": [101]}),
            policies,
        )
        is False
    )

    profile_rows = [{"region_id": 101, "category": "transport"}]
    state.tables.pop("regions")
    assert system._seed_profiles(state, profile_rows, policies, 0) is profile_rows
    system._materialize_read_models(state, profile_rows)

    state, system, policies = _prepared_state()
    state.tables["countries"] = pl.DataFrame({"id": ["USA"]})
    system._materialize_read_models_from_frames(
        state,
        state.get_table("regional_infrastructure"),
    )

    minimal_region_state, system, _ = _prepared_state()
    minimal_region_state.update_table(
        "regions",
        minimal_region_state.get_table("regions").select("id", "owner", "area_km2"),
    )
    system._materialize_read_models_from_frames(
        minimal_region_state,
        minimal_region_state.get_table("regional_infrastructure"),
    )
    assert "transport_access" in minimal_region_state.get_table("regions").columns


def test_due_infrastructure_event_effects_force_the_mutable_path() -> None:
    state = GameState()
    assert InfrastructureSystem._has_due_random_event_effects(state, 10) is False

    state.tables["random_event_effects"] = pl.DataFrame([_event_effect("event-1")])
    assert InfrastructureSystem._has_due_random_event_effects(state, 10) is True

    state.tables["random_event_effects"] = pl.DataFrame(
        [{**_event_effect("event-1"), "starts_at_minute": 20}]
    )
    assert InfrastructureSystem._has_due_random_event_effects(state, 10) is False


def test_frame_paths_skip_inactive_projects_and_fill_legacy_budget_columns() -> None:
    state, system, policies = _prepared_state()
    project_schema = state.get_table("infrastructure_projects").schema
    inactive_project = {column: None for column in project_schema}
    inactive_project.update(
        id="finished",
        country_id="USA",
        player_id="player-1",
        region_id=101,
        category="transport",
        status="completed",
    )
    state.update_table(
        "infrastructure_projects",
        pl.DataFrame([inactive_project], schema=project_schema, strict=False),
    )
    system._advance_projects_from_frames(state, 0, policies)

    system._advance_projects(
        state,
        [],
        [{**inactive_project, "status": "completed"}],
        [],
        1,
        policies,
    )

    state, system, policies = _prepared_state()
    state.globals["infrastructure_last_update_minute"] = 0
    system._depreciate_profiles_from_frames(state, policies, 60)
    system._materialize_read_models_from_frames(
        state,
        state.get_table("regional_infrastructure"),
    )

    state.update_table("countries", state.get_table("countries").head(0))
    system._materialize_read_models_from_frames(
        state,
        state.get_table("regional_infrastructure"),
    )


def test_project_helpers_pause_unresolvable_work_and_reject_invalid_actions() -> None:
    state, system, policies = _prepared_state()
    project = {
        "id": "missing-profile",
        "country_id": "USA",
        "player_id": "player-1",
        "region_id": 101,
        "category": "transport",
        "project_type": "upgrade",
        "status": "in_progress",
        "progress": 0.0,
        "started_at_minute": 0,
        "updated_at_minute": 0,
        "duration_minutes": 1,
    }
    system._advance_projects(state, [], [project], [], 1, policies)
    assert project["status"] == "paused"
    assert "profile is unavailable" in project["reason"]

    unknown_profile = {"region_id": 101, "category": "unknown"}
    InfrastructureSystem._normalize_profiles([unknown_profile], policies)
    repair_profile = {"level": 0.0, "condition": 0.0, "maximum": 1.0}
    InfrastructureSystem._complete_project(
        repair_profile,
        {"project_type": "repair", "target_level": 0.5},
    )
    assert repair_profile["condition"] == 0.0

    countries = InfrastructureSystem._country_rows(state)
    regions = InfrastructureSystem._region_rows(state)
    missing = ActionInvestRegionalInfrastructure(
        "player-1", "USA", 999, "transport", 0.8
    )
    system._invest(state, missing, {}, [], countries, regions, 0, policies)
    assert "unavailable" in state.journal.command_results[-1]["reason"]

    profile_rows = state.get_table("regional_infrastructure").to_dicts()
    profile_map = {
        (row["region_id"], row["category"]): row for row in profile_rows
    }
    excessive = ActionInvestRegionalInfrastructure(
        "player-1", "USA", 101, "transport", 999.0
    )
    system._invest(
        state,
        excessive,
        profile_map,
        [],
        countries,
        regions,
        0,
        policies,
    )
    assert "exceeds" in state.journal.command_results[-1]["reason"]

    damaged_profile = profile_map[(101, "transport")]
    damaged_profile["condition"] = 0.5
    damaged_profile["capacity"] = damaged_profile["level"] * 0.5
    invalid_repair = ActionInvestRegionalInfrastructure(
        "player-1", "USA", 101, "transport", damaged_profile["capacity"]
    )
    system._invest(
        state,
        invalid_repair,
        profile_map,
        [],
        countries,
        regions,
        0,
        policies,
    )
    assert "Repair target" in state.journal.command_results[-1]["reason"]

    projects = [
        {
            "id": "owned-project",
            "player_id": "player-1",
            "country_id": "USA",
            "status": "in_progress",
            "progress": 0.0,
            "cost_total": 100.0,
        }
    ]
    system._cancel(
        state,
        ActionCancelInfrastructureProject("other-player", "owned-project"),
        projects,
        countries,
        0,
    )
    system._cancel(
        state,
        ActionCancelInfrastructureProject("player-1", "missing-project"),
        projects,
        countries,
        0,
    )
    assert projects[0]["status"] == "in_progress"
    assert "missing or no longer cancellable" in state.journal.command_results[-1]["reason"]


def test_damage_pipeline_skips_invalid_sources_and_consumes_duplicate_effects() -> None:
    state, system, policies = _prepared_state()
    category = next(
        name
        for name, infrastructure_category in EVENT_INFRASTRUCTURE_CATEGORIES.items()
        if infrastructure_category == "transport"
    )
    state.tables["strategic_impacts"] = pl.DataFrame(
        [
            {"id": "outside", "region_id": 999, "category": "infrastructure", "severity": 0.5},
            {"id": "zero", "region_id": 101, "category": "infrastructure", "severity": 0.0},
        ]
    )
    profile = {
        "region_id": 101,
        "category": "transport",
        "level": 0.4,
        "maximum": 1.0,
        "condition": 0.8,
        "capacity": 0.32,
        "last_source_id": "strategic:impact-1:101:transport",
    }
    state.tables["strategic_impacts"] = pl.concat(
        [
            state.tables["strategic_impacts"],
            pl.DataFrame(
                [{"id": "impact-1", "region_id": 101, "category": "infrastructure", "severity": 0.5}]
            ),
        ]
    )
    _, records = system._apply_damage(state, [profile], [], 10, policies)
    assert records == []

    state = GameState(
        tables={"random_event_effects": pl.DataFrame([_event_effect("")])}
    )
    system._apply_damage(state, [], [], 10, policies)

    state = GameState(
        tables={"random_event_effects": pl.DataFrame([_event_effect("event-1")])}
    )
    system._apply_damage(state, [], [], 10, {})

    state = GameState(
        tables={
            "strategic_impacts": pl.DataFrame(
                [{"id": "impact-1", "region_id": 101, "category": "infrastructure", "severity": 0.5}]
            )
        }
    )
    system._apply_damage(state, [], [], 10, {})

    state = GameState()
    state.events.append(object())
    state.events.append(
        EventRandomEventTriggered("unknown-event", "unknown", 101, 0.5)
    )
    system._apply_damage(state, [], [], 10, policies)

    typed_profile = {
        "region_id": 101,
        "category": "transport",
        "level": 0.4,
        "maximum": 1.0,
        "condition": 0.8,
        "capacity": 0.32,
    }
    state = GameState(
        tables={
            "random_event_effects": pl.DataFrame([_event_effect("event-1")]),
            "random_event_instances": pl.DataFrame(
                [{"id": "event-1", "event_type": "earthquake"}]
            ),
        }
    )
    state.events.extend(
        [
            object(),
            EventRandomEventTriggered("event-1", "earthquake", 101, 0.5),
        ]
    )
    _, records = system._apply_damage(state, [typed_profile], [], 10, policies)
    assert len(records) == 1
    assert records[0]["id"] == "disaster:event-1:101:transport"
    assert state.tables["random_event_effects"]["status"][0] == "active"

    stable_id = "disaster:event-1:101:transport"
    state = GameState(
        tables={
            "random_event_effects": pl.DataFrame([_event_effect("event-1")]),
        }
    )
    existing_record = {
        "id": stable_id,
        "region_id": 101,
        "category": "transport",
        "severity": 0.4,
    }
    _, records = system._apply_damage(
        state,
        [
            {
                "region_id": 101,
                "category": "transport",
                "level": 0.4,
                "maximum": 1.0,
                "condition": 0.8,
                "capacity": 0.32,
            }
        ],
        [existing_record],
        10,
        policies,
    )
    assert records == [existing_record]
    assert state.tables["random_event_effects"]["status"][0] == "active"

    state = GameState(
        tables={
            "random_event_effects": pl.DataFrame(
                [_event_effect("", status="active", mitigation_pending=True)]
            )
        }
    )
    system._apply_damage(state, [], [], 10, policies)

    mitigation_profile = {
        "region_id": 101,
        "category": "transport",
        "level": 0.5,
        "maximum": 1.0,
        "condition": 0.6,
        "capacity": 0.3,
    }
    mitigation_effect = _event_effect(
        "event-1", status="active", mitigation_pending=True
    )
    mitigation_effect["magnitude"] = 0.1
    mitigation_record = {
        "id": stable_id,
        "region_id": 101,
        "category": "transport",
        "severity": 0.4,
    }
    state = GameState(
        tables={"random_event_effects": pl.DataFrame([mitigation_effect])}
    )
    _, records = system._apply_damage(
        state, [mitigation_profile], [mitigation_record], 10, policies
    )
    assert records[0]["severity"] == 0.1
    assert abs(mitigation_profile["condition"] - 0.9) < 1e-9
    assert state.tables["random_event_effects"]["mitigation_pending"][0] is False

    state = GameState(
        tables={
            "random_event_effects": pl.DataFrame(
                [
                    _event_effect(
                        "event-without-damage",
                        status="active",
                        mitigation_pending=True,
                        subject_id=999,
                    )
                ]
            )
        }
    )
    system._apply_damage(state, [], [], 10, policies)
    assert category in EVENT_INFRASTRUCTURE_CATEGORIES


def test_depreciation_read_models_and_numeric_helpers_cover_legacy_shapes() -> None:
    state, system, policies = _prepared_state()
    state.globals["infrastructure_last_update_minute"] = 0
    state.tables["countries"] = pl.DataFrame({"id": ["USA"]})
    system._depreciate_profiles_from_frames(state, policies, 60)

    state, system, policies = _prepared_state()
    state.globals["infrastructure_last_update_minute"] = 0
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.lit(1.0).alias("budget_infra_ratio")
        ),
    )
    profile = {
        "region_id": 101,
        "category": "transport",
        "level": 0.5,
        "maximum": 1.0,
        "condition": 0.8,
        "capacity": 0.4,
    }
    unknown_profile = {"region_id": 101, "category": "unknown", "condition": 0.5}
    system._apply_depreciation(
        state,
        [unknown_profile, profile],
        policies,
        365 * 24 * 60,
    )
    assert profile["condition"] == 0.8

    system._materialize_read_models(GameState(), [])
    empty_countries, _, _ = _prepared_state()
    empty_countries.update_table(
        "countries", empty_countries.get_table("countries").head(0)
    )
    system._materialize_read_models(empty_countries, [])

    state, system, _ = _prepared_state()
    system._materialize_read_models(
        state,
        [{"region_id": 999, "category": "transport", "capacity": 0.5}],
    )

    assert InfrastructureSystem._regional_weight({"pop_14": 10.0}) == 10.0
    weight = InfrastructureSystem._regional_weight_expression(
        pl.DataFrame({"pop_14": [10.0], "area_km2": [50.0]})
    )
    assert pl.DataFrame({"pop_14": [10.0], "area_km2": [50.0]}).select(
        weight.alias("weight")
    )["weight"][0] == 10.0
    cohort_regions = pl.DataFrame(
        {"pop_14": [10.0], "pop_15_64": [20.0], "pop_65": [5.0]}
    )
    cohort_weight = InfrastructureSystem._regional_weight_expression(cohort_regions)
    assert cohort_regions.select(cohort_weight.alias("weight"))["weight"][0] == 35.0
    assert InfrastructureSystem._regional_scale({"area_km2": 0.0}) == 1.0

    base_id = "infrastructure-USA-101-transport-5"
    assert InfrastructureSystem._next_project_id(
        [{"id": base_id}], "USA", 101, "transport", 5
    ) == f"{base_id}-001"

    empty = GameState()
    assert InfrastructureSystem._integer("invalid", 9) == 9
    InfrastructureSystem._write_rows(empty, "missing", [{"id": "unused"}])
    assert InfrastructureSystem._changed_row_ids(
        pl.DataFrame(schema={"id": pl.Int64}),
        pl.DataFrame(schema={"id": pl.Int64}),
        "id",
        ("capacity",),
    ).is_empty()
