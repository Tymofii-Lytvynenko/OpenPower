from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.economy.diplomatic_aid_system import DiplomaticAidSystem
from src.shared.events import EventRealSecond
from src.shared.state import GameState


class DiplomaticAidSystemTest(unittest.TestCase):
    def test_aid_respects_donor_and_recipient_caps(self) -> None:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "gdp": [100.0, 20.0], "money_reserves": [1_000.0, 1_000.0],
                "total_annual_expense": [1_000.0, 100.0], "trade_expense": [0.0, 100.0],
            }),
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["aid"], "country_id": ["CAN"], "effect": ["economic_aid_recipient"],
                "value": [0.10], "detail": ['["USA"]'],
            }),
        })
        state.events = [EventRealSecond(365.25 * 24 * 60 * 60, False)]
        DiplomaticAidSystem().update(state, 0.1)

        transfer = state.get_table("diplomatic_aid_transfers").to_dicts()[0]
        self.assertEqual(transfer["annual_amount"], 10.0)
        countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
        self.assertEqual(countries["USA"]["money_reserves"], 990.0)
        self.assertEqual(countries["CAN"]["money_reserves"], 1_010.0)


if __name__ == "__main__":
    unittest.main()
