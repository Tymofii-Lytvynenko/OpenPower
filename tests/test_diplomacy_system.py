import unittest

import polars as pl

from modules.base.systems.world.diplomacy_system import DiplomacySystem
from src.server.state_bootstrap import ensure_ui_support_tables
from src.shared.actions import (
    ActionCreateTreaty,
    ActionDeclareWar,
    ActionLeaveTreaty,
    ActionOfferPeace,
    ActionRespondTreaty,
)
from src.shared.events import EventTreatyProposed, EventTreatyRefused, EventWarStarted
from src.shared.state import GameState


class TestDiplomacySystem(unittest.TestCase):
    def setUp(self):
        self.system = DiplomacySystem()

    def test_treaty_create_accept_and_leave_lifecycle(self):
        state = self._build_state()
        state.current_actions = [
            ActionCreateTreaty(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                treaty_type="trade accord",
                title="North Trade",
                terms="Lower tariffs",
            )
        ]

        self.system.update(state, 0.1)

        pending = state.get_table("pending_treaties")
        self.assertEqual(len(pending), 1)
        self.assertTrue(any(isinstance(event, EventTreatyProposed) for event in state.events))
        self.assertEqual(pending["treaty_type"][0], "trade_accord")

        proposal_id = pending["id"][0]
        state.events.clear()
        state.current_actions = [
            ActionRespondTreaty(
                player_id="tester",
                treaty_id=proposal_id,
                responder_country_tag="CAN",
                accept=True,
            )
        ]

        self.system.update(state, 0.1)

        treaties = state.get_table("countries_treaties")
        self.assertEqual(len(state.get_table("pending_treaties")), 0)
        self.assertEqual(len(treaties), 1)
        self.assertEqual(treaties["name"][0], "North Trade")
        self.assertEqual(set(treaties["members"][0].to_list()), {"USA", "CAN"})
        relations = state.get_table("countries_relations")
        self.assertEqual(self._relation_value(relations, "USA", "CAN"), 35.0)
        self.assertEqual(self._relation_value(relations, "CAN", "USA"), 35.0)

        treaty_id = treaties["id"][0]
        state.events.clear()
        state.current_actions = [
            ActionLeaveTreaty(
                player_id="tester",
                treaty_id=treaty_id,
                country_tag="CAN",
            )
        ]

        self.system.update(state, 0.1)

        self.assertEqual(len(state.get_table("countries_treaties")), 0)
        relations = state.get_table("countries_relations")
        self.assertEqual(self._relation_value(relations, "USA", "CAN"), 30.0)
        self.assertEqual(self._relation_value(relations, "CAN", "USA"), 30.0)

    def test_treaty_rejection_emits_event_and_penalty(self):
        state = self._build_state()
        state.current_actions = [
            ActionCreateTreaty(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="CAN",
                treaty_type="research accord",
                title="Joint Labs",
                terms="Shared funding",
            )
        ]
        self.system.update(state, 0.1)

        proposal_id = state.get_table("pending_treaties")["id"][0]
        state.events.clear()
        state.current_actions = [
            ActionRespondTreaty(
                player_id="tester",
                treaty_id=proposal_id,
                responder_country_tag="CAN",
                accept=False,
            )
        ]

        self.system.update(state, 0.1)

        self.assertEqual(len(state.get_table("pending_treaties")), 0)
        self.assertEqual(len(state.get_table("countries_treaties")), 0)
        self.assertTrue(any(isinstance(event, EventTreatyRefused) for event in state.events))
        relations = state.get_table("countries_relations")
        self.assertEqual(self._relation_value(relations, "USA", "CAN"), 20.0)
        self.assertEqual(self._relation_value(relations, "CAN", "USA"), 20.0)

    def test_war_declaration_expands_allies_and_peace_removes_entry(self):
        state = self._build_state()
        state.update_table(
            "countries_treaties",
            pl.DataFrame(
                [
                    {
                        "id": "atlantic_pact",
                        "name": "Atlantic Pact",
                        "type": "military_alliance",
                        "members": ["GBR", "FRA"],
                        "status": "active",
                        "terms": "Shared defense",
                        "created_at": "2001-01-01 00:00",
                        "source_country_id": "",
                        "target_country_id": "",
                    }
                ],
                schema={
                    "id": pl.Utf8,
                    "name": pl.Utf8,
                    "type": pl.Utf8,
                    "members": pl.List(pl.Utf8),
                    "status": pl.Utf8,
                    "terms": pl.Utf8,
                    "created_at": pl.Utf8,
                    "source_country_id": pl.Utf8,
                    "target_country_id": pl.Utf8,
                },
            ),
        )
        state.current_actions = [
            ActionDeclareWar(
                player_id="tester",
                source_country_tag="USA",
                target_country_tag="GBR",
                casus_belli="Maritime blockade",
            )
        ]

        self.system.update(state, 0.1)

        wars = state.get_table("countries_wars")
        self.assertEqual(len(wars), 1)
        self.assertTrue(any(isinstance(event, EventWarStarted) for event in state.events))
        self.assertEqual(set(wars["side_a"][0].to_list()), {"USA"})
        self.assertEqual(set(wars["side_b"][0].to_list()), {"GBR", "FRA"})
        relations = state.get_table("countries_relations")
        self.assertEqual(self._relation_value(relations, "USA", "GBR"), -100.0)
        self.assertEqual(self._relation_value(relations, "USA", "FRA"), -100.0)

        war_id = wars["id"][0]
        state.events.clear()
        state.current_actions = [
            ActionOfferPeace(
                player_id="tester",
                war_id=war_id,
                source_country_tag="USA",
                terms="Immediate ceasefire",
            )
        ]

        self.system.update(state, 0.1)

        self.assertEqual(len(state.get_table("countries_wars")), 0)
        relations = state.get_table("countries_relations")
        self.assertEqual(self._relation_value(relations, "USA", "GBR"), -85.0)
        self.assertEqual(self._relation_value(relations, "GBR", "USA"), -85.0)

    def _build_state(self) -> GameState:
        state = GameState(
            tables={
                "countries": pl.DataFrame({"id": ["USA", "CAN", "GBR", "FRA"]}),
                "countries_relations": pl.DataFrame(
                    {
                        "source": ["USA", "CAN", "USA", "GBR", "FRA"],
                        "target": ["CAN", "USA", "GBR", "USA", "USA"],
                        "value": [25.0, 25.0, 10.0, 10.0, 5.0],
                    }
                ),
            }
        )
        ensure_ui_support_tables(state)
        return state

    def _relation_value(self, relations: pl.DataFrame, source: str, target: str) -> float:
        match = relations.filter((pl.col("source") == source) & (pl.col("target") == target))
        self.assertFalse(match.is_empty(), f"Missing relation for {source}->{target}")
        return float(match["value"][0])


if __name__ == "__main__":
    unittest.main()

