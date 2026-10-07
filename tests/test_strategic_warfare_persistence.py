from __future__ import annotations

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from modules.base.systems.military.strategic_warfare_system import StrategicWarfareSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionLaunchStrategicStrike, ActionProduceStrategicWeapon
from src.shared.config import GameConfig
from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState


_PERSISTED_WARFARE_TABLES = (
    "strategic_weapons",
    "strategic_production_orders",
    "strategic_launch_orders",
    "missile_defense_layers",
    "strategic_impacts",
    "countries",
    "regions",
    "countries_relations",
    "messages",
)


def _pending_strike_state() -> GameState:
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["USA", "CAN"],
            "money_reserves": [100.0, 100.0],
            "gvt_approval": [50.0, 50.0],
        }),
        "regions": pl.DataFrame({
            "id": [1, 2],
            "owner": ["USA", "CAN"],
            "controller": ["USA", "CAN"],
            "latitude": [0.0, 0.0],
            "longitude": [0.0, 5.0],
            "environment_health": [1.0, 1.0],
            "migration_pressure": [0.0, 0.0],
        }),
        "countries_wars": pl.DataFrame({
            "id": ["war"], "name": ["War"], "side_a": [["USA"]], "side_b": [["CAN"]],
            "status": ["active"], "casus_belli": [""], "created_at": [""],
            "leader_a": ["USA"], "leader_b": ["CAN"], "intent_a": [""], "intent_b": [""],
        }),
        "countries_relations": pl.DataFrame({
            "source": ["USA", "CAN"], "target": ["CAN", "USA"], "value": [0.0, 0.0],
        }),
    })
    ensure_base_tables(state)
    state.update_table("strategic_weapons", pl.DataFrame([{
        "id": "usa-icbm", "country_id": "USA", "weapon_type": "icbm", "weapon_class": "icbm",
        "quantity": 2, "ready": 2, "origin_region_id": 1, "range_km": 12000.0,
        "payload_level": 1, "max_payload_level": 1, "operational": True,
        "launch_cost": 0.0, "flight_minutes": 10,
        "production_cost": 25.0, "production_minutes": 10,
    }], schema=state.get_table("strategic_weapons").schema))
    state.update_table("research_tracks", pl.DataFrame([
        {"id": "program", "country_id": "USA", "branch": "strategic_program", "research_level": 1},
        {"id": "weapons", "country_id": "USA", "branch": "strategic_weapons", "research_level": 1},
    ], schema=state.get_table("research_tracks").schema))
    state.globals["strategic_authorization_policy"] = "war"
    state.determinism.seed = 23
    state.current_actions = [
        ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", target_mode="civilian", payload_level=1,
        ),
        ActionProduceStrategicWeapon("USA", "USA", "usa-icbm", 1),
    ]
    StrategicWarfareSystem().update(state, 0.0)
    state.current_actions = []
    return state


def _resolve_at_minute(state: GameState, minute: int) -> None:
    state.time.total_minutes = minute
    state.current_actions = []
    StrategicWarfareSystem().update(state, 0.0)


def test_pending_strike_resolves_identically_after_snapshot_ipc_and_save_load(tmp_path) -> None:
    original = _pending_strike_state()
    registry = build_base_schema_registry()
    snapshot = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(original, force_full=True))
    ipc = GameState.from_ipc(original.to_ipc())
    registry.ensure_state(snapshot)
    registry.ensure_state(ipc)

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(original, "strategic-continue")
    loaded = DataLoader(config, schema_registry=registry).load_save("strategic-continue")
    continuations = (original, snapshot, ipc, loaded)

    for candidate in continuations[1:]:
        for table_name in _PERSISTED_WARFARE_TABLES:
            assert candidate.get_table(table_name).to_dicts() == original.get_table(table_name).to_dicts()

    for candidate in continuations:
        _resolve_at_minute(candidate, 10)
    for candidate in continuations[1:]:
        for table_name in _PERSISTED_WARFARE_TABLES:
            assert candidate.get_table(table_name).to_dicts() == original.get_table(table_name).to_dicts()

    for candidate in continuations:
        _resolve_at_minute(candidate, 70)
    for candidate in continuations[1:]:
        for table_name in _PERSISTED_WARFARE_TABLES:
            assert candidate.get_table(table_name).to_dicts() == original.get_table(table_name).to_dicts()

    order = original.get_table("strategic_launch_orders").to_dicts()[0]
    assert order["status"] == "impact"
    assert order["origin_region_id"] == 1
    production = original.get_table("strategic_production_orders").to_dicts()[0]
    assert production["status"] == "completed"
    assert original.get_table("strategic_weapons")[0, "ready"] == 2
    assert original.get_table("strategic_impacts").height > 0
