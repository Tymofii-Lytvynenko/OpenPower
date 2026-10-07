from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import polars as pl

from modules.base.systems.military.research_program_system import ResearchProgramSystem
from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem
from src.shared.actions import (
    ActionCancelProductionOrder,
    ActionCreateUnitDesign,
    ActionQueueUnitProduction,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
    ActionUpdateResearchFunding,
)
from src.shared.events import EventRealSecond
from src.shared.state import GameState


class ResearchProgramSystemTest(unittest.TestCase):
    def test_idle_update_does_not_advance_research_table_revisions(self) -> None:
        state = self._state()
        before = dict(state.table_revisions)

        ResearchProgramSystem().update(state, 0.0)

        self.assertEqual(dict(state.table_revisions), before)

    def test_research_funding_action_only_advances_the_research_table_revision(self) -> None:
        state = self._state()
        before = dict(state.table_revisions)
        unrelated_tables = tuple(state.get_table(name) for name in ("unit_designs", "production_orders", "countries"))
        original_to_dicts = pl.DataFrame.to_dicts
        state.current_actions = [ActionUpdateResearchFunding("player", "USA", "ground", 0.5)]

        def fail_on_unrelated_tables(frame, *args, **kwargs):
            if any(frame is table for table in unrelated_tables):
                raise AssertionError("Research funding must not materialize unrelated military tables.")
            return original_to_dicts(frame, *args, **kwargs)

        with patch.object(pl.DataFrame, "to_dicts", new=fail_on_unrelated_tables):
            ResearchProgramSystem().update(state, 0.0)

        self.assertEqual(state.table_revisions["research_tracks"], before["research_tracks"] + 1)
        for table_name in ("unit_designs", "production_orders", "countries"):
            self.assertEqual(state.table_revisions[table_name], before[table_name], table_name)

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
        self.assertEqual(state.get_table("production_orders")["status"][0], "awaiting_deployment")
        delivered_units = state.get_table("units").filter(pl.col("unit_type") == "artillery").to_dicts()
        self.assertEqual(len(delivered_units), 1)
        self.assertEqual(delivered_units[0]["strength"], 3)
        self.assertEqual(delivered_units[0]["current_region_id"], 0)
        self.assertEqual(delivered_units[0]["unit_lifecycle"], "deployment_queued")
        self.assertEqual(state.get_table("unit_deployment_orders")["status"][0], "queued")
        self.assertEqual(state.get_table("countries")["military_count"][0], 4)

    def test_design_availability_and_ids_are_stable_across_snapshot_continuation(self) -> None:
        state = self._state()
        state.update_table("research_tracks", pl.DataFrame([{
            "id": "ground-research", "country_id": "USA", "branch": "ground",
            "research_level": 1,
        }], schema=state.get_table("research_tracks").schema))
        first_design = ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Artillery 1",
            {"cost": 20.0, "required_research_level": 1},
        )
        ResearchProgramSystem().update(state, 0.0)
        state.current_actions = [first_design]
        ResearchProgramSystem().update(state, 0.0)
        self.assertEqual(state.get_table("unit_designs")["id"].to_list(), ["design-USA-artillery-001"])

        restored = GameState.from_ipc(state.to_ipc())
        ensure_base_tables(restored)
        next_design = ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Artillery 2",
            {"cost": 30.0, "required_research_level": 1},
        )
        for replay_state in (state, restored):
            replay_state.current_actions = [next_design]
            ResearchProgramSystem().update(replay_state, 0.0)
            replay_state.current_actions = [ActionQueueUnitProduction(
                "player", "USA", "design-USA-artillery-002", 1,
            )]
            ResearchProgramSystem().update(replay_state, 0.0)

        self.assertTrue(state.get_table("unit_designs").equals(restored.get_table("unit_designs")))
        self.assertTrue(state.get_table("production_orders").equals(restored.get_table("production_orders")))
        self.assertTrue(state.get_table("research_tracks").equals(restored.get_table("research_tracks")))

    def test_cancelling_queued_order_keeps_incurred_cost(self) -> None:
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
        cancelled = state.get_table("production_orders").to_dicts()[0]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["remaining_work"], 150.0)
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 850.0)

    def test_pause_resume_and_priority_changes_preserve_partial_progress(self) -> None:
        state = self._state()
        system = ResearchProgramSystem()
        state.current_actions = [ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Artillery Brigade", {"cost": 50.0},
        )]
        system.update(state, 0.0)
        design_id = state.get_table("unit_designs")["id"][0]
        state.current_actions = [
            ActionQueueUnitProduction("player", "USA", design_id, 1, 2),
            ActionQueueUnitProduction("player", "USA", design_id, 1, 1),
        ]
        system.update(state, 0.0)
        orders = state.get_table("production_orders")
        first_id, second_id = orders["id"].to_list()
        state.update_table(
            "production_orders",
            orders.with_columns(
                pl.when(pl.col("id") == first_id).then(0.4).otherwise(pl.col("progress")).alias("progress"),
                pl.when(pl.col("id") == first_id).then(30.0).otherwise(pl.col("remaining_work")).alias("remaining_work"),
            ),
        )

        state.current_actions = [ActionSetProductionPaused("player", first_id, True)]
        system.update(state, 0.0)
        paused = {row["id"]: row for row in state.get_table("production_orders").to_dicts()}
        self.assertEqual(paused[first_id]["status"], "paused")
        self.assertEqual(paused[first_id]["progress"], 0.4)
        self.assertEqual(paused[first_id]["remaining_work"], 30.0)

        state.current_actions = [ActionSetProductionPriority("player", second_id, 7)]
        system.update(state, 0.0)
        changed = {row["id"]: row for row in state.get_table("production_orders").to_dicts()}
        self.assertEqual(changed[second_id]["priority"], 7)
        self.assertEqual(changed[first_id]["progress"], 0.4)
        self.assertEqual(changed[first_id]["remaining_work"], 30.0)

        state.current_actions = [ActionSetProductionPaused("player", first_id, False)]
        system.update(state, 0.0)
        resumed = {row["id"]: row for row in state.get_table("production_orders").to_dicts()}
        self.assertEqual(resumed[first_id]["status"], "queued")
        self.assertEqual(resumed[first_id]["progress"], 0.4)
        self.assertEqual(resumed[first_id]["remaining_work"], 30.0)

    def test_research_levels_unlock_designs_and_share_role_capabilities(self) -> None:
        state = self._state()
        state.current_actions = [ActionUpdateResearchFunding("player", "USA", "ground", 1.0)]
        state.events = [EventRealSecond(365.25 * 24 * 60 * 60 * 0.5, False)]
        system = ResearchProgramSystem()
        system.update(state, 0.0)
        track = state.get_table("research_tracks").to_dicts()[0]
        self.assertEqual(track["research_level"], 1)
        self.assertEqual(track["progress"], 0.0)

        state.events = []
        state.current_actions = [ActionCreateUnitDesign(
            "player", "USA", "ground", "artillery", "Advanced Artillery",
            {"cost": 20.0, "required_research_level": 1, "gun_range": 55.0},
        )]
        system.update(state, 0.0)
        design = state.get_table("unit_designs").to_dicts()[0]
        self.assertEqual(design["domain"], "land")
        self.assertEqual(design["research_level"], 1)
        self.assertIn('"gun_range":55.0', design["capabilities_json"])

        state.current_actions = [ActionCreateUnitDesign(
            "player", "USA", "ground", "tank", "Locked Prototype",
            {"cost": 20.0, "required_research_level": 2},
        )]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("unit_designs").height, 1)

    def test_strategic_design_requires_program_and_weapon_research_at_creation_and_queue(self) -> None:
        state = self._state()
        system = ResearchProgramSystem()
        action = ActionCreateUnitDesign(
            "player", "USA", "strategic_weapons", "strategic_missiles", "Strategic Missile",
            {"cost": 100.0},
        )
        state.current_actions = [action]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("unit_designs").is_empty())

        state.update_table("research_tracks", pl.DataFrame([
            {"id": "program", "country_id": "USA", "branch": "strategic_program", "research_level": 1},
            {"id": "weapons", "country_id": "USA", "branch": "strategic_weapons", "research_level": 1},
        ], schema=state.get_table("research_tracks").schema))
        system.update(state, 0.0)
        design = state.get_table("unit_designs").to_dicts()[0]
        self.assertEqual(design["domain"], "strategic")
        self.assertEqual(json.loads(design["research_requirements_json"]), {
            "strategic_program": 1, "strategic_weapons": 1,
        })

        tracks = state.get_table("research_tracks").to_dicts()
        tracks[1]["research_level"] = 0
        state.update_table("research_tracks", pl.DataFrame(tracks, schema=state.get_table("research_tracks").schema))
        before = state.get_table("countries")["money_reserves"][0]
        state.current_actions = [ActionQueueUnitProduction("player", "USA", design["id"], 1)]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("production_orders").is_empty())
        self.assertEqual(state.get_table("countries")["money_reserves"][0], before)

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
        state.globals["player_country_map"] = {"player": "USA"}
        return state


if __name__ == "__main__":
    unittest.main()
