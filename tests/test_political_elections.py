from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.election_policy import resolve_election
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.events import EventPoliticalElectionResolved
from src.shared.state import GameState


def test_election_policy_snapshots_eligible_support_and_breaks_ties_deterministically() -> None:
    parties = [
        _party("beta", 0.5, 1.0),
        _party("alpha", 0.5, 1.0),
        _party("excluded", 0.9, 1.0, eligible=False),
    ]
    rules = {
        "election_turnout_base": 0.6,
        "election_turnout_approval_weight": 0.003,
        "election_turnout_stability_weight": 0.002,
        "incumbent_advantage": 0.0,
    }

    first = resolve_election(
        parties,
        ruling_party_id="beta",
        approval=50.0,
        stability=50.0,
        form_rule=rules,
    )
    replay = resolve_election(
        parties,
        ruling_party_id="beta",
        approval=50.0,
        stability=50.0,
        form_rule=rules,
    )

    assert first == replay
    assert first.eligible_party_ids == ("alpha", "beta")
    assert first.winner_party_id == "alpha"
    assert first.coalition_party_ids == ("alpha",)
    assert first.turnout == 0.6
    assert json.loads(first.support_snapshot_json)["alpha"]["support_share"] == 0.5
    assert "excluded" not in json.loads(first.results_json)


def test_election_policy_forms_a_minimal_majority_coalition_in_rank_order() -> None:
    result = resolve_election(
        [
            _party("alpha", 0.4, 1.0),
            _party("bravo", 0.35, 1.0),
            _party("charlie", 0.25, 1.0),
        ],
        ruling_party_id="alpha",
        approval=50.0,
        stability=50.0,
        form_rule={"incumbent_advantage": 0.0, "coalition_threshold": 0.6},
    )

    assert result.winner_party_id == "alpha"
    assert result.coalition_party_ids == ("alpha", "bravo")


def test_incumbent_advantage_responds_to_approval_without_changing_tie_rules() -> None:
    parties = [_party("alpha", 0.5, 1.0), _party("beta", 0.5, 1.0)]
    rules = {"incumbent_advantage": 0.2, "coalition_threshold": 0.5}

    high_approval = resolve_election(
        parties,
        ruling_party_id="beta",
        approval=100.0,
        stability=50.0,
        form_rule=rules,
    )
    low_approval = resolve_election(
        parties,
        ruling_party_id="beta",
        approval=0.0,
        stability=50.0,
        form_rule=rules,
    )

    assert high_approval.winner_party_id == "beta"
    assert low_approval.winner_party_id == "alpha"


def test_election_policy_uses_an_incumbent_fallback_when_no_party_is_eligible() -> None:
    result = resolve_election(
        [_party("ruling", 0.2, 0.5, eligible=False)],
        ruling_party_id="ruling",
        approval=50.0,
        stability=0.5,
        form_rule={"election_turnout_base": 0.65},
    )

    assert result.winner_party_id == "ruling"
    assert result.eligible_party_ids == ("ruling",)
    assert result.turnout == 0.65

    successor_result = resolve_election(
        [_party("successor", 0.0, 0.5, eligible=False)],
        ruling_party_id="ruling",
        succession_party_id="successor",
        approval=50.0,
        stability=50.0,
        form_rule={"succession_rule": "configured_successor"},
    )
    assert successor_result.winner_party_id == "successor"


def test_due_election_resolves_once_and_schedules_the_next_configured_date() -> None:
    state = _state(next_election=110)
    system = PoliticalLifecycleSystem()

    system.update(state, 0.0)
    scheduled = state.get_table("political_elections")
    assert scheduled.height == 1
    assert scheduled["status"][0] == "scheduled"
    assert scheduled["scheduled_at_minute"][0] == 110

    state.time.total_minutes = 110
    state.current_actions = []
    state.events = []
    system.update(state, 0.0)

    elections = state.get_table("political_elections").sort("scheduled_at_minute")
    resolved = elections.filter(pl.col("status") == "resolved")
    future = elections.filter(pl.col("status") == "scheduled")
    government = state.get_table("country_governments").row(0, named=True)
    assert resolved.height == 1
    assert resolved["winner_party_id"][0] == "bravo"
    assert resolved["eligible_party_ids"].to_list()[0] == ["alpha", "bravo"]
    assert resolved["coalition_party_ids"].to_list()[0] == ["bravo"]
    assert abs(resolved["turnout"][0] - 0.69) < 1e-12
    assert future.height == 1
    assert future["scheduled_at_minute"][0] == 130
    assert government["ruling_party_id"] == "bravo"
    assert government["next_election_at_minute"] == 130
    assert state.get_table("political_parties").filter(pl.col("is_ruling"))["party_id"].to_list() == ["bravo"]
    assert any(isinstance(event, EventPoliticalElectionResolved) for event in state.events)
    assert state.get_table("political_history").height == 1
    assert state.get_table("messages").height == 1

    state.events = []
    system.update(state, 0.0)
    assert state.get_table("political_elections").height == 2
    assert not any(isinstance(event, EventPoliticalElectionResolved) for event in state.events)


def test_electoral_legacy_government_without_a_date_gets_a_four_year_default() -> None:
    state = _state(next_election=0, initialized=True, interval=0)
    state.time.total_minutes = 25

    PoliticalLifecycleSystem().update(state, 0.0)

    expected = 25 + 4 * 365 * 24 * 60
    assert state.get_table("country_governments")["next_election_at_minute"][0] == expected
    assert state.get_table("political_elections")["scheduled_at_minute"][0] == expected


def _state(*, next_election: int, initialized: bool = True, interval: int = 20) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [60.0],
                    "gvt_stability": [55.0],
                    "gvt_corruption": [10.0],
                    "human_dev": [0.5],
                    "money_reserves": [100.0],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "government_type": ["Transitional republic"],
                    "government_form_id": ["transitional republic"],
                    "ruling_party_id": ["alpha"],
                    "election_eligible": [True],
                    "next_election_at_minute": [next_election],
                    "succession_party_id": ["alpha"],
                    "crisis_status": ["none"],
                    "initialized": [initialized],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["transitional republic"],
                    "display_name": ["Transitional republic"],
                    "election_eligible": [True],
                    "election_interval_minutes": [interval],
                    "election_turnout_base": [0.65],
                    "election_turnout_approval_weight": [0.003],
                    "election_turnout_stability_weight": [0.002],
                    "incumbent_advantage": [0.1],
                    "law_permissions_json": ['["*"]'],
                }
            ),
            "political_parties": pl.DataFrame(
                [
                    _party("alpha", 0.4, 1.0, ruling=True),
                    _party("bravo", 0.6, 1.0),
                ]
            ),
        },
        globals={"tick": 3},
    )
    state.time.total_minutes = 100
    ensure_base_tables(state)
    return state


def _party(
    party_id: str,
    support: float,
    organization: float,
    *,
    eligible: bool = True,
    ruling: bool = False,
) -> dict:
    return {
        "country_id": "AAA",
        "party_id": party_id,
        "display_name": party_id.title(),
        "support_share": support,
        "organization": organization,
        "policy_positions_json": "{}",
        "eligible": eligible,
        "is_ruling": ruling,
        "updated_at_minute": 0,
    }
