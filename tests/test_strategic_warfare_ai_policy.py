from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.strategic_warfare_system import StrategicWarfareSystem
from modules.base.systems.world.ai.strategic_warfare_policy import StrategicWarfarePolicy
from src.core.ai_framework import AITableContext, DeclarativeAIFramework
from src.shared.actions import ActionLaunchStrategicStrike
from src.shared.state import GameState


class StrategicWarfareAIPolicyTest(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"],
                "money_reserves": [100.0, 100.0],
                "gdp": [1000.0, 900.0],
                "military_count": [10, 8],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["USA", "CAN"],
                "controller": ["USA", "CAN"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0, 5.0],
                "infrastructure_health": [1.0, 1.0],
            }),
            "countries_wars": pl.DataFrame({
                "id": ["war"], "name": ["War"], "side_a": [["USA"]], "side_b": [["CAN"]],
                "status": ["active"], "casus_belli": [""], "created_at": [""],
                "leader_a": ["USA"], "leader_b": ["CAN"], "intent_a": [""], "intent_b": [""],
            }),
        })
        ensure_base_tables(state)
        state.globals.update({
            "player_tag": "USA",
            "strategic_authorization_policy": "war",
            "strategic_flight_minutes": 10,
        })
        state.update_table("research_tracks", pl.DataFrame([
            {"id": "can-program", "country_id": "CAN", "branch": "strategic_program", "research_level": 1},
            {"id": "can-weapons", "country_id": "CAN", "branch": "strategic_weapons", "research_level": 1},
        ], schema=state.get_table("research_tracks").schema))
        state.update_table("strategic_weapons", pl.DataFrame([{
            "id": "can-icbm", "country_id": "CAN", "weapon_type": "icbm", "weapon_class": "icbm",
            "quantity": 2, "ready": 2, "origin_region_id": 2, "range_km": 12000.0,
            "payload_level": 1, "max_payload_level": 1, "operational": True, "launch_cost": 0.0,
        }], schema=state.get_table("strategic_weapons").schema))
        state.update_table("strategic_launch_orders", pl.DataFrame([{
            "id": "incoming", "country_id": "USA", "weapon_id": "usa-icbm", "weapon_type": "icbm",
            "target_country_id": "CAN", "target_region_id": 2, "target_mode": "military",
            "payload_level": 1, "status": "impact", "updated_at_minute": 100,
            "launched_at_minute": 80, "resolves_at_minute": 100,
        }], schema=state.get_table("strategic_launch_orders").schema))
        return state

    def _context(self, state: GameState) -> AITableContext:
        return AITableContext(
            tables=state.tables,
            day_ordinal=1,
            total_minutes=1440,
            date_text="2000-01-02",
            player_tag="USA",
            globals=state.globals,
        )

    def test_ai_retaliates_only_after_confirmed_hostile_impact_and_uses_shared_validator(self) -> None:
        state = self._state()
        evaluation = DeclarativeAIFramework(StrategicWarfarePolicy()).evaluate(self._context(state))

        self.assertEqual(len(evaluation.actions), 1)
        action = evaluation.actions[0]
        self.assertIsInstance(action, ActionLaunchStrategicStrike)
        self.assertEqual(action.player_id, "ai_system")
        self.assertEqual(action.country_tag, "CAN")
        self.assertEqual(action.target_country_tag, "USA")
        self.assertEqual(action.origin_region_id, 2)
        state.current_actions = list(evaluation.actions)

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders").filter(pl.col("status") == "pending").height, 1)
        self.assertEqual(
            state.get_table("strategic_weapons").filter(pl.col("id") == "can-icbm")["quantity"][0],
            1,
        )

    def test_ai_does_not_repeat_a_retaliation_for_the_same_impact(self) -> None:
        state = self._state()
        orders = state.get_table("strategic_launch_orders")
        rows = orders.to_dicts()
        rows.append({
            **rows[0],
            "id": "retaliation-already-launched",
            "country_id": "CAN",
            "weapon_id": "can-icbm",
            "target_country_id": "USA",
            "launched_at_minute": 100,
            "status": "pending",
        })
        state.update_table("strategic_launch_orders", pl.DataFrame(rows, schema=orders.schema))

        evaluation = DeclarativeAIFramework(StrategicWarfarePolicy()).evaluate(self._context(state))

        self.assertEqual(evaluation.actions, ())

    def test_ai_does_not_research_or_launch_before_both_required_tracks(self) -> None:
        state = self._state()
        tracks = state.get_table("research_tracks")
        rows = tracks.to_dicts()
        rows[1]["research_level"] = 0
        state.update_table("research_tracks", pl.DataFrame(rows, schema=tracks.schema))

        evaluation = DeclarativeAIFramework(StrategicWarfarePolicy()).evaluate(self._context(state))

        self.assertEqual(evaluation.actions, ())


if __name__ == "__main__":
    unittest.main()
