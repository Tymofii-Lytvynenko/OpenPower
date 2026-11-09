from __future__ import annotations

import unittest
from unittest.mock import Mock

import polars as pl

from modules.base.systems.economy.trade_system import TradeSystem
from modules.base.systems.economy.treaty_trade_policy import TreatyTradePolicy
from src.shared.state import GameState


class TreatyTradePolicyTest(unittest.TestCase):
    def test_trade_system_delegates_compatibility_state_and_dataframe_helpers(self) -> None:
        system = TradeSystem()
        seen_columns = {"domestic_production"}
        system._missing_columns = seen_columns
        self.assertIs(system._market_column_warning_registry.seen_columns, seen_columns)

        market_cache = object()
        system._market_index_cache = market_cache
        self.assertIs(system._unconstrained_market_simulator.market_index_cache, market_cache)

        state = GameState()
        production = pl.DataFrame().lazy()
        market = pl.DataFrame()
        simulator = Mock()
        system._dataframe_market_simulator = simulator
        applied_bonus = object()
        mapped_countries = object()
        simulator.apply_treaty_production_bonus.return_value = applied_bonus
        simulator.countries_from_constrained_market.return_value = mapped_countries

        self.assertIs(system._apply_treaty_production_bonus(state, production), applied_bonus)
        self.assertIs(system._countries_from_constrained_market(state, market), mapped_countries)
        simulator.apply_treaty_production_bonus.assert_called_once_with(state, production)
        simulator.countries_from_constrained_market.assert_called_once_with(state, market)

    def test_market_cycle_checks_required_tables_before_fraction(self) -> None:
        system = TradeSystem()
        system._simulate_market_cycle(GameState(tables={}), -1.0)

        state = GameState(
            tables={
                "countries": pl.DataFrame(),
                "domestic_production": pl.DataFrame(),
            }
        )
        with self.assertRaisesRegex(ValueError, "finite and non-negative"):
            system._simulate_market_cycle(state, -1.0)

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

    def test_regional_allocator_rejects_invalid_market_and_source_records(self) -> None:
        policy = TreatyTradePolicy()
        effects = pl.DataFrame()
        market = pl.DataFrame(
            {
                "country_id": ["AAA"],
                "game_resource_id": ["cereals"],
                "export_desired": [10.0],
                "affordable_import": [0.0],
            }
        )
        production = pl.DataFrame(
            {
                "country_id": ["AAA"],
                "region_id": [1],
                "game_resource_id": ["cereals"],
                "domestic_production": [10.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "complete market supply and demand"):
            policy.allocate_with_regional_sources(
                pl.DataFrame({"country_id": ["AAA"]}),
                effects,
                production,
                lambda *_args: True,
            )
        with self.assertRaisesRegex(ValueError, "missing required provenance"):
            policy.allocate_with_regional_sources(
                market,
                effects,
                pl.DataFrame({"country_id": ["AAA"]}),
                lambda *_args: True,
            )

        for region_id, message in (("bad-region", "invalid source region ID"), (0, "positive source region ID")):
            with self.subTest(region_id=region_id), self.assertRaisesRegex(ValueError, message):
                policy.allocate_with_regional_sources(
                    market,
                    effects,
                    production.with_columns(pl.lit(region_id).alias("region_id")),
                    lambda *_args: True,
                )

        unknown_source = production.with_columns(pl.lit("CCC").alias("country_id"))
        with self.assertRaisesRegex(ValueError, "has no national market row"):
            policy.allocate_with_regional_sources(
                market,
                effects,
                unknown_source,
                lambda *_args: True,
            )

        overproduced_market = market.with_columns(pl.lit(5.0).alias("domestic_production"))
        with self.assertRaisesRegex(ValueError, "exceeds national production"):
            policy.allocate_with_regional_sources(
                overproduced_market,
                effects,
                production,
                lambda *_args: True,
            )

    def test_regional_and_general_allocation_cover_access_and_remainder_paths(self) -> None:
        policy = TreatyTradePolicy()
        market = pl.DataFrame(
            {
                "country_id": ["AAA", "BBB"],
                "game_resource_id": ["cereals", "cereals"],
                "export_desired": [10.0, 0.0],
                "affordable_import": [0.0, 5.0],
                "domestic_production": [10.0, 0.0],
            }
        )
        production = pl.DataFrame(
            {
                "country_id": ["AAA"],
                "region_id": [17],
                "game_resource_id": ["cereals"],
                "domestic_production": [8.0],
            }
        )
        inaccessible_flows = policy.allocate_with_regional_sources(
            market,
            pl.DataFrame(),
            production,
            lambda *_args: False,
        )
        self.assertEqual(inaccessible_flows.height, 1)
        self.assertIsNone(inaccessible_flows["source_region_id"][0])
        self.assertEqual(inaccessible_flows["trade_value_usd"][0], 2.0)

        common_effects = pl.DataFrame(
            {
                "country_id": ["BBB"],
                "effect": ["common_market_priority"],
                "detail": ['["AAA"]'],
            }
        )
        fully_tagged = production.with_columns(pl.lit(10.0).alias("domestic_production"))
        common_flows = policy.allocate_with_regional_sources(
            market,
            common_effects,
            fully_tagged,
            lambda *_args: True,
        )
        self.assertEqual(common_flows["trade_value_usd"].sum(), 5.0)

        embargo_effects = pl.DataFrame(
            {
                "country_id": ["BBB", "AAA"],
                "effect": ["common_market_priority", "resource_trade_embargo"],
                "detail": ['["AAA"]', '["BBB"]'],
            }
        )
        self.assertTrue(policy.allocate(market, embargo_effects).is_empty())

        small_demand = market.with_columns(
            pl.when(pl.col("country_id") == "BBB")
            .then(pl.lit(2.0))
            .otherwise(pl.col("affordable_import"))
            .alias("affordable_import")
        )
        general_flows = policy.allocate(small_demand, pl.DataFrame())
        self.assertEqual(general_flows["trade_value_usd"].sum(), 2.0)

    def test_treaty_trade_helpers_handle_malformed_values_and_empty_flows(self) -> None:
        policy = TreatyTradePolicy()

        self.assertEqual(policy._detail_tags("not-json"), ())
        self.assertEqual(policy._detail_tags('{"not": "a list"}'), ())
        self.assertEqual(policy._detail_tags('["usa", "USA", null]'), ("USA",))
        self.assertEqual(policy._number(None), 0.0)
        self.assertEqual(policy._finite_nonnegative("invalid"), 0.0)
        with self.assertRaisesRegex(ValueError, "not numeric"):
            policy._validated_nonnegative("invalid", "not numeric")
        with self.assertRaisesRegex(ValueError, "negative"):
            policy._validated_nonnegative(-1, "negative")

        flows: list[dict[str, object]] = []
        self.assertEqual(
            policy._record_flow(flows, "cereals", "AAA", "BBB", 0.0, {"AAA": 10.0}, {"BBB": 0.0}),
            0.0,
        )
        self.assertEqual(flows, [])


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
