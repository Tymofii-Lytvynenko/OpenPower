from __future__ import annotations

import json

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.campaign_system import CampaignSetupSystem, CampaignSystem
from modules.base.systems.world.campaign_objective_policy import measure_objective
from modules.base.systems.world.ai_system import AISystem
from src.shared.actions import ActionSetSphereDelegation, ActionStartCampaign
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["USA", "CAN"],
                    "name": ["United States", "Canada"],
                    "is_playable": [True, True],
                    "gdp": [1000.0, 500.0],
                    "population": [100.0, 50.0],
                    "money_reserves": [10.0, 20.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1, 2],
                    "original_owner": ["USA", "CAN"],
                    "owner": ["USA", "CAN"],
                    "controller": ["USA", "CAN"],
                    "pop_14": [10, 20],
                    "pop_15_64": [60, 30],
                    "pop_65": [10, 5],
                }
            ),
            "countries_treaties": pl.DataFrame(
                {"id": ["trade_union"], "members": [["USA", "CAN"]], "status": ["active"]}
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["USA", "CAN"],
                    "game_resource_id": ["oil", "oil"],
                    "domestic_production": [80.0, 20.0],
                }
            ),
            "research_tracks": pl.DataFrame(
                {
                    "id": ["USA-strategic"],
                    "country_id": ["USA"],
                    "branch": ["strategic"],
                    "progress": [0.8],
                    "research_level": [2],
                }
            ),
            "strategic_weapons": pl.DataFrame(
                {"id": ["usa-icbm"], "country_id": ["USA"], "weapon_type": ["missile"], "quantity": [2]}
            ),
            "strategic_launch_orders": pl.DataFrame(
                {"id": ["strike-1"], "country_id": ["USA"], "weapon_type": ["missile"], "status": ["resolved"]}
            ),
        }
    )
    registry = build_base_schema_registry()
    registry.capture_state(state)
    registry.ensure_state(state)
    state.globals["player_tag"] = "USA"
    state.globals["tick"] = 1
    return state


def _add_scenario(state: GameState, objectives: list[dict], setup: dict | None = None) -> None:
    table = state.tables["campaign_scenarios"]
    scenario = {
        "id": "test",
        "title": "Test Campaign",
        "description": "Scenario used by deterministic system tests.",
        "selectable_country_ids_json": '["USA"]',
        "political_scope": "country",
        "sphere_scope": "",
        "starting_setup_json": json.dumps(setup or {}),
        "enabled_rules_json": "{}",
        "objectives_json": json.dumps(objectives),
        "win_conditions_json": "{}",
        "loss_conditions_json": "{}",
        "max_duration_minutes": 0,
        "sandbox_allowed": True,
        "enabled": True,
    }
    state.update_table("campaign_scenarios", pl.DataFrame([scenario], schema=table.schema, strict=False))


def _start(system: CampaignSystem, state: GameState) -> None:
    state.current_actions = [ActionStartCampaign("local_admin", "test", "USA")]
    CampaignSetupSystem().update(state, 0.0)
    system.update(state, 0.0)
    state.current_actions = []


def test_scenario_setup_is_applied_once_and_authoritative_objective_can_win() -> None:
    state = _state()
    _add_scenario(
        state,
        [{
            "id": "oil-target",
            "title": "Secure oil production",
            "objective_type": "resource_quantity",
            "target_resource_id": "oil",
            "target_value": 75,
        }],
        {"updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": 42.0}}]},
    )
    system = CampaignSystem()

    _start(system, state)

    assert state.tables["countries"].filter(pl.col("id") == "USA")["money_reserves"][0] == 42.0
    assert state.tables["campaigns"][0, "setup_applied"] is True
    assert state.tables["campaigns"][0, "outcome"] == "victory"
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "")
    assert objective[0, "status"] == "completed"
    assert objective[0, "current_value"] == 80.0
    assert json.loads(objective[0, "evidence_json"])[-1]["source_table"] == "domestic_production"

    state.current_actions = [ActionStartCampaign("local_admin", "test", "USA")]
    CampaignSetupSystem().update(state, 0.0)
    system.update(state, 0.0)
    state.current_actions = []
    assert state.tables["countries"].filter(pl.col("id") == "USA")["money_reserves"][0] == 42.0
    assert state.tables["campaigns"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_region_control_hold_duration_requires_continuous_control() -> None:
    state = _state()
    _add_scenario(
        state,
        [{
            "id": "hold-region",
            "objective_type": "control_region",
            "target_id": "1",
            "hold_duration_minutes": 10,
        }],
    )
    system = CampaignSystem()
    _start(system, state)

    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "")
    assert objective[0, "status"] == "active"
    assert objective[0, "hold_started_at_minute"] == 0
    state.time.total_minutes = 5
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "")
    assert objective[0, "held_minutes"] == 5
    assert objective[0, "status"] == "active"

    state.update_table("regions", state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 1).then(pl.lit("CAN")).otherwise(pl.col("controller")).alias("controller")
    ))
    state.time.total_minutes = 8
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "")
    assert objective[0, "hold_started_at_minute"] == -1
    assert objective[0, "held_minutes"] == 0


def test_new_objective_is_pending_during_bootstrap_then_active_after_measurement() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "pending-oil", "objective_type": "resource_quantity",
        "target_resource_id": "oil", "target_value": 90,
    }])
    state.current_actions = [ActionStartCampaign("local_admin", "test", "USA")]
    CampaignSetupSystem().update(state, 0.0)
    assert state.tables["objectives"].filter(pl.col("campaign_id") != "")[0, "status"] == "pending"

    CampaignSystem().update(state, 0.0)
    assert state.tables["objectives"].filter(pl.col("campaign_id") != "")[0, "status"] == "active"


def test_region_control_decay_uses_only_preserved_hold_progress_after_control_returns() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "decaying-hold", "objective_type": "control_region", "target_id": "1",
        "hold_duration_minutes": 10, "progress_rule": "decay",
    }])
    system = CampaignSystem()
    _start(system, state)
    state.time.total_minutes = 5
    system.update(state, 0.0)

    state.update_table("regions", state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 1).then(pl.lit("CAN")).otherwise(pl.col("controller")).alias("controller")
    ))
    state.time.total_minutes = 8
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["held_minutes"] == 2
    assert objective["progress"] == 0.2
    assert objective["hold_started_at_minute"] == -1

    state.update_table("regions", state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 1).then(pl.lit("USA")).otherwise(pl.col("controller")).alias("controller")
    ))
    state.time.total_minutes = 9
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["held_minutes"] == 2
    assert objective["progress"] == 0.2
    assert objective["status"] == "active"

    state.time.total_minutes = 17
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["status"] == "completed"
    assert objective["held_minutes"] == 10


def test_two_objectives_using_the_same_source_transition_independently() -> None:
    state = _state()
    _add_scenario(state, [
        {"id": "lower-oil", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 70},
        {"id": "higher-oil", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 90},
    ])

    _start(CampaignSystem(), state)

    objectives = state.tables["objectives"].filter(pl.col("campaign_id") != "").to_dicts()
    by_title = {row["title"]: row for row in objectives}
    assert (by_title["lower-oil"]["current_value"], by_title["lower-oil"]["status"]) == (80.0, "completed")
    assert (by_title["higher-oil"]["current_value"], by_title["higher-oil"]["status"]) == (80.0, "active")
    assert all(json.loads(row["evidence_json"])[-1]["source_table"] == "domestic_production" for row in objectives)


def test_legacy_objective_without_campaign_starts_from_authoritative_state() -> None:
    state = _state()
    table = state.tables["objectives"]
    legacy = CampaignSystem._defaults_for("objectives")
    legacy.update({
        "id": "legacy-oil", "country_id": "USA", "title": "Maintain oil production",
        "status": "pending", "objective_type": "resource_quantity", "actor_id": "USA",
        "target_resource_id": "oil", "target_value": 75.0,
    })
    state.update_table("objectives", pl.DataFrame(
        [legacy], schema=table.schema, strict=False,
    ))

    CampaignSystem().update(state, 0.0)

    objective = state.tables["objectives"].row(0, named=True)
    assert objective["campaign_id"] == ""
    assert objective["status"] == "completed"
    assert objective["current_value"] == 80.0
    assert json.loads(objective["evidence_json"])[-1]["source_table"] == "domestic_production"


def test_changing_current_player_country_does_not_move_campaign_objective_actor() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "keep-oil", "objective_type": "resource_quantity",
        "target_resource_id": "oil", "target_value": 100,
    }])
    system = CampaignSystem()
    _start(system, state)
    state.globals["player_tag"] = "CAN"
    state.time.total_minutes = 1
    state.update_table("domestic_production", state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA").then(pl.lit(100.0))
        .otherwise(pl.col("domestic_production")).alias("domestic_production")
    ))

    system.update(state, 0.0)

    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["actor_id"] == "USA"
    assert objective["country_id"] == "USA"
    assert objective["status"] == "completed"


def test_missing_authoritative_data_blocks_objective_and_surfaces_advisor_recommendation() -> None:
    state = _state()
    _add_scenario(
        state,
        [{
            "id": "rare-resource",
            "objective_type": "resource_quantity",
            "target_resource_id": "lithium",
            "target_value": 1,
        }],
    )
    _start(CampaignSystem(), state)

    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "")
    assert objective[0, "status"] == "blocked"
    assert "No authoritative production record" in objective[0, "missing_data_reason"]
    assert state.tables["advisor_recommendations"].height == 1
    recommendation = state.tables["advisor_recommendations"].row(0, named=True)
    assert recommendation["urgency"] > 0.9
    assert recommendation["optional_action_json"] == ""


def test_malformed_setup_json_is_rejected_without_starting_campaign() -> None:
    state = _state()
    _add_scenario(state, [])
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit("{invalid").alias("starting_setup_json")
    ))

    _start(CampaignSystem(), state)

    assert state.tables["campaigns"].is_empty()
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_unsupported_setup_is_rejected_without_partial_state_changes() -> None:
    state = _state()
    _add_scenario(
        state,
        [],
        {"updates": [{"table": "countries", "key": "USA", "values": {"population": 1.0}}]},
    )
    before = state.tables["countries"].filter(pl.col("id") == "USA")["money_reserves"][0]
    _start(CampaignSystem(), state)

    assert state.tables["campaigns"].is_empty()
    assert state.tables["countries"].filter(pl.col("id") == "USA")["money_reserves"][0] == before
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_invalid_typed_setup_is_rejected_before_any_table_is_changed() -> None:
    state = _state()
    _add_scenario(
        state,
        [],
        {"updates": [
            {"table": "countries", "key": "USA", "values": {"money_reserves": 42.0}},
            {"table": "countries", "key": "USA", "values": {"gdp": "not-a-number"}},
        ]},
    )

    _start(CampaignSystem(), state)

    usa = state.tables["countries"].filter(pl.col("id") == "USA").row(0, named=True)
    assert state.tables["campaigns"].is_empty()
    assert usa["money_reserves"] == 10.0
    assert usa["gdp"] == 1000.0
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_scenario_setup_can_initialize_ruling_party_and_treaty_sphere() -> None:
    state = _state()
    parties = state.tables["political_parties"]
    state.update_table("political_parties", pl.DataFrame([{
        "country_id": "USA", "party_id": "party-a", "display_name": "Party A", "is_ruling": True,
    }], schema=parties.schema, strict=False))
    governments = state.tables["country_governments"]
    state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "ruling_party_id": "", "initialized": True,
    }], schema=governments.schema, strict=False))
    state.update_table("countries_relations", pl.DataFrame([{
        "source": "USA", "target": "CAN", "value": 0.0,
    }]))
    _add_scenario(
        state,
        [],
        {"updates": [
            {"table": "country_governments", "key": "USA", "values": {"ruling_party_id": "party-a"}},
            {"table": "countries_relations", "key": {"source": "USA", "target": "CAN"}, "values": {"value": 45.0}},
            {"table": "research_tracks", "key": "USA-strategic", "values": {"research_level": 3}},
            {"table": "strategic_weapons", "key": "usa-icbm", "values": {"quantity": 3}},
            {"table": "countries_treaties", "key": "trade_union", "values": {"members": ["USA", "CAN"]}},
        ]},
    )
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit("sphere").alias("political_scope"),
        pl.lit("trade_union").alias("sphere_scope"),
    ))

    _start(CampaignSystem(), state)

    assert state.tables["country_governments"].filter(pl.col("country_id") == "USA")["ruling_party_id"][0] == "party-a"
    assert state.tables["countries_relations"][0, "value"] == 45.0
    assert state.tables["research_tracks"].filter(pl.col("id") == "USA-strategic")[0, "research_level"] == 3
    assert state.tables["strategic_weapons"].filter(pl.col("id") == "usa-icbm")[0, "quantity"] == 3
    treaty_members = state.tables["countries_treaties"].filter(pl.col("id") == "trade_union")["members"].to_list()[0]
    assert treaty_members == ["USA", "CAN"]
    assert state.tables["campaigns"][0, "actor_scope"] == "sphere"
    assert state.journal.command_results[-1]["status"] == "applied"


def test_scenario_allowlist_rejects_existing_but_unselectable_actor() -> None:
    state = _state()
    _add_scenario(state, [])
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit('["USA"]').alias("selectable_country_ids_json")
    ))
    state.globals["player_tag"] = "CAN"
    state.current_actions = [ActionStartCampaign("local_admin", "test", "CAN")]

    CampaignSetupSystem().update(state, 0.0)

    assert state.tables["campaigns"].is_empty()
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "not available" in state.journal.command_results[-1]["reason"].lower()


def test_party_and_sphere_campaign_scopes_require_valid_current_membership() -> None:
    party_state = _state()
    _add_scenario(party_state, [])
    party_state.update_table("campaign_scenarios", party_state.tables["campaign_scenarios"].with_columns(
        pl.lit("party").alias("political_scope")
    ))
    party_state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "ruling_party_id": "missing-party", "initialized": True,
    }], schema=party_state.tables["country_governments"].schema, strict=False))
    _start(CampaignSystem(), party_state)
    assert party_state.tables["campaigns"].is_empty()
    assert party_state.journal.command_results[-1]["status"] == "rejected"

    sphere_state = _state()
    _add_scenario(sphere_state, [])
    sphere_state.update_table("campaign_scenarios", sphere_state.tables["campaign_scenarios"].with_columns(
        pl.lit("sphere").alias("political_scope"), pl.lit("trade_union").alias("sphere_scope")
    ))
    sphere_state.update_table("countries_treaties", sphere_state.tables["countries_treaties"].with_columns(
        pl.lit(["CAN"]).alias("members")
    ))
    _start(CampaignSystem(), sphere_state)
    assert sphere_state.tables["campaigns"].is_empty()
    assert sphere_state.journal.command_results[-1]["status"] == "rejected"


def test_delegation_is_scoped_and_return_to_player_is_persisted() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    assert state.tables["campaigns"][0, "outcome"] == "sandbox"

    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["stability"]
    )]
    CampaignSetupSystem().update(state, 0.0)
    system.update(state, 0.0)
    delegated = state.tables["sphere_delegations"].row(0, named=True)
    assert delegated["active"] is True
    assert delegated["current_controller"] == "ai"
    assert json.loads(delegated["authority_json"]) == ["economy"]
    assert state.tables["regions"][0, "owner"] == "USA"

    before_invalid = state.tables["sphere_delegations"].to_dicts()
    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["stability"],
        return_condition="unsupported",
    )]
    CampaignSetupSystem().update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.tables["sphere_delegations"].to_dicts() == before_invalid

    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["stability"],
    )]
    CampaignSetupSystem().update(state, 0.0)
    assert state.tables["sphere_delegations"].height == 1

    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["stability"], active=False
    )]
    CampaignSetupSystem().update(state, 0.0)
    system.update(state, 0.0)
    returned = state.tables["sphere_delegations"].row(0, named=True)
    assert returned["active"] is False
    assert returned["current_controller"] == "human"


def test_party_delegation_activates_only_for_the_ruling_party_and_political_domain() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    parties = state.tables["political_parties"]
    state.update_table("political_parties", pl.DataFrame([{
        "country_id": "USA", "party_id": "party-a", "display_name": "Party A", "is_ruling": True,
    }], schema=parties.schema, strict=False))
    governments = state.tables["country_governments"]
    state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "ruling_party_id": "party-a", "initialized": True,
    }], schema=governments.schema, strict=False))
    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "party", "party-a", "ai", ["politics"], ["elections"]
    )]
    CampaignSetupSystem().update(state, 0.0)

    domains, targets, treaties = AISystem._delegation_context(state)
    assert domains["USA"] == frozenset({"politics"})
    assert targets == {} and treaties == {}
    assert state.journal.command_results[-1]["status"] == "applied"

    state.update_table("country_governments", state.tables["country_governments"].with_columns(
        pl.lit("party-b").alias("ruling_party_id")
    ))
    assert AISystem._delegation_context(state)[0] == {}


def test_sphere_delegation_is_limited_to_an_active_treaty_membership() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "sphere", "trade_union", "ai", ["diplomacy"], ["alliance"]
    )]
    CampaignSetupSystem().update(state, 0.0)

    domains, targets, treaty_ids = AISystem._delegation_context(state)
    assert domains["USA"] == frozenset({"diplomacy"})
    assert targets["USA"] == frozenset({"CAN"})
    assert treaty_ids["USA"] == frozenset({"trade_union"})

    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "sphere", "trade_union", "ai", ["economy"], ["alliance"]
    )]
    CampaignSetupSystem().update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_advisor_consumes_unread_messages_and_authoritative_system_signals() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    for table_name, rows in (
        ("political_crises", [{"id": "crisis-1", "country_id": "USA", "status": "active", "reason": "Coalition confidence fell."}]),
        ("messages", [{"id": "message-1", "country_id": "USA", "category": "war", "subject": "Peace offer", "body": "Review response", "is_read": False}]),
        ("debt_distress_cases", [{"id": "debt-1", "country_id": "USA", "status": "arrears", "trigger": "missed payment", "reason": "Payment is overdue."}]),
        ("migration_signals", [{"country_id": "USA", "political_pressure": 0.8, "service_pressure": 0.2, "law_pressure": 0.1, "window_start_minute": 0}]),
        ("infrastructure_damage_records", [{"id": "damage-1", "region_id": 1, "category": "transport", "severity": 0.7, "recovered": False}]),
    ):
        table = state.tables[table_name]
        state.update_table(table_name, pl.DataFrame(rows, schema=table.schema, strict=False))

    system.update(state, 0.0)

    signals = {row["source_signal"] for row in state.tables["advisor_recommendations"].to_dicts()}
    assert any(signal.startswith("message:message-1") for signal in signals)
    assert any(signal.startswith("political_crisis:crisis-1") for signal in signals)
    assert any(signal.startswith("debt_distress:debt-1") for signal in signals)
    assert any(signal.startswith("migration_pressure:USA") for signal in signals)
    assert any(signal.startswith("infrastructure_damage:damage-1") for signal in signals)


def test_measurements_cover_every_campaign_objective_type_and_source() -> None:
    state = _state()
    state.update_table("regions", state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 2).then(pl.lit("USA")).otherwise(pl.col("controller")).alias("controller")
    ))
    state.update_table("countries", state.tables["countries"].with_columns(
        pl.Series("human_dev", [0.8, 0.7]),
    ))
    cases = [
        ({"objective_type": "control_region", "actor_id": "USA", "target_id": "1"}, 1.0, "regions"),
        ({"objective_type": "conquer_country", "actor_id": "USA", "target_id": "CAN"}, 1.0, "regions"),
        ({"objective_type": "treaty_membership", "actor_id": "USA", "target_id": "trade_union"}, 1.0),
        ({"objective_type": "resource_quantity", "actor_id": "USA", "target_resource_id": "oil"}, 80.0, "domestic_production"),
        ({"objective_type": "gdp_per_capita", "actor_id": "USA"}, 10.0, "countries"),
        ({"objective_type": "research_level", "actor_id": "USA", "target_branch": "strategic"}, 2.0, "research_tracks"),
        ({"objective_type": "strategic_weapon_construction", "actor_id": "USA", "target_id": "missile"}, 2.0, "strategic_weapons"),
        ({"objective_type": "strategic_weapon_use", "actor_id": "USA", "target_id": "missile"}, 1.0, "strategic_launch_orders"),
        ({"objective_type": "resource_share", "actor_id": "USA", "target_resource_id": "oil"}, 0.8, "domestic_production"),
        ({"objective_type": "population_threshold", "actor_id": "USA"}, 100.0, "countries"),
        ({"objective_type": "development_threshold", "actor_id": "USA"}, 0.8, "countries"),
    ]
    for case in cases:
        objective, expected, *source = case
        measurement = measure_objective(state, objective)
        assert measurement.available
        assert measurement.value == expected
        if source:
            assert measurement.source_table == source[0]

    regional_state = _state()
    regional_state.tables.pop("domestic_production")
    regional_state.update_table("regional_production", pl.DataFrame({
        "country_id": ["USA"], "game_resource_id": ["oil"], "domestic_production": [55.0],
    }))
    regional_measurement = measure_objective(regional_state, {
        "objective_type": "resource_quantity", "actor_id": "USA", "target_resource_id": "oil",
    })
    assert regional_measurement.available
    assert regional_measurement.value == 55.0
    assert regional_measurement.source_table == "regional_production"


def test_treaty_membership_ends_with_inactive_treaty_and_population_missing_is_blocked() -> None:
    state = _state()
    state.update_table("countries_treaties", state.tables["countries_treaties"].with_columns(
        pl.lit("dissolved").alias("status")
    ))
    treaty = measure_objective(state, {
        "objective_type": "treaty_membership", "actor_id": "USA", "target_id": "trade_union",
    })
    assert treaty.available and treaty.value == 0.0

    missing_population = GameState(tables={"countries": pl.DataFrame({"id": ["USA"]})})
    population = measure_objective(missing_population, {
        "objective_type": "population_threshold", "actor_id": "USA",
    })
    development = measure_objective(missing_population, {
        "objective_type": "development_threshold", "actor_id": "USA",
    })
    assert not population.available and "population" in population.reason.lower()
    assert not development.available and "development" in development.reason.lower()


def test_failure_conditions_and_exact_deadline_transitions_are_deterministic() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "deadline-objective",
        "objective_type": "resource_quantity",
        "target_resource_id": "oil",
        "target_value": 90,
        "deadline_minutes": 5,
    }])
    system = CampaignSystem()
    _start(system, state)
    state.time.total_minutes = 5
    state.update_table("domestic_production", state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA").then(pl.lit(90.0))
        .otherwise(pl.col("domestic_production")).alias("domestic_production")
    ))
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["status"] == "completed"
    assert objective["remaining"] == 0.0
    assert json.loads(objective["evidence_json"])[-1]["status"] == "completed"

    failed_state = _state()
    _add_scenario(failed_state, [{
        "id": "avoid-economic-threshold",
        "objective_type": "resource_quantity",
        "target_resource_id": "oil",
        "target_value": 100,
        "failure_conditions": [{
            "objective_type": "gdp_per_capita", "target_value": 10, "comparison": "at_least",
        }],
    }])
    failed_system = CampaignSystem()
    _start(failed_system, failed_state)
    objective = failed_state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["status"] == "failed"
    assert "failure condition" in objective["reason"].lower()
    assert failed_state.tables["campaigns"][0, "outcome"] == "defeat"


def test_unmet_objective_expires_after_its_deadline_and_records_the_transition() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "missed-deadline", "objective_type": "resource_quantity",
        "target_resource_id": "oil", "target_value": 100, "deadline_minutes": 5,
    }])
    system = CampaignSystem()
    _start(system, state)
    state.time.total_minutes = 5
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["status"] == "active"

    state.time.total_minutes = 6
    system.update(state, 0.0)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert objective["status"] == "expired"
    assert "deadline" in objective["reason"].lower()
    assert json.loads(objective["evidence_json"])[-1]["status"] == "expired"


def test_terminal_non_sandbox_cancels_optional_goals_but_sandbox_keeps_advisor_active() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "optional-goal", "objective_type": "resource_quantity",
        "target_resource_id": "oil", "target_value": 500, "required": False,
    }])
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit('{"conditions":[{"objective_type":"gdp_per_capita","target_value":9.0}]}').alias("win_conditions_json"),
        pl.lit(False).alias("sandbox_allowed"),
    ))
    _start(CampaignSystem(), state)
    objective = state.tables["objectives"].filter(pl.col("campaign_id") != "").row(0, named=True)
    assert state.tables["campaigns"][0, "outcome"] == "victory"
    assert objective["status"] == "cancelled"
    assert json.loads(objective["evidence_json"])[-1]["status"] == "cancelled"

    sandbox_state = _state()
    _add_scenario(sandbox_state, [])
    sandbox_state.update_table("campaign_scenarios", sandbox_state.tables["campaign_scenarios"].with_columns(
        pl.lit('{"conditions":[{"objective_type":"gdp_per_capita","target_value":9.0}]}').alias("win_conditions_json"),
        pl.lit(True).alias("sandbox_allowed"),
    ))
    system = CampaignSystem()
    _start(system, sandbox_state)
    news = sandbox_state.tables["news_items"]
    sandbox_state.update_table("news_items", pl.DataFrame([{
        "id": "post-victory-news", "category": "opportunity", "severity": "info",
        "headline": "New opportunity", "body": "A new opportunity is available.",
        "related_country_id": "USA",
    }], schema=news.schema, strict=False))
    system.update(sandbox_state, 0.0)
    assert sandbox_state.tables["campaigns"][0, "outcome"] == "victory"
    assert sandbox_state.tables["advisor_recommendations"].filter(
        pl.col("source_signal") == "news:post-victory-news"
    ).height == 1


def test_campaign_end_return_condition_restores_human_control() -> None:
    state = _state()
    _add_scenario(state, [{
        "id": "secure-oil", "objective_type": "resource_quantity",
        "target_resource_id": "oil", "target_value": 100,
    }])
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit(False).alias("sandbox_allowed")
    ))
    _start(CampaignSystem(), state)
    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["secure_oil"],
        return_condition="campaign_end",
    )]
    CampaignSetupSystem().update(state, 0.0)
    state.current_actions = []
    assert state.tables["sphere_delegations"][0, "active"] is True

    state.time.total_minutes = 1
    state.update_table("domestic_production", state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA").then(pl.lit(100.0))
        .otherwise(pl.col("domestic_production")).alias("domestic_production")
    ))
    CampaignSystem().update(state, 0.0)

    delegation = state.tables["sphere_delegations"].row(0, named=True)
    assert state.tables["campaigns"][0, "outcome"] == "victory"
    assert delegation["active"] is False
    assert delegation["current_controller"] == "human"


def test_recommendation_expiry_and_message_reading_clear_current_guidance() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    message_table = state.tables["messages"]
    state.update_table("messages", pl.DataFrame([{
        "id": "read-later", "country_id": "USA", "category": "war",
        "subject": "Review order", "body": "Read this message.", "is_read": False,
    }], schema=message_table.schema, strict=False))
    system.update(state, 0.0)
    recommendation = state.tables["advisor_recommendations"].filter(
        pl.col("source_signal") == "message:read-later"
    ).row(0, named=True)
    assert recommendation["confidence"] > 0.0
    assert recommendation["urgency"] > 0.0
    assert recommendation["expires_at_minute"] > recommendation["created_at_minute"]
    assert recommendation["optional_action_json"] == ""

    state.update_table("messages", state.tables["messages"].with_columns(pl.lit(True).alias("is_read")))
    state.time.total_minutes += 1
    system.update(state, 0.0)
    recommendation = state.tables["advisor_recommendations"].filter(
        pl.col("source_signal") == "message:read-later"
    ).row(0, named=True)
    assert recommendation["status"] == "stale"

    rows = state.tables["advisor_recommendations"].to_dicts()
    expired = dict(rows[0])
    expired.update({
        "id": "advisor:expired",
        "campaign_id": state.tables["campaigns"][0, "id"],
        "actor_country_id": "USA",
        "source_signal": "expired:signal",
        "status": "active",
        "expires_at_minute": state.time.total_minutes,
    })
    state.update_table("advisor_recommendations", pl.DataFrame(
        rows + [expired], schema=state.tables["advisor_recommendations"].schema, strict=False,
    ))
    system.update(state, 0.0)
    expired_row = state.tables["advisor_recommendations"].filter(pl.col("id") == "advisor:expired").row(0, named=True)
    assert expired_row["status"] == "expired"


def test_outcome_rules_support_metric_victory_and_draw_on_simultaneous_conditions() -> None:
    state = _state()
    _add_scenario(state, [], setup=None)
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit('{"conditions":[{"objective_type":"gdp_per_capita","target_value":9.0}]}').alias("win_conditions_json"),
        pl.lit("{}").alias("loss_conditions_json"),
        pl.lit(False).alias("sandbox_allowed"),
    ))
    system = CampaignSystem()
    _start(system, state)
    assert state.tables["campaigns"].row(0, named=True)["outcome"] == "victory"
    assert state.globals["active_scenario_rules"] == {}

    draw_state = _state()
    _add_scenario(
        draw_state,
        [
            {"id": "first", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 90},
            {"id": "second", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 100, "deadline_minutes": 0},
        ],
    )
    draw_state.update_table("campaign_scenarios", draw_state.tables["campaign_scenarios"].with_columns(
        pl.lit('{"objective_mode":"any"}').alias("win_conditions_json"),
        pl.lit('{"draw_on_simultaneous":true}').alias("loss_conditions_json"),
        pl.lit('{"combat":false}').alias("enabled_rules_json"),
    ))
    draw_system = CampaignSystem()
    _start(draw_system, draw_state)
    draw_state.time.total_minutes = 1
    draw_state.update_table("domestic_production", draw_state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA")
        .then(pl.lit(90.0))
        .otherwise(pl.col("domestic_production"))
        .alias("domestic_production")
    ))
    draw_system.update(draw_state, 0.0)

    campaign = draw_state.tables["campaigns"].row(0, named=True)
    assert campaign["outcome"] == "draw"
    assert draw_state.globals["active_scenario_rules"] == {"combat": False}


def test_resolved_objective_recommendation_is_marked_stale() -> None:
    state = _state()
    _add_scenario(
        state,
        [{
            "id": "time-sensitive",
            "objective_type": "resource_quantity",
            "target_resource_id": "oil",
            "target_value": 90,
            "deadline_minutes": 60,
        }],
    )
    system = CampaignSystem()
    _start(system, state)
    assert state.tables["advisor_recommendations"].height == 1
    assert state.tables["advisor_recommendations"][0, "status"] == "active"

    state.update_table("domestic_production", state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA")
        .then(pl.lit(95.0))
        .otherwise(pl.col("domestic_production"))
        .alias("domestic_production")
    ))
    state.time.total_minutes = 1
    system.update(state, 0.0)
    recommendation = state.tables["advisor_recommendations"].row(0, named=True)
    assert recommendation["status"] == "stale"
    assert "no longer active" in recommendation["stale_reason"]
