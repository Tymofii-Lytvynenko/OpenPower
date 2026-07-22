from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.military.research_program_system import ResearchProgramSystem
from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem
from src.shared.actions import ActionCancelProductionOrder, ActionCreateUnitDesign, ActionQueueUnitProduction, ActionUpdateResearchFunding
from src.shared.events import EventRealSecond
from src.shared.state import GameState


class ResearchProgramSystemTest(unittest.TestCase):
    def test_treaty_research_capacity_accelerates_track_progress(self) -> None:
        state = self._state()
        state.current_actions = [ActionUpdateResearchFunding("player", "USA", "ground", 1.0)]
        state.events = [EventRealSecond(365.25 * 24 * 60 * 60 * 0.1, False)]
        ResearchProgramSystem().update(state, 0.1)

        progress = state.get_table("research_tracks")["progress"][0]
        self.assertAlmostEqual(progress, 0.2, places=6)

    def test_design_and_production_queue_are_authoritatively_created(self) -> None:
        state = self._state()
        state.current_actions = [ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Artillery Brigade", {"cost": 50.0, "firepower": 2.0},
        )]
        system = ResearchProgramSystem()
        system.update(state, 0.0)
        design_id = state.get_table("unit_designs")["id"][0]

        state.current_actions = [ActionQueueUnitProduction("player", "USA", design_id, 3, 2)]
        state.events = []
        system.update(state, 0.0)
        order = state.get_table("production_orders").to_dicts()[0]
        self.assertEqual(order["design_id"], design_id)
        self.assertEqual(order["quantity"], 3)
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 850.0)

        state.current_actions = []
        state.events = [EventRealSecond(365.25 * 24 * 60 * 60 / 24, False)]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("production_orders")["status"][0], "completed")

        MilitarySystem().update(state, 0.0)
        self.assertEqual(state.get_table("production_orders")["status"][0], "delivered")
        delivered_units = state.get_table("units").filter(pl.col("unit_type") == "artillery").to_dicts()
        self.assertEqual(len(delivered_units), 1)
        self.assertEqual(delivered_units[0]["strength"], 3)
        self.assertEqual(delivered_units[0]["current_region_id"], 1)
        self.assertEqual(state.get_table("countries")["military_count"][0], 4)

    def test_cancelling_queued_order_refunds_reserved_cost(self) -> None:
        state = self._state()
        system = ResearchProgramSystem()
        state.current_actions = [ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Artillery Brigade", {"cost": 50.0},
        )]
        system.update(state, 0.0)
        design_id = state.get_table("unit_designs")["id"][0]

        state.current_actions = [ActionQueueUnitProduction("player", "USA", design_id, 3)]
        system.update(state, 0.0)
        order_id = state.get_table("production_orders")["id"][0]
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 850.0)

        state.current_actions = [ActionCancelProductionOrder("player", order_id)]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("production_orders").is_empty())
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 1000.0)

    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"], "gdp": [100.0], "budget_research_ratio": [0.1], "money_reserves": [1000.0], "military_count": [1],
            }),
            "regions": pl.DataFrame({
                "id": [1], "owner": ["USA"], "latitude": [38.0], "longitude": [-97.0],
            }),
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["research"], "country_id": ["USA"], "effect": ["research_capacity_bonus"],
                "value": [10.0], "detail": ['["USA"]'],
            }),
        })
        ensure_base_tables(state)
        return state


if __name__ == "__main__":
    unittest.main()
