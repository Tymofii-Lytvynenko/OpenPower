from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from src.shared.state import GameState


class TreatyTradePolicyTest(unittest.TestCase):
    def test_common_market_is_allocated_before_other_allowed_trade(self) -> None:
        market = pl.DataFrame({
            "country_id": ["USA", "CAN", "MEX"],
            "game_resource_id": ["cereals", "cereals", "cereals"],
            "export_desired": [10.0, 0.0, 0.0],
            "affordable_import": [0.0, 5.0, 5.0],
        })
        effects = pl.DataFrame([
            {"treaty_id": "market", "country_id": "USA", "effect": "common_market_priority", "value": 1.0, "detail": '["CAN"]'},
            {"treaty_id": "market", "country_id": "CAN", "effect": "common_market_priority", "value": 1.0, "detail": '["USA"]'},
        ])
        flows = TreatyTradePolicy().allocate(market, effects)
        self.assertEqual(flows.to_dicts()[0]["importer_id"], "CAN")
        self.assertEqual(flows.to_dicts()[0]["trade_value_usd"], 5.0)
        self.assertEqual(flows.to_dicts()[1]["importer_id"], "MEX")

    def test_constrained_flows_reconcile_market_stockpiles_and_budget(self) -> None:
        market = pl.DataFrame({
            "country_id": ["USA", "CAN"], "game_resource_id": ["cereals", "cereals"],
            "export_desired": [10.0, 0.0], "affordable_import": [0.0, 10.0],
            "import_actual": [0.0, 10.0], "export_actual": [10.0, 0.0],
            "production_penalty_pct": [0.0, 0.0], "domestic_production": [10.0, 0.0],
            "is_storable": [True, True], "decay_rate": [0.1, 0.1],
            "is_gov_controlled": [False, False], "is_legal": [True, True], "total_tax": [0.05, 0.05],
        })
        flows = pl.DataFrame({
            "exporter_id": ["USA"], "importer_id": ["CAN"], "game_resource_id": ["cereals"], "trade_value_usd": [10.0],
        })
        reconciled = TradeSystem()._apply_constrained_flows(market, flows, 1.0 / 365.0)
        self.assertEqual(reconciled.filter(pl.col("country_id") == "USA")["export_actual"][0], 10.0)
        self.assertEqual(reconciled.filter(pl.col("country_id") == "CAN")["import_actual"][0], 10.0)
        self.assertEqual(reconciled["new_stock_amount"].sum(), 0.0)

    def test_treaty_embargo_forces_policy_aware_market_path_and_blocks_trade(self) -> None:
        state = _trade_state()
        state.update_table(
            "treaty_effects",
            pl.DataFrame(
                [
                    {
                        "treaty_id": "embargo",
                        "country_id": "AAA",
                        "effect": "resource_trade_embargo",
                        "value": 1.0,
                        "detail": '["BBB"]',
                    }
                ]
            ),
        )
        system = TradeSystem()

        self.assertFalse(system._simulate_market_cycle_fast(state, 0.25))
        system._simulate_market_cycle(state, 0.25)

        self.assertTrue(state.get_table("trade_network").is_empty())
        self.assertAlmostEqual(
            state.get_table("stockpiles").filter(pl.col("country_id") == "AAA").item(0, "stock_amount"),
            97.5,
        )

    def test_regional_source_forces_general_path_and_preserves_flow_provenance(self) -> None:
        state = _trade_state()
        state.update_table(
            "regions",
            pl.DataFrame({"id": [17], "owner": ["AAA"]}),
        )
        state.update_table(
            "regional_production",
            pl.DataFrame(
                {
                    "country_id": ["AAA"],
                    "region_id": [17],
                    "game_resource_id": ["cereals"],
                    "domestic_production": [100.0],
                }
            ),
        )
        system = TradeSystem()

        self.assertFalse(system._simulate_market_cycle_fast(state, 0.25))
        system._simulate_market_cycle(state, 0.25)

        self.assertEqual(
            state.get_table("trade_network").select(
                "exporter_id", "importer_id", "game_resource_id", "source_region_id"
            ).rows(),
            [("AAA", "BBB", "cereals", 17)],
        )
        self.assertEqual(state.get_table("trade_network").item(0, "trade_value_usd"), 100.0)


def _trade_state() -> GameState:
    return GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA", "BBB"], "economic_trade_modifier": [1.0, 1.0]}
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "domestic_production": [100.0, 0.0],
                    "is_gov_controlled": [False, False],
                    "is_legal": [True, True],
                    "tax_rate": [0.05, 0.05],
                }
            ),
            "resource_ledger": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["cereals", "cereals"],
                    "consumption_usd": [0.0, 100.0],
                }
            ),
        }
    )


if __name__ == "__main__":
    unittest.main()
