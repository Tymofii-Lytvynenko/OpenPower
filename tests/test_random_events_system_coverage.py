from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import polars as pl

import modules.base.systems.world.random_events_system as random_event_module
import tests.test_random_event_responses as response_fixture
import tests.test_random_events_system as system_fixture
from modules.base.systems.world.random_event_policy import EVENT_BY_TYPE
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.shared.events import EventNewDay
from src.shared.state import GameState


def _response_action(instance: dict, response_id: str = "") -> ActionRespondToRandomEvent:
    return ActionRespondToRandomEvent(
        player_id="player-1",
        event_id=str(instance["id"]),
        response_id=response_id,
        country_tag="AAA",
    )


def test_update_skips_incomplete_world_and_processes_duplicate_day_once() -> None:
    RandomEventsSystem().update(GameState(), 0.0)

    state = system_fixture._state(17)
    system = RandomEventsSystem()
    system.update(state, 0.0)
    day = EventNewDay(state.time.day, state.time.month, state.time.year)
    state.events = [day, day]

    system.update(state, 0.0)

    assert state.tables["random_event_instances"].height == 1


def test_legacy_import_skips_bad_records_duplicates_and_unknown_owners() -> None:
    state = system_fixture._state()
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(pl.lit("UNKNOWN").alias("owner")),
    )
    state.globals["active_events"] = [
        "not a record",
        {"id": "bad", "region_id": "not-an-integer"},
        {
            "id": "legacy-duplicate",
            "event_type": "unknown_legacy_event",
            "region_id": 101,
            "start_minute": 1000,
            "expire_minute": 2000,
        },
        {
            "id": "legacy-duplicate",
            "event_type": "earthquake",
            "region_id": 102,
            "start_minute": 1000,
            "expire_minute": 2000,
        },
    ]

    RandomEventsSystem().update(state, 0.0)

    instances = state.tables["random_event_instances"]
    assert instances.height == 1
    assert instances.item(0, "id") == "legacy-duplicate"
    assert instances.item(0, "country_id") == ""


def test_due_effect_resolution_returns_for_empty_or_unmatched_rows() -> None:
    state = system_fixture._state()
    system = RandomEventsSystem()
    system._resolve_due_effects(state, ["missing"])

    system_fixture._seed_controls(system, state)
    system_fixture._trigger(system, state)
    assert not state.tables["random_event_effects"].is_empty()
    system._resolve_due_effects(state, ["another-event"])


def test_control_validation_rejects_invalid_values_and_updates_category_frequency() -> None:
    state = system_fixture._state()
    system = RandomEventsSystem()
    system.update(state, 0.0)
    invalid_actions = [
        ActionSetRandomEventControls(player_id="local_player"),
        ActionSetRandomEventControls(
            player_id="local_player", category="missing", category_enabled=False
        ),
        ActionSetRandomEventControls(player_id="local_player", frequency_multiplier=float("nan")),
        ActionSetRandomEventControls(player_id="local_player", frequency_multiplier=5.0),
        ActionSetRandomEventControls(player_id="local_player", maximum_active_events=True),
        ActionSetRandomEventControls(player_id="local_player", maximum_active_events=0),
        ActionSetRandomEventControls(player_id="local_player", seed=True),
    ]

    for action in invalid_actions:
        system._set_controls(state, action, 50)

    assert all(result["status"] == "rejected" for result in state.journal.command_results[-7:])

    system._set_controls(
        state,
        ActionSetRandomEventControls(
            player_id="local_player", category="health", frequency_multiplier=2.0
        ),
        60,
    )
    assert state.tables["random_event_controls"].filter(
        pl.col("category") == "health"
    ).item(0, "frequency_multiplier") == 2.0


def test_response_rejection_paths_cover_expired_missing_and_unavailable_targets(monkeypatch) -> None:
    state, system, instance = response_fixture._active_event_state()
    missing = _response_action({"id": "missing"}, "invalid")
    system._respond_to_event(state, missing, state.time.total_minutes, trusted_ai=True)
    assert state.journal.command_results[-1]["reason"] == "The selected event no longer exists."

    state, system, instance = response_fixture._active_event_state()
    state.update_table(
        "random_event_instances",
        state.tables["random_event_instances"].with_columns(
            pl.lit("resolved").alias("status")
        ),
    )
    system._respond_to_event(state, _response_action(instance), state.time.total_minutes, trusted_ai=True)
    assert "no longer active" in state.journal.command_results[-1]["reason"]

    state, system, instance = response_fixture._active_event_state()
    options = json.loads(instance["response_options_json"])
    chosen = options[0]["response_id"]
    definition = EVENT_BY_TYPE[instance["event_type"]]
    monkeypatch.setitem(
        EVENT_BY_TYPE,
        instance["event_type"],
        replace(
            definition,
            responses=(replace(definition.responses[0], authority_scope="global", available_after_days=0),),
        ),
    )
    system._respond_to_event(
        state,
        _response_action(instance, chosen),
        state.time.total_minutes,
        trusted_ai=True,
    )
    assert "authority is not supported" in state.journal.command_results[-1]["reason"]

    state, system, instance = response_fixture._active_event_state()
    state.update_table(
        "regions",
        state.tables["regions"].head(0),
    )
    options = json.loads(instance["response_options_json"])
    system._respond_to_event(
        state,
        _response_action(instance, options[0]["response_id"]),
        state.time.total_minutes,
        trusted_ai=True,
    )
    assert "target region no longer exists" in state.journal.command_results[-1]["reason"]


def test_response_rejects_unavailable_or_missing_funding_accounts(monkeypatch) -> None:
    state, system, instance = response_fixture._active_event_state()
    options = __import__("json").loads(instance["response_options_json"])
    state.tables.pop("countries")
    system._respond_to_event(
        state,
        _response_action(instance, options[0]["response_id"]),
        state.time.total_minutes,
        trusted_ai=True,
    )
    assert "funding account is unavailable" in state.journal.command_results[-1]["reason"]

    state, system, instance = response_fixture._active_event_state()
    options = __import__("json").loads(instance["response_options_json"])
    state.update_table(
        "countries",
        pl.DataFrame({"id": ["OTHER"], "money_reserves": [1000.0]}),
    )
    system._respond_to_event(
        state,
        _response_action(instance, options[0]["response_id"]),
        state.time.total_minutes,
        trusted_ai=True,
    )
    assert "funding country no longer exists" in state.journal.command_results[-1]["reason"]


def test_response_defensive_duplicate_checks_remain_effective(monkeypatch) -> None:
    state, system, instance = response_fixture._active_event_state()
    response_id = json.loads(instance["response_options_json"])[0]["response_id"]

    class ChangingId:
        reads = 0

        def __str__(self):
            self.reads += 1
            return "" if self.reads == 1 else "already-applied"

    class Matches:
        def is_empty(self):
            return False

        def row(self, *_args, **_kwargs):
            return {**instance, "response_id": ChangingId()}

    class Instances:
        @staticmethod
        def filter(*_args, **_kwargs):
            return Matches()

    state.tables["random_event_instances"] = Instances()
    rejections = []
    system._reject_response = lambda *args: rejections.append(args)
    system._respond_to_event(
        state,
        _response_action(instance, response_id),
        instance["expires_at_minute"] - 1,
        trusted_ai=True,
    )
    assert "already received a response" in rejections[-1][3]

    state, system, instance = response_fixture._active_event_state()
    definition = EVENT_BY_TYPE[instance["event_type"]]

    class ChangingDays:
        reads = 0

        def __mul__(self, _minutes):
            self.reads += 1
            return 0 if self.reads == 1 else 1

    delayed = SimpleNamespace(
        response_id="dynamic-timing",
        available_after_days=ChangingDays(),
    )
    monkeypatch.setitem(
        EVENT_BY_TYPE,
        instance["event_type"],
        replace(definition, responses=(delayed,)),
    )
    rejections = []
    system._reject_response = lambda *args: rejections.append(args)
    system._respond_to_event(
        state,
        _response_action(instance, "dynamic-timing"),
        instance["starts_at_minute"],
        trusted_ai=True,
    )
    assert "not available yet" in rejections[-1][3]


def test_daily_probability_and_weighted_choice_handle_degenerate_inputs(monkeypatch) -> None:
    monkeypatch.setattr(random_event_module, "EVENT_DEFINITIONS", [])
    assert RandomEventsSystem._daily_chance([], {}, 1.0, 0.5) == 0.0

    system = RandomEventsSystem()
    zero_weight = SimpleNamespace(weight=0.0, category="health")
    controls = {"health": {"frequency_multiplier": 1.0}}
    assert system._weighted_choice([zero_weight], controls, SimpleNamespace()) is zero_weight

    definitions = [
        SimpleNamespace(weight=1.0, category="health"),
        SimpleNamespace(weight=1.0, category="labor"),
    ]
    weighted_controls = {
        "health": {"frequency_multiplier": 1.0},
        "labor": {"frequency_multiplier": 1.0},
    }
    runtime = SimpleNamespace(uniform=lambda low, high: high)
    assert system._weighted_choice(definitions, weighted_controls, runtime) is definitions[-1]


def test_daily_roll_falls_back_for_bad_chance_and_stops_when_frequency_is_disabled() -> None:
    state = system_fixture._state()
    system = RandomEventsSystem()
    system.update(state, 0.0)
    runtime = SimpleNamespace(random=lambda: 1.0)

    state.globals["random_event_frequency_multiplier"] = 0.0
    assert system._roll_daily_event(state, state.time.total_minutes, runtime) is False

    state.globals["random_event_frequency_multiplier"] = 1.0
    state.globals["random_event_daily_chance"] = "invalid"
    assert system._roll_daily_event(state, state.time.total_minutes, runtime) is False

    state.update_table("regions", state.tables["regions"].head(0))
    state.globals["random_event_daily_chance"] = 1.0
    assert system._roll_daily_event(state, state.time.total_minutes, runtime) is False


def test_ai_event_skips_missing_world_targets_and_unavailable_responses(monkeypatch) -> None:
    state, system, _instance = response_fixture._active_event_state()
    state.tables.pop("countries")
    system._auto_respond_to_ai_events(state, state.time.total_minutes)

    state, system, _instance = response_fixture._active_event_state()
    state.update_table("regions", state.tables["regions"].with_columns(pl.lit("AI").alias("owner")))
    state.update_table("countries", pl.DataFrame({"id": ["OTHER"], "money_reserves": [1000.0]}))
    state.globals["player_country_map"] = {}
    state.globals["player_tag"] = ""
    system._auto_respond_to_ai_events(state, state.time.total_minutes)

    state, system, _instance = response_fixture._active_event_state()
    state.update_table("regions", state.tables["regions"].with_columns(pl.lit("AI").alias("owner")))
    state.update_table("countries", pl.DataFrame({"id": ["AI"], "money_reserves": [1000.0]}))
    state.globals["player_country_map"] = {}
    state.globals["player_tag"] = ""
    monkeypatch.setattr(random_event_module, "choose_event_response", lambda *_args, **_kwargs: None)
    system._auto_respond_to_ai_events(state, state.time.total_minutes)


def test_random_event_indexes_cooldowns_and_persistence_helpers_cover_missing_rows() -> None:
    system = RandomEventsSystem()
    state = system_fixture._state()
    state.tables.pop("countries")
    assert system._country_ids(state) == set()

    state = system_fixture._state()
    state.update_table("regions", pl.DataFrame({"id": [1]}))
    assert system._eligible_region_rows(state) == []

    state = system_fixture._state()
    system._upsert_cooldown(
        state,
        {"event_type": "quake", "target_scope": "region", "target_id": "1", "cooldown_until_minute": 10},
    )
    system._upsert_cooldown(
        state,
        {"event_type": "quake", "target_scope": "region", "target_id": "1", "cooldown_until_minute": 20},
    )
    assert state.tables["random_event_cooldowns"].item(0, "cooldown_until_minute") == 20

    state.globals["random_event_seed"] = "invalid"
    _runtime, dedicated = system._event_runtime(state)
    assert dedicated is None
    system._write_rows(state, "random_event_controls", [])
    assert state.tables["random_event_controls"].is_empty()

    system._append_rows(state, "random_event_cooldowns", [{"event_type": "missing-fields"}])
    appended = state.tables["random_event_cooldowns"].filter(
        pl.col("event_type") == "missing-fields"
    )
    assert appended.height == 1
    assert appended.item(0, "target_id") is None
    assert system._finite("not-a-number") is None


def test_secondary_response_effect_rows_preserve_response_scope() -> None:
    rows = RandomEventsSystem._secondary_effect_rows(
        event_id="event-1",
        country_id="AAA",
        response=SimpleNamespace(
            response_id="mitigate",
            secondary_effects=(("approval", 2.0, "points"),),
        ),
        now=100,
        expires=500,
    )

    assert rows == [
        {
            "id": "event-1:response:mitigate:approval",
            "event_id": "event-1",
            "category": "approval",
            "subject_type": "country",
            "subject_id": "AAA",
            "magnitude": 2.0,
            "unit": "points",
            "application_mode": "immediate",
            "starts_at_minute": 100,
            "expires_at_minute": 500,
            "last_applied_at_minute": 0,
            "status": "pending",
            "mitigation_pending": False,
            "recovery_state_json": "{}",
        }
    ]
