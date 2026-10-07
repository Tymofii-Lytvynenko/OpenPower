from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.actions import ActionResolvePoliticalCrisis
from src.shared.events import EventGovernmentFormChanged
from src.shared.state import GameState


def test_successful_regime_change_commits_all_declared_state_and_preserves_territory() -> None:
    state = _state(support=0.9)
    before_owners = state.get_table("regions")["owner"].to_list()
    before_controllers = state.get_table("regions")["controller"].to_list()
    state.current_actions = [ActionResolvePoliticalCrisis("AAA", "AAA", "crisis-1", "constitutional")]

    PoliticalLifecycleSystem().update(state, 0.0)

    government = state.get_table("country_governments").filter(pl.col("country_id") == "AAA").row(0, named=True)
    assert government["government_form_id"] == "transitional republic"
    assert government["ruling_party_id"] == "beta"
    assert government["election_eligible"] is True
    assert government["next_election_at_minute"] == 7_000
    parties = state.get_table("political_parties").filter(pl.col("country_id") == "AAA")
    assert parties.filter(pl.col("party_id") == "beta")["is_ruling"][0] is True
    assert parties.filter(pl.col("party_id") == "alpha")["is_ruling"][0] is False
    law = state.get_table("country_laws").filter(pl.col("law_id") == "party_system").row(0, named=True)
    assert law["value"] == "Competitive"
    assert law["last_changed_at_minute"] == 5_000
    assert state.get_table("countries").filter(pl.col("id") == "AAA")["gvt_approval"][0] == 64.0
    assert state.get_table("countries").filter(pl.col("id") == "AAA")["gvt_stability"][0] == 56.0
    assert state.get_table("countries").filter(pl.col("id") == "AAA")["gvt_corruption"][0] == 8.0
    relations = state.get_table("countries_relations")
    assert _relation(relations, "AAA", "BBB") == 100.0
    assert _relation(relations, "BBB", "AAA") == 100.0
    crisis = state.get_table("political_crises").filter(pl.col("id") == "crisis-1").row(0, named=True)
    assert crisis["status"] == "resolved"
    assert crisis["outcome"] == "success"
    assert state.get_table("law_transitions").filter(pl.col("id") == "transition-1")["status"][0] == "cancelled"
    assert state.get_table("political_elections").filter(pl.col("id") == "election-old")["status"][0] == "cancelled"
    assert state.get_table("political_effects").filter(pl.col("source_type") == "regime_change").height == 1
    assert state.get_table("political_history").filter(pl.col("event_type") == "regime_change_resolved").height == 1
    assert any(isinstance(event, EventGovernmentFormChanged) for event in state.events)
    assert state.journal.command_results[-1]["status"] == "success"
    assert state.get_table("regions")["owner"].to_list() == before_owners
    assert state.get_table("regions")["controller"].to_list() == before_controllers


def test_failed_attempt_keeps_regime_law_relations_and_territory_intact() -> None:
    state = _state(support=0.2)
    before_government = state.get_table("country_governments").filter(pl.col("country_id") == "AAA").row(0, named=True)
    before_law = state.get_table("country_laws").filter(pl.col("law_id") == "party_system")["value"][0]
    before_relations = state.get_table("countries_relations").to_dicts()
    before_owners = state.get_table("regions")["owner"].to_list()
    state.current_actions = [ActionResolvePoliticalCrisis("AAA", "AAA", "crisis-1", "constitutional")]

    PoliticalLifecycleSystem().update(state, 0.0)

    after_government = state.get_table("country_governments").filter(pl.col("country_id") == "AAA").row(0, named=True)
    assert after_government["government_form_id"] == before_government["government_form_id"]
    assert after_government["ruling_party_id"] == before_government["ruling_party_id"]
    assert state.get_table("country_laws").filter(pl.col("law_id") == "party_system")["value"][0] == before_law
    assert state.get_table("countries_relations").to_dicts() == before_relations
    country = state.get_table("countries").filter(pl.col("id") == "AAA").row(0, named=True)
    assert country["gvt_approval"] == 56.0
    assert country["gvt_stability"] == 41.0
    assert country["gvt_corruption"] == 13.0
    crisis = state.get_table("political_crises").filter(pl.col("id") == "crisis-1").row(0, named=True)
    assert crisis["status"] == "resolved"
    assert crisis["outcome"] == "failed"
    assert state.get_table("political_history").filter(pl.col("event_type") == "regime_change_resolved")["result"][0] == "failed"
    assert not any(isinstance(event, EventGovernmentFormChanged) for event in state.events)
    assert state.get_table("regions")["owner"].to_list() == before_owners
    assert state.journal.command_results[-1]["status"] == "failed"


def test_unauthorized_expired_and_invalid_effect_actions_are_rejected_without_gameplay_mutation() -> None:
    for actor, deadline, remove_relation in (("BBB", 0, False), ("AAA", 4_999, False), ("AAA", 0, True)):
        state = _state(support=0.9, deadline=deadline)
        if remove_relation:
            state.update_table(
                "countries_relations",
                state.get_table("countries_relations").filter(
                    ~((pl.col("source") == "BBB") & (pl.col("target") == "AAA"))
                ),
            )
        before_government = state.get_table("country_governments").to_dicts()
        before_parties = state.get_table("political_parties").to_dicts()
        before_countries = state.get_table("countries").to_dicts()
        state.current_actions = [ActionResolvePoliticalCrisis(actor, "AAA", "crisis-1", "constitutional")]

        PoliticalLifecycleSystem().update(state, 0.0)

        assert state.get_table("country_governments").to_dicts() == before_government
        assert state.get_table("political_parties").to_dicts() == before_parties
        assert state.get_table("country_laws").filter(pl.col("law_id") == "party_system")["value"][0] == "Single-party"
        assert state.get_table("countries").to_dicts() == before_countries
        assert state.get_table("political_crises").filter(pl.col("id") == "crisis-1")["status"][0] == "active"
        assert state.journal.command_results[-1]["status"] == "rejected"
        assert state.journal.command_results[-1]["reason"]


def test_regime_paths_are_normalized_deterministically_and_bound_effects() -> None:
    from modules.base.systems.politics.political_crisis_policy import normalize_regime_change_paths

    rules = _paths()
    rules[0]["outcome"]["approval_delta"] = 1_000.0
    rules.append(dict(rules[0]))
    normalized = normalize_regime_change_paths(json.dumps(rules))

    assert [path.path_id for path in normalized] == ["constitutional"]
    assert normalized[0].approval_delta == 100.0
    assert normalized[0].relation_effects[0].delta == 20.0


def _paths() -> list[dict[str, object]]:
    return [
        {
            "id": "constitutional",
            "crisis_types": ["coup_attempt"],
            "minimum_support": 0.7,
            "minimum_approval": 40.0,
            "minimum_stability": 40.0,
            "outcome": {
                "government_form_id": "transitional republic",
                "ruling_party_id": "beta",
                "law_values": {"party_system": "Competitive"},
                "approval_delta": 4.0,
                "stability_delta": 6.0,
                "corruption_delta": -2.0,
                "relation_effects": [
                    {"target_country_id": "BBB", "delta": 20.0, "reciprocal": True}
                ],
            },
            "failure_effects": {
                "approval_delta": -4.0,
                "stability_delta": -9.0,
                "corruption_delta": 3.0,
            },
        }
    ]


def _state(*, support: float, deadline: int = 0) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB"],
                    "gvt_approval": [60.0, 50.0],
                    "gvt_stability": [50.0, 50.0],
                    "gvt_corruption": [10.0, 10.0],
                    "human_dev": [0.5, 0.5],
                    "economic_political_modifier": [1.0, 1.0],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "government_type": ["Military-led state", "Transitional republic"],
                    "government_form_id": ["military-led state", "transitional republic"],
                    "ruling_party_id": ["alpha", "incumbent"],
                    "succession_party_id": ["alpha", "incumbent"],
                    "election_eligible": [False, True],
                    "next_election_at_minute": [0, 100_000],
                    "crisis_status": ["coup_attempt", "none"],
                    "initialized": [True, True],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["military-led state", "transitional republic"],
                    "display_name": ["Military-led state", "Transitional republic"],
                    "election_eligible": [False, True],
                    "election_interval_minutes": [0, 2_000],
                    "regime_change_paths_json": [json.dumps(_paths()), "[]"],
                }
            ),
            "political_parties": pl.DataFrame(
                {
                    "country_id": ["AAA", "AAA", "BBB"],
                    "party_id": ["alpha", "beta", "incumbent"],
                    "display_name": ["Alpha", "Beta", "Incumbent"],
                    "support_share": [0.6, 0.4, 1.0],
                    "organization": [0.8, 0.7, 0.5],
                    "eligible": [True, True, True],
                    "is_ruling": [True, False, True],
                }
            ),
            "country_laws": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "law_id": ["party_system"],
                    "group_name": ["Institutions"],
                    "title": ["Party system"],
                    "value": ["Single-party"],
                    "allowed_values_json": [json.dumps(["Single-party", "Competitive"])],
                    "effects_by_value_json": [json.dumps({"Competitive": [{"domain": "rights", "effect": "political_competition", "value": 0.2}]})],
                    "cooldown_minutes": [1_000],
                }
            ),
            "law_transitions": pl.DataFrame(
                {
                    "id": ["transition-1"],
                    "country_id": ["AAA"],
                    "law_id": ["labor_policy"],
                    "government_form_id": ["military-led state"],
                    "carry_over_rule": ["cancel_on_regime_change"],
                    "status": ["scheduled"],
                    "effective_at_minute": [9_000],
                }
            ),
            "political_elections": pl.DataFrame(
                {
                    "id": ["election-old"],
                    "country_id": ["AAA"],
                    "government_form_id": ["military-led state"],
                    "scheduled_at_minute": [90_000],
                    "status": ["scheduled"],
                }
            ),
            "political_crises": pl.DataFrame(
                {
                    "id": ["crisis-1"],
                    "country_id": ["AAA"],
                    "crisis_type": ["coup_attempt"],
                    "trigger": ["coup"],
                    "created_at_minute": [1_000],
                    "deadline_at_minute": [deadline],
                    "support": [support],
                    "proposed_form_id": [""],
                    "proposed_ruling_party_id": [""],
                    "status": ["active"],
                }
            ),
            "countries_relations": pl.DataFrame(
                {
                    "source": ["AAA", "BBB"],
                    "target": ["BBB", "AAA"],
                    "value": [95.0, 93.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1, 2],
                    "owner": ["AAA", "BBB"],
                    "controller": ["AAA", "BBB"],
                }
            ),
        },
        globals={"tick": 5},
    )
    ensure_base_tables(state)
    state.time.total_minutes = 5_000
    return state


def _relation(relations: pl.DataFrame, source: str, target: str) -> float:
    row = relations.filter((pl.col("source") == source) & (pl.col("target") == target))
    return float(row["value"][0])
