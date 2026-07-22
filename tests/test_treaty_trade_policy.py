from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy


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


if __name__ == "__main__":
    unittest.main()
