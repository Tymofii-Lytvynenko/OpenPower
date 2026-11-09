from __future__ import annotations

import polars as pl
import pytest

from modules.base.systems.military.strategic_warfare_system import (
    StrategicEventBuffer,
    StrategicUpdateIndexes,
    StrategicWarfareSystem,
)
from src.shared.actions import ActionLaunchStrategicStrike, ActionProduceStrategicWeapon
from tests.test_strategic_warfare_system import StrategicWarfareSystemTest


def _state():
    return StrategicWarfareSystemTest()._state()


def _launch_action(**changes) -> ActionLaunchStrategicStrike:
    values = {
        "player_id": "USA",
        "country_tag": "USA",
        "target_region_id": 2,
        "weapon_type": "icbm",
        "target_country_tag": "CAN",
        "payload_level": 1,
    }
    values.update(changes)
    player_id = values.pop("player_id")
    country_tag = values.pop("country_tag")
    target_region_id = values.pop("target_region_id")
    weapon_type = values.pop("weapon_type")
    return ActionLaunchStrategicStrike(player_id, country_tag, target_region_id, weapon_type, **values)


def _prepare_launch(state, action, orders=None):
    return StrategicWarfareSystem()._prepare_launch(
        state,
        state.get_table("strategic_weapons").to_dicts(),
        orders or [],
        action,
        state.get_table("countries").to_dicts(),
    )


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("missing_region", "target region does not exist"),
        ("invalid_country", "target country or region is invalid"),
        ("unauthorized", "cannot authorize this country's launch"),
        ("missing_weapon", "No matching strategic weapon"),
        ("unavailable_weapon", "destroyed, unavailable, or not ready"),
        ("pending_order", "already has a pending launch order"),
        ("invalid_mode", "target mode is unsupported"),
        ("invalid_object", "target object is not a military unit"),
        ("payload", "payload level exceeds"),
        ("origin_missing", "requested weapon origin region does not exist"),
        ("origin_unowned", "origin region is not controlled by its owner"),
        ("no_origin", "no valid origin region"),
        ("authorization", "Political launch authorization is missing"),
    ],
)
def test_launch_preparation_rejects_invalid_requests_without_creating_orders(case: str, reason: str) -> None:
    state = _state()
    action = _launch_action()
    orders = []
    weapons = state.get_table("strategic_weapons")

    if case == "missing_region":
        action = _launch_action(target_region_id=999)
    elif case == "invalid_country":
        action = _launch_action(target_country_tag="USA")
    elif case == "unauthorized":
        action = _launch_action(player_id="unauthorized-user")
    elif case == "missing_weapon":
        action = _launch_action(weapon_id="missing-design")
    elif case == "unavailable_weapon":
        state.update_table("strategic_weapons", weapons.with_columns(pl.lit(False).alias("operational")))
    elif case == "pending_order":
        orders = [{"status": "pending", "weapon_id": "usa-icbm"}]
    elif case == "invalid_mode":
        action = _launch_action(target_mode="economic")
    elif case == "invalid_object":
        action = _launch_action(target_object_id="missing-unit")
    elif case == "payload":
        action = _launch_action(payload_level=2)
    elif case == "origin_missing":
        action = _launch_action(origin_region_id=999)
        state.update_table("strategic_weapons", weapons.with_columns(pl.lit(0).alias("origin_region_id")))
    elif case == "origin_unowned":
        action = _launch_action(origin_region_id=2)
        state.update_table("strategic_weapons", weapons.with_columns(pl.lit(2).alias("origin_region_id")))
    elif case == "no_origin":
        state.update_table("strategic_weapons", weapons.with_columns(pl.lit(0).alias("origin_region_id")))
        state.update_table("regions", state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 1).then(pl.lit("MEX")).otherwise(pl.col("owner")).alias("owner"),
        ))
    elif case == "authorization":
        state.globals["strategic_authorization_policy"] = "explicit"
        state.update_table("countries_wars", state.get_table("countries_wars").head(0))

    order = _prepare_launch(state, action, orders)

    assert order is None
    assert reason in state.journal.command_results[-1]["reason"]


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unavailable", "production is unavailable"),
        ("unauthorized", "cannot authorize this country's production"),
        ("policy", "lacks policy authority"),
        ("missing_design", "No matching strategic weapon design"),
        ("research", "research are incomplete"),
        ("payload", "payload exceeds completed research"),
        ("quantity", "Production quantity must be"),
        ("configuration", "no configured production cost and duration"),
        ("funds", "cannot fund this order"),
    ],
)
def test_weapon_production_preparation_rejects_unavailable_or_unauthorized_orders(case: str, reason: str) -> None:
    state = _state()
    action = ActionProduceStrategicWeapon("USA", "USA", "usa-icbm", 1)
    weapons = state.get_table("strategic_weapons").to_dicts()
    countries = state.get_table("countries").to_dicts()

    if case == "unavailable":
        state.tables.pop("strategic_production_orders")
    elif case == "unauthorized":
        action = ActionProduceStrategicWeapon("unauthorized-user", "USA", "usa-icbm", 1)
    elif case == "policy":
        state.globals["strategic_production_authorized_countries"] = ["CAN"]
    elif case == "missing_design":
        action = ActionProduceStrategicWeapon("USA", "USA", "missing-design", 1)
    elif case == "research":
        state.globals["strategic_weapon_research_level"] = 2
    elif case == "payload":
        weapons[0]["payload_level"] = 2
    elif case == "quantity":
        action = ActionProduceStrategicWeapon("USA", "USA", "usa-icbm", 0)
    elif case == "configuration":
        weapons[0]["production_cost"] = 0.0
        weapons[0]["production_minutes"] = 0
    elif case == "funds":
        weapons[0]["production_cost"] = 25.0
        weapons[0]["production_minutes"] = 5
        countries[0]["money_reserves"] = 0.0

    order = StrategicWarfareSystem()._prepare_weapon_production(
        state, weapons, [], action, countries, 0,
    )

    assert order is None
    assert reason in state.journal.command_results[-1]["reason"]


def test_production_completion_cancels_invalid_orders_and_refunds_pending_cost() -> None:
    state = _state()
    countries = state.get_table("countries").to_dicts()
    weapons = state.get_table("strategic_weapons").to_dicts()
    orders = [
        {"id": "not-due", "country_id": "USA", "weapon_id": "usa-icbm", "quantity": 1, "status": "pending", "completes_at_minute": 20},
        {"id": "missing-design", "country_id": "USA", "weapon_id": "missing", "quantity": 1, "status": "pending", "completes_at_minute": 5, "cost_total": 12.0},
        {"id": "not-ready", "country_id": "USA", "weapon_id": "usa-icbm", "quantity": 1, "status": "readying", "ready_at_minute": 20},
        {"id": "lost-design", "country_id": "USA", "weapon_id": "missing", "quantity": 1, "status": "readying", "ready_at_minute": 5},
        {"id": "already-done", "country_id": "USA", "weapon_id": "usa-icbm", "quantity": 1, "status": "completed", "completes_at_minute": 1},
    ]

    changed = StrategicWarfareSystem()._complete_production_orders(state, weapons, orders, countries, 10)

    assert changed is True
    assert orders[0]["status"] == "pending"
    assert orders[1]["status"] == "cancelled"
    assert orders[2]["status"] == "readying"
    assert orders[3]["status"] == "cancelled"
    assert orders[4]["status"] == "completed"
    assert countries[0]["money_reserves"] == 112.0


def test_escalation_relations_update_existing_rows_and_add_the_reverse_pair() -> None:
    state = _state()
    state.tables["countries_relations"] = pl.DataFrame(
        {"source": ["USA"], "target": ["CAN"], "value": [97.0]},
    )

    StrategicWarfareSystem()._apply_escalation_relations(state, "USA", "CAN", "impact", True)

    relations = state.tables["countries_relations"].sort(["source", "target"]).to_dicts()
    assert relations == [
        {"source": "CAN", "target": "USA", "value": -10.0},
        {"source": "USA", "target": "CAN", "value": 87.0},
    ]


def test_transition_publication_handles_observers_and_missing_message_tables() -> None:
    state = _state()
    state.globals["strategic_observer_country_ids"] = ["CAN", "MEX", "USA"]
    pending = {
        "id": "strike-pending", "country_id": "USA", "target_country_id": "CAN", "target_region_id": 2,
        "status": "pending", "launch_detected": True, "launch_attributed": False,
    }
    system = StrategicWarfareSystem()

    system._publish_transition(state, pending)

    recipients = state.get_table("messages")["country_id"].to_list()
    assert recipients == ["USA", "CAN", "MEX"]
    assert "source is unknown" in state.get_table("messages")["body"][1]

    resolved = {**pending, "id": "strike-impact", "status": "impact", "reason": "Payload reached target."}
    system._publish_transition(state, resolved)
    recipients = state.get_table("messages")["country_id"].to_list()
    assert recipients[-2:] == ["USA", "CAN"]

    state.tables.pop("messages")
    event_count = len(state.events)
    system._publish_transition(state, pending)
    assert len(state.events) == event_count + 1

    state = _state()
    system._publish_transition(state, {
        "id": "strike-missing-owner", "country_id": "", "target_country_id": "CAN", "target_region_id": 2,
        "status": "impact", "reason": "Impact resolved.",
    })
    assert state.get_table("messages")["country_id"].to_list() == ["CAN"]


def test_event_buffer_initializes_message_batch_and_flushes_new_relation_columns() -> None:
    state = _state()
    StrategicEventBuffer(None, None).add_message(state, "USA", "pending", "No message table.")
    messages = state.get_table("messages")
    buffer = StrategicEventBuffer(messages, messages.schema, message_additions=None, relation_deltas={})
    buffer.add_message(state, "USA", "pending", "Launch notification.")
    assert buffer.message_additions is not None and len(buffer.message_additions) == 1

    state.tables["countries_relations"] = pl.DataFrame(schema={
        "source": pl.Utf8,
        "target": pl.Utf8,
        "value": pl.Float64,
        "relation_type": pl.Utf8,
    })
    buffer.add_escalation("USA", "CAN", "impact", True)
    buffer.flush(state)

    assert state.get_table("messages").height == 1
    relations = state.tables["countries_relations"].sort(["source", "target"]).to_dicts()
    assert len(relations) == 2
    assert all(row["value"] == -10.0 and row["relation_type"] is None for row in relations)


def test_supported_impact_effects_cover_country_aliases_population_and_collateral() -> None:
    state = _state()
    system = StrategicWarfareSystem()
    country = {"id": "CAN", "gdp": 1000.0, "economic_health": 0.9, "gvt_approval": 50.0}
    system._apply_supported_country_effects([country], {"target_country_id": "CAN"}, 0.5)
    assert country["gdp"] < 1000.0
    assert country["economic_health"] < 0.9
    assert country["gvt_approval"] < 50.0
    legacy = {"id": "CAN", "approval_rating": 50.0}
    system._apply_supported_country_effects([legacy], {"target_country_id": "CAN"}, 0.5)
    assert legacy["approval_rating"] < 50.0
    system._apply_supported_country_effects([], {"target_country_id": "CAN"}, 0.5)

    regions = state.get_table("regions").with_columns(
        pl.when(pl.col("id") == 1).then(pl.lit(0.0)).otherwise(pl.lit(0.01)).alias("longitude"),
        pl.lit(100.0).alias("infrastructure"),
        pl.lit(100.0).alias("communications"),
        pl.lit(100.0).alias("health_capacity"),
        pl.lit(1000.0).alias("population"),
        pl.lit(1000.0).alias("total_population"),
        pl.lit(1000).alias("pop_14"),
        pl.lit(1000).alias("pop_15_64"),
        pl.lit(1000).alias("pop_65"),
    )
    state.update_table("regions", regions)
    target = regions.filter(pl.col("id") == 2).row(0, named=True)
    impacts = []

    system._apply_supported_region_effects(
        state,
        target,
        {"id": "strike", "country_id": "USA", "target_country_id": "CAN", "target_mode": "civilian", "blast_radius_km": 20.0},
        0.6,
        impacts,
        5,
    )

    updated = state.get_table("regions").sort("id").to_dicts()
    assert updated[1]["population"] == 900.0
    assert updated[1]["total_population"] == 900.0
    assert updated[1]["migration_pressure"] > 0.0
    assert updated[1]["environment_health"] < 1.0
    assert updated[0]["infrastructure"] < 100.0
    assert impacts[0]["category"] == "collateral_infrastructure"

    system._apply_supported_region_effects(
        state,
        updated[1],
        {"id": "strike-no-collateral", "country_id": "USA", "target_country_id": "CAN", "target_mode": "military", "blast_radius_km": 0.0},
        0.6,
        [],
        6,
    )


def test_research_authorization_and_payload_helpers_handle_optional_tables() -> None:
    state = _state()
    system = StrategicWarfareSystem()
    weapon = {"max_payload_level": 3, "payload_level": 1}
    defense = {"researched": True, "country_id": "USA"}

    state.globals["strategic_research_gate_enabled"] = False
    assert system._research_permits(state, "USA", weapon) is True
    assert system._defense_is_researched(state, defense) is True
    state.globals["strategic_research_gate_enabled"] = True
    state.tables.pop("research_tracks")
    assert system._research_permits(state, "USA", weapon) is False
    assert system._defense_is_researched(state, defense) is False
    assert system._researched_payload_cap(state, "USA", weapon) == 3
    assert system._research_levels(state, "USA") == {}
    state.globals["strategic_payload_profiles"] = {"2": {"yield_kt": 250.0, "blast_radius_km": 20.0}}
    assert system._payload_profile(state, 2) == (250.0, 20.0)


def test_launch_authorization_accepts_explicit_paths_and_rejects_ended_wars() -> None:
    state = _state()
    system = StrategicWarfareSystem()

    state.globals["strategic_authorization_policy"] = "open"
    assert system._launch_authorized(state, "USA", "CAN", "") is True
    state.globals["strategic_authorization_policy"] = "war_or_explicit"
    state.globals["strategic_authorized_countries"] = [" usa "]
    assert system._launch_authorized(state, "USA", "CAN", "") is True
    state.globals["strategic_authorized_countries"] = []
    state.globals["strategic_authorization_contexts"] = ["cabinet-order"]
    assert system._launch_authorized(state, "USA", "CAN", "cabinet-order") is True
    state.globals["strategic_authorization_contexts"] = []
    state.globals["strategic_authorization_policy"] = "explicit"
    assert system._launch_authorized(state, "USA", "CAN", "unapproved") is False

    state.globals["strategic_authorization_policy"] = "war"
    state.tables.pop("countries_wars")
    assert system._launch_authorized(state, "USA", "CAN", "") is False

    state = _state()
    system = StrategicWarfareSystem()
    state.update_table("countries_wars", state.get_table("countries_wars").with_columns(
        pl.lit("ended").alias("status"),
    ))
    assert system._launch_authorized(state, "USA", "CAN", "") is False


def test_defense_maintenance_disables_layers_without_an_owner_or_funding() -> None:
    state = _state()
    state.globals["strategic_research_gate_enabled"] = False
    countries = state.get_table("countries").to_dicts()
    defenses = [
        {"country_id": "USA", "researched": False, "operational": True, "coverage_region_ids": [1], "maintenance_cost": 1.0},
        {"country_id": "MEX", "researched": True, "operational": True, "coverage_region_ids": [1], "maintenance_cost": 1.0},
        {"country_id": "USA", "researched": True, "operational": True, "coverage_region_ids": [1], "maintenance_cost": 1_000_000.0},
    ]

    StrategicWarfareSystem()._maintain_defenses(state, defenses, countries)

    assert [defense["operational"] for defense in defenses] == [True, False, False]


def test_region_indexes_and_fallback_lookups_choose_the_capital_and_handle_missing_tables() -> None:
    state = _state()
    regions = state.get_table("regions")
    rows = regions.to_dicts()
    capital = dict(rows[0])
    capital["id"] = 3
    rows.append(capital)
    state.update_table("regions", pl.DataFrame(rows, schema=regions.schema))
    governments = state.get_table("country_governments")
    state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "capital_region_id": 3,
    }], schema=governments.schema, strict=False))
    tracks = state.get_table("research_tracks")
    state.update_table("research_tracks", pl.concat([
        tracks,
        pl.DataFrame([{"id": "empty", "country_id": "", "branch": "", "research_level": 0}], schema=tracks.schema, strict=False),
    ]))

    indexes = StrategicUpdateIndexes.build(state)
    assert indexes.home_region_by_country["USA"]["id"] == 3
    assert indexes.regions_by_id[2]["owner"] == "CAN"
    assert StrategicWarfareSystem()._home_region(state, "USA")["id"] == 3
    assert StrategicWarfareSystem()._region_by_id(state, 2)["owner"] == "CAN"

    state.tables.pop("regions")
    assert StrategicWarfareSystem()._home_region(state, "USA") is None
    assert StrategicWarfareSystem()._region_by_id(state, 2) is None


def test_defense_coverage_uses_explicit_regions_when_a_center_is_unavailable_or_outside_radius() -> None:
    state = _state()
    system = StrategicWarfareSystem()
    target = state.get_table("regions").filter(pl.col("id") == 2).row(0, named=True)

    no_center = {
        "country_id": "MEX", "coverage_region_ids": [2], "center_latitude": None,
        "center_longitude": None, "range_km": 0.0, "coverage_radius_km": 0.0,
    }
    assert system._coverage_matches(state, no_center, target) is True
    outside_radius = {
        "country_id": "USA", "coverage_region_ids": [2], "center_latitude": 0.0,
        "center_longitude": 0.0, "range_km": 0.0, "coverage_radius_km": 10.0,
    }
    assert system._coverage_matches(state, outside_radius, target) is True


def test_system_guards_and_empty_defense_helpers_return_without_work() -> None:
    system = StrategicWarfareSystem()
    assert system.id == "base.strategic_warfare"
    assert system.dependencies == ["base.time", "base.diplomacy", "base.military_programs"]
    state = _state()
    state.tables.pop("strategic_impacts")
    system.update(state, 0.0)
    assert StrategicWarfareSystem._has_maintainable_defenses(pl.DataFrame()) is False
    assert StrategicWarfareSystem._has_maintainable_defenses(pl.DataFrame({"operational": [True]})) is False


def test_defense_resolution_skips_unconfigured_layers() -> None:
    state = _state()
    state.globals["strategic_research_gate_enabled"] = False
    region = state.get_table("regions").filter(pl.col("id") == 2).row(0, named=True)
    defense = {
        "id": "unknown-layer", "country_id": "CAN", "layer": "unconfigured",
        "researched": True, "operational": True, "readiness": 1.0, "coverage_region_ids": [2],
    }

    intercepted, results = StrategicWarfareSystem()._resolve_defense(
        state, {"id": "strike", "target_country_id": "CAN"}, region, [defense],
    )

    assert intercepted is False
    assert results == []


def test_unresearched_defense_layer_is_not_considered_researched() -> None:
    state = _state()

    assert StrategicWarfareSystem()._defense_is_researched(state, {"researched": False, "country_id": "CAN"}) is False
