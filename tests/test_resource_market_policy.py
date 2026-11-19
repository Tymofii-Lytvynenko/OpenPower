"""Real trade clearing must honor targets without creating or losing reserves."""
from unittest.mock import patch

import polars as pl
import pytest

from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.economy.trade_system import TradeSystem
from src.shared.actions import ActionUpdateResourcePolicy
from src.shared.state import GameState


def market_state(*, storable=True):
    resource = "cereals" if storable else "electricity"
    return GameState(tables={
        "countries": pl.DataFrame({"id": ["AAA", "BBB", "CCC"], "global_resource_tax_modifier": [0.10, 0.02, 0.02]}),
        "domestic_production": pl.DataFrame({
            "country_id": ["AAA", "BBB", "CCC"], "game_resource_id": [resource] * 3,
            "domestic_production": [100.0, 0.0, 0.0], "tax_rate": [0.05] * 3,
            "is_gov_controlled": [False] * 3, "is_legal": [True] * 3,
            "meet_consumption": [False] * 3, "desired_trade_usd": [30.0, -20.0, -50.0],
        }),
        "resource_ledger": pl.DataFrame({"country_id": ["AAA", "BBB", "CCC"],
            "game_resource_id": [resource] * 3, "consumption_usd": [10.0, 5.0, 5.0]}),
    })


@pytest.mark.parametrize("use_fast", [True, False])
def test_targets_clear_and_retained_goods_become_stock_with_country_tax(use_fast):
    state = market_state()
    system = TradeSystem()
    if use_fast:
        assert system._simulate_market_cycle_fast(state, 0.0)
    else:
        with patch.object(system, "_simulate_market_cycle_fast", return_value=False):
            system._simulate_market_cycle(state, 0.0)
    flows = state.tables["trade_network"]
    exports = flows.filter(pl.col("exporter_id") == "AAA")["trade_value_usd"].sum()
    assert exports == pytest.approx(30.0)
    stocks = {row["country_id"]: row["stock_amount"] for row in state.tables["stockpiles"].to_dicts()}
    assert stocks["AAA"] == pytest.approx(60.0)
    assert sum(stocks.values()) == pytest.approx(100.0 - 10.0 - 5.0 - 5.0)
    income = state.tables["countries"].filter(pl.col("id") == "AAA")["trade_income"][0]
    assert income == pytest.approx(30.0 * 0.15)
    assert state.tables["domestic_production"]["desired_trade_usd"].to_list() == [30.0, -20.0, -50.0]


@pytest.mark.parametrize("use_fast", [True, False])
def test_unstorable_imports_are_capped_at_consumption_gap(use_fast):
    state = market_state(storable=False)
    system = TradeSystem()
    if use_fast:
        assert system._simulate_market_cycle_fast(state, 0.0)
    else:
        with patch.object(system, "_simulate_market_cycle_fast", return_value=False):
            system._simulate_market_cycle(state, 0.0)
    assert state.tables["stockpiles"]["stock_amount"].sum() == 0.0
    imports = state.tables["trade_network"].filter(pl.col("exporter_id") == "WORLD")["trade_value_usd"].sum()
    assert imports == pytest.approx(10.0)


@pytest.mark.parametrize("fields", [{"global_tax_modifier": float("nan")},
                                    {"global_tax_modifier": -0.1},
                                    {"desired_trade_usd": float("inf")},
                                    {"meet_consumption": "yes"}])
def test_invalid_policy_changes_reject_atomically(fields):
    state = market_state()
    state.globals["player_country_map"] = {"player": "AAA"}
    before = {name: frame.clone() for name, frame in state.tables.items()}
    state.current_actions = [ActionUpdateResourcePolicy("player", "AAA", "cereals", False, True, 0.05, **fields)]
    InternalEconomySystem().update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.tables["domestic_production"].equals(before["domestic_production"])
    assert state.tables["countries"].equals(before["countries"])


def test_policy_changes_persist_on_resource_and_country_without_affecting_peers():
    state = market_state()
    state.globals["player_country_map"] = {"player": "AAA"}
    state.current_actions = [ActionUpdateResourcePolicy(
        "player", "AAA", "cereals", False, True, 0.05,
        global_tax_modifier=0.20, desired_trade_usd=-80.0, meet_consumption=False,
    )]
    InternalEconomySystem().update(state, 0.0)
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.tables["countries"]["global_resource_tax_modifier"].to_list() == [0.20, 0.02, 0.02]
    assert state.tables["domestic_production"]["desired_trade_usd"].to_list() == [-80.0, -20.0, -50.0]


def test_manual_targets_cannot_bypass_embargo_and_unsold_stock_is_preserved():
    state = market_state()
    state.tables["treaty_effects"] = pl.DataFrame([{
        "treaty_id": "embargo", "country_id": "AAA", "effect": "resource_trade_embargo",
        "value": 1.0, "detail": '["CCC"]',
    }])
    TradeSystem()._simulate_market_cycle(state, 0.0)
    flows = state.tables["trade_network"]
    assert flows.filter(pl.col("importer_id") == "CCC").is_empty()
    assert flows["trade_value_usd"].sum() == pytest.approx(20.0)
    stock = state.tables["stockpiles"].filter(pl.col("country_id") == "AAA")["stock_amount"][0]
    assert stock == pytest.approx(70.0)
