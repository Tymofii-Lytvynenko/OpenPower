from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from modules.base.systems.world.ai.political_policy import (
    PoliticalCrisisPolicy,
    PoliticalElectionPolicy,
    PoliticalLawPolicy,
)
from modules.base.systems.world.ai_system import AISystem
from src.shared.actions import (
    ActionChangePoliticalLaw,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
)
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.core.ai_framework import AITableContext


def test_law_ai_uses_shared_authoritative_validator_and_records_choice_reason() -> None:
    state = _state()
    context = _context(state)
    policy = PoliticalLawPolicy()

    first = policy.build_candidates(context).collect()
    repeated = policy.build_candidates(context).collect()
    assert first.equals(repeated)
    action = policy.resolve_action(first.row(0, named=True))

    assert isinstance(action, ActionChangePoliticalLaw)
    assert action.player_id == "AI_SYSTEM"
    assert action.country_tag == "AAA"
    assert action.decision_reason
    state.current_actions = [action]
    PoliticalLifecycleSystem().update(state, 0.0)
    result = state.journal.command_results[-1]
    assert result["status"] == "applied"
    assert "declared effects" in result["decision_reason"]


def test_election_ai_respects_configured_override_and_shared_validator() -> None:
    state = _state(include_override=True)
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "AAA").then(25.0).otherwise(pl.col("gvt_approval")).alias("gvt_approval")
        ),
    )
    candidates = PoliticalElectionPolicy().build_candidates(_context(state)).collect()
    action = PoliticalElectionPolicy().resolve_action(candidates.row(0, named=True))

    assert isinstance(action, ActionSetElectionOverride)
    assert action.override_type == "postpone"
    assert action.player_id == "AI_SYSTEM"
    assert action.decision_reason
    state.current_actions = [action]
    PoliticalLifecycleSystem().update(state, 0.0)
    result = state.journal.command_results[-1]
    assert result["status"] == "applied"
    assert result["decision_reason"].startswith("Selected postpone")


def test_crisis_ai_schedules_action_through_ai_system_and_shared_regime_path() -> None:
    state = _state(include_crisis=True)
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "AAA").then(60.0).otherwise(pl.col("gvt_approval")).alias("gvt_approval")
        ),
    )
    state.events = [EventNewDay(1, 1, 2001)]
    ai = AISystem()

    ai.update(state, 0.0)

    action = next(
        action
        for action in state.current_actions
        if isinstance(action, ActionResolvePoliticalCrisis)
    )
    assert action.player_id == "AI_SYSTEM"
    assert action.country_tag == "AAA"
    assert action.crisis_id == "crisis-ai"
    assert action.decision_reason
    PoliticalLifecycleSystem().update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "success"
    assert "configured support" in state.journal.command_results[-1]["decision_reason"]
    assert state.get_table("political_crises").filter(pl.col("id") == "crisis-ai")["outcome"][0] == "success"
    assert any(
        row.get("policy_id") == "political_crisis" and row.get("reason_code")
        for row in ai.last_decisions.to_dicts()
    )


def test_political_policies_do_not_issue_commands_for_human_controlled_country() -> None:
    state = _state()
    context = _context(state)
    law_actions = PoliticalLawPolicy().build_candidates(context).collect()

    assert law_actions["country_id"].to_list() == ["AAA"]
    assert "HUM" not in law_actions["country_id"].to_list()
    assert PoliticalCrisisPolicy().resolve_action({"action_kind": "unknown"}) is None


def _context(state: GameState, *, day_ordinal: int = 7) -> AITableContext:
    return AITableContext(
        tables=state.tables,
        day_ordinal=day_ordinal,
        total_minutes=int(state.time.total_minutes),
        date_text=str(state.time.date_str),
        player_tag="HUM",
        globals=state.globals,
    )


def _state(*, include_override: bool = False, include_crisis: bool = False) -> GameState:
    path = {
        "id": "constitutional",
        "crisis_types": ["coup_attempt"],
        "minimum_support": 0.7,
        "minimum_approval": 40.0,
        "minimum_stability": 40.0,
        "outcome": {
            "government_form_id": "transitional republic",
            "ruling_party_id": "beta",
            "approval_delta": 2.0,
        },
    }
    overrides = [
        {
            "type": "postpone",
            "minimum_duration_days": 5,
            "maximum_duration_days": 30,
            "cost": 0.0,
            "cooldown_days": 0,
        }
    ] if include_override else []
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB", "HUM"],
                    "money_reserves": [1_000.0, 500.0, 500.0],
                    "gvt_approval": [30.0, 50.0, 50.0],
                    "gvt_stability": [60.0, 50.0, 50.0],
                    "gvt_corruption": [10.0, 10.0, 10.0],
                    "human_dev": [0.5, 0.5, 0.5],
                    "economic_political_modifier": [1.0, 1.0, 1.0],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB", "HUM"],
                    "government_type": ["Multi-party democracy"] * 3,
                    "government_form_id": ["multi-party democracy"] * 3,
                    "ruling_party_id": ["alpha", "incumbent", "human"],
                    "succession_party_id": ["beta", "incumbent", "human"],
                    "election_eligible": [True, True, True],
                    "next_election_at_minute": [10_000, 10_000, 10_000],
                    "crisis_status": ["none", "none", "none"],
                    "initialized": [True, True, True],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["multi-party democracy", "transitional republic"],
                    "display_name": ["Multi-party democracy", "Transitional republic"],
                    "election_eligible": [True, True],
                    "election_interval_minutes": [10_000, 10_000],
                    "law_permissions_json": ['["*"]', '["*"]'],
                    "election_overrides_json": [json.dumps(overrides), "[]"],
                    "regime_change_paths_json": [json.dumps([path]), "[]"],
                }
            ),
            "political_parties": pl.DataFrame(
                {
                    "country_id": ["AAA", "AAA", "BBB", "HUM"],
                    "party_id": ["alpha", "beta", "incumbent", "human"],
                    "display_name": ["Alpha", "Beta", "Incumbent", "Human"],
                    "support_share": [0.6, 0.4, 1.0, 1.0],
                    "organization": [0.8, 0.7, 0.5, 0.5],
                    "eligible": [True, True, True, True],
                    "is_ruling": [True, False, True, True],
                }
            ),
            "country_laws": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "law_id": ["civil_rights"],
                    "group_name": ["Rights"],
                    "title": ["Civil rights"],
                    "value": ["Restricted"],
                    "allowed_values_json": [json.dumps(["Restricted", "Protected"])],
                    "effects_by_value_json": [json.dumps({
                        "Restricted": [{"domain": "rights", "effect": "public_rights", "value": -0.2}],
                        "Protected": [{"domain": "rights", "effect": "public_rights", "value": 0.2}],
                    })],
                }
            ),
            "political_elections": pl.DataFrame(
                {
                    "id": ["election-ai"],
                    "country_id": ["AAA"],
                    "government_form_id": ["multi-party democracy"],
                    "scheduled_at_minute": [10_000],
                    "status": ["scheduled"],
                }
            ),
            "political_crises": pl.DataFrame(
                {
                    "id": ["crisis-ai"] if include_crisis else [],
                    "country_id": ["AAA"] if include_crisis else [],
                    "crisis_type": ["coup_attempt"] if include_crisis else [],
                    "trigger": ["ai-test"] if include_crisis else [],
                    "created_at_minute": [1_000] if include_crisis else [],
                    "deadline_at_minute": [0] if include_crisis else [],
                    "support": [0.9] if include_crisis else [],
                    "status": ["active"] if include_crisis else [],
                }
            ),
            "countries_relations": pl.DataFrame(
                {
                    "source": ["AAA", "BBB"],
                    "target": ["BBB", "AAA"],
                    "value": [95.0, 90.0],
                }
            ),
        },
        globals={
            "tick": 5,
            "player_tag": "HUM",
            "player_country_map": {"human-player": "HUM"},
        },
    )
    ensure_base_tables(state)
    state.time.total_minutes = 5_000
    return state
