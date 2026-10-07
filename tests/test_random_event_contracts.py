import polars as pl

from modules.base.schema import BASE_TABLE_SCHEMAS, build_base_schema_registry
from modules.base.systems.world.random_event_policy import EVENT_DEFINITIONS, validate_catalog
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.actions import ActionRespondToRandomEvent, ActionSetRandomEventControls
from src.shared.events import EventRandomEventTriggered
from src.shared.state import GameState
from src.shared.system_interfaces import system_access


def test_event_catalog_definitions_are_valid_and_bounded() -> None:
    assert validate_catalog() == ()
    assert len({definition.event_type for definition in EVENT_DEFINITIONS}) == len(EVENT_DEFINITIONS)
    assert all(0.0 <= definition.severity_minimum <= definition.severity_maximum <= 1.0 for definition in EVENT_DEFINITIONS)


def test_event_tables_have_typed_keys_and_persistent_fields() -> None:
    schemas = {schema.name: schema for schema in BASE_TABLE_SCHEMAS}
    expected_keys = {
        "random_event_instances": ("id",),
        "random_event_effects": ("id",),
        "random_event_responses": ("id",),
        "random_event_controls": ("category",),
        "random_event_cooldowns": ("event_type", "target_scope", "target_id"),
    }
    for name, keys in expected_keys.items():
        assert schemas[name].key_columns == keys

    state = GameState()
    build_base_schema_registry().ensure_state(state)
    assert state.tables["random_event_instances"].schema["seed"] == pl.Int64
    assert state.tables["random_event_effects"].schema["magnitude"] == pl.Float64
    assert state.tables["random_event_effects"].schema["mitigation_pending"] == pl.Boolean
    assert state.tables["random_event_responses"].schema["cost"] == pl.Float64
    assert state.tables["random_event_controls"].schema["enabled"] == pl.Boolean
    assert state.tables["random_event_cooldowns"].schema["cooldown_until_minute"] == pl.Int64


def test_actions_are_declared_and_legacy_trigger_constructor_still_works() -> None:
    access = system_access(RandomEventsSystem())
    assert ActionSetRandomEventControls in access.handles
    assert ActionRespondToRandomEvent in access.handles
    legacy_event = EventRandomEventTriggered("quake-1", "earthquake", 12, 0.5)
    assert legacy_event.seed == 0
    assert legacy_event.category == "disaster"
