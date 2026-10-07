from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from modules.base.systems.world.ai.battle_strategy_policy import BattleStrategyPolicy
from modules.base.systems.world.ai_system import AISystem
from src.core.ai_framework import AITableContext, DeclarativeAIFramework
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionSetBattleStrategy
from src.shared.events import EventNewDay
from src.shared.state import GameState


class BattleStrategyAITest(unittest.TestCase):
    def _tables(self) -> dict[str, pl.DataFrame]:
        factory = UnitFactory()
        return {
            "countries": pl.DataFrame({
                "id": ["AAA", "PLAYER"], "is_playable": [True, True],
                "gdp": [1_000_000.0, 1_000_000.0], "budget_research_ratio": [0.1, 0.1],
            }),
            "units": pl.DataFrame([
                factory.create("aaa-1", "AAA", "infantry", 120, 1, GeoCoordinate(0.0, 0.0), 0),
                factory.create("player-1", "PLAYER", "infantry", 80, 1, GeoCoordinate(0.0, 0.0), 0),
            ], schema=UNIT_SCHEMA),
            "battles": pl.DataFrame([{
                "id": "battle-1", "region_id": 1, "attacker_side": "AAA",
                "defender_side": "PLAYER", "status": "active",
            }]),
            "battle_units": pl.DataFrame([
                {"battle_id": "battle-1", "unit_id": "aaa-1", "country_id": "AAA", "side": "SIDE_A"},
                {"battle_id": "battle-1", "unit_id": "player-1", "country_id": "PLAYER", "side": "SIDE_B"},
            ]),
            "battle_force_postures": pl.DataFrame(schema={
                "unit_id": pl.Utf8, "battle_id": pl.Utf8, "country_id": pl.Utf8,
                "strategy": pl.Utf8, "status": pl.Utf8,
            }),
        }

    def _context(self, tables, *, player_tag="PLAYER", delegated_domains=None, globals=None):
        return AITableContext(
            tables=tables, day_ordinal=1, total_minutes=1_440, date_text="2001-01-02",
            player_tag=player_tag, delegated_domains=delegated_domains or {},
            globals=globals or {},
        )

    def test_policy_selects_deterministic_posture_for_ai_participants(self) -> None:
        tables = self._tables()
        policy = BattleStrategyPolicy()

        first = DeclarativeAIFramework(policy).evaluate(self._context(tables))
        second = DeclarativeAIFramework(policy).evaluate(self._context(tables))

        actions = [action for action in first.actions if isinstance(action, ActionSetBattleStrategy)]
        self.assertEqual(actions, [ActionSetBattleStrategy(
            "ai_system", "battle-1", "attack", country_tag="AAA", unit_type="infantry",
        )])
        self.assertEqual(actions, list(second.actions))

    def test_player_is_excluded_and_delegated_military_scope_allows_its_orders(self) -> None:
        tables = self._tables()
        policy = BattleStrategyPolicy()
        excluded = DeclarativeAIFramework(policy).evaluate(
            self._context(tables, player_tag="AAA"),
        )
        self.assertFalse(any(
            isinstance(action, ActionSetBattleStrategy) and action.country_tag == "AAA"
            for action in excluded.actions
        ))

        delegated = DeclarativeAIFramework(policy).evaluate(self._context(
            tables, player_tag="AAA", delegated_domains={"AAA": frozenset({"military"})},
        ))
        self.assertTrue(any(
            isinstance(action, ActionSetBattleStrategy) and action.country_tag == "AAA"
            for action in delegated.actions
        ))

    def test_existing_force_order_blocks_replacing_its_entire_target_group(self) -> None:
        tables = self._tables()
        factory = UnitFactory()
        additional_unit = factory.create(
            "aaa-2", "AAA", "infantry", 60, 1, GeoCoordinate(0.0, 0.0), 0,
        )
        tables["units"] = pl.concat([
            tables["units"], pl.DataFrame([additional_unit], schema=UNIT_SCHEMA),
        ])
        tables["battle_units"] = pl.concat([
            tables["battle_units"],
            pl.DataFrame([{
                "battle_id": "battle-1", "unit_id": "aaa-2", "country_id": "AAA", "side": "SIDE_A",
            }]),
        ])
        tables["battle_force_postures"] = pl.DataFrame([{
            "unit_id": "aaa-1", "battle_id": "battle-1", "country_id": "AAA",
            "strategy": "defend", "status": "active",
        }])

        result = DeclarativeAIFramework(BattleStrategyPolicy()).evaluate(self._context(tables))

        self.assertFalse(any(
            isinstance(action, ActionSetBattleStrategy) and action.country_tag == "AAA"
            for action in result.actions
        ))

    def test_policy_retreats_from_overwhelming_disadvantage(self) -> None:
        tables = self._tables()
        unit_rows = tables["units"].to_dicts()
        unit_rows[0]["strength"] = 20
        unit_rows[1]["strength"] = 100
        tables["units"] = pl.DataFrame(unit_rows, schema=UNIT_SCHEMA)

        result = DeclarativeAIFramework(BattleStrategyPolicy()).evaluate(self._context(tables))

        actions = [action for action in result.actions if isinstance(action, ActionSetBattleStrategy)]
        self.assertEqual(actions, [ActionSetBattleStrategy(
            "ai_system", "battle-1", "retreat", country_tag="AAA", unit_type="infantry",
        )])

    def test_policy_reorganizes_low_cohesion_forces_at_a_safe_funded_location(self) -> None:
        tables = self._tables()
        unit_rows = tables["units"].to_dicts()
        unit_rows[0]["cohesion"] = 0.3
        tables["units"] = pl.DataFrame(unit_rows, schema=UNIT_SCHEMA)
        tables["regions"] = pl.DataFrame([{
            "id": 1, "owner": "AAA", "controller": "AAA",
        }])
        tables["countries"] = tables["countries"].with_columns(pl.lit(10_000.0).alias("money_reserves"))

        result = DeclarativeAIFramework(BattleStrategyPolicy()).evaluate(self._context(
            tables,
            globals={"battle_ai_reorganize_cohesion_threshold": 0.5},
        ))

        actions = [action for action in result.actions if isinstance(action, ActionSetBattleStrategy)]
        self.assertEqual(actions, [ActionSetBattleStrategy(
            "ai_system", "battle-1", "reorganize", country_tag="AAA", unit_type="infantry",
        )])

    def test_registered_ai_command_uses_authoritative_battle_strategy_handler(self) -> None:
        tables = self._tables()
        state = GameState(tables=tables)
        ensure_base_tables(state)
        state.globals["player_tag"] = "PLAYER"
        state.events = [EventNewDay(day=2, month=1, year=2001)]

        ai = AISystem()
        ai.update(state, 0.0)
        actions = [action for action in state.current_actions if isinstance(action, ActionSetBattleStrategy)]
        self.assertTrue(actions)
        self.assertTrue(all(action.player_id == "ai_system" and action.country_tag == "AAA" for action in actions))

        BattleStrategySystem().update(state, 0.0)

        posture = state.get_table("battle_force_postures").filter(pl.col("country_id") == "AAA")
        self.assertEqual(posture.height, 1)
        self.assertEqual(posture["strategy"][0], "attack")
        self.assertEqual(state.get_table("battle_command_orders")["status"][0], "applied")

    def test_ai_reorganization_uses_authoritative_cost_and_lifecycle_checks(self) -> None:
        tables = self._tables()
        unit_rows = tables["units"].to_dicts()
        unit_rows[0]["cohesion"] = 0.3
        tables["units"] = pl.DataFrame(unit_rows, schema=UNIT_SCHEMA)
        tables["countries"] = tables["countries"].with_columns(pl.lit(10_000.0).alias("money_reserves"))
        tables["regions"] = pl.DataFrame([{
            "id": 1, "owner": "AAA", "controller": "AAA", "latitude": 0.0, "longitude": 0.0,
        }])
        state = GameState(tables=tables)
        ensure_base_tables(state)
        state.globals["player_tag"] = "PLAYER"
        state.globals["battle_ai_reorganize_cohesion_threshold"] = 0.5
        state.globals["battle_reorganization_cost_per_strength"] = 0.1
        state.events = [EventNewDay(day=2, month=1, year=2001)]

        AISystem().update(state, 0.0)
        BattleStrategySystem().update(state, 0.0)

        posture = state.get_table("battle_force_postures").filter(pl.col("country_id") == "AAA")
        self.assertEqual(posture["strategy"][0], "reorganize")
        self.assertEqual(posture["status"][0], "reorganizing")
        self.assertEqual(state.get_table("battle_command_orders")["status"][0], "applied")
        self.assertAlmostEqual(state.get_table("countries").filter(pl.col("id") == "AAA")["money_reserves"][0], 9_988.0)


if __name__ == "__main__":
    unittest.main()
