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

    def test_precomputed_context_preserves_treaty_and_war_access(self) -> None:
        state = GameState(tables={
            "countries_wars": pl.DataFrame({
                "side_a": [["USA", "CAN"]], "side_b": [["MEX"]], "status": ["active"],
            }),
            "treaty_effects": pl.DataFrame({
                "country_id": ["USA", "USA"],
                "effect": ["transit_rights", "stationing_rights"],
                "detail": ['["GBR"]', '["FRA"]'],
            }),
        })
        policy = MovementAccessPolicy()
        context = policy.for_country(state, "usa")

        self.assertTrue(context.can_station({"owner": "MEX"}))
        self.assertTrue(context.can_transit({"owner": "MEX"}))
        self.assertTrue(context.can_transit({"owner": "GBR"}))
        self.assertFalse(context.can_station({"owner": "GBR"}))
        self.assertTrue(context.can_station({"owner": "FRA"}))
        self.assertTrue(context.can_transit({"owner": "FRA"}))
        self.assertTrue(context.can_station({"owner": "USA"}))

    def test_ended_war_does_not_grant_movement_access(self) -> None:
        state = GameState(tables={
            "countries_wars": pl.DataFrame({
                "side_a": [["USA"]], "side_b": [["MEX"]], "status": ["ended"],
            }),
        })

        context = MovementAccessPolicy().for_country(state, "USA")

        self.assertFalse(context.can_station({"owner": "MEX"}))
        self.assertFalse(context.can_transit({"owner": "MEX"}))

    def test_malformed_treaty_detail_has_no_country_tags(self) -> None:
        self.assertEqual(MovementAccessPolicy()._detail_tags("not-json"), ())


if __name__ == "__main__":
    unittest.main()
