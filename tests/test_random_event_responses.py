import json

import polars as pl
import pytest

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.actions import ActionRespondToRandomEvent
from src.shared.determinism import DeterminismState
from src.shared.events import EventNewDay
from src.shared.state import GameState


def _active_event_state() -> tuple[GameState, RandomEventsSystem, dict]:
    state = GameState(determinism=DeterminismState(seed=42))
    build_base_schema_registry().ensure_state(state)
    state.update_table("countries", pl.DataFrame({"id": ["AAA"], "money_reserves": [100_000.0]}))
    state.update_table(
        "regions",
        pl.DataFrame({"id": pl.Series([17], dtype=pl.Int32), "owner": ["AAA"], "name": ["Capital"]}),
    )
    state.time.total_minutes = 1_440
    state.globals["random_event_daily_chance"] = 1.0
    state.globals["player_country_map"] = {"player-1": "AAA"}
    system = RandomEventsSystem()
    system.update(state, 0.0)
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    system.update(state, 0.1)
    return state, system, state.tables["random_event_instances"].row(0, named=True)


def _first_response(instance: dict) -> str:
    options = json.loads(instance["response_options_json"])
    return options[0]["response_id"]


def test_valid_response_deducts_once_records_choice_and_mitigates_adverse_effects() -> None:
    state, system, instance = _active_event_state()
    response_id = _first_response(instance)
    before_money = float(state.tables["countries"]["money_reserves"][0])
    before_effects = {
        row["id"]: float(row["magnitude"])
        for row in state.tables["random_event_effects"].filter(
            pl.col("event_id") == instance["id"]
        ).iter_rows(named=True)
    }
    state.current_actions = [
        ActionRespondToRandomEvent(
            player_id="player-1",
            event_id=instance["id"],
            response_id=response_id,
            country_tag="AAA",
        )
    ]
    state.events = []

    system.update(state, 0.0)

    updated = state.tables["random_event_instances"].row(0, named=True)
    response = state.tables["random_event_responses"].row(0, named=True)
    assert updated["response_id"] == response_id
    assert response["status"] == "applied"
    assert response["country_id"] == "AAA"
    assert 0.0 < response["cost"] <= before_money
    assert float(state.tables["countries"]["money_reserves"][0]) == before_money - response["cost"]
    for row in state.tables["random_event_effects"].filter(
        pl.col("event_id") == instance["id"]
    ).iter_rows(named=True):
        previous = before_effects[row["id"]]
        if row["category"].startswith("infrastructure_") or previous < 0.0:
            assert abs(float(row["magnitude"])) < abs(previous)


def test_duplicate_response_is_rejected_without_a_second_charge() -> None:
    state, system, instance = _active_event_state()
    response_id = _first_response(instance)
    action = ActionRespondToRandomEvent(
        player_id="player-1",
        event_id=instance["id"],
        response_id=response_id,
        country_tag="AAA",
    )
    state.current_actions = [action]
    state.events = []
    system.update(state, 0.0)
    after_first = float(state.tables["countries"].item(0, "money_reserves"))

    state.current_actions = [action]
    system.update(state, 0.0)

    assert float(state.tables["countries"].item(0, "money_reserves")) == after_first
    assert state.tables["random_event_responses"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"


@pytest.mark.parametrize(
    "response_id,country_tag,actor_id,balance",
    [
        ("not-an-option", "AAA", "player-1", 100_000.0),
        ("valid", "AAA", "unauthorized", 100_000.0),
        ("valid", "BBB", "player-1", 100_000.0),
        ("valid", "AAA", "player-1", 0.0),
    ],
)
def test_invalid_response_is_atomic(
    response_id: str,
    country_tag: str,
    actor_id: str,
    balance: float,
) -> None:
    state, system, instance = _active_event_state()
    if response_id == "valid":
        response_id = _first_response(instance)
    state.update_table(
        "countries",
        state.tables["countries"].with_columns(pl.lit(balance).alias("money_reserves")),
    )
    before_effects = state.tables["random_event_effects"].filter(
        pl.col("event_id") == instance["id"]
    )
    state.current_actions = [
        ActionRespondToRandomEvent(
            player_id=actor_id,
            event_id=instance["id"],
            response_id=response_id,
            country_tag=country_tag,
        )
    ]
    state.events = []

    system.update(state, 0.0)

    assert float(state.tables["countries"]["money_reserves"][0]) == balance
    assert state.tables["random_event_responses"].is_empty()
    assert state.tables["random_event_instances"].row(0, named=True)["response_id"] == ""
    assert state.tables["random_event_effects"].equals(before_effects)
    assert state.journal.command_results[-1]["status"] == "rejected"
