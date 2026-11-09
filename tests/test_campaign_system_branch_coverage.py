from __future__ import annotations

import json

import polars as pl
import pytest

from modules.base.systems.world.campaign_system import CampaignSetupSystem, CampaignSystem
from src.shared.actions import ActionSetSphereDelegation, ActionStartCampaign
from tests.test_campaign_system import _add_scenario, _start, _state


def _active_campaign_state():
    state = _state()
    _add_scenario(state, [])
    _start(CampaignSystem(), state)
    return state


def _delegation_action(
    *,
    country_tag: str = "USA",
    scope_type: str = "country",
    scope_id: str = "USA",
    authority: list[str] | None = None,
    delegate_id: str = "ai",
    active: bool = True,
    return_condition: str = "manual",
) -> ActionSetSphereDelegation:
    return ActionSetSphereDelegation(
        "local_admin",
        country_tag,
        scope_type,
        scope_id,
        delegate_id,
        ["economy"] if authority is None else authority,
        ["stability"],
        active=active,
        return_condition=return_condition,
    )


def _apply_delegation(state, action: ActionSetSphereDelegation) -> dict:
    state.current_actions = [action]
    CampaignSetupSystem().update(state, 0.0)
    state.current_actions = []
    return state.journal.command_results[-1]


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (_delegation_action(country_tag="CAN", scope_id="CAN"), "campaign owner"),
        (_delegation_action(scope_type="planet"), "valid scope"),
        (_delegation_action(scope_id=""), "valid scope"),
        (_delegation_action(authority=["unknown"]), "unsupported domain"),
        (_delegation_action(return_condition="unsupported"), "return condition"),
        (_delegation_action(delegate_id="human-player"), "existing AI controller"),
        (_delegation_action(scope_id="CAN"), "actor country"),
        (_delegation_action(scope_type="party", scope_id="party-a", authority=[]), "political authority"),
        (_delegation_action(scope_type="party", scope_id="party-a", authority=["politics"]), "current ruling party"),
        (_delegation_action(scope_type="sphere", scope_id="trade_union", authority=[]), "limited to diplomacy"),
        (_delegation_action(scope_type="sphere", scope_id="missing", authority=["diplomacy"]), "active treaty"),
        (_delegation_action(authority=[]), "at least one authority"),
    ],
)
def test_invalid_delegation_requests_are_rejected_without_writing_rows(action, message: str) -> None:
    state = _active_campaign_state()
    before = state.tables["sphere_delegations"].to_dicts()

    result = _apply_delegation(state, action)

    assert result["status"] == "rejected"
    assert message in result["reason"]
    assert state.tables["sphere_delegations"].to_dicts() == before


def test_delegation_requires_an_active_campaign() -> None:
    state = _active_campaign_state()
    campaigns = state.tables["campaigns"]
    state.update_table("campaigns", campaigns.head(0))

    result = _apply_delegation(state, _delegation_action())

    assert result["status"] == "rejected"
    assert "active campaign" in result["reason"]
    assert state.tables["sphere_delegations"].is_empty()


def test_party_delegation_can_resolve_the_ruling_party_from_party_rows() -> None:
    state = _active_campaign_state()
    parties = state.tables["political_parties"]
    state.update_table("political_parties", pl.DataFrame([{
        "country_id": "USA", "party_id": "party-a", "display_name": "Party A", "is_ruling": True,
    }], schema=parties.schema, strict=False))
    governments = state.tables["country_governments"]
    state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "ruling_party_id": "", "initialized": True,
    }], schema=governments.schema, strict=False))

    result = _apply_delegation(
        state,
        _delegation_action(scope_type="party", scope_id="party-a", authority=["politics"]),
    )

    assert result["status"] == "applied"
    assert state.tables["sphere_delegations"][0, "scope_id"] == "party-a"


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ("not-an-object", "must be an object"),
        ({"objective_type": "unsupported"}, "Unsupported objective type"),
        ([{"id": "same", "objective_type": "region_control"}, {"id": "same", "objective_type": "region_control"}], "Duplicate objective id"),
        ({"objective_type": "region_control", "target_value": float("nan")}, "target_value must be finite"),
        ({"objective_type": "region_control", "hold_duration_minutes": -1}, "cannot be negative"),
        ({"objective_type": "region_control", "comparison": "approximately"}, "Unsupported objective comparison"),
        ({"objective_type": "region_control", "progress_rule": "increase"}, "progress_rule must be"),
        ({"objective_type": "region_control", "failure_conditions": {}}, "failure_conditions must be a list"),
        ({"objective_type": "region_control", "failure_conditions": ["invalid"]}, "Each objective failure condition"),
        ({"objective_type": "region_control", "failure_conditions": [{"objective_type": "unsupported"}]}, "Unsupported objective failure condition"),
        ({"objective_type": "region_control", "failure_conditions": [{"objective_type": "region_control", "comparison": "approximately"}]}, "Unsupported failure condition comparison"),
        ({"objective_type": "region_control", "failure_conditions": [{"objective_type": "region_control", "target_value": "invalid"}]}, "failure condition target_value must be finite"),
        ({"objective_type": "region_control", "failure_conditions": [{"objective_type": "region_control", "target_value": float("inf")}]}, "failure condition target_value must be finite"),
    ],
)
def test_objective_definition_validation_rejects_invalid_contracts(definition, message: str) -> None:
    definitions = definition if isinstance(definition, list) and definition and isinstance(definition[0], dict) else [definition]

    with pytest.raises(ValueError, match=message):
        CampaignSystem()._objective_definitions({"objectives_json": json.dumps(definitions)})


def _replace_rows(state, table_name: str, rows: list[dict]) -> None:
    table = state.tables[table_name]
    state.update_table(table_name, pl.DataFrame(rows, schema=table.schema, strict=False))


def test_advisor_filters_irrelevant_inputs_deduplicates_and_preserves_ai_policy_rows() -> None:
    state = _active_campaign_state()
    _replace_rows(state, "political_crises", [
        {"id": "crisis-valid", "country_id": "USA", "status": "active"},
        {"id": "crisis-foreign", "country_id": "CAN", "status": "active"},
        {"id": "crisis-resolved", "country_id": "USA", "status": "resolved"},
    ])
    _replace_rows(state, "news_items", [
        {"id": "news-valid", "category": "conflict", "severity": "critical", "related_country_id": "USA"},
        {"id": "news-foreign", "category": "conflict", "severity": "urgent", "related_country_id": "CAN"},
        {"id": "news-quiet", "category": "routine", "severity": "info", "related_country_id": "USA"},
        {"id": "", "category": "opportunity", "severity": "", "related_country_id": "USA"},
    ])
    _replace_rows(state, "messages", [
        {"id": "message-valid", "country_id": "USA", "is_read": False, "category": "economy"},
        {"id": "message-read", "country_id": "USA", "is_read": True, "category": "war"},
        {"id": "message-foreign", "country_id": "CAN", "is_read": False, "category": "war"},
        {"id": "", "country_id": "USA", "is_read": False, "category": "war"},
    ])
    _replace_rows(state, "debt_distress_cases", [
        {"id": "debt-valid", "country_id": "USA", "status": "arrears"},
        {"id": "debt-foreign", "country_id": "CAN", "status": "arrears"},
        {"id": "debt-closed", "country_id": "USA", "status": "resolved"},
    ])
    _replace_rows(state, "migration_signals", [
        {"country_id": "USA", "political_pressure": 0.7, "service_pressure": 0.0, "law_pressure": 0.0, "window_start_minute": 5},
        {"country_id": "USA", "political_pressure": 0.4, "service_pressure": 0.3, "law_pressure": 0.1, "window_start_minute": 6},
        {"country_id": "CAN", "political_pressure": 0.9, "service_pressure": 0.0, "law_pressure": 0.0, "window_start_minute": 7},
    ])
    _replace_rows(state, "infrastructure_damage_records", [
        {"id": "damage-valid", "region_id": 1, "severity": 0.7, "recovered": False},
        {"id": "damage-foreign", "region_id": 2, "severity": 0.9, "recovered": False},
        {"id": "damage-recovered", "region_id": 1, "severity": 0.9, "recovered": True},
        {"id": "damage-minor", "region_id": 1, "severity": 0.2, "recovered": False},
    ])
    ai_policy = CampaignSystem._defaults_for("advisor_recommendations")
    ai_policy.update({
        "id": "advisor:campaign:ai-policy",
        "campaign_id": state.tables["campaigns"][0, "id"],
        "actor_country_id": "USA",
        "source_signal": "ai_policy:budget",
        "status": "active",
        "expires_at_minute": 10_000,
    })
    _replace_rows(state, "advisor_recommendations", [ai_policy])

    system = CampaignSystem()
    system._refresh_recommendations(state)
    first_rows = state.tables["advisor_recommendations"].to_dicts()
    expected = {
        "political_crisis:crisis-valid",
        "news:news-valid",
        "message:message-valid",
        "debt_distress:debt-valid:arrears",
        "migration_pressure:USA:5",
        "infrastructure_damage:damage-valid",
    }
    assert expected.issubset({row["source_signal"] for row in first_rows})

    system._refresh_recommendations(state)

    rows = state.tables["advisor_recommendations"].to_dicts()
    assert len(rows) == len(first_rows)
    assert next(row for row in rows if row["source_signal"] == "ai_policy:budget")["status"] == "active"


def test_recommendation_refresh_returns_when_output_table_is_unavailable() -> None:
    state = _state()
    state.tables.pop("advisor_recommendations")

    CampaignSystem()._refresh_recommendations(state)


def test_campaign_system_contract_and_empty_scenario_bootstrap() -> None:
    setup_system = CampaignSetupSystem()
    campaign_system = CampaignSystem()
    assert setup_system.id == "base.campaign_setup"
    assert setup_system.dependencies == ["base.time", "base.bootstrap"]
    assert campaign_system.id == "base.campaign"
    assert campaign_system.dependencies == ["base.campaign_setup"]

    state = _state()
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].head(0))
    setup_system.update(state, 0.0)

    scenario = state.tables["campaign_scenarios"].row(0, named=True)
    assert scenario["id"] == "open_sandbox"
    assert scenario["title"] == "Open Sandbox"
    assert scenario["enabled"] is True


def _start_action(state, action: ActionStartCampaign) -> dict:
    state.current_actions = [action]
    CampaignSetupSystem().update(state, 0.0)
    state.current_actions = []
    return state.journal.command_results[-1]


@pytest.mark.parametrize(
    ("country_tag", "scenario_id", "player_party_id", "reason"),
    [
        ("CAN", "test", "", "not assigned to this player"),
        ("USA", "missing", "", "unavailable or disabled"),
        ("MEX", "test", "", "no current country record"),
        ("USA", "test", "missing-party", "political party is unavailable"),
    ],
)
def test_campaign_start_rejects_invalid_player_scenario_country_or_party(
    country_tag: str,
    scenario_id: str,
    player_party_id: str,
    reason: str,
) -> None:
    state = _state()
    _add_scenario(state, [])
    if country_tag == "MEX":
        state.globals["player_tag"] = ""

    result = _start_action(
        state,
        ActionStartCampaign("local_admin", scenario_id, country_tag, player_party_id),
    )

    assert result["status"] == "rejected"
    assert reason in result["reason"]
    assert state.tables["campaigns"].is_empty()


@pytest.mark.parametrize(
    ("scenario_change", "reason"),
    [
        (lambda table: table.with_columns(pl.lit("{}").alias("selectable_country_ids_json")), "selectable countries must be a JSON list"),
        (lambda table: table.with_columns(pl.lit('["CAN"]').alias("selectable_country_ids_json")), "not available in this scenario"),
        (
            lambda table: table.with_columns(pl.lit(False).alias("sandbox_allowed")),
            "must allow sandbox continuation",
        ),
    ],
)
def test_campaign_start_rejects_invalid_allowlist_and_no_outcome_scenarios(scenario_change, reason: str) -> None:
    state = _state()
    _add_scenario(state, [])
    state.update_table("campaign_scenarios", scenario_change(state.tables["campaign_scenarios"]))

    result = _start_action(state, ActionStartCampaign("local_admin", "test", "USA"))

    assert result["status"] == "rejected"
    assert reason in result["reason"]
    assert state.tables["campaigns"].is_empty()


def test_campaign_start_rejects_a_scenario_already_started_for_the_country() -> None:
    state = _state()
    _add_scenario(state, [])
    _start(CampaignSystem(), state)

    result = _start_action(state, ActionStartCampaign("local_admin", "test", "USA"))

    assert result["status"] == "rejected"
    assert "already started" in result["reason"]
    assert state.tables["campaigns"].height == 1


@pytest.mark.parametrize(
    ("setup", "message", "remove_table"),
    [
        ({"unexpected": True}, "unsupported keys", None),
        ({"updates": {}}, "updates must be a list", None),
        ({"updates": ["invalid"]}, "Each starting setup update must be an object", None),
        ({"updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": 1}, "extra": 1}]}, "unsupported keys", None),
        ({"updates": [{"table": "unknown", "key": "USA", "values": {"money_reserves": 1}}]}, "not permitted", None),
        ({"updates": [{"table": "countries", "key": {}, "values": {"money_reserves": 1}}]}, "requires key fields", None),
        ({"updates": [{"table": "countries", "key": "USA", "values": {}}]}, "non-empty values object", None),
        ({"updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": None}}]}, "cannot be null", None),
        ({"updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": float("inf")}}]}, "must be finite", None),
        ({"updates": [{"table": "countries", "key": "MEX", "values": {"money_reserves": 1}}]}, "exactly one", None),
        ({"updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": 1}}]}, "unavailable", "countries"),
    ],
)
def test_starting_setup_validation_rejects_invalid_updates_without_mutating_state(setup, message: str, remove_table) -> None:
    state = _state()
    before = state.tables["countries"].to_dicts()
    if remove_table:
        state.tables.pop(remove_table)

    with pytest.raises(ValueError, match=message):
        CampaignSystem()._prepare_setup(state, setup)

    if "countries" in state.tables:
        assert state.tables["countries"].to_dicts() == before


def test_objective_evaluation_blocks_invalid_failure_data_and_calculates_non_default_remaining_values() -> None:
    state = _state()
    _add_scenario(state, [
        {"id": "limited", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 50, "comparison": "at_most"},
        {"id": "exact", "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 75, "comparison": "equals"},
    ])
    system = CampaignSystem()
    _start(system, state)

    objectives = state.tables["objectives"]
    assert objectives.filter(pl.col("title") == "limited")[0, "remaining"] == 30.0
    assert objectives.filter(pl.col("title") == "exact")[0, "remaining"] == 5.0
    state.update_table("objectives", objectives.with_columns(
        pl.when(pl.col("title") == "limited")
        .then(pl.lit("{}"))
        .otherwise(pl.col("failure_conditions_json"))
        .alias("failure_conditions_json")
    ))

    system._evaluate_objectives(state)

    limited = state.tables["objectives"].filter(pl.col("title") == "limited").row(0, named=True)
    assert limited["status"] == "blocked"
    assert "failure-condition data is invalid" in limited["missing_data_reason"]


@pytest.mark.parametrize(
    "condition",
    [
        "not-an-object",
        {"objective_type": "unsupported", "target_value": 1},
        {"objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": "invalid"},
        {"objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": float("inf")},
    ],
)
def test_campaign_condition_matching_treats_invalid_or_unavailable_conditions_as_false(condition) -> None:
    state = _state()

    assert CampaignSystem()._condition_matches(state, condition, "USA") is False


def test_campaign_outcome_ignores_malformed_rules_and_honors_both_deadline_forms() -> None:
    state = _state()
    _add_scenario(state, [])
    system = CampaignSystem()
    _start(system, state)
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit("{").alias("win_conditions_json"),
        pl.lit("{").alias("loss_conditions_json"),
    ))

    system._evaluate_campaign_outcomes(state)

    assert state.tables["campaigns"][0, "outcome"] == "sandbox"

    for deadline in ({"deadline_at_minute": 1}, {"deadline_minutes": 1}):
        candidate = _state()
        _add_scenario(candidate, [])
        candidate.update_table("campaign_scenarios", candidate.tables["campaign_scenarios"].with_columns(
            pl.lit(json.dumps(deadline)).alias("loss_conditions_json"),
        ))
        evaluator = CampaignSystem()
        _start(evaluator, candidate)
        candidate.time.total_minutes = 2
        evaluator._evaluate_campaign_outcomes(candidate)
        assert candidate.tables["campaigns"][0, "outcome"] == "defeat"


def test_campaign_loss_conditions_and_territory_rules_can_end_a_campaign() -> None:
    condition_state = _state()
    _add_scenario(condition_state, [])
    condition_state.update_table("campaign_scenarios", condition_state.tables["campaign_scenarios"].with_columns(
        pl.lit(json.dumps({"conditions": [{
            "objective_type": "resource_quantity", "target_resource_id": "oil", "target_value": 50,
        }]})).alias("loss_conditions_json"),
    ))
    condition_system = CampaignSystem()
    _start(condition_system, condition_state)
    assert condition_state.tables["campaigns"][0, "outcome"] == "defeat"

    territory_state = _state()
    _add_scenario(territory_state, [])
    territory_state.update_table("campaign_scenarios", territory_state.tables["campaign_scenarios"].with_columns(
        pl.lit('{"lose_if_no_territory":true}').alias("loss_conditions_json"),
    ))
    territory_system = CampaignSystem()
    _start(territory_system, territory_state)
    territory_state.update_table("regions", territory_state.tables["regions"].with_columns(
        pl.lit("CAN").alias("owner"), pl.lit("CAN").alias("controller"),
    ))

    territory_system._evaluate_campaign_outcomes(territory_state)

    assert territory_state.tables["campaigns"][0, "outcome"] == "defeat"


def test_remaining_campaign_helpers_handle_invalid_or_missing_input() -> None:
    system = CampaignSystem()
    state = _state()

    assert CampaignSystem._progress(2.0, 0.0, False, "at_most") == 0.0
    assert CampaignSystem._progress(0.0, 0.0, True, "at_most") == 1.0
    assert CampaignSystem._progress(10.0, 5.0, False, "at_most") == 0.5
    assert CampaignSystem._progress(5.0, 5.0, True, "equals") == 1.0
    assert CampaignSystem._progress(0.0, 0.0, True, "at_least") == 1.0
    assert CampaignSystem._country_exists(state, "USA") is True
    state.tables.pop("countries")
    assert CampaignSystem._country_exists(state, "USA") is False
    assert CampaignSystem._defaults_for("unknown_table") == {}
    assert CampaignSystem._tag_list("USA,CAN") == {"USA", "CAN"}
    assert CampaignSystem._tag_list(42) == set()
    with pytest.raises(ValueError, match="must be a JSON object"):
        CampaignSystem._json_object("[]", "object")
    with pytest.raises(ValueError, match="must be a JSON list"):
        CampaignSystem._json_list("{}", "list")

    state = _active_campaign_state()
    state.update_table("campaigns", state.tables["campaigns"].with_columns(
        pl.lit("{").alias("enabled_rules_json"),
    ))
    system._publish_active_rules(state)
    assert state.globals["active_scenario_rules"] == {}


def test_campaign_start_rejects_unknown_actor_scope_and_setup_columns() -> None:
    state = _state()
    _add_scenario(state, [])
    state.update_table("campaign_scenarios", state.tables["campaign_scenarios"].with_columns(
        pl.lit("galaxy").alias("political_scope"),
    ))

    result = _start_action(state, ActionStartCampaign("local_admin", "test", "USA"))

    assert result["status"] == "rejected"
    assert "Unsupported campaign actor scope" in result["reason"]

    malformed_state = _state()
    malformed_state.tables["countries"] = pl.DataFrame({"name": ["United States"]})
    with pytest.raises(ValueError, match="unavailable columns"):
        CampaignSystem()._prepare_setup(malformed_state, {
            "updates": [{"table": "countries", "key": "USA", "values": {"money_reserves": 1}}],
        })


def test_objective_evaluation_skips_rows_without_a_type() -> None:
    state = _state()
    row = CampaignSystem._defaults_for("objectives")
    row.update({"id": "legacy-empty", "campaign_id": "", "objective_type": ""})
    state.update_table("objectives", pl.DataFrame([row], schema=state.tables["objectives"].schema, strict=False))

    CampaignSystem()._evaluate_objectives(state)

    assert state.tables["objectives"][0, "id"] == "legacy-empty"
