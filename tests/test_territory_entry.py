from dataclasses import replace

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem, UnitFactory
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.territory_entry import validate_territory_entry, authorized_entry_moves
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionInvadeTerritory
from src.shared.events import EventTerritoryEntryAuthorized, EventWarStarted
from src.shared.state import GameState


def world():
    state = GameState()
    ensure_base_tables(state)
    state.globals["player_country_map"] = {"player": "UKR"}
    state.tables["countries"] = pl.DataFrame([dict(id=tag, name=tag, money_reserves=1000.) for tag in ("UKR", "POL", "DEU")])
    state.tables["regions"] = pl.DataFrame([
        dict(id=1, owner="UKR", controller="UKR", name="Kyiv", latitude=50., longitude=30., is_water=False),
        dict(id=2, owner="POL", controller="POL", name="Warsaw", latitude=52., longitude=21., is_water=False),
    ])
    state.tables["region_adjacency"] = pl.DataFrame([dict(region_id=1, neighbor_region_id=2)])
    unit = UnitFactory().create("one", "UKR", "infantry", 1000, 1, GeoCoordinate(50, 30), 0)
    unit["readiness_status"] = "ready"
    state.tables["units"] = pl.DataFrame([unit])
    return state


def order(**changes):
    return replace(ActionInvadeTerritory("player", "entry-1", ["one"], 2, "POL", 52., 21.), **changes)


def test_confirmed_order_declares_one_war_and_enters_existing_movement_pipeline():
    state = world()
    state.current_actions = [order()]
    assert not authorized_entry_moves(state)
    DiplomacySystem().update(state, 0)
    assert state.tables["countries_wars"].height == 1
    assert any(isinstance(e, EventWarStarted) for e in state.events)
    assert len(authorized_entry_moves(state)) == 1
    MilitarySystem().update(state, 0)
    assert state.tables["units"].row(0, named=True)["target_region_id"] == 2
    assert state.tables["unit_movement_routes"].row(0, named=True)["route_region_ids"] == [1, 2]
    # A repeat intent while already at war must not duplicate declarations.
    state.events.clear()
    DiplomacySystem().update(state, 0)
    assert state.tables["countries_wars"].height == 1


@pytest.mark.parametrize("changes", [dict(player_id="intruder"), dict(unit_ids=["removed"]),
    dict(unit_ids=["one", "one"]), dict(expected_controller="DEU"), dict(target_latitude=float("nan")),
    dict(target_longitude=181), dict(order_id=""), dict(target_latitude=True), dict(target_region_id=True)])
def test_invalid_order_cannot_declare_war_or_create_movement(changes):
    state = world()
    state.current_actions = [order(**changes)]
    before = state.tables["units"].clone()
    DiplomacySystem().update(state, 0)
    assert state.tables["countries_wars"].is_empty()
    assert not authorized_entry_moves(state)
    assert state.tables["units"].equals(before)
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_domain_and_blocked_route_are_checked_before_hostilities():
    state = world()
    state.tables["regions"] = state.tables["regions"].with_columns((pl.col("id") == 2).alias("is_water"))
    assert validate_territory_entry(state, order(), [])[1]
    state = world()
    state.tables["regions"] = pl.concat([state.tables["regions"], pl.DataFrame([
        dict(id=3, owner="DEU", controller="DEU", name="Transit", latitude=51., longitude=25., is_water=False)])])
    state.tables["region_adjacency"] = pl.DataFrame([
        dict(region_id=1, neighbor_region_id=3), dict(region_id=3, neighbor_region_id=2)])
    assert validate_territory_entry(state, order(), [])[1]


def test_stationing_rights_and_stale_controller_do_not_start_unnecessary_wars():
    state = world()
    state.tables["treaty_effects"] = pl.DataFrame([dict(country_id="UKR", effect="stationing_rights", detail='["POL"]')])
    assert "permission changed" in validate_territory_entry(state, order(), [])[1]
    state.tables["regions"] = state.tables["regions"].with_columns(
        pl.when(pl.col("id") == 2).then(pl.lit("DEU")).otherwise(pl.col("controller")).alias("controller"))
    assert "controller changed" in validate_territory_entry(state, order(), [])[1]


def test_invalid_route_geography_and_mixed_ownership_refuse_before_war():
    state = world()
    own = state.tables["units"].row(0, named=True)
    state.tables["units"] = pl.DataFrame([own, {**own, "id": "foreign", "owner": "POL"}])
    assert validate_territory_entry(state, order(unit_ids=["one", "foreign"]), [])[1]
    state = world()
    state.tables["regions"] = state.tables["regions"].with_columns(pl.lit(None).cast(pl.Float64).alias("latitude"))
    state.current_actions = [order()]
    DiplomacySystem().update(state, 0)
    assert state.tables["countries_wars"].is_empty()
    assert "coordinates" in state.journal.command_results[-1]["reason"]


def test_occupation_access_uses_military_controller_instead_of_political_owner():
    access = MovementAccessPolicy().for_country(world(), "UKR")
    assert not access.can_station(dict(owner="UKR", controller="POL"))
    assert access.can_station(dict(owner="POL", controller="UKR"))


def test_authorization_cannot_be_used_for_another_action_or_new_unit_owner():
    state = world()
    state.current_actions = [order()]
    DiplomacySystem().update(state, 0)
    assert any(isinstance(e, EventTerritoryEntryAuthorized) for e in state.events)
    state.current_actions = [order(target_region_id=1)]
    assert not authorized_entry_moves(state)
    state.current_actions = [order()]
    changed = state.tables["units"].with_columns(pl.lit("POL").alias("owner"))
    assert not authorized_entry_moves(state, changed)


def test_mixed_invalid_actions_do_not_break_a_valid_authorization():
    state = world()
    state.current_actions = [order(unit_ids=None, order_id="invalid"), order()]
    DiplomacySystem().update(state, 0)
    assert len(authorized_entry_moves(state)) == 1


def test_replay_through_real_engine_preserves_authority_order_and_snapshot_results():
    from src.engine.simulator import Engine
    from src.shared.system_interfaces import SystemAccess
    from src.shared.system_state import SYSTEM_STATE_HELPER

    class DependencyPort:
        access = SystemAccess()
        runtime_state_contract = {"_name": SYSTEM_STATE_HELPER}

        def __init__(self, name):
            self._name = name

        @property
        def id(self):
            return self._name

        @property
        def dependencies(self):
            return []

        def update(self, state, delta_time):
            pass

    original = world()
    restored = GameState.from_ipc(original.to_ipc())
    for state in (original, restored):
        engine = Engine(dev_mode=True)
        ports = [DependencyPort("base." + name) for name in
                 ("time", "bootstrap", "population", "economy", "military_programs")]
        engine.register_systems([MilitarySystem(), DiplomacySystem(), *ports])
        assert ActionInvadeTerritory in engine.handled_action_types
        assert engine.step(state, [order()], 0).success
        names = [system.id for system in engine.execution_order]
        assert names.index("base.diplomacy") < names.index("base.military")
        assert state.tables["units"].row(0, named=True)["is_moving"]
    for table in ("countries_wars", "unit_movement_routes", "units"):
        assert original.tables[table].equals(restored.tables[table])


@pytest.mark.parametrize(
    "latitude",
    ["invalid", 91.0, float("nan")],
    ids=["not-numeric", "out-of-range", "not-finite"],
)
def test_selected_unit_requires_a_valid_geographic_position(latitude):
    state = world()
    state.tables["units"] = state.tables["units"].with_columns(
        pl.lit(latitude).alias("latitude")
    )

    owner, reason = validate_territory_entry(state, order(), [])

    assert owner == ""
    assert "valid geographic position" in reason


def test_strategic_units_cannot_start_conventional_territory_entry():
    state = world()
    state.tables["units"] = state.tables["units"].with_columns(
        pl.lit("strategic").alias("unit_domain")
    )

    owner, reason = validate_territory_entry(state, order(), [])

    assert owner == ""
    assert "Strategic assets" in reason


def test_invalid_target_coordinate_text_is_rejected():
    owner, reason = validate_territory_entry(
        world(), order(target_latitude="invalid"), []
    )

    assert owner == ""
    assert "destination coordinates" in reason


def test_missing_destination_region_is_rejected():
    owner, reason = validate_territory_entry(
        world(), order(target_region_id=99), []
    )

    assert owner == ""
    assert "no longer available" in reason


def test_intermediate_route_region_requires_finite_coordinates():
    state = world()
    state.tables["regions"] = pl.concat(
        [
            state.tables["regions"],
            pl.DataFrame(
                [
                    dict(
                        id=3,
                        owner="UKR",
                        controller="UKR",
                        name="Transit",
                        latitude=float("nan"),
                        longitude=25.0,
                        is_water=False,
                    )
                ]
            ),
        ]
    )
    state.tables["region_adjacency"] = pl.DataFrame(
        [
            dict(region_id=1, neighbor_region_id=3),
            dict(region_id=3, neighbor_region_id=2),
        ]
    )

    owner, reason = validate_territory_entry(state, order(), [])

    assert owner == ""
    assert "without valid coordinates" in reason


def test_unavailable_unit_lifecycle_rejects_entry():
    state = world()
    state.tables["units"] = state.tables["units"].with_columns(
        pl.lit("moving").alias("unit_lifecycle")
    )

    owner, reason = validate_territory_entry(state, order(), [])

    assert owner == ""
    assert "deployed and available" in reason
