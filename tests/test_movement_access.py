from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.military.movement_access import MovementAccessPolicy
from src.shared.state import GameState


class MovementAccessPolicyTest(unittest.TestCase):
    def test_transit_right_allows_passing_through_without_stationing(self) -> None:
        state = GameState(tables={
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["transit"], "country_id": ["USA"], "effect": ["transit_rights"],
                "value": [1.0], "detail": ['["CAN"]'],
            }),
        })
        policy = MovementAccessPolicy()
        canadian_region = {"owner": "CAN"}
        self.assertTrue(policy.can_transit(state, "USA", canadian_region))
        self.assertFalse(policy.can_station(state, "USA", canadian_region))


if __name__ == "__main__":
    unittest.main()
