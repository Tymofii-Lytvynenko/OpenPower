from __future__ import annotations

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, MilitarySystem, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionSetBattleStrategy
from src.shared.config import GameConfig
from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState


def _retreat_state() -> GameState:
    factory = UnitFactory()
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["USA", "CAN"], "money_reserves": [1_000.0, 1_000.0],
        }),
        "regions": pl.DataFrame([
            {"id": 1, "owner": "USA", "controller": "USA", "latitude": 10.0, "longitude": 19.0},
            {"id": 2, "owner": "USA", "controller": "USA", "latitude": 10.0, "longitude": 20.0},
        ]),
        "units": pl.DataFrame([
            factory.create("usa-1", "USA", "infantry", 100, 2, GeoCoordinate(10.0, 20.0), 0),
            factory.create("can-1", "CAN", "infantry", 80, 2, GeoCoordinate(10.0, 21.0), 0),
        ], schema=UNIT_SCHEMA),
        "battles": pl.DataFrame([{
            "id": "battle-1", "region_id": 2, "attacker_side": "USA",
            "defender_side": "CAN", "status": "active",
        }]),
        "battle_units": pl.DataFrame([
            {"battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA", "side": "SIDE_A"},
            {"battle_id": "battle-1", "unit_id": "can-1", "country_id": "CAN", "side": "SIDE_B"},
        ]),
    })
    ensure_base_tables(state)
    state.update_table("region_adjacency", pl.DataFrame([{
        "region_id": 2, "neighbor_region_id": 1,
    }]))
    state.update_table("country_governments", pl.DataFrame([{
        "country_id": "USA", "capital_region_id": 1,
        "ruling_party_id": "", "government_type": "",
    }]))
    state.current_actions = [ActionSetBattleStrategy(
        "USA", "battle-1", "retreat", country_tag="USA",
    )]
    BattleStrategySystem().update(state, 0.0)
    return state


def _advance_to(state: GameState, minute: int) -> None:
    state.time.total_minutes = minute
    state.current_actions = []
    moved_units = MilitarySystem()._update_unit_movements(
        state, state.get_table("units"), minute,
    )
    state.update_table("units", moved_units)
    BattleStrategySystem().update(state, 0.0)


def test_retreat_route_and_regroup_continue_identically_after_ipc_snapshot_and_save(tmp_path) -> None:
    state = _retreat_state()
    registry = build_base_schema_registry()
    snapshot = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(state, force_full=True))
    ipc = GameState.from_ipc(state.to_ipc())
    registry.ensure_state(snapshot)
    registry.ensure_state(ipc)

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "battle-retreat")
    loaded = DataLoader(config, schema_registry=registry).load_save("battle-retreat")
    continuations = (state, snapshot, ipc, loaded)
    persisted_tables = (
        "units", "battle_force_postures", "battle_command_orders", "unit_movement_routes",
    )
    for candidate in continuations[1:]:
        for table_name in persisted_tables:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()

    initial_arrival = int(state.get_table("units").filter(pl.col("id") == "usa-1")["arrival_at_minute"][0])
    for candidate in continuations:
        _advance_to(candidate, initial_arrival)
    for candidate in continuations[1:]:
        for table_name in persisted_tables:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()

    regroup_until = int(state.get_table("battle_force_postures").filter(
        pl.col("unit_id") == "usa-1",
    )["expires_at_minute"][0])
    for candidate in continuations:
        _advance_to(candidate, regroup_until)
    return_arrival = int(state.get_table("units").filter(pl.col("id") == "usa-1")["arrival_at_minute"][0])
    for candidate in continuations:
        _advance_to(candidate, return_arrival)

    for candidate in continuations[1:]:
        for table_name in persisted_tables:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()
    assert state.get_table("battle_force_postures").filter(
        pl.col("unit_id") == "usa-1",
    )["status"][0] == "completed"


def test_replaying_the_same_retreat_command_reproduces_projections_and_next_transitions() -> None:
    original = _retreat_state()
    replayed = _retreat_state()
    persisted_tables = (
        "units", "battle_units", "battle_force_postures", "battle_command_orders",
        "unit_movement_routes",
    )

    def assert_equal_state() -> None:
        for table_name in persisted_tables:
            assert replayed.get_table(table_name).to_dicts() == original.get_table(table_name).to_dicts()

    assert_equal_state()
    arrival = int(original.get_table("units").filter(pl.col("id") == "usa-1")["arrival_at_minute"][0])
    _advance_to(original, arrival)
    _advance_to(replayed, arrival)
    assert_equal_state()

    regroup_until = int(original.get_table("battle_force_postures").filter(
        pl.col("unit_id") == "usa-1",
    )["expires_at_minute"][0])
    _advance_to(original, regroup_until)
    _advance_to(replayed, regroup_until)
    assert_equal_state()

    return_arrival = int(original.get_table("units").filter(pl.col("id") == "usa-1")["arrival_at_minute"][0])
    _advance_to(original, return_arrival)
    _advance_to(replayed, return_arrival)
    assert_equal_state()

    posture = original.get_table("battle_force_postures").filter(pl.col("unit_id") == "usa-1").to_dicts()[0]
    unit = original.get_table("units").filter(pl.col("id") == "usa-1").to_dicts()[0]
    assert posture["status"] == "completed"
    assert unit["combat_posture"] == "hold"
    assert unit["combat_attack_risk_modifier"] == 1.0
    assert unit["combat_readiness_modifier"] == 1.0
