from __future__ import annotations

import json
import math
import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.strategic_warfare_system import StrategicWarfareSystem
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from src.shared.actions import ActionLaunchStrategicStrike, ActionProduceStrategicWeapon
from src.shared.events import EventNewDay
from src.shared.state import GameState


class StrategicWarfareSystemTest(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
            "id": ["USA", "CAN"], "money_reserves": [100.0, 100.0],
            "gdp": [1000.0, 900.0], "military_count": [10, 8],
            "gvt_approval": [50.0, 50.0],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"], "controller": ["USA", "CAN"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 5.0],
                "infrastructure_health": [1.0, 1.0],
                "migration_pressure": [0.0, 0.0], "environment_health": [1.0, 1.0],
            }),
            "countries_wars": pl.DataFrame({
                "id": ["war"], "name": ["War"], "side_a": [["USA"]], "side_b": [["CAN"]],
                "status": ["active"], "casus_belli": [""], "created_at": [""],
                "leader_a": ["USA"], "leader_b": ["CAN"], "intent_a": [""], "intent_b": [""],
            }),
        })
        ensure_base_tables(state)
        state.update_table("strategic_weapons", pl.DataFrame([{
            "id": "usa-icbm", "country_id": "USA", "weapon_type": "icbm", "weapon_class": "icbm",
            "quantity": 2, "ready": 2, "origin_region_id": 1, "range_km": 12000.0,
            "payload_level": 1, "max_payload_level": 1, "operational": True, "launch_cost": 0.0,
            "program_level": 1,
        }], schema=state.get_table("strategic_weapons").schema))
        state.update_table("research_tracks", pl.DataFrame([
            {"id": "program", "country_id": "USA", "branch": "strategic_program", "research_level": 1},
            {"id": "weapons", "country_id": "USA", "branch": "strategic_weapons", "research_level": 1},
        ], schema=state.get_table("research_tracks").schema))
        state.globals["strategic_authorization_policy"] = "war"
        state.globals["strategic_flight_minutes"] = 10
        return state

    def test_covered_strike_is_intercepted_before_impact(self) -> None:
        state = self._state()
        self._add_defense_research(state)
        state.update_table("missile_defense_layers", pl.DataFrame([{
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_region_ids": [2],
            "readiness": 1.0, "first_attempt_probability": 1.0,
            "second_attempt_probability": 0.5,
        }], schema=state.get_table("missile_defense_layers").schema))
        state.current_actions = [ActionLaunchStrategicStrike("USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1)]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        self.assertEqual(state.get_table("strategic_weapons")["ready"][0], 1)
        state.time.total_minutes += 10
        state.current_actions = []
        system.update(state, 0.0)
        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["status"], "intercepted")
        self.assertEqual(state.get_table("strategic_impacts").filter(pl.col("category") == "military_capability").height, 0)
        self.assertEqual(state.get_table("strategic_impacts").filter(pl.col("category") == "interception").height, 1)

    def test_unresearched_fielded_layer_does_not_attempt_interception(self) -> None:
        state = self._state()
        state.update_table("missile_defense_layers", pl.DataFrame([{
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_region_ids": [2],
            "readiness": 1.0, "first_attempt_probability": 1.0,
        }], schema=state.get_table("missile_defense_layers").schema))
        state.current_actions = [ActionLaunchStrategicStrike("USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1)]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []

        system.update(state, 0.0)

        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["status"], "impact")
        self.assertEqual(order["defense_result_json"], "[]")

    def test_civilian_impact_records_and_applies_bounded_displacement_and_environment_effects(self) -> None:
        state = self._state()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", target_mode="civilian", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []

        system.update(state, 0.0)

        target_region = state.get_table("regions").filter(pl.col("id") == 2).to_dicts()[0]
        categories = set(state.get_table("strategic_impacts")["category"].to_list())
        self.assertIn("migration_pressure", categories)
        self.assertIn("environmental_damage", categories)
        self.assertGreater(target_region["migration_pressure"], 0.0)
        self.assertLess(target_region["environment_health"], 1.0)
        self.assertGreaterEqual(target_region["migration_pressure"], 0.0)
        self.assertLessEqual(target_region["migration_pressure"], 1.0)
        approval = state.get_table("countries").filter(pl.col("id") == "CAN")["gvt_approval"][0]
        self.assertLess(approval, 50.0)
        self.assertGreaterEqual(approval, 0.0)
        self.assertLessEqual(approval, 100.0)

    def test_civilian_impact_changes_authoritative_population_age_bands(self) -> None:
        state = self._state()
        regions = state.get_table("regions").with_columns(
            pl.lit(10_000, dtype=pl.Int64).alias("pop_14"),
            pl.lit(20_000, dtype=pl.Int64).alias("pop_15_64"),
            pl.lit(5_000, dtype=pl.Int64).alias("pop_65"),
        )
        state.update_table("regions", regions)
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", target_mode="civilian", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []

        system.update(state, 0.0)

        target = state.get_table("regions").filter(pl.col("id") == 2).to_dicts()[0]
        for column in ("pop_14", "pop_15_64", "pop_65"):
            self.assertGreaterEqual(target[column], 0)
            self.assertLess(target[column], regions.filter(pl.col("id") == 2)[column][0])

    def test_weapon_flight_minutes_override_global_resolution_time(self) -> None:
        state = self._state()
        weapons = state.get_table("strategic_weapons")
        state.update_table("strategic_weapons", weapons.with_columns(pl.lit(3).cast(pl.Int32).alias("flight_minutes")))
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["resolves_at_minute"], 3)

    def test_zero_weapon_flight_minutes_uses_existing_global_resolution_time(self) -> None:
        state = self._state()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["resolves_at_minute"], 10)

    def test_launch_persists_registered_origin_and_rejects_a_conflicting_origin(self) -> None:
        state = self._state()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
            origin_region_id=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders")[0, "origin_region_id"], 1)

        conflicting = self._state()
        before = conflicting.get_table("strategic_weapons").to_dicts()
        conflicting.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
            origin_region_id=2,
        )]
        StrategicWarfareSystem().update(conflicting, 0.0)
        self.assertEqual(conflicting.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(conflicting.get_table("strategic_weapons").to_dicts(), before)

    def test_detection_and_impact_notify_participants_without_early_impact_disclosure(self) -> None:
        state = self._state()
        state.globals["strategic_launch_detection_probability"] = 1.0
        state.globals["strategic_launch_attribution_probability"] = 0.0
        state.update_table("countries_relations", pl.DataFrame([
            {"source": "USA", "target": "CAN", "value": 0.0},
            {"source": "CAN", "target": "USA", "value": 0.0},
        ], schema={"source": pl.Utf8, "target": pl.Utf8, "value": pl.Float64}))
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)

        pending_order = state.get_table("strategic_launch_orders").to_dicts()[0]
        pending_messages = state.get_table("messages").to_dicts()
        target_alert = next(message for message in pending_messages if message["country_id"] == "CAN")
        self.assertTrue(pending_order["launch_detected"])
        self.assertFalse(pending_order["launch_attributed"])
        self.assertIn("remain unconfirmed", target_alert["body"])
        self.assertNotIn("resolved as impact", target_alert["body"])

        state.time.total_minutes += 10
        state.current_actions = []
        system.update(state, 0.0)

        messages = state.get_table("messages").to_dicts()
        final_recipients = {
            message["country_id"] for message in messages
            if "resolved as impact" in message["body"]
        }
        self.assertEqual(final_recipients, {"USA", "CAN"})
        relations = state.get_table("countries_relations").to_dicts()
        relation_values = {(row["source"], row["target"]): row["value"] for row in relations}
        self.assertEqual(relation_values[("USA", "CAN")], -10.0)
        self.assertEqual(relation_values[("CAN", "USA")], -10.0)
        self.assertEqual(
            sum(type(event).__name__ == "EventStrategicStrikeTransition" for event in state.events),
            2,
        )

    def test_weapon_design_can_require_a_higher_completed_research_level(self) -> None:
        state = self._state()
        state.update_table("strategic_weapons", state.get_table("strategic_weapons").with_columns(
            pl.lit(2).cast(pl.Int32).alias("required_research_level"),
        ))
        before = state.get_table("strategic_weapons").to_dicts()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons").to_dicts(), before)

    def test_configured_weapon_production_queues_cost_and_completes_at_its_eta(self) -> None:
        state = self._state()
        weapons = state.get_table("strategic_weapons").with_columns(
            pl.lit(25.0).alias("production_cost"),
            pl.lit(5).cast(pl.Int32).alias("production_minutes"),
            pl.lit(3).cast(pl.Int32).alias("readiness_minutes"),
        )
        state.update_table("strategic_weapons", weapons)
        state.current_actions = [ActionProduceStrategicWeapon("USA", "USA", "usa-icbm", 2)]

        system = StrategicWarfareSystem()
        system.update(state, 0.0)

        order = state.get_table("strategic_production_orders").to_dicts()[0]
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["completes_at_minute"], 5)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 50.0)
        self.assertEqual(state.get_table("strategic_weapons")["quantity"][0], 2)
        self.assertEqual(state.get_table("strategic_weapons")["ready"][0], 2)

        state.time.total_minutes = 5
        state.current_actions = []
        system.update(state, 0.0)

        completed = state.get_table("strategic_production_orders").to_dicts()[0]
        self.assertEqual(completed["status"], "readying")
        self.assertEqual(state.get_table("strategic_weapons")["quantity"][0], 4)
        self.assertEqual(state.get_table("strategic_weapons")["ready"][0], 2)

        state.time.total_minutes = 8
        system.update(state, 0.0)

        completed = state.get_table("strategic_production_orders").to_dicts()[0]
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(state.get_table("strategic_weapons")["ready"][0], 4)

    def test_weapon_production_is_rejected_before_research_without_charging(self) -> None:
        state = self._state()
        state.update_table("strategic_weapons", state.get_table("strategic_weapons").with_columns(
            pl.lit(25.0).alias("production_cost"),
            pl.lit(5).cast(pl.Int32).alias("production_minutes"),
        ))
        tracks = state.get_table("research_tracks")
        state.update_table("research_tracks", tracks.with_columns(
            pl.when(pl.col("branch") == "strategic_weapons")
            .then(pl.lit(0))
            .otherwise(pl.col("research_level"))
            .alias("research_level")
        ))
        state.current_actions = [ActionProduceStrategicWeapon("USA", "USA", "usa-icbm", 1)]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_production_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons")["quantity"][0], 2)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 100.0)

    def test_long_range_second_attempt_uses_default_probability_after_first_failure(self) -> None:
        state = self._state()
        self._add_defense_research(state)
        layer = {
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_region_ids": [2],
            "readiness": 1.0, "first_attempt_probability": 0.0,
        }
        order = {"id": "strike-default-defense", "target_country_id": "CAN"}

        intercepted, results = StrategicWarfareSystem()._resolve_defense(
            state, order, state.get_table("regions").filter(pl.col("id") == 2).to_dicts()[0], [layer],
        )

        self.assertEqual([result["probability"] for result in results], [0.0, 0.5])
        self.assertEqual(intercepted, results[-1]["intercepted"])

    def test_two_defense_layers_resolve_in_default_order_with_deterministic_attempts(self) -> None:
        outcomes = []
        for _ in range(3):
            state = self._state()
            self._add_defense_research(state)
            state.determinism.seed = 41
            state.update_table("missile_defense_layers", pl.DataFrame([
                {
                    "id": "can-short", "country_id": "CAN", "layer": "short_range",
                    "researched": True, "operational": True, "coverage_region_ids": [2],
                    "readiness": 1.0, "first_attempt_probability": 1.0,
                },
                {
                    "id": "can-long", "country_id": "CAN", "layer": "long_range",
                    "researched": True, "operational": True, "coverage_region_ids": [2],
                    "readiness": 1.0, "first_attempt_probability": 0.0,
                    "second_attempt_probability": 0.0,
                },
            ], schema=state.get_table("missile_defense_layers").schema))
            state.current_actions = [ActionLaunchStrategicStrike(
                "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
            )]
            system = StrategicWarfareSystem()
            system.update(state, 0.0)
            state.time.total_minutes += 10
            state.current_actions = []
            system.update(state, 0.0)
            order = state.get_table("strategic_launch_orders").to_dicts()[0]
            outcomes.append((order["status"], json.loads(order["defense_result_json"])))

        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1], outcomes[2])
        self.assertEqual(outcomes[0][0], "intercepted")
        self.assertEqual([row["layer"] for row in outcomes[0][1]], ["long_range", "short_range"])
        self.assertEqual([row["attempt"] for row in outcomes[0][1]], [1, 1])

    def test_scenario_can_override_defense_layer_order(self) -> None:
        state = self._state()
        self._add_defense_research(state)
        state.globals["missile_defense_layer_order"] = ["short_range", "long_range"]
        state.update_table("missile_defense_layers", pl.DataFrame([
            {
                "id": "can-long", "country_id": "CAN", "layer": "long_range",
                "researched": True, "operational": True, "coverage_region_ids": [2],
                "readiness": 1.0, "first_attempt_probability": 0.0,
                "second_attempt_probability": 0.0,
            },
            {
                "id": "can-short", "country_id": "CAN", "layer": "short_range",
                "researched": True, "operational": True, "coverage_region_ids": [2],
                "readiness": 1.0, "first_attempt_probability": 1.0,
            },
        ], schema=state.get_table("missile_defense_layers").schema))

        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []
        system.update(state, 0.0)

        result = json.loads(state.get_table("strategic_launch_orders")[0, "defense_result_json"])
        self.assertEqual([row["layer"] for row in result], ["short_range"])
        self.assertTrue(result[0]["intercepted"])

    def test_out_of_range_defense_has_no_interception_attempt(self) -> None:
        state = self._state()
        self._add_defense_research(state)
        state.update_table("missile_defense_layers", pl.DataFrame([{
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_region_ids": [2],
            "center_latitude": 0.0, "center_longitude": 0.0,
            "range_km": 100.0, "readiness": 1.0, "first_attempt_probability": 1.0,
        }], schema=state.get_table("missile_defense_layers").schema))
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []
        system.update(state, 0.0)

        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["status"], "impact")
        self.assertEqual(order["defense_result_json"], "[]")

    def test_target_ownership_change_cancels_pending_strike_without_impact(self) -> None:
        state = self._state()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.update_table("regions", state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2).then(pl.lit("MEX")).otherwise(pl.col("owner")).alias("owner"),
        ))
        state.time.total_minutes += 10
        state.current_actions = []

        system.update(state, 0.0)

        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["status"], "cancelled")
        self.assertEqual(state.get_table("strategic_impacts").height, 0)

    def test_insufficient_launch_funds_are_rejected_without_mutation(self) -> None:
        state = self._state()
        state.update_table("strategic_weapons", state.get_table("strategic_weapons").with_columns(
            pl.lit(101.0).alias("launch_cost"),
        ))
        before_weapons = state.get_table("strategic_weapons").to_dicts()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons").to_dicts(), before_weapons)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 100.0)
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")
        self.assertIn("cannot fund", state.journal.command_results[-1]["reason"])

    def test_daily_defense_maintenance_scales_with_covered_area(self) -> None:
        state = self._state()
        self._add_defense_research(state)
        state.globals["missile_defense_maintenance_reference_area_km2"] = math.pi * 100.0
        state.update_table("missile_defense_layers", pl.DataFrame([{
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_radius_km": 10.0,
            "readiness": 1.0, "maintenance_cost": 100.0,
        }], schema=state.get_table("missile_defense_layers").schema))
        state.events.append(EventNewDay(1, 1, 2020))

        StrategicWarfareSystem().update(state, 0.0)

        can_reserves = state.get_table("countries").filter(pl.col("id") == "CAN")["money_reserves"][0]
        self.assertAlmostEqual(can_reserves, 0.0)

    def _add_defense_research(self, state):
        tracks = state.get_table("research_tracks")
        rows = tracks.to_dicts()
        rows.extend([
            {"id": "can-program", "country_id": "CAN", "branch": "strategic_program", "research_level": 1},
            {"id": "can-defense", "country_id": "CAN", "branch": "strategic_defense", "research_level": 1},
        ])
        state.update_table("research_tracks", pl.DataFrame(rows, schema=tracks.schema))

    def test_out_of_range_attempt_preserves_inventory(self) -> None:
        state = self._state()
        weapons_before = state.get_table("strategic_weapons").to_dicts()
        state.current_actions = [ActionLaunchStrategicStrike("USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1)]
        state.globals["strategic_authorization_policy"] = "open"
        weapon_frame = state.get_table("strategic_weapons")
        rows = weapon_frame.to_dicts()
        rows[0]["range_km"] = 10.0
        state.update_table("strategic_weapons", pl.DataFrame(rows, schema=weapon_frame.schema))
        StrategicWarfareSystem().update(state, 0.0)
        self.assertEqual(state.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons")["ready"][0], weapons_before[0]["ready"])
        self.assertEqual(state.get_table("strategic_weapons")["quantity"][0], weapons_before[0]["quantity"])

    def test_weapon_program_level_cannot_replace_weapon_specific_research(self) -> None:
        state = self._state()
        tracks = state.get_table("research_tracks")
        rows = tracks.to_dicts()
        rows[1]["research_level"] = 0
        state.update_table("research_tracks", pl.DataFrame(rows, schema=tracks.schema))
        weapons_before = state.get_table("strategic_weapons").to_dicts()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
        )]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons").to_dicts(), weapons_before)

    def test_bootstrap_seeds_specialized_strategic_research_tracks(self) -> None:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"],
                "is_playable": [True],
                "budget_research_ratio": [0.12],
                "human_dev": [0.7],
            }),
        })

        rows = BootstrapSystem()._build_research_tracks(state)

        branches = {row["branch"] for row in rows}
        self.assertTrue({"strategic", "strategic_program", "strategic_weapons", "strategic_defense"}.issubset(branches))

    def test_bootstrap_applies_scenario_weapon_production_and_flight_profile(self) -> None:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"], "is_playable": [True], "military_count": [500_000],
                "money_reserves": [10_000_000_000.0], "budget_research_ratio": [0.1],
            }),
        })
        state.globals["strategic_weapon_production_profiles"] = {
            "icbm": {
                "required_research_level": 2,
                "production_cost": 250_000_000.0,
                "production_minutes": 43200,
                "readiness_minutes": 120,
                "flight_minutes": 60,
            },
        }

        rows = BootstrapSystem()._build_strategic_weapons(state)

        self.assertEqual(rows[0]["weapon_class"], "icbm")
        self.assertEqual(rows[0]["required_research_level"], 2)
        self.assertEqual(rows[0]["production_cost"], 250_000_000.0)
        self.assertEqual(rows[0]["production_minutes"], 43200)
        self.assertEqual(rows[0]["readiness_minutes"], 120)
        self.assertEqual(rows[0]["flight_minutes"], 60)

    def test_scenario_enabled_slbm_uses_its_profile_and_resolves_through_defense(self) -> None:
        bootstrap_state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"], "is_playable": [True], "military_count": [500_000],
                "money_reserves": [10_000_000_000.0], "budget_research_ratio": [0.1],
            }),
        })
        bootstrap_state.globals["strategic_weapon_profiles"] = {
            "slbm": {
                "range_km": 16_000.0,
                "payload_level": 2,
                "max_payload_level": 2,
                "required_research_level": 2,
                "initial_quantity": 1,
                "initial_ready": 1,
                "readiness_minutes": 90,
                "flight_minutes": 3,
            },
        }
        profiles = BootstrapSystem()._build_strategic_weapons(bootstrap_state)
        slbm = next(row for row in profiles if row["weapon_class"] == "slbm")
        self.assertEqual(slbm["range_km"], 16_000.0)
        self.assertEqual(slbm["max_payload_level"], 2)
        self.assertEqual(slbm["readiness_minutes"], 90)
        self.assertEqual(slbm["flight_minutes"], 3)
        self.assertNotIn("slbm", {row["weapon_class"] for row in BootstrapSystem()._build_strategic_weapons(
            GameState(tables={"countries": bootstrap_state.get_table("countries")})
        )})

        state = self._state()
        state.update_table("strategic_weapons", pl.DataFrame([slbm], schema=state.get_table("strategic_weapons").schema))
        tracks = state.get_table("research_tracks").to_dicts()
        next(row for row in tracks if row["branch"] == "strategic_weapons")["research_level"] = 2
        state.update_table("research_tracks", pl.DataFrame(tracks, schema=state.get_table("research_tracks").schema))
        self._add_defense_research(state)
        state.update_table("missile_defense_layers", pl.DataFrame([{
            "id": "can-long", "country_id": "CAN", "layer": "long_range",
            "researched": True, "operational": True, "coverage_region_ids": [2],
            "readiness": 1.0, "first_attempt_probability": 1.0,
        }], schema=state.get_table("missile_defense_layers").schema))
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "slbm", target_country_tag="CAN", payload_level=2, weapon_id=slbm["id"],
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        order = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(order["resolves_at_minute"], 3)
        state.time.total_minutes += 3
        state.current_actions = []

        system.update(state, 0.0)

        resolved = state.get_table("strategic_launch_orders").to_dicts()[0]
        self.assertEqual(resolved["status"], "intercepted")
        self.assertIn('"layer":"long_range"', resolved["defense_result_json"])

    def test_military_object_target_limits_unit_and_readiness_effects_to_that_object(self) -> None:
        state = self._state()
        state.tables["units"] = pl.DataFrame({
            "id": ["can-target", "can-other"],
            "owner": ["CAN", "CAN"],
            "current_region_id": [2, 2],
            "strength": [100, 200],
            "readiness_status": ["fortified", "ready"],
            "readiness_progress": [0.0, 0.0],
            "readiness_transition_id": ["", ""],
            "readiness_eta_minute": [0, 0],
        })
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
            target_object_id="can-target",
        )]
        system = StrategicWarfareSystem()
        system.update(state, 0.0)
        state.time.total_minutes += 10
        state.current_actions = []

        system.update(state, 0.0)

        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertLess(units["can-target"]["strength"], 100)
        self.assertEqual(units["can-target"]["readiness_status"], "ready")
        self.assertEqual(units["can-other"]["strength"], 200)
        self.assertEqual(units["can-other"]["readiness_status"], "ready")
        self.assertEqual(
            state.get_table("strategic_impacts").filter(pl.col("category") == "unit_readiness").height,
            1,
        )

    def test_unknown_military_object_is_rejected_without_consuming_weapon(self) -> None:
        state = self._state()
        state.tables["units"] = pl.DataFrame(schema={
            "id": pl.Utf8,
            "owner": pl.Utf8,
            "current_region_id": pl.Int32,
            "strength": pl.Int64,
        })
        before = state.get_table("strategic_weapons").to_dicts()
        state.current_actions = [ActionLaunchStrategicStrike(
            "USA", "USA", 2, "icbm", target_country_tag="CAN", payload_level=1,
            target_object_id="missing-unit",
        )]

        StrategicWarfareSystem().update(state, 0.0)

        self.assertEqual(state.get_table("strategic_launch_orders").height, 0)
        self.assertEqual(state.get_table("strategic_weapons").to_dicts(), before)


if __name__ == "__main__":
    unittest.main()
