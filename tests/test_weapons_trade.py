from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.military.military_system import MilitarySystem
from src.server.state_bootstrap import ensure_ui_support_tables
from src.shared.actions import ActionBuyMarketUnit
from src.shared.state import GameState


class WeaponsTradeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.system = MilitarySystem()

    def test_members_only_listing_creates_unit_for_weapons_trade_members(self) -> None:
        state = self._state()
        state.current_actions = [ActionBuyMarketUnit("player", "listing-1", "USA", 2)]
        self.system.update(state, 0.1)

        countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
        self.assertEqual(countries["USA"]["money_reserves"], 800.0)
        self.assertEqual(countries["CAN"]["money_reserves"], 200.0)
        self.assertEqual(countries["USA"]["military_count"], 12)
        acquired = state.get_table("units").filter((pl.col("owner") == "USA") & (pl.col("unit_type") == "tank"))
        self.assertEqual(acquired.height, 1)
        self.assertEqual(acquired["strength"][0], 2)
        self.assertTrue(state.get_table("unit_market_listings").is_empty())

    def test_weapons_embargo_blocks_even_authorized_members_only_listing(self) -> None:
        state = self._state(embargoed=True)
        state.current_actions = [ActionBuyMarketUnit("player", "listing-1", "USA", 2)]
        self.system.update(state, 0.1)

        countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
        self.assertEqual(countries["USA"]["money_reserves"], 1_000.0)
        self.assertEqual(countries["CAN"]["money_reserves"], 0.0)
        self.assertEqual(state.get_table("unit_market_listings")["quantity"][0], 2)

    def _state(self, embargoed: bool = False) -> GameState:
        effects = [
            {"treaty_id": "weapons", "country_id": "USA", "effect": "weapons_market_access", "value": 1.0, "detail": '["CAN"]'},
            {"treaty_id": "weapons", "country_id": "CAN", "effect": "weapons_market_access", "value": 1.0, "detail": '["USA"]'},
        ]
        if embargoed:
            effects.append({
                "treaty_id": "embargo", "country_id": "USA", "effect": "weapons_trade_embargo", "value": 1.0, "detail": '["CAN"]',
            })
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "money_reserves": [1_000.0, 0.0], "military_count": [10, 10],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"], "latitude": [0.0, 1.0], "longitude": [0.0, 1.0],
            }),
            "treaty_effects": pl.DataFrame(effects),
        })
        ensure_ui_support_tables(state)
        state.update_table("unit_designs", pl.DataFrame({
            "id": ["tank-v1"], "country_id": ["CAN"], "branch": ["land"], "class_name": ["tank"],
            "display_name": ["Tank"], "quality": [1.0], "cost": [100.0], "speed": [1.0], "firepower": [1.0],
        }))
        state.update_table("unit_market_listings", pl.DataFrame({
            "id": ["listing-1"], "seller_country_id": ["CAN"], "design_id": ["tank-v1"], "quantity": [2],
            "price": [100.0], "eligibility": ["members_only"],
        }))
        return state


if __name__ == "__main__":
    unittest.main()
