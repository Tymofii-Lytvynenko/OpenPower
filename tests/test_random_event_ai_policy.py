from __future__ import annotations

from modules.base.systems.world.ai.random_event_policy import choose_event_response
from modules.base.systems.world.random_event_policy import EventResponseDefinition
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.events import EventNewDay
import tests.test_random_events_system as random_event_fixture


def test_ai_policy_selects_available_most_effective_response_that_fits_treasury():
    responses = (
        EventResponseDefinition("cheap-low", "region_owner", 100.0, 0, 0.1, 0.0),
        EventResponseDefinition("best", "region_owner", 500.0, 0, 0.8, 0.05),
        EventResponseDefinition("delayed", "region_owner", 50.0, 2, 1.0, 0.0),
    )

    selected = choose_event_response(
        responses,
        treasury=600.0,
        starts_at_minute=1_440,
        now_minute=1_440,
    )

    assert selected is responses[1]


def test_ai_response_uses_the_same_authorized_payment_and_mitigation_path():
    state = random_event_fixture._state(seed=88)
    system = RandomEventsSystem()
    system.update(state, 0.0)
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    balance_before = state.tables["countries"].item(0, "money_reserves")

    system.update(state, 0.0)

    instance = state.tables["random_event_instances"].row(0, named=True)
    response = state.tables["random_event_responses"].row(0, named=True)
    assert instance["response_id"] == response["response_id"]
    assert response["player_id"] == "AI"
    assert state.tables["countries"].item(0, "money_reserves") == balance_before - response["cost"]
    assert state.journal.command_results[-1]["status"] == "applied"


def test_ai_does_not_respond_for_human_owned_country():
    state = random_event_fixture._state(seed=88)
    state.globals["player_country_map"] = {"human-player": "AAA"}
    system = RandomEventsSystem()
    system.update(state, 0.0)
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]

    system.update(state, 0.0)

    assert state.tables["random_event_responses"].is_empty()
    assert state.tables["random_event_instances"].item(0, "response_id") == ""
