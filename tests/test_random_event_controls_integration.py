from __future__ import annotations

from dataclasses import replace
import json

import polars as pl

import tests.test_random_event_responses as response_fixture
import tests.test_random_events_system as random_event_fixture
from modules.base.systems.world.random_event_policy import EVENT_BY_TYPE
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.shared.events import EventNewDay


def test_admin_controls_seed_frequency_and_global_disable_share_one_command_path() -> None:
    state = random_event_fixture._state(seed=99)
    system = RandomEventsSystem()
    system.update(state, 0.0)
    state.current_actions = [
        ActionSetRandomEventControls(
            player_id="local_player",
            enabled=False,
            frequency_multiplier=1.5,
            maximum_active_events=7,
            seed=4_242,
        )
    ]
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]

    system.update(state, 0.0)

    assert state.globals["random_events_enabled"] is False
    assert state.globals["random_event_frequency_multiplier"] == 1.5
    assert state.globals["random_event_max_active_events"] == 7
    assert state.globals["random_event_seed"] == 4_242
    assert state.tables["random_event_instances"].is_empty()
    assert state.journal.command_results[-1]["status"] == "applied"


def test_category_disable_and_invalid_admin_commands_do_not_partially_apply() -> None:
    state = random_event_fixture._state()
    system = RandomEventsSystem()
    system.update(state, 0.0)
    controls = state.tables["random_event_controls"].with_columns(
        (pl.col("category") == "health").alias("enabled")
    )
    state.update_table("random_event_controls", controls)
    state.current_actions = [
        ActionSetRandomEventControls(
            player_id="local_player",
            category="health",
            category_enabled=False,
        )
    ]
    state.events = []
    system.update(state, 0.0)

    assert not state.tables["random_event_controls"].filter(
        pl.col("category") == "health"
    ).item(0, "enabled")

    prior_seed = state.globals.get("random_event_seed")
    prior_frequency = state.globals["random_event_frequency_multiplier"]
    state.current_actions = [
        ActionSetRandomEventControls(
            player_id="unauthorized-player",
            frequency_multiplier=3.0,
            seed=2,
        )
    ]
    system.update(state, 0.0)

    assert state.globals.get("random_event_seed") == prior_seed
    assert state.globals["random_event_frequency_multiplier"] == prior_frequency
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_scenario_seed_replays_instances_independently_of_world_seed() -> None:
    states = [random_event_fixture._state(seed=1), random_event_fixture._state(seed=888)]
    systems = [RandomEventsSystem(), RandomEventsSystem()]
    for state, system in zip(states, systems):
        system.update(state, 0.0)
        state.current_actions = [
            ActionSetRandomEventControls(
                player_id="local_player",
                seed=21_337,
            )
        ]
        state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
        system.update(state, 0.0)

    first = states[0].tables["random_event_instances"].row(0, named=True)
    second = states[1].tables["random_event_instances"].row(0, named=True)
    assert (first["id"], first["event_type"], first["region_id"], first["seed"], first["severity"]) == (
        second["id"], second["event_type"], second["region_id"], second["seed"], second["severity"]
    )


def test_response_timing_rejects_early_choice_without_spending(monkeypatch) -> None:
    state, system, instance = response_fixture._active_event_state()
    options = json.loads(instance["response_options_json"])
    chosen = options[0]["response_id"]
    definition = EVENT_BY_TYPE[instance["event_type"]]
    delayed_response = replace(definition.responses[0], available_after_days=1)
    monkeypatch.setitem(
        EVENT_BY_TYPE,
        instance["event_type"],
        replace(definition, responses=(delayed_response, *definition.responses[1:])),
    )
    state.current_actions = [
        ActionRespondToRandomEvent(
            player_id="player-1",
            event_id=instance["id"],
            response_id=chosen,
            country_tag="AAA",
        )
    ]
    state.events = []
    balance = state.tables["countries"].item(0, "money_reserves")

    system.update(state, 0.0)

    assert state.tables["random_event_responses"].is_empty()
    assert state.tables["countries"].item(0, "money_reserves") == balance
    assert state.journal.command_results[-1]["status"] == "rejected"
