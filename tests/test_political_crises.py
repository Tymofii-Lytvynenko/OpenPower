from __future__ import annotations

import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.client.ui.panels.politics.political_overview_presenter import PoliticalOverviewPresenter
from src.shared.events import EventNewDay, EventPoliticalCrisisChanged
from src.shared.state import GameState


def test_threshold_jump_escalates_once_in_stable_order_and_recovers() -> None:
    state = _state(_crisis_rules())
    system = PoliticsSystem()

    system.update(state, 0.0)

    crises = state.get_table("political_crises").sort("trigger")
    assert crises["crisis_type"].to_list() == ["paralysis", "protest", "strike"]
    assert set(crises["status"].to_list()) == {"active"}
    assert state.get_table("country_governments")["crisis_status"][0] == "paralysis"
    assert state.get_table("political_history").filter(
        pl.col("event_type") == "political_crisis_opened"
    ).height == 3
    assert len(
        [event for event in state.events if isinstance(event, EventPoliticalCrisisChanged)]
    ) == 3
    assert state.get_table("messages").filter(pl.col("category") == "politics").height == 3
    assert state.get_table("news_items").filter(pl.col("category") == "politics").height == 3
    overview = PoliticalOverviewPresenter().build(state, "AAA")
    assert overview.crisis_status == "paralysis"
    assert any(cause.event_type == "political_crisis_opened" for cause in overview.recent_causes)

    first_ids = crises["id"].to_list()
    replay_state = _state(_crisis_rules())
    PoliticsSystem().update(replay_state, 0.0)
    assert replay_state.get_table("political_crises").sort("trigger")["id"].to_list() == first_ids

    system.update(state, 0.0)
    assert state.get_table("political_crises").height == 3
    assert state.get_table("political_history").filter(
        pl.col("event_type") == "political_crisis_opened"
    ).height == 3

    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.lit(80.0).alias("gvt_approval"),
            pl.lit(80.0).alias("gvt_stability"),
        ),
    )
    system.update(state, 0.0)

    crises = state.get_table("political_crises")
    assert set(crises["status"].to_list()) == {"resolved"}
    assert set(crises["outcome"].to_list()) == {"recovered"}
    assert state.get_table("country_governments")["crisis_status"][0] == "none"
    assert state.get_table("political_history").filter(
        pl.col("event_type") == "political_crisis_recovered"
    ).height == 3


def test_crisis_consequences_are_bounded_and_attributed_to_their_crisis() -> None:
    rule = _crisis_rules()[0]
    rule.update(
        {
            "approval_delta": -500.0,
            "stability_delta": 800.0,
            "corruption_delta": -900.0,
        }
    )
    state = _state([rule])

    PoliticsSystem().update(state, 0.0)

    effects = state.get_table("political_effects").filter(
        pl.col("source_type") == "political_crisis"
    )
    assert set(effects["effect"].to_list()) == {
        "approval_delta",
        "stability_delta",
        "corruption_delta",
    }
    assert all(-100.0 <= value <= 100.0 for value in effects["value"].to_list())
    assert effects["source_id"].to_list() == [state.get_table("political_crises")["id"][0]] * 3


def test_crisis_indicator_effects_are_consumed_once_by_the_political_owner() -> None:
    rule = _crisis_rules()[0]
    rule.update(
        {
            "approval_delta": -6.0,
            "stability_delta": 8.0,
            "corruption_delta": 10.0,
        }
    )
    state = _state([rule])
    system = PoliticsSystem()
    system.update(state, 0.0)
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.lit(0.2).alias("gvt_approval"),
            pl.lit(0.15).alias("gvt_stability"),
            pl.lit(0.1).alias("gvt_corruption"),
        ),
    )
    state.events = []

    system.update(state, 0.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["gvt_approval"] == 14.0
    assert country["gvt_stability"] == 23.0
    assert country["gvt_corruption"] == 20.0
    assert set(state.get_table("political_effects")["status"].to_list()) == {"applied"}

    system.update(state, 0.0)
    unchanged = state.get_table("countries").row(0, named=True)
    assert unchanged["gvt_approval"] == country["gvt_approval"]
    assert unchanged["gvt_stability"] == country["gvt_stability"]
    assert unchanged["gvt_corruption"] == country["gvt_corruption"]


def _crisis_rules() -> list[dict[str, object]]:
    return [
        {
            "id": "protest-approval",
            "type": "protest",
            "metric": "approval",
            "threshold": 40.0,
            "direction": "below",
            "recovery_threshold": 50.0,
            "priority": 1,
            "approval_delta": -2.0,
            "stability_delta": -2.0,
        },
        {
            "id": "strike-approval",
            "type": "strike",
            "metric": "approval",
            "threshold": 25.0,
            "direction": "below",
            "recovery_threshold": 35.0,
            "priority": 2,
            "approval_delta": -3.0,
            "stability_delta": -4.0,
        },
        {
            "id": "paralysis-stability",
            "type": "paralysis",
            "metric": "stability",
            "threshold": 20.0,
            "direction": "below",
            "recovery_threshold": 30.0,
            "priority": 3,
            "approval_delta": -4.0,
            "stability_delta": -5.0,
        },
    ]


def _state(crisis_rules: list[dict[str, object]]) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [20.0],
                    "gvt_stability": [15.0],
                    "gvt_corruption": [10.0],
                    "human_dev": [0.5],
                    "economic_political_modifier": [1.0],
                }
            ),
            "country_governments": pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "government_type": ["Transitional republic"],
                    "government_form_id": ["transitional republic"],
                    "ruling_party_id": ["alpha"],
                    "election_eligible": [True],
                    "next_election_at_minute": [100_000],
                    "crisis_status": ["none"],
                    "initialized": [True],
                }
            ),
            "government_form_rules": pl.DataFrame(
                {
                    "government_form_id": ["transitional republic"],
                    "election_eligible": [True],
                    "election_interval_minutes": [100_000],
                    "crisis_rules_json": [json.dumps(crisis_rules)],
                }
            ),
        },
        globals={"tick": 1},
    )
    ensure_base_tables(state)
    state.time.total_minutes = 7 * 24 * 60
    state.time.day = 8
    state.events = [EventNewDay(8, 1, 2001)]
    return state
