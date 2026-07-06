import unittest

import polars as pl

from modules.base.systems.world.ai_system import AISystem
from src.shared.actions import ActionCreateTreaty, ActionDeclareWar, ActionOfferPeace
from src.shared.events import EventNewDay
from src.shared.state import GameState


class TestAISystem(unittest.TestCase):
    def setUp(self):
        self.system = AISystem()

    def test_ai_proposes_treaty_for_friendly_neighbor(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN"],
                        "gdp": [10_000_000_000.0, 4_000_000_000.0],
                        "money_reserves": [2_000_000_000.0, 1_000_000_000.0],
                        "total_annual_revenue": [100.0, 80.0],
                        "total_annual_expense": [60.0, 70.0],
                        "human_dev": [0.8, 0.75],
                        "trait_threat_perception": [1.0, 1.0],
                        "military_count": [100, 80],
                        "personal_income_tax_rate": [0.2, 0.2],
                    }
                ),
                "countries_relations": pl.DataFrame(
                    {"source": ["USA"], "target": ["CAN"], "value": [82.0]}
                ),
            }
        )
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        self.system.update(state, 0.1)

        treaty_actions = [action for action in state.current_actions if isinstance(action, ActionCreateTreaty)]
        self.assertTrue(treaty_actions)
        self.assertEqual(treaty_actions[0].source_country_tag, "USA")
        self.assertEqual(treaty_actions[0].target_country_tag, "CAN")

    def test_ai_declares_war_when_hostile_and_stronger(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "MEX"],
                        "gdp": [12_000_000_000.0, 2_000_000_000.0],
                        "money_reserves": [4_000_000_000.0, 50_000_000.0],
                        "total_annual_revenue": [120.0, 15.0],
                        "total_annual_expense": [50.0, 20.0],
                        "human_dev": [0.8, 0.6],
                        "trait_threat_perception": [1.3, 1.0],
                        "military_count": [600, 80],
                        "personal_income_tax_rate": [0.2, 0.2],
                    }
                ),
                "countries_relations": pl.DataFrame(
                    {"source": ["USA"], "target": ["MEX"], "value": [-92.0]}
                ),
            }
        )
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        self.system.update(state, 0.1)

        war_actions = [action for action in state.current_actions if isinstance(action, ActionDeclareWar)]
        self.assertTrue(war_actions)
        self.assertEqual(war_actions[0].source_country_tag, "USA")
        self.assertEqual(war_actions[0].target_country_tag, "MEX")

    def test_ai_offers_peace_when_outmatched_and_broke(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN"],
                        "gdp": [3_000_000_000.0, 10_000_000_000.0],
                        "money_reserves": [-50_000_000.0, 1_000_000_000.0],
                        "total_annual_revenue": [30.0, 120.0],
                        "total_annual_expense": [180.0, 60.0],
                        "human_dev": [0.7, 0.8],
                        "trait_threat_perception": [1.1, 1.0],
                        "military_count": [40, 300],
                        "personal_income_tax_rate": [0.2, 0.2],
                    }
                ),
                "countries_wars": pl.DataFrame(
                    {
                        "id": ["war-001"],
                        "side_a": [["USA"]],
                        "side_b": [["CAN"]],
                        "status": ["active"],
                    },
                    schema={
                        "id": pl.Utf8,
                        "side_a": pl.List(pl.Utf8),
                        "side_b": pl.List(pl.Utf8),
                        "status": pl.Utf8,
                    },
                ),
            }
        )
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        self.system.update(state, 0.1)

        peace_actions = [action for action in state.current_actions if isinstance(action, ActionOfferPeace)]
        self.assertTrue(peace_actions)
        self.assertEqual(peace_actions[0].source_country_tag, "USA")
        self.assertEqual(peace_actions[0].war_id, "war-001")


if __name__ == "__main__":
    unittest.main()
