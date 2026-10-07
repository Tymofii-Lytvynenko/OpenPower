import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.random_event_policy import EVENT_DEFINITIONS
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.determinism import DeterminismState
from src.shared.events import EventNewDay, EventRandomEventLifecycleChanged, EventRandomEventTriggered
from src.shared.state import GameState


def _state(seed: int = 1) -> GameState:
    state = GameState(determinism=DeterminismState(seed=seed))
    build_base_schema_registry().ensure_state(state)
    state.update_table(
        "countries",
        pl.DataFrame({"id": ["AAA"], "money_reserves": [100_000.0]}),
    )
    state.update_table(
        "regions",
        pl.DataFrame(
            {
                "id": pl.Series([101, 102], dtype=pl.Int32),
                "owner": ["AAA", "AAA"],
                "name": ["North", "South"],
            }
        ),
    )
    state.time.total_minutes = 1_440
    state.globals["random_event_daily_chance"] = 1.0
    return state


def _seed_controls(system: RandomEventsSystem, state: GameState) -> None:
    system.update(state, 0.0)


def _trigger(system: RandomEventsSystem, state: GameState) -> None:
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    system.update(state, 0.1)


def test_due_daily_roll_creates_one_seeded_inspectable_instance_and_effects() -> None:
    state = _state(4)
    system = RandomEventsSystem()
    _seed_controls(system, state)

    _trigger(system, state)

    instances = state.tables["random_event_instances"]
    assert instances.height == 1
    instance = instances.row(0, named=True)
    assert instance["status"] == "active"
    assert instance["region_id"] in {101, 102}
    assert instance["country_id"] == "AAA"
    assert instance["seed"] > 0
    assert instance["expires_at_minute"] > instance["starts_at_minute"]
    assert 0.2 <= instance["severity"] <= 1.0
    assert state.tables["random_event_effects"].filter(
        pl.col("event_id") == instance["id"]
    ).height > 0
    assert any(isinstance(event, EventRandomEventTriggered) for event in state.events)


def test_identical_seed_and_world_state_replay_the_same_instance() -> None:
    first_state = _state(123)
    second_state = _state(123)
    first_system = RandomEventsSystem()
    second_system = RandomEventsSystem()
    _seed_controls(first_system, first_state)
    _seed_controls(second_system, second_state)

    _trigger(first_system, first_state)
    _trigger(second_system, second_state)

    first = first_state.tables["random_event_instances"].row(0, named=True)
    second = second_state.tables["random_event_instances"].row(0, named=True)
    assert {
        key: first[key]
        for key in ("id", "event_type", "region_id", "seed", "severity", "expires_at_minute")
    } == {
        key: second[key]
        for key in ("id", "event_type", "region_id", "seed", "severity", "expires_at_minute")
    }


def test_disabled_categories_and_global_disable_prevent_new_instances() -> None:
    state = _state()
    system = RandomEventsSystem()
    _seed_controls(system, state)
    controls = state.tables["random_event_controls"].with_columns(
        pl.lit(False).alias("enabled")
    )
    state.update_table("random_event_controls", controls)

    _trigger(system, state)
    assert state.tables["random_event_instances"].is_empty()

    state.update_table(
        "random_event_controls",
        controls.with_columns(pl.lit(True).alias("enabled")),
    )
    state.globals["random_events_enabled"] = False
    state.time.total_minutes += 1_440
    _trigger(system, state)
    assert state.tables["random_event_instances"].is_empty()


def test_active_cap_prevents_an_extra_instance() -> None:
    state = _state()
    system = RandomEventsSystem()
    _seed_controls(system, state)
    state.globals["random_event_max_active_events"] = 1
    _trigger(system, state)
    assert state.tables["random_event_instances"].filter(pl.col("status") == "active").height == 1

    state.time.total_minutes += 1_440
    _trigger(system, state)
    assert state.tables["random_event_instances"].height == 1


def test_missing_target_records_skipped_event_once() -> None:
    state = _state()
    state.update_table(
        "regions",
        pl.DataFrame(
            {
                "id": pl.Series([], dtype=pl.Int32),
                "owner": pl.Series([], dtype=pl.Utf8),
                "name": pl.Series([], dtype=pl.Utf8),
            }
        ),
    )
    system = RandomEventsSystem()
    _seed_controls(system, state)

    _trigger(system, state)

    instances = state.tables["random_event_instances"]
    assert instances.height == 1
    assert instances.row(0, named=True)["status"] == "skipped"
    assert any(
        isinstance(event, EventRandomEventLifecycleChanged) and event.status == "skipped"
        for event in state.events
    )


def test_cooldown_blocks_matching_target_and_due_boundary_resolves_event() -> None:
    state = _state(8)
    system = RandomEventsSystem()
    _seed_controls(system, state)
    _trigger(system, state)
    first = state.tables["random_event_instances"].row(0, named=True)

    cooldown_rows = [
        {
            "event_type": definition.event_type,
            "target_scope": "region",
            "target_id": str(region_id),
            "cooldown_until_minute": first["expires_at_minute"] + 100_000,
        }
        for definition in EVENT_DEFINITIONS
        for region_id in (101, 102)
    ]
    state.update_table(
        "random_event_cooldowns",
        pl.DataFrame(cooldown_rows, schema=state.tables["random_event_cooldowns"].schema),
    )
    state.events = []
    state.time.total_minutes = first["starts_at_minute"] + 1_440
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    system.update(state, 0.1)
    assert state.tables["random_event_instances"].height == 1

    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    state.time.total_minutes = first["expires_at_minute"] + 1
    system.update(state, 0.1)
    resolved = state.tables["random_event_instances"].filter(
        pl.col("id") == first["id"]
    ).row(0, named=True)
    assert resolved["status"] == "resolved"
    assert any(isinstance(event, EventRandomEventLifecycleChanged) for event in state.events)


def test_legacy_active_event_is_imported_once_without_losing_known_fields() -> None:
    state = _state()
    state.globals["active_events"] = [
        {
            "id": "legacy-quake",
            "event_type": "earthquake",
            "label": "Legacy quake",
            "region_id": 101,
            "severity": 0.6,
            "start_minute": 500,
            "expire_minute": 5_000,
        }
    ]
    system = RandomEventsSystem()

    system.update(state, 0.0)
    system.update(state, 0.0)

    instances = state.tables["random_event_instances"]
    assert instances.height == 1
    row = instances.row(0, named=True)
    assert row["id"] == "legacy-quake"
    assert row["region_id"] == 101
    assert row["severity"] == 0.6
    assert row["starts_at_minute"] == 500
