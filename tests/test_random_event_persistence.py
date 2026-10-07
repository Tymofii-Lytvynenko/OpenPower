from __future__ import annotations

import json

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.shared.config import GameConfig
from src.shared.events import EventNewDay
from src.shared.state import GameState
import tests.test_random_events_system as random_event_fixture


def test_random_event_state_survives_snapshot_save_load_and_deterministic_continuation(tmp_path):
    state = random_event_fixture._state(seed=357)
    state.globals["player_country_map"] = {"player-1": "AAA"}
    system = RandomEventsSystem()
    system.update(state, 0.0)
    state.current_actions = [
        ActionSetRandomEventControls(player_id="local_player", seed=50_051)
    ]
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    system.update(state, 0.0)
    instance = state.tables["random_event_instances"].row(0, named=True)
    response_id = json.loads(instance["response_options_json"])[0]["response_id"]
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
    state.current_actions = []

    snapshot = GameState.from_ipc(state.to_ipc())
    build_base_schema_registry().ensure_state(snapshot)
    for table in (
        "random_event_instances",
        "random_event_effects",
        "random_event_responses",
        "random_event_controls",
        "random_event_cooldowns",
    ):
        assert snapshot.get_table(table).to_dicts() == state.get_table(table).to_dicts()

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "random-events")
    loaded = DataLoader(
        config,
        schema_registry=build_base_schema_registry(),
    ).load_save("random-events")
    for table in (
        "random_event_instances",
        "random_event_effects",
        "random_event_responses",
        "random_event_controls",
        "random_event_cooldowns",
    ):
        assert loaded.get_table(table).to_dicts() == state.get_table(table).to_dicts()
    assert loaded.globals["random_event_seed"] == state.globals["random_event_seed"]
    assert loaded.globals["random_event_rng_state"] == state.globals["random_event_rng_state"]

    for candidate in (state, loaded):
        candidate.time.total_minutes += 1_440
        candidate.current_actions = []
        candidate.events = [
            EventNewDay(candidate.time.day, candidate.time.month, candidate.time.year)
        ]
        RandomEventsSystem().update(candidate, 0.0)
    assert state.get_table("random_event_instances").to_dicts() == loaded.get_table("random_event_instances").to_dicts()
    assert state.get_table("random_event_effects").to_dicts() == loaded.get_table("random_event_effects").to_dicts()
