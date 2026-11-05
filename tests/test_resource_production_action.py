from __future__ import annotations

import polars as pl

from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from src.shared.actions import ActionIncreaseResourceProduction
from src.shared.events import EventResourceProductionIncreased
from src.shared.resource_production_policy import (
    estimate_production_increase_cost,
    production_increase_basis,
)
from src.shared.state import GameState


def _state(*, regional_rows: list[dict] | None = None) -> GameState:
    return GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["UKR", "POL"],
                    "gdp": [1_000_000.0, 1_000_000.0],
                    "gdp_per_capita": [1000.0, 1000.0],
                    "poverty_rate": [0.1, 0.1],
                    "human_dev": [0.7, 0.7],
                    "real_income_index": [1.0, 1.0],
                    "economic_trade_modifier": [1.0, 1.0],
                    "money_reserves": [1000.0, 1000.0],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1, 2, 3],
                    "owner": ["UKR", "UKR", "POL"],
                    "controller": ["UKR", "POL", "POL"],
                    "pop_14": [100.0, 100.0, 100.0],
                    "pop_15_64": [800.0, 800.0, 800.0],
                    "pop_65": [100.0, 100.0, 100.0],
                }
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["UKR", "POL"],
                    "game_resource_id": ["fossil_fuels", "fossil_fuels"],
                    "domestic_production": [100.0, 200.0],
                    "is_gov_controlled": [False, False],
                    "is_legal": [True, True],
                    "tax_rate": [0.0, 0.0],
                }
            ),
            "regional_production": pl.DataFrame(
                regional_rows or [],
                schema={
                    "id": pl.Utf8,
                    "country_id": pl.Utf8,
                    "region_id": pl.Int32,
                    "game_resource_id": pl.Utf8,
                    "domestic_production": pl.Float64,
                },
            ),
        },
        globals={"player_country_map": {"ukr-player": "UKR"}},
    )


def _action(**overrides) -> ActionIncreaseResourceProduction:
    values = {
        "player_id": "ukr-player",
        "country_tag": "UKR",
        "resource_id": "fossil_fuels",
        "increase_percent": 25,
    }
    values.update(overrides)
    return ActionIncreaseResourceProduction(**values)


def _apply(state: GameState, action: ActionIncreaseResourceProduction) -> None:
    state.current_actions = [action]
    InternalEconomySystem().update(state, 0.0)


def test_national_production_increase_uses_openpower_usd_basis_and_refreshes_ledger() -> None:
    state = _state()
    basis = production_increase_basis(state, "ukr", "fossil_fuels")

    assert basis is not None
    assert basis.source == "national"
    assert basis.annual_value_usd == 100.0
    assert estimate_production_increase_cost(basis.annual_value_usd, 25) == 25.0

    _apply(state, _action())

    production = state.tables["domestic_production"].filter(pl.col("country_id") == "UKR")
    country = state.tables["countries"].filter(pl.col("id") == "UKR")
    ledger = state.tables["resource_ledger"].filter(
        (pl.col("country_id") == "UKR") & (pl.col("game_resource_id") == "fossil_fuels")
    )
    assert production["domestic_production"][0] == 125.0
    assert country["money_reserves"][0] == 975.0
    assert ledger["production_usd"][0] == 125.0
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.journal.command_results[-1]["cost_usd"] == 25.0
    event = state.events[-1]
    assert isinstance(event, EventResourceProductionIncreased)
    assert event.previous_production == 100.0
    assert event.new_production == 125.0


def test_regional_basis_changes_only_rows_controlled_by_the_requesting_country() -> None:
    state = _state(
        regional_rows=[
            {"id": "ukr-region-1", "country_id": "UKR", "region_id": 1, "game_resource_id": "fossil_fuels", "domestic_production": 40.0},
            {"id": "ukr-region-2", "country_id": "UKR", "region_id": 2, "game_resource_id": "fossil_fuels", "domestic_production": 30.0},
            {"id": "pol-region-3", "country_id": "POL", "region_id": 3, "game_resource_id": "fossil_fuels", "domestic_production": 60.0},
        ]
    )
    basis = production_increase_basis(state, "UKR", "fossil_fuels")

    assert basis is not None
    assert basis.source == "regional"
    assert basis.annual_value_usd == 40.0
    assert basis.regional_row_ids == ("ukr-region-1",)

    _apply(state, _action(increase_percent=10))

    regional = state.tables["regional_production"].sort("id")
    values = dict(zip(regional["id"].to_list(), regional["domestic_production"].to_list()))
    assert values == {"pol-region-3": 60.0, "ukr-region-1": 44.0, "ukr-region-2": 30.0}
    national = state.tables["domestic_production"].filter(pl.col("country_id") == "UKR")
    assert national["domestic_production"][0] == 104.0
    reserves = state.tables["countries"].filter(pl.col("id") == "UKR")["money_reserves"][0]
    assert reserves == 996.0


def test_increase_rejects_unauthorized_actor_without_mutating_economy() -> None:
    state = _state()

    _apply(state, _action(player_id="foreign-player"))

    assert state.tables["domestic_production"].filter(pl.col("country_id") == "UKR")["domestic_production"][0] == 100.0
    assert state.tables["countries"].filter(pl.col("id") == "UKR")["money_reserves"][0] == 1000.0
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "does not control" in state.journal.command_results[-1]["reason"]


def test_regional_records_outside_country_control_do_not_fall_back_to_national_total() -> None:
    state = _state(
        regional_rows=[
            {"id": "ukr-occupied", "country_id": "UKR", "region_id": 2, "game_resource_id": "fossil_fuels", "domestic_production": 30.0},
        ]
    )

    _apply(state, _action())

    assert state.tables["domestic_production"].filter(pl.col("country_id") == "UKR")["domestic_production"][0] == 100.0
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "positive production value" in state.journal.command_results[-1]["reason"]
