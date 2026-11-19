from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import (
    UNIT_SCHEMA,
    MilitarySystem,
    UnitFactory,
)
from src.core.map.geo import GeoCoordinate
from src.server.io.save_writer import SaveWriter
from src.server.session import GameSession
from src.shared.actions import ActionMoveUnit
from src.shared.config import GameConfig
from src.shared.state import GAME_EPOCH, GameState


def _freeplay_state() -> tuple[GameState, str]:
    unit = UnitFactory().create(
        "USA-infantry-001",
        "USA",
        "infantry",
        100,
        1,
        GeoCoordinate(0.0, 0.0),
        0,
    )
    unit["readiness_status"] = "ready"
    state = GameState(tables={
        "countries": pl.DataFrame([{
            "id": "USA",
            "money_reserves": 1_000.0,
            "personal_income_tax_rate": 0.35,
        }]),
        "regions": pl.DataFrame({
            "id": [1, 2],
            "owner": ["USA", "USA"],
            "latitude": [0.0, 0.0],
            "longitude": [0.0, 1.0],
        }),
        "region_adjacency": pl.DataFrame({
            "region_id": [1],
            "neighbor_region_id": [2],
        }),
        "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
    })
    ensure_base_tables(state)

    state.globals["player_tag"] = "USA"
    state.time.total_minutes = 754
    game_date = GAME_EPOCH + timedelta(minutes=state.time.total_minutes)
    state.time.year = game_date.year
    state.time.month = game_date.month
    state.time.day = game_date.day
    state.time.hour = game_date.hour
    state.time.minute = game_date.minute
    state.time.date_str = game_date.strftime("%Y-%m-%d %H:%M")

    state.current_actions = [ActionMoveUnit("USA", unit["id"], 2)]
    MilitarySystem().update(state, 0.0)
    state.current_actions = []

    moving_unit = state.get_table("units").filter(pl.col("id") == unit["id"]).row(0, named=True)
    assert moving_unit["is_moving"]
    assert moving_unit["target_region_id"] == 2
    return state, unit["id"]


def _headless_test_config(tmp_path: Path) -> GameConfig:
    repository_root = Path(__file__).resolve().parents[1]
    test_module = tmp_path / "modules" / "base"
    test_module.mkdir(parents=True)
    shutil.copy2(repository_root / "modules" / "base" / "mod.toml", test_module)
    shutil.copy2(repository_root / "modules" / "base" / "registration.py", test_module)
    return GameConfig(tmp_path)


def test_freeplay_without_campaign_data_resumes_tax_date_and_pending_move(tmp_path) -> None:
    state, unit_id = _freeplay_state()
    assert state.globals["player_tag"] == "USA"
    assert state.get_table("campaigns").is_empty()
    assert state.get_table("objectives").is_empty()

    config = _headless_test_config(tmp_path)
    assert SaveWriter(config).save_game(state, "freeplay")

    resumed_session = GameSession.create_headless(config, save_name="freeplay")
    loaded = resumed_session.get_state_snapshot()

    assert loaded.globals["player_tag"] == "USA"
    assert loaded.time.total_minutes == state.time.total_minutes
    assert loaded.time.date_str == state.time.date_str
    assert (loaded.time.year, loaded.time.month, loaded.time.day) == (
        state.time.year,
        state.time.month,
        state.time.day,
    )
    assert loaded.get_table("countries").filter(pl.col("id") == "USA").item(
        0, "personal_income_tax_rate"
    ) == 0.35
    assert loaded.get_table("campaigns").is_empty()
    assert loaded.get_table("objectives").is_empty()
    assert loaded.get_table("unit_movement_routes").to_dicts() == state.get_table(
        "unit_movement_routes"
    ).to_dicts()

    loaded_unit = loaded.get_table("units").filter(pl.col("id") == unit_id).row(0, named=True)
    assert loaded_unit["is_moving"]
    assert loaded_unit["target_region_id"] == 2
    assert loaded_unit["arrival_at_minute"] > loaded.time.total_minutes
    route_before_tick = loaded.get_table("unit_movement_routes").row(0, named=True)

    tick_before_load = loaded.globals["tick"]
    minute_before_load = loaded.time.total_minutes
    resumed_session.tick(1.0 / 30.0 + 0.000001)

    resumed = resumed_session.get_state_snapshot()
    assert resumed.globals["tick"] == tick_before_load + 1
    assert resumed.time.total_minutes == minute_before_load + 1
    continued_date = GAME_EPOCH + timedelta(minutes=minute_before_load + 1)
    assert resumed.time.date_str == continued_date.strftime("%Y-%m-%d %H:%M")
    assert (resumed.time.year, resumed.time.month, resumed.time.day) == (
        continued_date.year,
        continued_date.month,
        continued_date.day,
    )
    assert resumed.globals["player_tag"] == "USA"
    assert resumed.get_table("countries").filter(pl.col("id") == "USA").item(
        0, "personal_income_tax_rate"
    ) == 0.35
    assert resumed.get_table("campaigns").is_empty()
    objectives = resumed.get_table("objectives")
    assert objectives.filter(pl.col("campaign_id") != "").is_empty()
    route_after_tick = resumed.get_table("unit_movement_routes").row(0, named=True)
    assert route_after_tick["destination_region_id"] == route_before_tick["destination_region_id"] == 2
    assert route_after_tick["status"] == route_before_tick["status"]
    continued_unit = resumed.get_table("units").filter(pl.col("id") == unit_id).row(0, named=True)
    assert continued_unit["is_moving"]
    assert continued_unit["movement_progress"] > loaded_unit["movement_progress"]
