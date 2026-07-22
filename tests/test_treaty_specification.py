from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.schema import ensure_base_tables
from src.shared.actions import ActionCreateTreaty, ActionJoinTreaty, ActionRespondTreaty
from src.shared.state import GameState
from src.shared.treaties import TREATY_DEFINITIONS


class TreatySpecificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.system = DiplomacySystem()

    def test_catalog_covers_every_requested_treaty_type(self) -> None:
        expected = {
            "request_war_declaration", "alliance", "military_trespassing_right",
            "request_military_presence_removal", "annexation", "free_region",
            "cultural_exchanges", "noble_cause", "research_partnership",
            "human_development_collaboration", "economic_partnership", "common_market",
            "economic_aid", "assume_foreign_debt", "economic_embargo", "weapons_trade",
            "weapons_trade_embargo",
        }
        self.assertEqual(set(TREATY_DEFINITIONS), expected)
        self.assertTrue(TREATY_DEFINITIONS["alliance"].long_term)
        self.assertTrue(TREATY_DEFINITIONS["economic_aid"].two_sided)
        self.assertFalse(TREATY_DEFINITIONS["annexation"].long_term)

    def test_multilateral_open_treaty_requires_acceptance_and_checks_conditions(self) -> None:
        state = self._state()
        self._propose(
            state,
            treaty_type="cultural_exchanges",
            members=["USA", "CAN", "GBR"],
            open_to_new_members=True,
            conditions={"max_economic_strength_ratio": 1.5},
        )

        proposal_id = state.get_table("pending_treaties")["id"][0]
        self._respond(state, proposal_id, "CAN")
        self.assertEqual(len(state.get_table("pending_treaties")), 1)
        self._respond(state, proposal_id, "GBR")

        treaty = state.get_table("countries_treaties").to_dicts()[0]
        self.assertEqual(set(treaty["members"]), {"USA", "CAN", "GBR"})
        self.assertTrue(treaty["open_to_new_members"])

        state.current_actions = [ActionJoinTreaty("player", treaty["id"], "FRA")]
        self.system.update(state, 0.1)
        self.assertEqual(set(state.get_table("countries_treaties")["members"][0].to_list()), {"USA", "CAN", "GBR"})

    def test_punctual_presence_removal_relocates_foreign_units(self) -> None:
        state = self._state()
        state.update_table(
            "units",
            pl.DataFrame(
                {
                    "id": ["CAN-army-001"],
                    "owner": ["CAN"],
                    "current_region_id": [1],
                    "latitude": [5.0],
                    "longitude": [5.0],
                    "source_region_id": [1],
                    "source_latitude": [5.0],
                    "source_longitude": [5.0],
                    "target_region_id": [-1],
                    "target_latitude": [5.0],
                    "target_longitude": [5.0],
                    "departed_at_minute": [0],
                    "arrival_at_minute": [0],
                    "movement_progress": [0.0],
                    "is_moving": [False],
                    "strength": [100],
                    "unit_type": ["army"],
                }
            ),
        )
        self._propose(state, treaty_type="request_military_presence_removal", members=["USA", "CAN"])
        proposal_id = state.get_table("pending_treaties")["id"][0]
        self._respond(state, proposal_id, "CAN")

        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["current_region_id"], 3)
        self.assertFalse(unit["is_moving"])
        self.assertEqual(state.get_table("countries_treaties")["status"][0], "completed")

    def test_long_term_effects_publish_budget_research_and_production_modifiers(self) -> None:
        state = self._state()
        self._propose(state, treaty_type="research_partnership", members=["USA", "CAN"])
        proposal_id = state.get_table("pending_treaties")["id"][0]
        self._respond(state, proposal_id, "CAN")
        effects = state.get_table("treaty_effects")
        self.assertEqual(set(effects["effect"].to_list()), {"research_capacity_bonus"})
        self.assertTrue(all(value > 0 for value in effects["value"].to_list()))
        self.assertTrue(all(value > 0 for value in state.get_table("countries")["treaty_maintenance"].to_list()[:2]))

    def _propose(
        self,
        state: GameState,
        *,
        treaty_type: str,
        members: list[str],
        open_to_new_members: bool = False,
        conditions: dict | None = None,
    ) -> None:
        state.current_actions = [
            ActionCreateTreaty(
                player_id="player",
                source_country_tag="USA",
                target_country_tag="CAN",
                treaty_type=treaty_type,
                title=treaty_type,
                terms="",
                member_country_tags=members,
                conditions=conditions or {},
                open_to_new_members=open_to_new_members,
            )
        ]
        self.system.update(state, 0.1)

    def _respond(self, state: GameState, proposal_id: str, country_tag: str) -> None:
        state.current_actions = [ActionRespondTreaty("player", proposal_id, country_tag, True)]
        self.system.update(state, 0.1)

    def _state(self) -> GameState:
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN", "GBR", "FRA"],
                        "gdp": [100.0, 100.0, 100.0, 200.0],
                        "military_count": [100, 100, 100, 200],
                        "budget_research_ratio": [0.1, 0.1, 0.1, 0.1],
                        "human_dev": [0.9, 0.6, 0.7, 0.8],
                        "money_reserves": [1000.0, 1000.0, 1000.0, 1000.0],
                    }
                ),
                "countries_relations": pl.DataFrame(
                    {
                        "source": ["USA", "CAN", "USA", "GBR", "CAN", "GBR"],
                        "target": ["CAN", "USA", "GBR", "USA", "GBR", "CAN"],
                        "value": [40.0, 40.0, 40.0, 40.0, 40.0, 40.0],
                    }
                ),
                "regions": pl.DataFrame(
                    {
                        "id": [1, 2, 3],
                        "owner": ["USA", "CAN", "CAN"],
                        "controller": ["USA", "USA", "CAN"],
                        "latitude": [5.0, 10.0, 20.0],
                        "longitude": [5.0, 10.0, 20.0],
                    }
                ),
            }
        )
        ensure_base_tables(state)
        return state


if __name__ == "__main__":
    unittest.main()
