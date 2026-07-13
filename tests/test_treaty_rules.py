from __future__ import annotations

import unittest

import polars as pl

from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.schema import ensure_base_tables
from src.shared.actions import ActionCreateTreaty, ActionJoinTreaty, ActionRespondTreaty
from src.shared.state import GameState


class TreatyRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.system = DiplomacySystem()

    def test_geographic_condition_filters_open_treaty_members(self) -> None:
        state = self._state()
        self._propose(state, "cultural_exchanges", ["USA", "CAN"], {
            "maximum_geographic_distance_km": 1_000.0,
        })
        proposal_id = state.get_table("pending_treaties")["id"][0]
        self._respond(state, proposal_id, "CAN")
        treaty_id = state.get_table("countries_treaties")["id"][0]

        state.current_actions = [ActionJoinTreaty("player", treaty_id, "GBR")]
        self.system.update(state, 0.1)
        members = set(state.get_table("countries_treaties")["members"][0].to_list())
        self.assertIn("GBR", members)

        state.current_actions = [ActionJoinTreaty("player", treaty_id, "FRA")]
        self.system.update(state, 0.1)
        members = set(state.get_table("countries_treaties")["members"][0].to_list())
        self.assertNotIn("FRA", members)

    def test_control_change_voids_annexation_claim_and_its_neighbor(self) -> None:
        state = self._state()
        state.update_table(
            "regions",
            pl.DataFrame({
                "id": [1, 2, 3, 4],
                "owner": ["CAN", "CAN", "CAN", "FRA"],
                "controller": ["USA", "USA", "CAN", "FRA"],
                "latitude": [0.0, 0.5, 1.0, 60.0],
                "longitude": [0.0, 0.5, 1.0, 60.0],
            }),
        )
        state.update_table("region_adjacency", pl.DataFrame({
            "region_id": [1], "neighbor_region_id": [2],
        }))
        self._propose(state, "annexation", ["USA", "CAN"], {})
        proposal_id = state.get_table("pending_treaties")["id"][0]
        self._respond(state, proposal_id, "CAN")
        self.assertEqual(state.get_table("annexation_claims").height, 2)

        state.update_table("regions", state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 1).then(pl.lit("CAN")).otherwise(pl.col("controller")).alias("controller")
        ))
        state.current_actions = []
        self.system.update(state, 0.1)
        statuses = set(state.get_table("annexation_claims")["status"].to_list())
        self.assertEqual(statuses, {"void"})

    def _propose(self, state: GameState, treaty_type: str, members: list[str], conditions: dict) -> None:
        state.current_actions = [ActionCreateTreaty(
            player_id="player",
            source_country_tag="USA",
            target_country_tag="CAN",
            treaty_type=treaty_type,
            title=treaty_type,
            terms="",
            member_country_tags=members,
            open_to_new_members=True,
            conditions=conditions,
        )]
        self.system.update(state, 0.1)

    def _respond(self, state: GameState, proposal_id: str, country_tag: str) -> None:
        state.current_actions = [ActionRespondTreaty("player", proposal_id, country_tag, True)]
        self.system.update(state, 0.1)

    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN", "GBR", "FRA"],
                "gdp": [100.0, 100.0, 100.0, 100.0],
                "military_count": [100, 100, 100, 100],
                "budget_research_ratio": [0.1, 0.1, 0.1, 0.1],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2, 3, 4],
                "owner": ["USA", "CAN", "GBR", "FRA"],
                "controller": ["USA", "CAN", "GBR", "FRA"],
                "latitude": [0.0, 0.5, 1.0, 60.0],
                "longitude": [0.0, 0.5, 1.0, 60.0],
            }),
        })
        ensure_base_tables(state)
        return state


if __name__ == "__main__":
    unittest.main()
