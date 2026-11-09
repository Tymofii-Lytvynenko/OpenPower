from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from modules.base.systems.world.ai.political_policy import (
    PoliticalCrisisPolicy,
    PoliticalElectionPolicy,
    PoliticalLawPolicy,
    _bounded_int,
    _effect_totals,
    _is_ai_country,
    _json_object,
    _json_records,
    _law_value_utility,
    _percent,
    _string_list,
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


def test_political_policies_and_resolvers_fail_closed_for_missing_data() -> None:
    context = AITableContext(
        tables={},
        day_ordinal=7,
        total_minutes=5_000,
        date_text="2001-01-08",
        player_tag="HUM",
        globals={},
    )
    for policy in (PoliticalLawPolicy(), PoliticalElectionPolicy(), PoliticalCrisisPolicy()):
        assert policy.build_candidates(context).collect().is_empty()

    assert PoliticalLawPolicy().resolve_action({"action_kind": "other"}) is None
    assert PoliticalLawPolicy().resolve_action({"action_kind": "law_change"}) is None
    assert PoliticalElectionPolicy().resolve_action({"action_kind": "other"}) is None
    assert PoliticalElectionPolicy().resolve_action(
        {"action_kind": "election_override", "country_tag": "", "override_type": "postpone"}
    ) is None
    assert PoliticalCrisisPolicy().resolve_action(
        {"action_kind": "resolve_crisis", "country_tag": "AAA", "crisis_id": "", "path_id": "path"}
    ) is None


def test_political_policy_parsers_and_utility_cover_malformed_and_domain_values() -> None:
    assert _json_records("not-json") == []
    assert _json_records('{"rules":[{"type":"postpone"}, null]}') == [{"type": "postpone"}]
    assert _json_object("not-json") == {}
    assert _json_object("[]") == {}
    assert _string_list("not-json") == []
    assert _string_list('{"value":"not a list"}') == []
    assert _percent(0.75, 50.0) == 75.0
    assert _bounded_int("invalid", 1, 36, 7) == 7
    assert _effect_totals(None) == {}
    assert _effect_totals(
        [None, {"domain": "", "effect": "ignored", "value": 4.0},
         {"domain": "rights", "effect": "public_rights", "value": 0.2}]
    ) == {("rights", "public_rights"): 0.2}

    score, reason = _law_value_utility(
        {
            "effects_by_value_json": json.dumps(
                {
                    "current": [
                        {"domain": "rights", "effect": "public_rights", "value": 0.2},
                        {"domain": "stability", "effect": "stability_modifier", "value": 0.0},
                        {"domain": "economy", "effect": "tax_efficiency", "value": 0.0},
                    ],
                    "target": [
                        {"domain": "rights", "effect": "public_rights", "value": 0.2},
                        {"domain": "stability", "effect": "stability_modifier", "value": 0.3},
                        {"domain": "economy", "effect": "tax_efficiency", "value": 0.5},
                    ],
                }
            )
        },
        "current",
        "target",
        approval=50.0,
        stability=50.0,
    )
    assert score > 0.0
    assert reason == "economic_resilience"


def test_election_policy_covers_acceleration_and_rejected_override_rules() -> None:
    state = _state()
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "AAA").then(pl.lit(80.0)).otherwise(pl.col("gvt_approval")).alias("gvt_approval"),
            pl.when(pl.col("id") == "AAA").then(pl.lit(80.0)).otherwise(pl.col("gvt_stability")).alias("gvt_stability"),
        ),
    )
    state.update_table(
        "government_form_rules",
        state.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit(json.dumps([{"type": "accelerate", "minimum_duration_days": 5, "maximum_duration_days": 30, "cost": 0.0, "cooldown_days": 0}])))
            .otherwise(pl.col("election_overrides_json"))
            .alias("election_overrides_json")
        ),
    )
    state.update_table(
        "political_history",
        pl.DataFrame({"country_id": ["AAA"], "event_type": ["election_override_applied"], "game_minute": [1_000]}),
    )
    accelerated = PoliticalElectionPolicy().build_candidates(_context(state)).collect()
    assert accelerated.filter(pl.col("country_id") == "AAA")["override_type"].to_list() == ["accelerate"]

    skipped = _state()
    skipped.update_table(
        "countries",
        skipped.get_table("countries").with_columns(
            pl.when(pl.col("id") == "AAA").then(pl.lit(80.0)).otherwise(pl.col("gvt_approval")).alias("gvt_approval"),
            pl.when(pl.col("id") == "AAA").then(pl.lit(60.0)).otherwise(pl.col("gvt_stability")).alias("gvt_stability"),
        ),
    )
    skipped.update_table(
        "government_form_rules",
        skipped.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit(json.dumps([{"type": "postpone"}, {"type": "accelerate"}, {"type": "succession"}, {"type": "future"}])))
            .otherwise(pl.col("election_overrides_json"))
            .alias("election_overrides_json")
        ),
    )
    assert PoliticalElectionPolicy().build_candidates(_context(skipped)).collect().is_empty()


def test_crisis_policy_skips_paths_for_unconfigured_crisis_types() -> None:
    state = _state(include_crisis=True)
    state.update_table(
        "political_crises",
        state.get_table("political_crises").with_columns(pl.lit("unconfigured_crisis").alias("crisis_type")),
    )

    assert PoliticalCrisisPolicy().build_candidates(_context(state)).collect().is_empty()


def test_ai_country_policy_respects_empty_tags_and_explicit_control_sets() -> None:
    context = _context(_state())
    assert not _is_ai_country(context, "")

    controlled = AITableContext(
        tables=context.tables,
        day_ordinal=context.day_ordinal,
        total_minutes=context.total_minutes,
        date_text=context.date_text,
        player_tag=context.player_tag,
        globals={"ai_controlled_countries": ["AAA"]},
    )
    assert _is_ai_country(controlled, "AAA")
    assert not _is_ai_country(controlled, "BBB")

    mapped = AITableContext(
        tables=context.tables,
        day_ordinal=context.day_ordinal,
        total_minutes=context.total_minutes,
        date_text=context.date_text,
        player_tag=context.player_tag,
        globals={"player_country_map": {"ai-player": "AAA"}},
    )
    assert not _is_ai_country(mapped, "AAA")


def test_law_policy_skips_crisis_pending_unmapped_and_non_improving_changes() -> None:
    crisis = _state(include_crisis=True)
    assert PoliticalLawPolicy().build_candidates(_context(crisis)).collect().is_empty()

    unmapped = _state()
    unmapped.update_table(
        "country_governments",
        unmapped.get_table("country_governments").with_columns(
            pl.when(pl.col("country_id") == "AAA")
            .then(pl.lit("missing form"))
            .otherwise(pl.col("government_form_id"))
            .alias("government_form_id")
        ),
    )
    assert PoliticalLawPolicy().build_candidates(_context(unmapped)).collect().is_empty()

    pending = _state()
    pending.update_table(
        "law_transitions",
        pl.DataFrame(
            {"country_id": ["AAA"], "law_id": ["civil_rights"], "status": ["scheduled"]}
        ),
    )
    assert PoliticalLawPolicy().build_candidates(_context(pending)).collect().is_empty()

    disallowed = _state()
    disallowed.update_table(
        "government_form_rules",
        disallowed.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit("[]"))
            .otherwise(pl.col("law_permissions_json"))
            .alias("law_permissions_json")
        ),
    )
    assert PoliticalLawPolicy().build_candidates(_context(disallowed)).collect().is_empty()

    non_improving = _state()
    identical_effects = json.dumps(
        {
            "Restricted": [{"domain": "rights", "effect": "public_rights", "value": 0.2}],
            "Protected": [{"domain": "rights", "effect": "public_rights", "value": 0.2}],
        }
    )
    non_improving.update_table(
        "country_laws",
        non_improving.get_table("country_laws").with_columns(
            pl.lit(identical_effects).alias("effects_by_value_json")
        ),
    )
    assert PoliticalLawPolicy().build_candidates(_context(non_improving)).collect().is_empty()


def test_election_policy_skips_ineligible_governments_and_invalid_dates_then_accepts_succession() -> None:
    ineligible = _state(include_override=True)
    ineligible.update_table(
        "country_governments",
        ineligible.get_table("country_governments").with_columns(
            pl.when(pl.col("country_id") == "AAA")
            .then(pl.lit(False))
            .otherwise(pl.col("election_eligible"))
            .alias("election_eligible")
        ),
    )
    assert PoliticalElectionPolicy().build_candidates(_context(ineligible)).collect().is_empty()

    missing_form = _state(include_override=True)
    missing_form.update_table(
        "country_governments",
        missing_form.get_table("country_governments").with_columns(
            pl.when(pl.col("country_id") == "AAA")
            .then(pl.lit("missing form"))
            .otherwise(pl.col("government_form_id"))
            .alias("government_form_id")
        ),
    )
    assert PoliticalElectionPolicy().build_candidates(_context(missing_form)).collect().is_empty()

    invalid_acceleration = _state()
    invalid_acceleration.update_table(
        "countries",
        invalid_acceleration.get_table("countries").with_columns(
            pl.when(pl.col("id") == "AAA").then(pl.lit(80.0)).otherwise(pl.col("gvt_approval")).alias("gvt_approval"),
            pl.when(pl.col("id") == "AAA").then(pl.lit(80.0)).otherwise(pl.col("gvt_stability")).alias("gvt_stability"),
        ),
    )
    invalid_acceleration.update_table(
        "political_elections",
        invalid_acceleration.get_table("political_elections").with_columns(
            pl.when(pl.col("country_id") == "AAA")
            .then(pl.lit(6_000))
            .otherwise(pl.col("scheduled_at_minute"))
            .alias("scheduled_at_minute")
        ),
    )
    invalid_acceleration.update_table(
        "government_form_rules",
        invalid_acceleration.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit(json.dumps([{"type": "accelerate", "minimum_duration_days": 5, "maximum_duration_days": 30}])))
            .otherwise(pl.col("election_overrides_json"))
            .alias("election_overrides_json")
        ),
    )
    assert PoliticalElectionPolicy().build_candidates(_context(invalid_acceleration)).collect().is_empty()

    succession = _state()
    succession.update_table(
        "political_parties",
        succession.get_table("political_parties").with_columns(
            pl.when(pl.col("party_id") == "alpha")
            .then(pl.lit(False))
            .otherwise(pl.col("eligible"))
            .alias("eligible")
        ),
    )
    succession.update_table(
        "government_form_rules",
        succession.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit(json.dumps([{"type": "succession", "minimum_duration_days": 5, "maximum_duration_days": 30}])))
            .otherwise(pl.col("election_overrides_json"))
            .alias("election_overrides_json")
        ),
    )
    candidates = PoliticalElectionPolicy().build_candidates(_context(succession)).collect()
    assert candidates.filter(pl.col("country_id") == "AAA")["override_type"].to_list() == ["succession"]


def test_crisis_policy_skips_missing_government_form_and_empty_paths() -> None:
    missing_government = _state(include_crisis=True)
    missing_government.update_table(
        "country_governments",
        missing_government.get_table("country_governments").filter(pl.col("country_id") != "AAA"),
    )
    assert PoliticalCrisisPolicy().build_candidates(_context(missing_government)).collect().is_empty()

    missing_form = _state(include_crisis=True)
    missing_form.update_table(
        "country_governments",
        missing_form.get_table("country_governments").with_columns(
            pl.when(pl.col("country_id") == "AAA")
            .then(pl.lit("missing form"))
            .otherwise(pl.col("government_form_id"))
            .alias("government_form_id")
        ),
    )
    assert PoliticalCrisisPolicy().build_candidates(_context(missing_form)).collect().is_empty()

    no_paths = _state(include_crisis=True)
    no_paths.update_table(
        "government_form_rules",
        no_paths.get_table("government_form_rules").with_columns(
            pl.when(pl.col("government_form_id") == "multi-party democracy")
            .then(pl.lit("[]"))
            .otherwise(pl.col("regime_change_paths_json"))
            .alias("regime_change_paths_json")
        ),
    )
    assert PoliticalCrisisPolicy().build_candidates(_context(no_paths)).collect().is_empty()


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
