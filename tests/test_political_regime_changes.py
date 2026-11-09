from __future__ import annotations

import json
from dataclasses import replace

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from modules.base.systems.politics.political_crisis_policy import (
    _decode_path_records,
    _decode_records,
    _decode_string_list,
    _finite,
    _integer,
    _percentage,
    assess_regime_change,
    evaluate_crisis_transitions,
    normalize_crisis_rules,
    normalize_regime_change_paths,
)
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


def _assessment_arguments(state: GameState) -> dict[str, object]:
    path = normalize_regime_change_paths(_paths())[0]
    return {
        "paths": (path,),
        "path_id": path.path_id,
        "crisis": state.get_table("political_crises").filter(pl.col("id") == "crisis-1").row(0, named=True),
        "current_form_id": "military-led state",
        "government": state.get_table("country_governments").filter(pl.col("country_id") == "AAA").row(0, named=True),
        "country": state.get_table("countries").filter(pl.col("id") == "AAA").row(0, named=True),
        "form_rules": state.get_table("government_form_rules").to_dicts(),
        "parties": state.get_table("political_parties").filter(pl.col("country_id") == "AAA").to_dicts(),
        "laws": state.get_table("country_laws").filter(pl.col("country_id") == "AAA").to_dicts(),
        "countries": state.get_table("countries").to_dicts(),
        "relations": state.get_table("countries_relations").to_dicts(),
        "now_minute": state.time.total_minutes,
    }


def test_crisis_rule_normalization_rejects_malformed_records_and_generates_ids() -> None:
    valid = {"type": "protest", "metric": "approval", "threshold": 50, "priority": 3}
    records = [
        {**valid, "type": "war"},
        {**valid, "direction": "sideways"},
        {**valid, "recovery_threshold": 50},
        {**valid, "priority": 100_001},
        {**valid, "id": "bad-delta", "approval_delta": "NaN"},
        valid,
        valid,
    ]

    rules = normalize_crisis_rules(records)

    assert len(rules) == 1
    assert rules[0].rule_id == "protest-approval-50-3"
    assert rules[0].recovery_threshold == 55
    assert rules[0].approval_delta == 0


def test_crisis_transitions_ignore_missing_metrics_and_decode_supported_shapes() -> None:
    rules = normalize_crisis_rules(
        '{"thresholds":[{"type":"strike","metric":"stability","threshold":40}]}'
    )

    assert len(rules) == 1
    assert normalize_crisis_rules("{malformed") == ()
    assert normalize_crisis_rules('{"other": []}') == ()
    assert _decode_records([{"type": "protest"}, None, "ignored"]) == [{"type": "protest"}]
    assert _decode_records("42") == []
    assert _decode_records('{"rules":[{"id":"r"}]}') == [{"id": "r"}]

    transitions = evaluate_crisis_transitions(rules, {"gvt_approval": 20}, [])

    assert transitions == ()


def test_regime_path_normalization_filters_invalid_shapes_and_bounds_effects() -> None:
    valid = _paths()[0]
    invalid_records = [
        {**valid, "crisis_types": 12},
        {**valid, "minimum_support": 1.1},
        {**valid, "law_values": []},
        {**valid, "law_values": {"": "value"}},
        {**valid, "relation_effects": {}},
        {**valid, "relation_effects": ["not an effect"]},
        {
            **valid,
            "relation_effects": [
                {"target_country_id": "BBB", "delta": 1, "reciprocal": True},
                {"target_country_id": "BBB", "delta": 2, "reciprocal": True},
            ],
        },
        {**valid, "outcome": {"approval_delta": "NaN"}},
    ]

    assert all(normalize_regime_change_paths([record]) == () for record in invalid_records)
    normalized = normalize_regime_change_paths(
        [{"id": "single-type", "crisis_type": "coup_attempt", "outcome": []}]
    )
    assert len(normalized) == 1
    assert normalized[0].crisis_types == frozenset({"coup_attempt"})
    assert _decode_path_records([{"id": "x"}, None]) == [{"id": "x"}]
    assert _decode_path_records('{"paths":[{"id":"y"}]}') == [{"id": "y"}]
    assert _decode_path_records("{malformed") == []
    assert _decode_path_records("42") == []
    assert _decode_string_list(["A", 1, "B"]) == ["A", "B"]
    assert _decode_string_list('{"not":"a list"}') == []
    assert _decode_string_list("{malformed") == []


def test_regime_change_assessment_rejects_stale_or_unavailable_targets() -> None:
    cases: list[tuple[str, dict[str, object], str]] = []

    args = _assessment_arguments(_state(support=0.9))
    args["path_id"] = "unknown"
    cases.append(("unknown path", args, "not configured"))

    args = _assessment_arguments(_state(support=0.9))
    args["crisis"] = {**args["crisis"], "status": "resolved"}  # type: ignore[misc]
    cases.append(("resolved crisis", args, "no longer active"))

    args = _assessment_arguments(_state(support=0.9))
    args["crisis"] = {**args["crisis"], "crisis_type": "protest"}  # type: ignore[misc]
    cases.append(("wrong crisis type", args, "does not apply"))

    args = _assessment_arguments(_state(support=0.9))
    args["crisis"] = {**args["crisis"], "deadline_at_minute": "bad"}  # type: ignore[misc]
    cases.append(("invalid deadline", args, "deadline has passed"))

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (replace(path, government_form_id="missing form"),)
    cases.append(("missing form", args, "government form is unavailable"))

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (replace(path, ruling_party_id="missing party"),)
    cases.append(("missing party", args, "ruling party does not exist"))

    args = _assessment_arguments(_state(support=0.9))
    args["parties"] = [
        {**party, "eligible": False} if party["party_id"] == "beta" else party
        for party in args["parties"]  # type: ignore[union-attr]
    ]
    cases.append(("ineligible party", args, "not eligible"))

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (replace(path, ruling_party_id=""),)
    args["government"] = {**args["government"], "ruling_party_id": "missing"}  # type: ignore[misc]
    cases.append(("missing successor", args, "no valid successor"))

    args = _assessment_arguments(_state(support=0.9))
    args["laws"] = [*args["laws"], dict(args["laws"][0])]  # type: ignore[index]
    cases.append(("duplicate laws", args, "ambiguous duplicate"))

    args = _assessment_arguments(_state(support=0.9))
    args["laws"] = []
    cases.append(("missing law", args, "law 'party_system' is unavailable"))

    args = _assessment_arguments(_state(support=0.9))
    args["laws"] = [
        {**law, "allowed_values_json": '["Single-party"]'}
        for law in args["laws"]  # type: ignore[union-attr]
    ]
    cases.append(("forbidden law value", args, "value is not allowed"))

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (
        replace(path, relation_effects=(replace(path.relation_effects[0], target_country_id="AAA"),)),
    )
    cases.append(("self relation effect", args, "relation-effect target 'AAA' is unavailable"))

    args = _assessment_arguments(_state(support=0.9))
    args["relations"] = [
        {**relation, "value": "bad"} if relation["source"] == "AAA" else relation
        for relation in args["relations"]  # type: ignore[union-attr]
    ]
    cases.append(("nonnumeric relation", args, "non-numeric relation value"))

    for name, args, message in cases:
        assessment, reason = assess_regime_change(**args)
        assert assessment is None, name
        assert message in reason, name


def test_regime_change_assessment_handles_failure_and_election_boundaries() -> None:
    args = _assessment_arguments(_state(support=0.9))
    args["crisis"] = {**args["crisis"], "support": "bad"}  # type: ignore[misc]
    assessment, reason = assess_regime_change(**args)
    assert assessment is not None and not assessment.success
    assert "support 0.000 is below" in assessment.reason
    assert reason == ""

    args = _assessment_arguments(_state(support=0.9))
    args["form_rules"] = [
        {**rule, "election_interval_minutes": -1}
        if rule["government_form_id"] == "transitional republic"
        else rule
        for rule in args["form_rules"]  # type: ignore[union-attr]
    ]
    assessment, reason = assess_regime_change(**args)
    assert assessment is None and "interval is invalid" in reason

    args = _assessment_arguments(_state(support=0.9))
    args["now_minute"] = 9_223_372_036_854_775_807
    assessment, reason = assess_regime_change(**args)
    assert assessment is None and "exceeds the supported" in reason

    args = _assessment_arguments(_state(support=0.9))
    args["now_minute"] = "bad"
    assessment, reason = assess_regime_change(**args)
    assert assessment is None and "schedule is invalid" in reason

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (
        replace(path, minimum_support=0.95, minimum_approval=70, minimum_stability=60),
    )
    assessment, reason = assess_regime_change(**args)
    assert assessment is not None and not assessment.success
    assert "support" in assessment.reason
    assert "approval" in assessment.reason
    assert "stability" in assessment.reason
    assert reason == ""

    args = _assessment_arguments(_state(support=0.9))
    path = args["paths"][0]  # type: ignore[index]
    args["paths"] = (
        replace(path, government_form_id="", ruling_party_id="", relation_effects=()),
    )
    args["crisis"] = {
        **args["crisis"],
        "proposed_ruling_party_id": "",
    }  # type: ignore[misc]
    args["laws"] = [
        *args["laws"],
        {**args["laws"][0], "country_id": "BBB"},  # type: ignore[index]
    ]
    args["relations"] = None
    assessment, reason = assess_regime_change(**args)
    assert assessment is not None and assessment.success
    assert assessment.next_election_at_minute == 0
    assert reason == ""


def test_percentage_and_numeric_parsers_use_safe_defaults_and_bounds() -> None:
    assert _percentage("invalid", 42.0) == 42.0
    assert _percentage("0.5", 42.0) == 50.0
    assert _percentage(150, 42.0) == 100.0
    assert _finite("inf") is None
    assert _finite(None) is None
    assert _integer(True) is None
    assert _integer("bad") is None
    assert _integer(1.5) is None
