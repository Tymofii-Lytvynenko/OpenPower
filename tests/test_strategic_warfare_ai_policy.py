from __future__ import annotations

import unittest
from unittest.mock import patch

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

    def test_policy_respects_doctrine_and_empty_schedule(self) -> None:
        policy = StrategicWarfarePolicy()
        state = self._state()
        state.globals["strategic_ai_doctrine"] = "first_strike"
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        countries = state.get_table("countries").with_columns(
            pl.lit(False).alias("is_playable")
        )
        state.update_table("countries", countries)
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

    def test_policy_handles_missing_required_table_and_stale_scheduled_country(self) -> None:
        policy = StrategicWarfarePolicy()
        state = self._state()
        state.tables.pop("strategic_weapons")
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        state.update_table(
            "countries",
            state.get_table("countries").filter(pl.col("id") != "CAN"),
        )
        scheduled = pl.DataFrame({"country_id": ["CAN"]}).lazy()
        with patch(
            "modules.base.systems.world.ai.strategic_warfare_policy.country_frame",
            return_value=scheduled,
        ):
            candidates = policy.build_candidates(self._context(state)).collect()
        self.assertTrue(candidates.is_empty())

    def test_policy_requires_program_research_for_a_retaliation(self) -> None:
        state = self._state()
        tracks = state.get_table("research_tracks").with_columns(
            pl.when(pl.col("branch") == "strategic_program")
            .then(pl.lit(0))
            .otherwise(pl.col("research_level"))
            .alias("research_level")
        )
        state.update_table("research_tracks", tracks)

        candidates = StrategicWarfarePolicy().build_candidates(self._context(state)).collect()

        self.assertTrue(candidates.is_empty())

    def test_policy_ignores_missing_active_wars_and_unconfirmed_incoming_orders(self) -> None:
        policy = StrategicWarfarePolicy()
        state = self._state()
        state.update_table("countries_wars", state.get_table("countries_wars").head(0))
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        state.update_table(
            "strategic_launch_orders",
            state.get_table("strategic_launch_orders").with_columns(
                pl.lit("pending").alias("status")
            ),
        )
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

    def test_policy_rejects_unknown_or_incomplete_action_rows(self) -> None:
        policy = StrategicWarfarePolicy()

        self.assertIsNone(policy.resolve_action({"action_kind": "unknown"}))
        self.assertIsNone(
            policy.resolve_action(
                {
                    "action_kind": "launch_strategic_strike",
                    "country_id": "CAN",
                    "target_country_id": "USA",
                    "weapon_id": "",
                    "target_region_id": 1,
                }
            )
        )

    def test_policy_requires_an_owned_origin_and_a_target_region(self) -> None:
        policy = StrategicWarfarePolicy()
        state = self._state()
        regions = state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2)
            .then(pl.lit(""))
            .otherwise(pl.col("owner"))
            .alias("owner")
        )
        state.update_table("regions", regions)
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        regions = state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 1)
            .then(pl.lit("MEX"))
            .otherwise(pl.col("owner"))
            .alias("owner")
        )
        state.update_table("regions", regions)
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

    def test_policy_filters_inoperable_unfunded_and_foreign_origin_weapons(self) -> None:
        policy = StrategicWarfarePolicy()

        state = self._state()
        state.update_table(
            "strategic_weapons",
            state.get_table("strategic_weapons").with_columns(
                pl.lit(False).alias("operational")
            ),
        )
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(
                pl.when(pl.col("id") == "CAN")
                .then(pl.lit(0.0))
                .otherwise(pl.col("money_reserves"))
                .alias("money_reserves")
            ),
        )
        state.update_table(
            "strategic_weapons",
            state.get_table("strategic_weapons").with_columns(
                pl.lit(1.0).alias("launch_cost")
            ),
        )
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        state.update_table(
            "strategic_weapons",
            state.get_table("strategic_weapons").with_columns(
                pl.lit(1).cast(pl.Int32).alias("origin_region_id")
            ),
        )
        self.assertTrue(policy.build_candidates(self._context(state)).collect().is_empty())

        state = self._state()
        state.update_table(
            "strategic_weapons",
            state.get_table("strategic_weapons").with_columns(
                pl.lit(999).cast(pl.Int32).alias("origin_region_id")
            ),
        )
        candidates = policy.build_candidates(self._context(state)).collect()
        self.assertEqual(candidates["target_region_id"].to_list(), [1])

    def test_origin_region_prefers_the_government_capital(self) -> None:
        policy = StrategicWarfarePolicy()
        first = {"id": 2, "owner": "CAN"}
        capital = {"id": 3, "owner": "CAN"}

        selected = policy._origin_region(
            "CAN",
            {"CAN": [first, capital]},
            {2: first, 3: capital},
            {"CAN": 3},
        )

        self.assertIs(selected, capital)

    def test_policy_number_parser_uses_the_given_default_for_invalid_text(self) -> None:
        self.assertEqual(StrategicWarfarePolicy()._number("not-a-number", 4.5), 4.5)


if __name__ == "__main__":
    unittest.main()
