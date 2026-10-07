from __future__ import annotations

import json

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.shared.actions import ActionSetElectionOverride
from src.shared.events import EventPoliticalElectionOverrideApplied
from src.shared.state import GameState


MINUTES_PER_DAY = 24 * 60


def test_postponement_updates_the_authoritative_date_and_applies_cost_and_consequences_once() -> None:
    state = _state(
        [
            {
                "type": "postpone",
                "minimum_duration_days": 2,
                "maximum_duration_days": 30,
                "cost": 10.0,
                "cooldown_days": 10,
                "approval_delta": -5.0,
                "stability_delta": -3.0,
            }
        ]
    )
    lifecycle = PoliticalLifecycleSystem()
    lifecycle.update(state, 0.0)
    state.current_actions = [ActionSetElectionOverride("player-1", "AAA", "postpone", 3)]

    lifecycle.update(state, 0.0)

    expected_date = 5_000 + 3 * MINUTES_PER_DAY
    government = state.get_table("country_governments").row(0, named=True)
    election = state.get_table("political_elections").filter(pl.col("status") == "scheduled").row(0, named=True)
    assert government["next_election_at_minute"] == expected_date
    assert election["scheduled_at_minute"] == expected_date
    assert election["override_type"] == "postpone"
    assert state.get_table("countries")["money_reserves"][0] == 90.0
    assert state.get_table("countries")["gvt_approval"][0] == 60.0
    assert state.get_table("countries")["gvt_stability"][0] == 55.0
    assert state.get_table("political_history").filter(
        pl.col("event_type") == "election_override_applied"
    ).height == 1
    assert any(isinstance(event, EventPoliticalElectionOverrideApplied) for event in state.events)
    consequences = state.get_table("political_effects").filter(
        pl.col("source_type") == "election_override"
    )
    assert consequences.height == 2
    assert set(consequences["status"].to_list()) == {"pending"}
    assert [row["status"] for row in state.journal.command_results[-1:]] == ["applied"]

    state.current_actions = []
    politics = PoliticsSystem()
    politics.update(state, 0.0)
    assert state.get_table("countries")["gvt_approval"][0] == 55.0
    assert state.get_table("countries")["gvt_stability"][0] == 52.0
    politics.update(state, 0.0)
    assert state.get_table("countries")["gvt_approval"][0] == 55.0
    assert state.get_table("countries")["gvt_stability"][0] == 52.0
    assert set(
        state.get_table("political_effects").filter(
            pl.col("source_type") == "election_override"
        )["status"].to_list()
    ) == {"applied"}


@pytest.mark.parametrize(
    ("override_type", "duration_days", "expected_date", "expected_ruling_party"),
    [
        ("accelerate", 10, 1_000 + 5 * MINUTES_PER_DAY, "alpha"),
        ("suspend", 10, 1_000 + 10 * MINUTES_PER_DAY, "alpha"),
        ("succession", 3, 1_000 + 3 * MINUTES_PER_DAY, "bravo"),
    ],
)
def test_configured_override_types_respect_their_date_rules(
    override_type: str,
    duration_days: int,
    expected_date: int,
    expected_ruling_party: str,
) -> None:
    config = {
        "type": override_type,
        "minimum_duration_days": 1,
        "maximum_duration_days": 30,
        "minimum_notice_days": 5,
        "cost": 0.0,
        "cooldown_days": 0,
    }
    state = _state([config], next_election=9_000 if override_type == "accelerate" else 5_000)
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    state.current_actions = [
        ActionSetElectionOverride("player-1", "AAA", override_type, duration_days)
    ]

    system.update(state, 0.0)

    government = state.get_table("country_governments").row(0, named=True)
    scheduled = state.get_table("political_elections").filter(pl.col("status") == "scheduled")
    assert government["next_election_at_minute"] == expected_date
    assert scheduled["scheduled_at_minute"][0] == expected_date
    assert scheduled["override_type"][0] == override_type
    assert government["ruling_party_id"] == expected_ruling_party
    assert set(state.get_table("regions")["owner"].drop_nulls().to_list()) <= {"AAA"}
    assert state.journal.command_results[-1]["status"] == "applied"


@pytest.mark.parametrize(
    "case",
    [
        "unauthorized",
        "unconfigured",
        "too_short",
        "too_long",
        "oversized_duration",
        "underfunded",
        "cooldown",
        "government_crisis",
        "active_crisis",
        "non_electoral",
        "invalid_cost",
    ],
)
def test_rejected_overrides_leave_authoritative_political_state_unchanged(case: str) -> None:
    config = {
        "type": "postpone",
        "minimum_duration_days": 2,
        "maximum_duration_days": 30,
        "cost": 10.0,
        "cooldown_days": 10,
    }
    player_id = "player-1"
    duration = 3
    next_election = 5_000
    money = 100.0
    overrides = [config]
    government_changes: dict[str, object] = {}
    rule_changes: dict[str, object] = {}
    crisis_rows: list[dict[str, object]] = []
    history_rows: list[dict[str, object]] = []

    if case == "unauthorized":
        player_id = "player-2"
    elif case == "unconfigured":
        overrides = []
    elif case == "too_short":
        duration = 1
    elif case == "too_long":
        duration = 31
    elif case == "oversized_duration":
        duration = 36_501
        config["maximum_duration_days"] = duration
    elif case == "underfunded":
        money = 5.0
    elif case == "cooldown":
        history_rows.append(
            {
                "id": "prior-override",
                "country_id": "AAA",
                "event_type": "election_override_applied",
                "source_type": "action",
                "source_id": "prior-action",
                "game_minute": 1,
                "result": "applied",
            }
        )
    elif case == "government_crisis":
        government_changes["crisis_status"] = "government_crisis"
    elif case == "active_crisis":
        crisis_rows.append(
            {
                "id": "crisis-1",
                "country_id": "AAA",
                "crisis_type": "protest",
                "status": "active",
            }
        )
    elif case == "non_electoral":
        government_changes["election_eligible"] = False
        rule_changes["election_eligible"] = False
    elif case == "invalid_cost":
        config["cost"] = -1.0

    state = _state(
        overrides,
        money=money,
        government_changes=government_changes,
        rule_changes=rule_changes,
        crisis_rows=crisis_rows,
        history_rows=history_rows,
        next_election=next_election,
    )
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    protected_tables = (
        "countries",
        "country_governments",
        "political_parties",
        "political_elections",
        "political_effects",
        "political_history",
    )
    before = {name: state.get_table(name).clone() for name in protected_tables}
    state.current_actions = [
        ActionSetElectionOverride(player_id, "AAA", "postpone", duration)
    ]

    system.update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.journal.command_results[-1]["reason"]
    for name in protected_tables:
        assert state.get_table(name).equals(before[name]), name


def _state(
    overrides: list[dict[str, object]],
    *,
    next_election: int = 5_000,
    money: float = 100.0,
    government_changes: dict[str, object] | None = None,
    rule_changes: dict[str, object] | None = None,
    crisis_rows: list[dict[str, object]] | None = None,
    history_rows: list[dict[str, object]] | None = None,
) -> GameState:
    government = {
        "country_id": "AAA",
        "government_type": "Transitional republic",
        "government_form_id": "transitional republic",
        "ruling_party_id": "alpha",
        "succession_party_id": "bravo",
        "election_eligible": True,
        "next_election_at_minute": next_election,
        "crisis_status": "none",
        "initialized": True,
    }
    government.update(government_changes or {})
    form_rule = {
        "government_form_id": "transitional republic",
        "display_name": "Transitional republic",
        "election_eligible": True,
        "election_interval_minutes": 20_000,
        "election_turnout_base": 0.65,
        "law_permissions_json": '["*"]',
        "election_overrides_json": json.dumps(overrides),
    }
    form_rule.update(rule_changes or {})
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [60.0],
                    "gvt_stability": [55.0],
                    "gvt_corruption": [10.0],
                    "human_dev": [0.5],
                    "money_reserves": [money],
                }
            ),
            "country_governments": pl.DataFrame([government]),
            "government_form_rules": pl.DataFrame([form_rule]),
            "political_parties": pl.DataFrame(
                [
                    _party("alpha", 0.6, ruling=True),
                    _party("bravo", 0.4),
                ]
            ),
            "political_elections": pl.DataFrame(
                [
                    {
                        "id": "election-aaa-000000005000",
                        "country_id": "AAA",
                        "government_form_id": "transitional republic",
                        "scheduled_at_minute": next_election,
                        "status": "scheduled",
                        "reason": "Scenario election.",
                    }
                ]
            ),
            "political_crises": pl.DataFrame(crisis_rows or []),
            "political_history": pl.DataFrame(history_rows or []),
            "regions": pl.DataFrame(
                {"id": [1], "owner": ["AAA"], "controller": ["AAA"]}
            ),
        },
        globals={"player_country_map": {"player-1": "AAA"}, "tick": 5},
    )
    state.time.total_minutes = 1_000
    ensure_base_tables(state)
    return state


def _party(party_id: str, support: float, *, ruling: bool = False) -> dict[str, object]:
    return {
        "country_id": "AAA",
        "party_id": party_id,
        "display_name": party_id.title(),
        "support_share": support,
        "organization": 0.8,
        "policy_positions_json": "{}",
        "eligible": True,
        "is_ruling": ruling,
        "updated_at_minute": 0,
    }
