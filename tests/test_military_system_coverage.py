from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

import modules.base.systems.military.military_system as military_module
from modules.base.systems.military.military_system import MilitarySystem, UNIT_SCHEMA
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


def test_military_system_adapters_forward_to_their_composed_services(monkeypatch):
    system = MilitarySystem()
    state = GameState()
    geo = GeoCoordinate(10.0, 20.0)
    preflight = SimpleNamespace(
        valid_hostile_attack=Mock(return_value=True),
        interpolate_row_geo=Mock(return_value=geo),
    )
    system._contact_transition_preflight = preflight
    assert system._valid_hostile_attack({"id": "A"}, {"id": "B"}, set(), state) is True
    assert system._interpolate_row_geo({"id": "A"}, 0.5) == geo

    monkeypatch.setattr(military_module, "player_controls_country", lambda *_args: True)
    assert system._deployment_actor_authorized(state, "player", "AAA") is True
    system._deployment_service.next_deployment_id = Mock(return_value="order-2")
    assert system._next_deployment_id("order", [{"id": "order-1"}]) == "order-2"

    movement_policy = SimpleNamespace(
        domain_for_unit=Mock(return_value="air"),
        has_domain_metadata=Mock(return_value=True),
        domain_route_compatible=Mock(return_value=True),
        region_is_water=Mock(return_value=False),
        bounded_multiplier=Mock(return_value=1.25),
        resolve_target_geo=Mock(return_value=geo),
    )
    system._movement_order_policy = movement_policy
    assert system._domain_for_unit({"unit_domain": "air"}) == "air"
    assert system._has_domain_route_metadata([]) is True
    assert system._domain_route_compatible("air", {}, {}, False, []) is True
    assert system._region_is_water({}) is False
    assert system._bounded_multiplier("bad", 1.0) == 1.25
    action = SimpleNamespace()
    assert system._resolve_action_target_geo(action, 1, {1: geo}) == geo

    workflow = SimpleNamespace(
        release_fortified_for_order=Mock(return_value=True),
        unit_is_transitioning=Mock(return_value=False),
        queue_move=Mock(return_value="move-1"),
        queue_attack=Mock(return_value="attack-1"),
        attach_pending_to_transition=Mock(),
        ensure_pending_table=Mock(return_value=pl.DataFrame()),
    )
    system._unit_order_workflow = workflow
    assert system._release_fortified_for_order(state, {"id": "A"}) is True
    assert system._unit_is_transitioning(state, "A") is False
    assert system._queue_pending_move(state, action) == "move-1"
    assert system._queue_pending_attack(state, action) == "attack-1"
    system._attach_pending_to_transition(state, "A", "move-1")
    assert system._ensure_pending_table(None).is_empty()
    assert system._pending_schema()

    progression = SimpleNamespace(
        first_hostile_contact=Mock(return_value=None),
        unit_geo_at=Mock(return_value=geo),
        stop_unit_at=Mock(),
    )
    system._movement_progression = progression
    assert system._first_hostile_contact({}, [], geo, geo, 0) is None
    assert system._unit_geo_at({}, 0) == geo
    system._stop_unit_at({}, geo, 0)


def test_initial_unit_creation_handles_missing_tables_and_zero_strength_rows(monkeypatch):
    system = MilitarySystem()
    assert system._create_initial_units(GameState()).is_empty()
    assert system._create_initial_units(
        GameState(tables={"regions": pl.DataFrame(), "countries": pl.DataFrame()})
    ).is_empty()
    missing_id = GameState(
        tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["AAA"]}),
            "countries": pl.DataFrame({"military_count": [10]}),
        }
    )
    assert system._create_initial_units(missing_id).is_empty()

    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {"id": [1], "owner": ["AAA"], "latitude": [1.0], "longitude": [2.0]}
            ),
            "countries": pl.DataFrame({"id": ["AAA"]}),
        }
    )
    monkeypatch.setattr(
        system,
        "_country_initial_unit_types",
        lambda *_args: {"AAA": (("infantry", 0, 0),)},
    )
    assert system._create_initial_units(state).is_empty()


def test_initial_unit_helpers_skip_missing_identifiers_and_strength_columns():
    system = MilitarySystem()

    assert system._country_strengths(pl.DataFrame({"id": ["AAA"]})) == {}
    assert system._country_initial_unit_types(
        pl.DataFrame({"id": [None], "military_count": [10]}), {}
    ) == {}


def test_capability_projection_and_number_parsing_skip_bad_values(monkeypatch):
    system = MilitarySystem()
    monkeypatch.setattr(
        military_module,
        "get_role_profile",
        lambda role, *_args: SimpleNamespace(
            capabilities={"speed": 0.0 if role == "zero-speed" else 1.0}
        ),
    )
    state = GameState(
        tables={
            "unit_capability_projections": pl.DataFrame(
                {
                    "unit_id": ["bad-json", "not-an-object", "no-speed"],
                    "role": ["infantry", "infantry", "zero-speed"],
                    "domain": ["land", "land", "land"],
                    "capabilities_json": ["{bad", "[]", "{}"],
                }
            )
        }
    )

    assert system._capability_speed_by_unit(state) == {}
    assert system._row_float_from_mapping("bad", 3.0) == 3.0
    assert system._row_float_from_mapping(float("inf"), 3.0) == 3.0


def test_unit_and_country_schemas_are_backfilled_from_snapshot_data():
    system = MilitarySystem()
    countries = system._ensure_country_columns(pl.DataFrame({"id": ["AAA"]}))
    assert countries.item(0, "military_count") == 0
    assert countries.item(0, "money_reserves") == 0.0

    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {"id": [1], "latitude": [12.5], "longitude": [45.5]}
            )
        }
    )
    units = system._normalize_units_table(
        pl.DataFrame({"strength": [20], "current_region_id": [1]}), state
    )

    assert units.columns == list(UNIT_SCHEMA)
    assert units.item(0, "equipment_quantity") == 20
    assert units.item(0, "latitude") == 12.5
    assert units.item(0, "longitude") == 45.5
    assert units.item(0, "target_region_id") == -1


def test_movement_and_manpower_guards_handle_partial_snapshots():
    system = MilitarySystem()
    assert system._unit_movement_is_idle(pl.DataFrame()) is True
    assert system._unit_movement_is_idle(pl.DataFrame({"id": ["unit"]})) is False

    no_population = GameState(tables={"regions": pl.DataFrame({"owner": ["AAA"]})})
    assert system._update_manpower(no_population) is None

    empty_countries = GameState(
        tables={
            "regions": pl.DataFrame({"owner": ["AAA"], "pop_15_64": [100.0]}),
            "countries": pl.DataFrame(schema={"id": pl.Utf8}),
        }
    )
    assert system._update_manpower(empty_countries) is None

    populated_state = GameState(
        tables={
            "regions": pl.DataFrame(
                {"owner": ["AAA"], "pop_15_64": [100.0]}
            ),
            "countries": pl.DataFrame({"id": ["AAA"]}),
        }
    )
    assert system._update_manpower(populated_state) is None
    assert (
        populated_state.get_table("countries").item(0, "total_core_manpower")
        == 100.0
    )
