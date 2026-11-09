from __future__ import annotations

import polars as pl

import modules.base.systems.economy.budget_system as budget_module
from modules.base.systems.economy.budget_system import BudgetSystem
from src.shared.actions import ActionUpdateBudget
from src.shared.economy_meta import RESOURCE_MAPPING
from src.shared.state import GameState


def _dense_budget_state(country_ids: tuple[str, ...] = ("AAA",)) -> GameState:
    countries = {
        column: [value] * len(country_ids)
        for column, value in budget_module._REQUIRED_COUNTRY_DEFAULTS.items()
    }
    countries["id"] = list(country_ids)
    resource_ids = tuple(sorted(RESOURCE_MAPPING))
    ledger = pl.DataFrame(
        {
            "country_id": [country_id for country_id in country_ids for _ in resource_ids],
            "game_resource_id": list(resource_ids) * len(country_ids),
            "consumption_usd": [0.0] * (len(country_ids) * len(resource_ids)),
        }
    )
    return GameState(tables={"countries": pl.DataFrame(countries), "resource_ledger": ledger})


def test_budget_entry_points_return_when_countries_are_missing():
    state = GameState()
    system = BudgetSystem()

    system._process_budget(state, fraction=1.0)
    system._handle_update_budget(
        state,
        ActionUpdateBudget(player_id="player-1", country_tag="AAA", allocations={}),
    )


def test_fast_path_rejects_invalid_shapes_and_unsupported_values():
    malformed_trade = _dense_budget_state()
    malformed_trade.tables["trade_network"] = pl.DataFrame({"invalid": [1]})
    assert not BudgetSystem()._try_process_budget_fast(malformed_trade, fraction=1.0)

    unsorted_countries = _dense_budget_state(("BBB", "AAA"))
    system = BudgetSystem()
    # Isolate the fast path's ordering guard from its earlier layout validation.
    system._dense_total_demand = lambda countries, _ledger: pl.DataFrame(
        {"id": countries.get_column("id"), "total_demand": [0.0] * countries.height}
    )
    assert not system._try_process_budget_fast(unsorted_countries, fraction=1.0)

    non_numeric = _dense_budget_state()
    non_numeric.tables["countries"] = non_numeric.tables["countries"].with_columns(
        pl.Series("gdp", ["invalid"])
    )
    assert not BudgetSystem()._try_process_budget_fast(non_numeric, fraction=1.0)

    null_without_default = _dense_budget_state()
    null_without_default.tables["countries"] = null_without_default.tables[
        "countries"
    ].with_columns(pl.Series("gdp", [None], dtype=pl.Float64))
    assert not BudgetSystem()._try_process_budget_fast(null_without_default, fraction=1.0)


def test_fast_path_fills_nullable_tax_and_supports_missing_trade_network():
    state = _dense_budget_state()
    state.tables["countries"] = state.tables["countries"].with_columns(
        pl.Series("personal_income_tax_rate", [None], dtype=pl.Float64)
    )

    assert BudgetSystem()._try_process_budget_fast(state, fraction=1.0)
    country = state.get_table("countries").row(0, named=True)
    assert country["personal_income_tax_rate"] is None
    assert country["tourism_income"] == 0.0


def test_dense_demand_rejects_unsorted_and_misaligned_ledger_layouts():
    system = BudgetSystem()
    unsorted = _dense_budget_state(("BBB", "AAA"))
    assert system._dense_total_demand(
        unsorted.get_table("countries"), unsorted.get_table("resource_ledger")
    ) is None

    misaligned = _dense_budget_state(("AAA", "BBB"))
    reversed_ledger = misaligned.get_table("resource_ledger").reverse()
    assert system._dense_total_demand(
        misaligned.get_table("countries"), reversed_ledger
    ) is None
