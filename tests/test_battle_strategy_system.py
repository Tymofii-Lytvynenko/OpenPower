from __future__ import annotations

import unittest
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.battle_strategy_system import BattleStrategySystem
from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import MilitarySystem, UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionOccupyRegion, ActionSetBattleStrategy
from src.shared.state import GameState


class BattleStrategySystemTest(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0]}),
            "units": pl.DataFrame([{
                "id": "usa-1", "owner": "USA", "unit_type": "infantry", "strength": 100,
                "current_region_id": 1, "latitude": 10.0, "longitude": 20.0,
                "is_moving": False, "readiness_status": "ready",
            }], schema=UNIT_SCHEMA),
            "battles": pl.DataFrame([{
                "id": "battle-1", "war_id": "war-1", "region_id": 1,
                "attacker_side": "USA", "defender_side": "CAN", "status": "active",
            }]),
            "battle_units": pl.DataFrame([{"battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA"}]),
        })
        ensure_base_tables(state)
        return state

    def test_posture_is_per_owner_and_changes_combat_projection(self) -> None:
        state = self._state()
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "attack", country_tag="USA", unit_type="infantry")]
        BattleStrategySystem().update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["combat_posture"], "attack")
        self.assertEqual(unit["combat_strength_modifier"], 1.1)
        self.assertEqual(state.get_table("battle_command_orders")["affected_unit_ids"].to_list()[0], ["usa-1"])

    def test_supported_stationary_postures_apply_distinct_combat_projections(self) -> None:
        state = self._state()
        expected = {
            "attack": (1.10, 1.00, 1.10, 1.15, 0.95, 0.90, 0.85),
            "defend": (0.96, 1.15, 0.82, 0.85, 1.00, 1.15, 1.15),
            "hold": (1.00, 1.00, 0.95, 1.00, 1.00, 1.00, 1.00),
            "back_off": (0.82, 1.00, 0.75, 0.85, 0.85, 1.05, 0.75),
        }
        system = BattleStrategySystem()

        for strategy, (attack, defense, casualty, risk, readiness, holding, counterattack) in expected.items():
            state.current_actions = [ActionSetBattleStrategy(
                "USA", "battle-1", strategy, country_tag="USA", unit_type="infantry",
            )]
            system.update(state, 0.0)
            unit = state.get_table("units").to_dicts()[0]
            self.assertEqual(unit["combat_posture"], strategy)
            self.assertAlmostEqual(unit["combat_strength_modifier"], attack)
            self.assertAlmostEqual(unit["combat_defense_modifier"], defense)
            self.assertAlmostEqual(unit["combat_casualty_modifier"], casualty)
            self.assertAlmostEqual(unit["combat_attack_risk_modifier"], risk)
            self.assertAlmostEqual(unit["combat_readiness_modifier"], readiness)
            self.assertAlmostEqual(unit["combat_holding_modifier"], holding)
            self.assertAlmostEqual(unit["combat_counterattack_modifier"], counterattack)

    def test_force_type_filter_does_not_change_other_units_or_allied_country(self) -> None:
        state = self._state()
        factory = UnitFactory()
        extra_units = [
            factory.create("usa-armor", "USA", "armor", 50, 1, GeoCoordinate(10.0, 20.0), 0),
            factory.create("mex-infantry", "MEX", "infantry", 40, 1, GeoCoordinate(10.0, 20.0), 0),
        ]
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame(extra_units, schema=UNIT_SCHEMA),
        ]))
        participants = state.get_table("battle_units")
        state.update_table("battle_units", pl.concat([
            participants,
            pl.DataFrame([
                {"battle_id": "battle-1", "unit_id": "usa-armor", "country_id": "USA"},
                {"battle_id": "battle-1", "unit_id": "mex-infantry", "country_id": "MEX"},
            ], schema=participants.schema),
        ]))
        state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "attack", country_tag="USA", unit_type="infantry",
        )]

        BattleStrategySystem().update(state, 0.0)

        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertEqual(units["usa-1"]["combat_posture"], "attack")
        self.assertEqual(units["usa-armor"]["combat_posture"], "hold")
        self.assertEqual(units["mex-infantry"]["combat_posture"], "hold")
        self.assertEqual(state.get_table("battle_command_orders")["affected_unit_ids"].to_list()[0], ["usa-1"])

    def test_unauthorized_command_is_rejected_without_posture_change(self) -> None:
        state = self._state()
        before_units = state.get_table("units").to_dicts()
        before_unit_revision = state.table_revisions.get("units", 0)
        state.current_actions = [ActionSetBattleStrategy("CAN", "battle-1", "attack", country_tag="USA")]
        BattleStrategySystem().update(state, 0.0)
        self.assertEqual(state.get_table("units").to_dicts(), before_units)
        self.assertEqual(state.table_revisions.get("units", 0), before_unit_revision)
        self.assertEqual(state.get_table("battle_command_orders").height, 0)
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_same_boundary_force_specific_order_wins_independent_of_arrival_order(self) -> None:
        actions = [
            ActionSetBattleStrategy("USA", "battle-1", "attack", country_tag="USA"),
            ActionSetBattleStrategy("USA", "battle-1", "attack", country_tag="USA", unit_type="infantry"),
            ActionSetBattleStrategy("USA", "battle-1", "defend", country_tag="USA", unit_type="infantry"),
        ]
        outcomes = []
        for batch in (actions, list(reversed(actions))):
            state = self._state()
            state.current_actions = batch
            BattleStrategySystem().update(state, 0.0)
            outcomes.append((
                state.get_table("units").select("combat_posture").to_dicts(),
                state.get_table("battle_command_orders").select("strategy", "status").to_dicts(),
            ))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][0], [{"combat_posture": "defend"}])
        self.assertEqual(outcomes[0][1], [
            {"strategy": "attack", "status": "applied"},
            {"strategy": "attack", "status": "applied"},
            {"strategy": "defend", "status": "applied"},
        ])

    def test_scenario_rejected_order_leaves_authoritative_tables_and_revisions_unchanged(self) -> None:
        state = self._state()
        unit_rows = state.get_table("units").to_dicts()
        for key in (
            "combat_posture", "combat_strength_modifier", "combat_casualty_modifier",
            "combat_defense_modifier", "combat_attack_risk_modifier", "combat_readiness_modifier",
            "combat_holding_modifier", "combat_counterattack_modifier",
        ):
            unit_rows[0][key] = None
        state.update_table("units", pl.DataFrame(unit_rows, schema=UNIT_SCHEMA))
        state.globals["battle_strategy_constraints"] = [{
            "battle_id": "battle-1", "country_id": "USA", "unit_type": "infantry",
            "allowed_strategies": ["defend"],
        }]
        state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "attack", country_tag="USA", unit_type="infantry",
        )]
        table_names = (
            "units", "battles", "battle_units", "battle_force_postures",
            "battle_command_orders", "unit_movement_routes", "regions", "countries",
        )
        before_tables = {name: state.get_table(name).to_dicts() for name in table_names if name in state.tables}
        before_revisions = {name: state.table_revisions.get(name, 0) for name in table_names}

        BattleStrategySystem().update(state, 0.0)

        self.assertEqual(
            {name: state.get_table(name).to_dicts() for name in before_tables}, before_tables,
        )
        self.assertEqual(
            {name: state.table_revisions.get(name, 0) for name in table_names}, before_revisions,
        )
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")
        self.assertIn("Scenario does not allow", state.journal.command_results[-1]["reason"])

    def test_retreat_withdraws_to_rear_regroups_and_returns_to_capital(self) -> None:
        state = self._state()
        regions = pl.DataFrame([
            {"id": 1, "owner": "USA", "latitude": 10.0, "longitude": 19.0},
            {"id": 2, "owner": "USA", "latitude": 10.0, "longitude": 20.0},
        ])
        state.update_table("regions", regions)
        state.update_table("region_adjacency", pl.DataFrame([{"region_id": 1, "neighbor_region_id": 2}]))
        state.update_table("country_governments", pl.DataFrame([{"country_id": "USA", "capital_region_id": 1}]))
        unit_rows = state.get_table("units").to_dicts()
        unit_rows[0].update(current_region_id=2, latitude=10.0, longitude=20.0)
        state.update_table("units", pl.DataFrame(unit_rows, schema=UNIT_SCHEMA))
        state.update_table("battle_units", pl.DataFrame([{
            "battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA", "side": "SIDE_A",
        }]))
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "retreat", country_tag="USA")]

        system = BattleStrategySystem()
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["unit_lifecycle"], "battle_retreating")
        self.assertTrue(unit["is_moving"])
        self.assertEqual(unit["target_region_id"], 2)
        self.assertNotEqual((unit["target_latitude"], unit["target_longitude"]), (unit["latitude"], unit["longitude"]))
        self.assertEqual(len(CombatSystem()._stationary_units_by_region([unit])[2]), 1)

        state.time.total_minutes = int(unit["arrival_at_minute"])
        moved = MilitarySystem()._update_unit_movements(state, state.get_table("units"), state.time.total_minutes)
        state.update_table("units", moved)
        state.current_actions = []
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        self.assertEqual(unit["unit_lifecycle"], "reorganizing")
        self.assertEqual(posture["status"], "reorganizing")
        self.assertEqual(posture["strategy"], "retreat")

        state.time.total_minutes = int(posture["expires_at_minute"])
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        self.assertEqual(posture["status"], "returning")
        self.assertEqual(unit["unit_lifecycle"], "battle_returning")
        self.assertTrue(unit["is_moving"])
        self.assertEqual(route["destination_region_id"], 1)
        self.assertEqual(state.get_table("battle_units").filter(pl.col("unit_id") == "usa-1").height, 0)

        state.time.total_minutes = int(unit["arrival_at_minute"])
        moved = MilitarySystem()._update_unit_movements(state, state.get_table("units"), state.time.total_minutes)
        state.update_table("units", moved)
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        self.assertEqual(unit["current_region_id"], 1)
        self.assertEqual(unit["combat_posture"], "hold")
        self.assertEqual(posture["status"], "completed")

    def test_concluded_battle_cancels_a_pending_retreat_without_resuming_combat(self) -> None:
        state = self._state()
        battle_rows = state.get_table("battles").to_dicts()
        battle_rows[0]["status"] = "concluded"
        state.update_table("battles", pl.DataFrame(battle_rows))
        unit_rows = state.get_table("units").to_dicts()
        unit_rows[0].update(
            combat_posture="retreat", is_moving=True, unit_lifecycle="battle_retreating",
            source_latitude=10.0, source_longitude=20.0, target_latitude=10.1, target_longitude=20.0,
            departed_at_minute=0, arrival_at_minute=100, movement_progress=0.0,
        )
        state.update_table("units", pl.DataFrame(unit_rows, schema=UNIT_SCHEMA))
        state.update_table("battle_force_postures", pl.DataFrame([{
            "unit_id": "usa-1", "battle_id": "battle-1", "country_id": "USA", "strategy": "retreat",
            "issuer_player_id": "USA", "status": "retreating", "effective_at_minute": 0,
        }], schema=state.get_table("battle_force_postures").schema))
        state.update_table("unit_movement_routes", pl.DataFrame([{
            "unit_id": "usa-1", "owner_country_id": "USA", "source_region_id": 1,
            "destination_region_id": 1, "route_region_ids": [1], "route_index": 0,
            "status": "retreating", "updated_at_minute": 0,
        }], schema=state.get_table("unit_movement_routes").schema))
        state.time.total_minutes = 50

        BattleStrategySystem().update(state, 0.0)

        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        self.assertFalse(unit["is_moving"])
        self.assertEqual(unit["unit_lifecycle"], "available")
        self.assertEqual(unit["combat_posture"], "hold")
        self.assertEqual(posture["status"], "cancelled")
        self.assertEqual(route["status"], "interrupted")

    def test_configured_preset_applies_unit_type_defaults_and_specific_order_wins(self) -> None:
        state = self._state()
        extra = UnitFactory().create("usa-2", "USA", "armor", 50, 1, GeoCoordinate(10.0, 20.0), 0)
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([extra], schema=UNIT_SCHEMA),
        ]))
        participants = state.get_table("battle_units")
        state.update_table("battle_units", pl.concat([
            participants,
            pl.DataFrame([{
                "battle_id": "battle-1", "unit_id": "usa-2", "country_id": "USA", "side": "SIDE_A",
            }], schema=participants.schema),
        ]))
        state.globals["battle_strategy_presets"] = {
            "balanced": {"default": "defend", "unit_types": {"infantry": "attack"}},
        }
        system = BattleStrategySystem()
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "attack", country_tag="USA", unit_type="infantry")]
        system.update(state, 0.0)

        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "balanced", country_tag="USA")]
        system.update(state, 0.0)

        postures = {row["unit_id"]: row for row in state.get_table("battle_force_postures").to_dicts()}
        self.assertEqual(postures["usa-1"]["strategy"], "attack")
        self.assertEqual(postures["usa-2"]["strategy"], "defend")
        latest_order = state.get_table("battle_command_orders").to_dicts()[-1]
        self.assertEqual(latest_order["affected_unit_ids"], ["usa-2"])

    def test_unsupported_per_type_preset_is_recorded_as_a_visible_rejection(self) -> None:
        state = self._state()
        state.globals["battle_strategy_presets"] = {
            "invalid": {"default": "defend", "unit_types": {"infantry": "unsupported_posture"}},
        }
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "invalid", country_tag="USA")]

        BattleStrategySystem().update(state, 0.0)

        order = state.get_table("battle_command_orders").to_dicts()[0]
        self.assertEqual(order["status"], "rejected")
        self.assertIn("unsupported_posture", order["reason"])
        self.assertEqual(state.get_table("battle_force_postures").height, 0)
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_back_off_stops_assault_and_reorganization_recovers_after_cost_and_deadline(self) -> None:
        state = self._state()
        state.update_table("countries", pl.DataFrame([{
            "id": "USA", "money_reserves": 1_000.0,
        }], schema=state.get_table("countries").schema))
        state.globals["battle_reorganization_cost_per_strength"] = 0.1
        state.globals["battle_reorganization_minutes"] = 60
        system = BattleStrategySystem()
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "back_off", country_tag="USA")]
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["engagement_mode"], "")
        self.assertEqual(unit["combat_posture"], "back_off")
        self.assertTrue(unit["is_moving"])
        self.assertEqual(unit["unit_lifecycle"], "battle_disengaging")
        arrival = int(unit["arrival_at_minute"])
        self.assertEqual(state.get_table("unit_movement_routes")["status"][0], "disengaging")

        state.time.total_minutes = arrival
        moved = MilitarySystem()._update_unit_movements(state, state.get_table("units"), arrival)
        state.update_table("units", moved)
        state.current_actions = []
        system.update(state, 0.0)
        self.assertFalse(state.get_table("units")["is_moving"][0])
        self.assertEqual(state.get_table("unit_movement_routes")["status"][0], "arrived")

        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "reorganize", country_tag="USA")]
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        self.assertEqual(unit["unit_lifecycle"], "reorganizing")
        self.assertEqual(unit["reorganization_until_minute"], arrival + 60)
        self.assertEqual(posture["status"], "reorganizing")
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 990.0)

        state.time.total_minutes = arrival + 60
        state.current_actions = []
        system.update(state, 0.0)
        self.assertEqual(state.get_table("units")["unit_lifecycle"][0], "available")
        self.assertEqual(state.get_table("battle_force_postures")["status"][0], "completed")

    def test_retreat_route_block_is_reported_and_force_remains_out_of_assault(self) -> None:
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "USA", "latitude": 10.0, "longitude": 19.0},
            {"id": 2, "owner": "USA", "latitude": 10.0, "longitude": 20.0},
        ]))
        state.update_table("region_adjacency", pl.DataFrame([{"region_id": 1, "neighbor_region_id": 2}]))
        state.update_table("country_governments", pl.DataFrame([{"country_id": "USA", "capital_region_id": 1}]))
        state.update_table("battle_units", pl.DataFrame([{
            "battle_id": "battle-1", "unit_id": "usa-1", "country_id": "USA", "side": "SIDE_A",
        }], schema=state.get_table("battle_units").schema))
        state.current_actions = [ActionSetBattleStrategy("USA", "battle-1", "retreat", country_tag="USA")]
        system = BattleStrategySystem()
        system.update(state, 0.0)
        route_frame = state.get_table("unit_movement_routes")
        route = route_frame.to_dicts()[0]
        route.update(status="blocked", rejection_reason="A route segment became inaccessible.")
        state.update_table("unit_movement_routes", pl.DataFrame([route], schema=route_frame.schema))
        unit_rows = state.get_table("units").to_dicts()
        unit_rows[0].update(is_moving=False, unit_lifecycle="route_blocked")
        state.update_table("units", pl.DataFrame(unit_rows, schema=UNIT_SCHEMA))
        state.current_actions = []

        system.update(state, 0.0)

        unit = state.get_table("units").to_dicts()[0]
        posture = state.get_table("battle_force_postures").to_dicts()[0]
        self.assertEqual(posture["status"], "blocked")
        self.assertIn("inaccessible", posture["reason"])
        self.assertEqual(unit["combat_posture"], "back_off")
        self.assertEqual(unit["engagement_mode"], "")

    def test_occupation_establishes_only_military_control_after_hostile_clearance(self) -> None:
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "CAN", "controller": "CAN", "latitude": 0.0, "longitude": 0.0},
            {"id": 2, "owner": "CAN", "controller": "CAN", "latitude": 1.0, "longitude": 1.0},
        ]))
        usa_unit = UnitFactory().create("usa-2", "USA", "infantry", 50, 2, GeoCoordinate(1.0, 1.0), 0)
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([usa_unit], schema=UNIT_SCHEMA),
        ]))
        state.update_table("countries_wars", pl.DataFrame([{
            "id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active",
        }], schema={"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}))
        state.current_actions = [ActionOccupyRegion("USA", 1, "USA")]

        BattleStrategySystem().update(state, 0.0)

        regions = state.get_table("regions").sort("id")
        self.assertEqual(regions["owner"].to_list(), ["CAN", "CAN"])
        self.assertEqual(regions["controller"].to_list(), ["USA", "USA"])
        self.assertEqual(state.get_table("battle_command_orders")["strategy"].to_list(), ["occupy"])
        occupation = state.get_table("occupations").filter(pl.col("region_id") == 1).to_dicts()[0]
        self.assertEqual(occupation["controller_country_id"], "USA")
        self.assertEqual(occupation["garrison_strength"], 100)
        self.assertEqual(state.journal.command_results[-1]["status"], "applied")

    def test_occupation_routes_surplus_garrison_to_an_unoccupied_valid_region(self) -> None:
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "CAN", "controller": "CAN", "latitude": 0.0, "longitude": 0.0},
            {"id": 2, "owner": "CAN", "controller": "CAN", "latitude": 1.0, "longitude": 1.0},
            {"id": 3, "owner": "CAN", "controller": "CAN", "latitude": 2.0, "longitude": 2.0},
        ]))
        extra = UnitFactory().create("usa-2", "USA", "infantry", 50, 1, GeoCoordinate(0.0, 0.0), 0)
        extra["current_region_id"] = 1
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([extra], schema=UNIT_SCHEMA),
        ]))
        state.update_table("countries_wars", pl.DataFrame([{
            "id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active",
        }], schema={"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}))
        state.update_table("region_adjacency", pl.DataFrame([
            {"region_id": 1, "neighbor_region_id": 2},
            {"region_id": 2, "neighbor_region_id": 3},
        ]))
        state.current_actions = [ActionOccupyRegion("USA", 1, "USA")]

        BattleStrategySystem().update(state, 0.0)

        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        route = state.get_table("unit_movement_routes").to_dicts()[0]
        regions = state.get_table("regions").sort("id")
        self.assertTrue(units[route["unit_id"]]["is_moving"])
        self.assertEqual(units[route["unit_id"]]["target_region_id"], 2)
        self.assertEqual(route["route_region_ids"], [1, 2])
        self.assertEqual(regions["owner"].to_list(), ["CAN", "CAN", "CAN"])
        self.assertEqual(regions["controller"].to_list(), ["USA", "CAN", "CAN"])

        state.time.total_minutes = int(units[route["unit_id"]]["arrival_at_minute"])
        moved = MilitarySystem()._update_unit_movements(state, state.get_table("units"), state.time.total_minutes)
        state.update_table("units", moved)
        CombatSystem().update(state, 0.0)

        final_regions = state.get_table("regions").sort("id")
        self.assertEqual(final_regions["owner"].to_list(), ["CAN", "CAN", "CAN"])
        self.assertEqual(final_regions["controller"].to_list(), ["USA", "USA", "CAN"])

    def test_occupation_rejects_surviving_hostiles_and_unauthorized_actor(self) -> None:
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "CAN", "controller": "CAN", "latitude": 0.0, "longitude": 0.0},
        ]))
        state.update_table("countries_wars", pl.DataFrame([{
            "id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active",
        }], schema={"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}))
        hostile = UnitFactory().create("can-1", "CAN", "infantry", 20, 1, GeoCoordinate(0.0, 0.0), 0)
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([hostile], schema=UNIT_SCHEMA),
        ]))
        original_regions = state.get_table("regions")
        system = BattleStrategySystem()

        state.current_actions = [ActionOccupyRegion("USA", 1, "USA")]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("regions").equals(original_regions))
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

        state.current_actions = [ActionOccupyRegion("CAN", 1, "USA")]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("regions").equals(original_regions))
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_occupation_rejects_surviving_hostile_coalition_force(self) -> None:
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "CAN", "controller": "CAN", "latitude": 0.0, "longitude": 0.0},
        ]))
        state.update_table("countries_wars", pl.DataFrame([{
            "id": "war-1", "side_a": ["USA"], "side_b": ["CAN", "MEX"], "status": "active",
        }], schema={"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}))
        allied_hostile = UnitFactory().create("mex-1", "MEX", "infantry", 20, 1, GeoCoordinate(0.0, 0.0), 0)
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([allied_hostile], schema=UNIT_SCHEMA),
        ]))
        original_regions = state.get_table("regions")
        state.current_actions = [ActionOccupyRegion("USA", 1, "USA")]

        BattleStrategySystem().update(state, 0.0)

        self.assertTrue(state.get_table("regions").equals(original_regions))
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_occupation_rejects_non_hostile_and_unknown_regions_without_authoritative_mutation(self) -> None:
        for region_id, active_war in ((1, False), (99, True)):
            with self.subTest(region_id=region_id, active_war=active_war):
                state = self._state()
                state.update_table("regions", pl.DataFrame([{
                    "id": 1, "owner": "CAN", "controller": "CAN", "latitude": 0.0, "longitude": 0.0,
                }]))
                if active_war:
                    state.update_table("countries_wars", pl.DataFrame([{
                        "id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active",
                    }], schema={
                        "id": pl.Utf8, "side_a": pl.List(pl.Utf8),
                        "side_b": pl.List(pl.Utf8), "status": pl.Utf8,
                    }))
                table_names = (
                    "regions", "units", "countries", "occupations", "unit_movement_routes",
                    "battle_command_orders",
                )
                before = {name: state.get_table(name).to_dicts() for name in table_names}
                revisions = {name: state.table_revisions.get(name, 0) for name in table_names}
                state.current_actions = [ActionOccupyRegion("USA", region_id, "USA")]

                BattleStrategySystem().update(state, 0.0)

                self.assertEqual(
                    {name: state.get_table(name).to_dicts() for name in table_names}, before,
                )
                self.assertEqual(
                    {name: state.table_revisions.get(name, 0) for name in table_names}, revisions,
                )
                self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_update_skips_incomplete_idle_state_and_rejects_invalid_strategy_requests(self) -> None:
        system = BattleStrategySystem()
        system.update(GameState(tables={}), 0.0)

        idle = self._state()
        idle.current_actions = []
        system.update(idle, 0.0)

        cases = (
            ("missing-battle", "attack", "infantry"),
            ("battle-1", "unsupported", "infantry"),
            ("battle-1", "attack", "armor"),
        )
        for battle_id, strategy, unit_type in cases:
            with self.subTest(battle_id=battle_id, strategy=strategy, unit_type=unit_type):
                state = self._state()
                state.current_actions = [ActionSetBattleStrategy(
                    "USA", battle_id, strategy, country_tag="USA", unit_type=unit_type,
                )]

                system.update(state, 0.0)

                self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_withdrawal_helpers_reject_missing_routes_and_reorganization_requirements(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        battle = state.get_table("battles").to_dicts()[0]
        state.tables.pop("regions")

        self.assertFalse(system._begin_retreat(state, unit, "USA", battle, []))
        self.assertFalse(system._begin_back_off(state, unit, "USA", battle, []))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        battle = state.get_table("battles").to_dicts()[0]
        self.assertFalse(system._begin_retreat(state, unit, "USA", battle, []))

        system._battle_rear_position = lambda *_args: None
        self.assertFalse(system._begin_rear_withdrawal(
            state,
            unit,
            "USA",
            battle,
            [],
            {1: GeoCoordinate(10.0, 20.0)},
            SimpleNamespace(),
            lifecycle="battle_retreating",
            route_status="retreating",
        ))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        state.tables.pop("countries")
        self.assertFalse(system._start_reorganization(
            state, unit, "USA", [], "battle-1", "USA", 0,
        ))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        state.update_table("regions", pl.DataFrame([{
            "id": 1, "owner": "CAN", "controller": "CAN",
            "latitude": 10.0, "longitude": 20.0,
        }]))
        self.assertFalse(system._start_reorganization(
            state, unit, "USA", [], "battle-1", "USA", 0,
        ))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        country_schema = state.get_table("countries").schema
        state.update_table("countries", pl.DataFrame([{
            "id": "USA", "money_reserves": 0.0,
        }], schema=country_schema))
        self.assertFalse(system._start_reorganization(
            state, unit, "USA", [], "battle-1", "USA", 0,
        ))

    def test_strategy_constraints_and_coordinate_helpers_cover_invalid_inputs(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        state.globals["battle_strategy_constraints"] = "invalid"
        self.assertIsNone(system._scenario_constraint_rejection(
            state, "battle-1", "USA", "infantry", "attack",
        ))

        state.globals["battle_strategy_constraints"] = [
            None,
            {"battle_id": "other", "required_strategy": "defend"},
            {"country_id": "CAN", "allowed_strategies": []},
            {"unit_type": "armor", "allowed_strategies": []},
            {"required_strategy": "defend"},
        ]
        self.assertIn("requires defend", system._scenario_constraint_rejection(
            state, "battle-1", "USA", "infantry", "attack",
        ))

        self.assertEqual(system._unit_coordinate(None, GeoCoordinate(1.0, 2.0)), GeoCoordinate(1.0, 2.0))
        self.assertEqual(system._unit_coordinate({"latitude": "bad", "longitude": 0}, None), None)
        self.assertEqual(system._unit_coordinate({"latitude": 91, "longitude": 0}, None), None)
        self.assertEqual(system._finite(object()), 0.0)

    def test_lifecycle_cancels_missing_forces_and_interrupted_disengagements(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        state.time.is_paused = True
        paused_posture = {"unit_id": "missing", "status": "reorganizing"}
        system._advance_posture_lifecycle(state, [], [paused_posture], [], [], 10)
        self.assertEqual(paused_posture["status"], "reorganizing")

        state.time.is_paused = False
        missing_posture = {"unit_id": "missing", "status": "retreating"}
        system._advance_posture_lifecycle(state, [], [missing_posture], [], [], 10)
        self.assertEqual(missing_posture["status"], "cancelled")

        unit = state.get_table("units").to_dicts()[0]
        unit.update(
            is_moving=True,
            unit_lifecycle="battle_disengaging",
            movement_progress=0.25,
            departed_at_minute=0,
            arrival_at_minute=100,
            source_latitude=10.0,
            source_longitude=19.0,
            target_latitude=10.0,
            target_longitude=21.0,
        )
        posture = {
            "unit_id": "usa-1", "battle_id": "battle-1",
            "strategy": "back_off", "status": "disengaging",
        }
        route = {"unit_id": "usa-1", "status": "moving"}
        system._advance_posture_lifecycle(
            state,
            [unit],
            [posture],
            [route],
            [{"id": "battle-1", "status": "concluded"}],
            50,
        )
        self.assertEqual(posture["status"], "cancelled")
        self.assertEqual(route["status"], "interrupted")
        self.assertFalse(unit["is_moving"])
        self.assertEqual(unit["combat_posture"], "hold")

        blocked_posture = {
            "unit_id": "usa-1", "battle_id": "battle-1",
            "strategy": "back_off", "status": "disengaging",
        }
        blocked_route = {
            "unit_id": "usa-1", "status": "blocked", "rejection_reason": "",
        }
        system._advance_posture_lifecycle(
            state,
            [unit],
            [blocked_posture],
            [blocked_route],
            [{"id": "battle-1", "status": "active"}],
            60,
        )
        self.assertEqual(blocked_posture["status"], "blocked")
        self.assertFalse(unit["is_moving"])

    def test_occupation_distribution_and_route_helpers_return_safely_on_missing_data(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        state.tables.pop("unit_movement_routes")
        system._plan_occupation_distribution(
            state, "USA", target_country_ids={1, 2}, occupied_region_ids={1},
            units=[], routes=[], now=0,
        )

        state = self._state()
        regions_schema = state.get_table("regions").schema
        state.update_table("regions", pl.DataFrame(schema=regions_schema))
        system._plan_occupation_distribution(
            state, "USA", target_country_ids={1, 2}, occupied_region_ids={1},
            units=[], routes=[], now=0,
        )

        plan = SimpleNamespace(region_ids=[1, 2])
        self.assertFalse(system._start_occupation_route(
            state, "USA", {"id": "usa-1", "current_region_id": 1}, plan,
            [], {}, SimpleNamespace(), 0,
        ))

    def test_identity_fallback_participants_and_failed_posture_routes(self) -> None:
        system = BattleStrategySystem()
        self.assertEqual(system.id, "base.battle_strategy")
        self.assertEqual(system.dependencies, ["base.time", "base.military"])

        state = self._state()
        state.tables.pop("battle_units")
        state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "attack", country_tag="USA", unit_type="infantry",
        )]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("units")["combat_posture"].to_list(), ["attack"])

        retreat_state = self._state()
        retreat_state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "retreat", country_tag="USA",
        )]
        system.update(retreat_state, 0.0)
        self.assertIn("No valid route", retreat_state.journal.command_results[-1]["reason"])

        back_off_state = self._state()
        back_off_state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "back_off", country_tag="USA",
        )]
        system._begin_back_off = lambda *_args: False
        system.update(back_off_state, 0.0)
        self.assertIn("No valid route", back_off_state.journal.command_results[-1]["reason"])

        reorganize_state = self._state()
        country_schema = reorganize_state.get_table("countries").schema
        reorganize_state.update_table("countries", pl.DataFrame([{
            "id": "USA", "money_reserves": 0.0,
        }], schema=country_schema))
        reorganize_state.current_actions = [ActionSetBattleStrategy(
            "USA", "battle-1", "reorganize", country_tag="USA",
        )]
        BattleStrategySystem().update(reorganize_state, 0.0)
        self.assertIn("sufficient funds", reorganize_state.journal.command_results[-1]["reason"])

    def test_rear_withdrawal_reuses_route_and_calculates_enemy_or_anchor_bearing(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        battle = state.get_table("battles").to_dicts()[0]
        system._battle_rear_position = lambda *_args: GeoCoordinate(10.0, 21.0)
        route = {"unit_id": "usa-1", "status": "old"}
        duration = SimpleNamespace(estimate_between=lambda *_args: 5)

        self.assertTrue(system._begin_rear_withdrawal(
            state, unit, "USA", battle, [route], {1: GeoCoordinate(10.0, 20.0)}, duration,
            lifecycle="battle_retreating", route_status="retreating",
        ))
        self.assertEqual(route["status"], "retreating")
        self.assertEqual(route["updated_at_minute"], state.time.total_minutes)

        system = BattleStrategySystem()
        self.assertIsNone(system._battle_rear_position(
            state, {"current_region_id": 99}, "USA", battle, {},
        ))
        anchored = system._battle_rear_position(
            state,
            unit,
            "USA",
            {**battle, "anchor_latitude": 0.0, "anchor_longitude": 0.0},
            {1: GeoCoordinate(10.0, 20.0)},
        )
        self.assertIsInstance(anchored, GeoCoordinate)

        enemy = UnitFactory().create(
            "can-1", "CAN", "infantry", 50, 1, GeoCoordinate(9.0, 19.0), 0,
        )
        state.update_table("units", pl.concat([
            state.get_table("units"), pl.DataFrame([enemy], schema=UNIT_SCHEMA),
        ]))
        participants = state.get_table("battle_units")
        state.update_table("battle_units", pl.concat([
            participants,
            pl.DataFrame([{
                "battle_id": "battle-1", "unit_id": "can-1", "country_id": "CAN",
            }], schema=participants.schema),
        ]))
        rear = system._battle_rear_position(
            state, unit, "USA", battle, {1: GeoCoordinate(10.0, 20.0)},
        )
        self.assertIsInstance(rear, GeoCoordinate)

    def test_retreat_lifecycle_blocks_failed_return_and_handles_empty_participants(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        regrouping = {
            "unit_id": "usa-1", "battle_id": "battle-1", "country_id": "USA",
            "strategy": "retreat", "status": "reorganizing", "expires_at_minute": 10,
        }
        system._advance_posture_lifecycle(
            state, [unit], [regrouping], [], [{"id": "battle-1", "status": "active"}], 10,
        )
        self.assertEqual(regrouping["status"], "blocked")
        self.assertEqual(unit["combat_posture"], "back_off")

        returning = {
            "unit_id": "usa-1", "battle_id": "battle-1", "country_id": "USA",
            "strategy": "retreat", "status": "returning",
        }
        blocked_route = {"unit_id": "usa-1", "status": "blocked", "rejection_reason": ""}
        system._advance_posture_lifecycle(
            state,
            [unit],
            [returning],
            [blocked_route],
            [{"id": "battle-1", "status": "active"}],
            20,
        )
        self.assertEqual(returning["status"], "blocked")
        self.assertEqual(returning["reason"], "The return route became unavailable.")

        state.tables.pop("battle_units")
        system._remove_battle_participant(state, "battle-1", "usa-1")

    def test_return_to_capital_validates_route_and_updates_existing_route(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        state.tables.pop("regions")
        self.assertFalse(system._begin_return_to_capital(state, unit, "USA", [], 5))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        system._plan_capital_route = lambda *_args: (99, SimpleNamespace(region_ids=[1]))
        self.assertFalse(system._begin_return_to_capital(state, unit, "USA", [], 5))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        system._plan_capital_route = lambda *_args: (1, SimpleNamespace(region_ids=[1, 99]))
        self.assertFalse(system._begin_return_to_capital(state, unit, "USA", [], 5))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        unit.update(latitude="invalid", longitude="invalid", current_region_id=99)
        system._plan_capital_route = lambda *_args: (1, SimpleNamespace(region_ids=[99, 1]))
        self.assertFalse(system._begin_return_to_capital(state, unit, "USA", [], 5))

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        system._plan_capital_route = lambda *_args: (1, SimpleNamespace(region_ids=[1]))
        route = {"unit_id": "usa-1", "status": "old"}
        self.assertTrue(system._begin_return_to_capital(state, unit, "USA", [route], 5))
        self.assertEqual(route["status"], "arrived")
        self.assertEqual(route["route_index"], 0)

        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        appended_routes = []
        self.assertTrue(system._begin_return_to_capital(
            state, unit, "USA", appended_routes, 5,
        ))
        self.assertEqual(appended_routes[0]["status"], "arrived")

    def test_occupation_rejects_missing_region_and_force_outside_target(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        state.tables.pop("regions")
        system._occupy_cleared_region(
            state, ActionOccupyRegion("USA", 1, "USA"), [], [], [], 0,
        )
        self.assertIn("target region", state.journal.command_results[-1]["reason"])

        state = self._state()
        state.update_table("regions", pl.DataFrame([{
            "id": 1, "owner": "CAN", "controller": "CAN",
            "latitude": 0.0, "longitude": 0.0,
        }]))
        state.update_table("countries_wars", pl.DataFrame([{
            "id": "war-1", "side_a": ["USA"], "side_b": ["CAN"], "status": "active",
        }], schema={
            "id": pl.Utf8, "side_a": pl.List(pl.Utf8),
            "side_b": pl.List(pl.Utf8), "status": pl.Utf8,
        }))
        system._occupy_cleared_region(
            state,
            ActionOccupyRegion("USA", 1, "USA"),
            [],
            [],
            [],
            0,
        )
        self.assertIn("No eligible force", state.journal.command_results[-1]["reason"])

    def test_occupation_route_updates_existing_route_and_handles_filtered_units(self) -> None:
        system = BattleStrategySystem()
        state = self._state()
        unit = {
            "id": "usa-1", "current_region_id": 1,
            "latitude": 10.0, "longitude": 20.0,
        }
        route = {"unit_id": "usa-1", "status": "old"}
        duration = SimpleNamespace(
            estimate_from_distance=lambda _distance: 8,
            estimate_between=lambda *_args: 12,
        )
        self.assertTrue(system._start_occupation_route(
            state,
            "USA",
            unit,
            SimpleNamespace(region_ids=[1, 2]),
            [route],
            {1: GeoCoordinate(10.0, 20.0), 2: GeoCoordinate(11.0, 21.0)},
            duration,
            10,
            {(1, 2): 30.0},
        ))
        self.assertEqual(route["status"], "moving")
        self.assertEqual(unit["arrival_at_minute"], 18)

        state.tables["unit_movement_routes"] = state.get_table("unit_movement_routes")
        system._plan_occupation_distribution(
            state,
            "USA",
            target_country_ids={1, 2},
            occupied_region_ids={1},
            units=[{"id": "can-1", "owner": "CAN", "current_region_id": 1, "strength": 5}],
            routes=[],
            now=0,
        )

    def test_occupation_distribution_uses_location_cost_when_graph_edge_cost_is_missing(self) -> None:
        module = import_module("modules.base.systems.military.battle_strategy_system")
        state = self._state()
        state.update_table("regions", pl.DataFrame([
            {"id": 1, "owner": "CAN", "latitude": 10.0, "longitude": 20.0},
            {"id": 2, "owner": "CAN", "latitude": 11.0, "longitude": 21.0},
        ]))
        prepared = SimpleNamespace(
            region_by_id={
                1: {"id": 1, "owner": "CAN"},
                2: {"id": 2, "owner": "CAN"},
            },
            edge_distance_km={},
        )

        class _Planner:
            def prepare(self, *_args):
                return prepared

            def plan(self, *_args, segment_cost, **_kwargs):
                cost = segment_cost({"id": 1}, {"id": 2})
                return SimpleNamespace(is_valid=True, region_ids=[1, 2], travel_cost=cost)

        class _DurationPolicy:
            def region_locations(self, _regions):
                return {1: GeoCoordinate(10.0, 20.0), 2: GeoCoordinate(11.0, 21.0)}

            def estimate_between(self, source, target):
                assert source is not None and target is not None
                return 12

        class _AccessPolicy:
            def for_country(self, *_args):
                return SimpleNamespace(can_station=lambda _region: True, can_transit=lambda _region: True)

        system = BattleStrategySystem()
        system._start_occupation_route = lambda *_args, **_kwargs: False
        units = [
            {"id": "usa-1", "owner": "USA", "current_region_id": 1, "strength": 5},
            {"id": "usa-2", "owner": "USA", "current_region_id": 1, "strength": 5},
        ]

        with (
            patch.object(module, "MilitaryRoutePlanner", _Planner),
            patch.object(module, "MovementDurationPolicy", _DurationPolicy),
            patch.object(module, "MovementAccessPolicy", _AccessPolicy),
        ):
            system._plan_occupation_distribution(
                state,
                "USA",
                target_country_ids={1, 2},
                occupied_region_ids={1},
                units=units,
                routes=[],
                now=0,
            )


if __name__ == "__main__":
    unittest.main()
