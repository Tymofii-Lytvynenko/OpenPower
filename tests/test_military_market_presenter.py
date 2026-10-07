from __future__ import annotations

import json
import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class MilitaryMarketPresenterTest(unittest.TestCase):
    def test_market_hides_ineligible_sellers_and_keeps_seller_inventory_visible(self) -> None:
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA", "CAN"]}),
            "units": pl.DataFrame(schema=UNIT_SCHEMA),
        })
        ensure_base_tables(state)
        state.update_table("unit_designs", pl.DataFrame([{
            "id": "can-design", "country_id": "CAN", "display_name": "Infantry",
        }], schema=state.get_table("unit_designs").schema))
        state.update_table("unit_market_listings", pl.DataFrame([{
            "id": "listing-1", "seller_country_id": "CAN", "design_id": "can-design",
            "unit_id": "can-unit", "quantity": 2, "price": 100.0, "status": "listed",
        }], schema=state.get_table("unit_market_listings").schema))
        presenter = MilitaryPresenter()

        self.assertEqual(presenter.market_listings_for_country(state, "USA"), [])
        self.assertEqual(presenter.market_listings_for_country(state, "CAN")[0]["design_name"], "Infantry")

        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "trade", "country_id": "USA", "effect": "weapons_market_access",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        self.assertEqual(len(presenter.market_listings_for_country(state, "USA")), 1)

        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "embargo", "country_id": "USA", "effect": "weapons_trade_embargo",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        self.assertEqual(presenter.market_listings_for_country(state, "USA"), [])

    def test_only_stationary_unengaged_units_can_be_listed(self) -> None:
        factory = UnitFactory()
        units = [
            factory.create("USA-open", "USA", "army", 10, 1, GeoCoordinate(0.0, 0.0), 0),
            factory.create("USA-listed", "USA", "army", 10, 1, GeoCoordinate(0.0, 0.0), 0),
            factory.create("USA-moving", "USA", "army", 10, 1, GeoCoordinate(0.0, 0.0), 0),
        ]
        units[2]["is_moving"] = True
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA"]}),
            "units": pl.DataFrame(units, schema=UNIT_SCHEMA),
        })
        ensure_base_tables(state)
        state.update_table("unit_market_listings", pl.DataFrame([{
            "id": "listing-1", "seller_country_id": "USA", "design_id": "", "unit_id": "USA-listed",
            "quantity": 10, "price": 10.0, "status": "listed",
        }], schema=state.get_table("unit_market_listings").schema))
        state.update_table("battle_units", pl.DataFrame([{
            "battle_id": "battle-1", "unit_id": "USA-open", "country_id": "USA", "side": "SIDE_A",
        }], schema=state.get_table("battle_units").schema))

        result = MilitaryPresenter().marketable_units_for_country(state, "USA")

        self.assertEqual([row["id"] for row in result], [])
        state.update_table("battle_units", pl.DataFrame(schema=state.get_table("battle_units").schema))
        result = MilitaryPresenter().marketable_units_for_country(state, "USA")
        self.assertEqual([row["id"] for row in result], ["USA-open"])

    def test_production_and_foreign_order_statuses_are_projected_for_the_ui(self) -> None:
        state = GameState(tables={"countries": pl.DataFrame({"id": ["USA", "CAN"]})})
        ensure_base_tables(state)
        state.update_table("unit_designs", pl.DataFrame([{
            "id": "can-design", "country_id": "CAN", "branch": "ground",
            "class_name": "infantry", "display_name": "Infantry", "cost": 10.0,
        }], schema=state.get_table("unit_designs").schema))
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "trade", "country_id": "USA", "effect": "weapons_market_access",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        state.update_table("seller_acceptance_profiles", pl.DataFrame([{
            "country_id": "CAN", "accepts_foreign_orders": True,
        }], schema=state.get_table("seller_acceptance_profiles").schema))
        state.update_table("foreign_unit_orders", pl.DataFrame([{
            "id": "contract-1", "buyer_country_id": "USA", "seller_country_id": "CAN",
            "design_id": "can-design", "quantity": 2, "price": 25.0,
            "status": "in_production", "reason": "Delivery in 10 days.",
        }], schema=state.get_table("foreign_unit_orders").schema))
        state.update_table("production_orders", pl.DataFrame([{
            "id": "order-1", "country_id": "USA", "design_id": "local-design",
            "quantity": 3, "priority": 4, "progress": 0.5, "eta_days": 6,
            "remaining_work": 15.0, "assigned_capacity": 2.5,
            "blocking_reason": "Capacity constrained.",
        }], schema=state.get_table("production_orders").schema))
        presenter = MilitaryPresenter()

        foreign_designs = presenter.foreign_designs_for_country(state, "USA")
        self.assertEqual(len(foreign_designs), 1)
        self.assertTrue(foreign_designs[0]["seller_accepts_orders"])
        foreign_order = presenter.foreign_orders_for_country(state, "USA")[0]
        self.assertEqual((foreign_order["status"], foreign_order["price"], foreign_order["reason"]), (
            "in_production", 25.0, "Delivery in 10 days.",
        ))
        production_order = presenter.production_orders_for_country(state, "USA")[0]
        self.assertEqual((production_order["eta_days"], production_order["assigned_capacity"]), (6, 2.5))
        self.assertEqual(production_order["blocking_reason"], "Capacity constrained.")


if __name__ == "__main__":
    unittest.main()
