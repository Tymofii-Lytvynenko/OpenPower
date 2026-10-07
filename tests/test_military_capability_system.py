from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.capability_system import (
    MilitaryCapabilitySystem,
    project_capabilities,
    researched_capabilities,
    trained_capabilities,
)
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionCancelUnitTraining, ActionSetUnitTrainingPaused, ActionTrainUnit
from src.shared.events import EventRealSecond
from src.shared.state import GameState


class MilitaryCapabilitySystemTest(unittest.TestCase):
    def test_projection_cache_recomputes_only_units_with_changed_inputs(self) -> None:
        state = self._state()
        units = state.get_table("units").to_dicts()
        units.extend({**units[0], "id": f"USA-{index}"} for index in range(2, 4))
        system = MilitaryCapabilitySystem()

        baseline = system._build_projections(state, units, [])
        self.assertEqual(len(baseline), 3)

        with patch(
            "modules.base.systems.military.capability_system.trained_capabilities",
            wraps=trained_capabilities,
        ) as project_training:
            unchanged = system._build_projections(state, units, [])

        self.assertEqual(project_training.call_count, 0)
        self.assertEqual(unchanged, baseline)

        changed_units = [dict(unit) for unit in units]
        changed_units[0]["training_level"] = "Regular"
        with patch(
            "modules.base.systems.military.capability_system.trained_capabilities",
            wraps=trained_capabilities,
        ) as project_training:
            changed = system._build_projections(state, changed_units, [])

        self.assertEqual(project_training.call_count, 1)
        self.assertEqual(changed[0]["training_level"], "Regular")
        self.assertEqual(changed[1:], unchanged[1:])

    def test_projection_cache_invalidates_referenced_design_research_and_bonus_changes(self) -> None:
        state = self._state()
        units = state.get_table("units").to_dicts()
        units.extend({**units[0], "id": f"USA-{index}"} for index in range(2, 4))
        for unit in units:
            unit["design_id"] = "shared-design"
        state.update_table(
            "unit_designs",
            pl.DataFrame([{
                "id": "shared-design",
                "class_name": "infantry",
                "domain": "land",
                "branch": "land",
                "capabilities_json": "{}",
                "valid_targets_json": "[]",
                "vulnerabilities_json": "[]",
            }]),
        )
        state.update_table("research_tracks", pl.DataFrame([{
            "id": "research-usa-land",
            "country_id": "USA",
            "branch": "land",
            "research_level": 1,
        }]))
        system = MilitaryCapabilitySystem()
        system._build_projections(state, units, [])

        state.update_table(
            "unit_designs",
            state.get_table("unit_designs").with_columns(
                pl.lit('{"speed":500.0}').alias("capabilities_json")
            ),
        )
        with patch(
            "modules.base.systems.military.capability_system.project_capabilities",
            wraps=project_capabilities,
        ) as project_design:
            system._build_projections(state, units, [])
        self.assertEqual(project_design.call_count, 3)

        state.update_table(
            "research_tracks",
            state.get_table("research_tracks").with_columns(
                pl.lit(3).cast(pl.Int32).alias("research_level")
            ),
        )
        with patch(
            "modules.base.systems.military.capability_system.researched_capabilities",
            wraps=researched_capabilities,
        ) as project_research:
            system._build_projections(state, units, [])
        self.assertEqual(project_research.call_count, 3)

        state.globals["military_training_bonuses"] = {"Recruit": 0.2}
        with patch(
            "modules.base.systems.military.capability_system.trained_capabilities",
            wraps=trained_capabilities,
        ) as project_training:
            system._build_projections(state, units, [])
        self.assertEqual(project_training.call_count, 3)

    def test_research_projects_configured_capability_gains_into_combat_state(self) -> None:
        state = self._state()
        unit = state.get_table("units").to_dicts()[0]
        unit.update(unit_type="fighter", design_id="usa-fighter")
        state.update_table("units", pl.DataFrame([unit], schema=UNIT_SCHEMA))
        design = {
            "id": "usa-fighter", "country_id": "USA", "branch": "air",
            "class_name": "fighter", "display_name": "Fighter", "quality": 0.0,
            "cost": 20.0, "speed": 1.0, "firepower": 1.0, "domain": "air",
            "capabilities_json": "{}", "valid_targets_json": "[]",
            "vulnerabilities_json": "[]", "research_level": 0,
            "research_requirements_json": "{}",
        }
        state.update_table("unit_designs", pl.DataFrame([design], schema=state.get_table("unit_designs").schema))
        state.update_table("research_tracks", pl.DataFrame([{
            "id": "air-research", "country_id": "USA", "branch": "air",
            "research_level": 3,
        }]))
        state.globals["military_research_capability_bonuses"] = {
            "air": {"sensors": {"per_level": 0.1, "max_bonus": 0.2}},
        }

        MilitaryCapabilitySystem().update(state, 0.0)

        projection = state.get_table("unit_capability_projections").to_dicts()[0]
        capabilities = json.loads(projection["capabilities_json"])
        self.assertAlmostEqual(capabilities["speed"], 2200.0)
        self.assertAlmostEqual(capabilities["sensors"], 300.0)
        self.assertEqual(projection["research_level"], 3)

        restored = GameState.from_ipc(state.to_ipc())
        ensure_base_tables(restored)
        MilitaryCapabilitySystem().update(state, 0.0)
        MilitaryCapabilitySystem().update(restored, 0.0)
        self.assertTrue(
            restored.get_table("unit_capability_projections").equals(
                state.get_table("unit_capability_projections")
            )
        )

    def test_training_removes_unit_from_map_and_restores_it_at_completion(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        system.update(state, 0.0)

        unit = state.get_table("units").to_dicts()[0]
        order = state.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual(unit["current_region_id"], 0)
        self.assertEqual(unit["training_state"], "training")
        self.assertEqual(unit["training_facility_id"], "site-usa-1")
        self.assertEqual(unit["training_location_region_id"], 1)
        self.assertEqual(order["status"], "active")
        self.assertEqual(order["facility_id"], "site-usa-1")
        self.assertEqual(order["training_location_region_id"], 1)
        self.assertEqual(order["last_event"], "started")
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 900.0)

        state.current_actions = []
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)
        self.assertAlmostEqual(state.get_table("unit_training_orders")["progress"][0], 0.5)

        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["training_level"], "Regular")
        self.assertEqual(unit["current_region_id"], 1)
        self.assertEqual(unit["training_facility_id"], "")
        self.assertEqual(unit["training_location_region_id"], 0)
        self.assertEqual(state.get_table("unit_training_orders")["status"][0], "completed")
        self.assertEqual(state.get_table("unit_training_orders")["last_event"][0], "completed")
        self.assertEqual(state.get_table("unit_training_orders")["completed_at_minute"][0], state.time.total_minutes)

        projection = state.get_table("unit_capability_projections").to_dicts()[0]
        self.assertEqual(projection["training_level"], "Regular")
        self.assertIn("speed", projection["capabilities_json"])

    def test_cancelling_training_preserves_cost_and_returns_unit_to_recorded_region(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Veteran")]
        system.update(state, 0.0)
        state.current_actions = [ActionCancelUnitTraining("player", "USA-1")]
        system.update(state, 0.0)

        unit = state.get_table("units").to_dicts()[0]
        order = state.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual(order["status"], "cancelled")
        self.assertEqual(unit["current_region_id"], 1)
        self.assertEqual(unit["training_state"], "")
        self.assertEqual(unit["training_level"], "Recruit")
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 800.0)
        self.assertEqual(state.get_table("unit_training_orders")["last_event"][0], "cancelled")
        self.assertGreaterEqual(state.get_table("unit_training_orders")["cancelled_at_minute"][0], 0)

    def test_training_actions_require_country_authority(self) -> None:
        state = self._state()
        state.current_actions = [ActionTrainUnit("intruder", "USA", "USA-1", "Regular")]

        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertEqual(state.get_table("units")["unit_lifecycle"][0], "available")
        self.assertEqual(state.get_table("countries")["money_reserves"][0], 1000.0)
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_paused_training_preserves_progress_until_resumed(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        system.update(state, 0.0)
        state.current_actions = [ActionSetUnitTrainingPaused("player", "USA-1", True)]
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)

        self.assertEqual(state.get_table("unit_training_orders")["status"][0], "paused")
        self.assertEqual(state.get_table("unit_training_orders")["progress"][0], 0.0)

        state.events = []
        state.current_actions = [ActionSetUnitTrainingPaused("player", "USA-1", False)]
        system.update(state, 0.0)
        state.current_actions = []
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)
        self.assertAlmostEqual(state.get_table("unit_training_orders")["progress"][0], 0.5)

    def test_moving_units_cannot_enter_training(self) -> None:
        state = self._state()
        rows = state.get_table("units").to_dicts()
        rows[0]["is_moving"] = True
        state.update_table("units", pl.DataFrame(rows, schema=UNIT_SCHEMA))
        MilitaryCapabilitySystem().update(state, 0.0)
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertEqual(state.get_table("units")["current_region_id"][0], 1)

    def test_training_requires_a_configured_facility_and_available_instructor(self) -> None:
        state = self._state()
        state.update_table("unit_training_facilities", pl.DataFrame(schema=state.get_table("unit_training_facilities").schema))
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertIn("facility", state.journal.command_results[-1]["reason"].lower())

        state = self._state()
        facilities = state.get_table("unit_training_facilities").with_columns(pl.lit(0).cast(pl.Int32).alias("instructor_count"))
        state.update_table("unit_training_facilities", facilities)
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertIn("instructor", state.journal.command_results[-1]["reason"].lower())

    def test_training_rejects_a_facility_for_another_domain_or_insufficient_funding(self) -> None:
        state = self._state()
        state.update_table(
            "unit_training_facilities",
            state.get_table("unit_training_facilities").with_columns(pl.Series("supported_domains", [["air"]])),
        )
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertIn("domain", state.journal.command_results[-1]["reason"].lower())

        state = self._state()
        state.update_table("countries", state.get_table("countries").with_columns(pl.lit(0.0).alias("money_reserves")))
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertTrue(state.get_table("unit_training_orders").is_empty())
        self.assertIn("fund", state.journal.command_results[-1]["reason"].lower())
        self.assertEqual(state.get_table("unit_training_facilities")["capacity"][0], 1)

    def test_training_facility_selection_and_capacity_are_deterministic(self) -> None:
        state = self._state()
        facilities = state.get_table("unit_training_facilities").to_dicts()
        facilities.append({
            "id": "site-a", "country_id": "USA", "region_id": 1,
            "supported_domains": ["land"], "capacity": 1, "instructor_count": 1, "enabled": True,
        })
        state.update_table("unit_training_facilities", pl.DataFrame(facilities, schema=state.get_table("unit_training_facilities").schema))
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)
        self.assertEqual(state.get_table("unit_training_orders")["facility_id"][0], "site-a")

        state = self._state()
        order_schema = state.get_table("unit_training_orders").schema
        state.update_table("unit_training_orders", pl.DataFrame([{
            "id": "training-other", "unit_id": "other-unit", "country_id": "USA",
            "facility_id": "site-usa-1", "status": "active",
        }], schema=order_schema, strict=False))
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        MilitaryCapabilitySystem().update(state, 0.0)

        self.assertEqual(state.get_table("unit_training_orders").height, 1)
        self.assertIn("capacity", state.journal.command_results[-1]["reason"].lower())

    def test_training_pauses_without_facility_capacity_and_resumes_without_losing_progress(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        system.update(state, 0.0)
        state.current_actions = []
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)
        self.assertAlmostEqual(state.get_table("unit_training_orders")["progress"][0], 0.5)

        state.update_table(
            "unit_training_facilities",
            state.get_table("unit_training_facilities").with_columns(pl.lit(0).cast(pl.Int32).alias("instructor_count")),
        )
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)
        order = state.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual(order["status"], "paused")
        self.assertAlmostEqual(order["progress"], 0.5)
        self.assertEqual(order["last_event"], "paused")

        state.update_table(
            "unit_training_facilities",
            state.get_table("unit_training_facilities").with_columns(pl.lit(1).cast(pl.Int32).alias("instructor_count")),
        )
        state.current_actions = [ActionSetUnitTrainingPaused("player", "USA-1", False)]
        state.events = []
        system.update(state, 0.0)
        state.current_actions = []
        state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
        system.update(state, 0.0)

        order = state.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual(order["status"], "completed")
        self.assertEqual(order["last_event"], "completed")
        self.assertAlmostEqual(order["progress"], 1.0)

    def test_training_assignment_and_progress_survive_snapshot_and_deterministic_continuation(self) -> None:
        original = self._state()
        system = MilitaryCapabilitySystem()
        original.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular")]
        system.update(original, 0.0)
        restored = GameState.from_ipc(original.to_ipc())
        ensure_base_tables(restored)

        for state in (original, restored):
            state.current_actions = []
            state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
            MilitaryCapabilitySystem().update(state, 0.0)

        self.assertEqual(
            original.get_table("unit_training_orders").to_dicts(),
            restored.get_table("unit_training_orders").to_dicts(),
        )
        self.assertTrue(
            original.get_table("unit_capability_projections").equals(
                restored.get_table("unit_capability_projections")
            )
        )
        self.assertEqual(
            original.get_table("units").select("training_facility_id", "training_location_region_id", "training_progress").to_dicts(),
            restored.get_table("units").select("training_facility_id", "training_location_region_id", "training_progress").to_dicts(),
        )

        for state in (original, restored):
            state.events = []
            state.current_actions = [ActionSetUnitTrainingPaused("player", "USA-1", True)]
            MilitaryCapabilitySystem().update(state, 0.0)
        paused_snapshot = GameState.from_ipc(original.to_ipc())
        ensure_base_tables(paused_snapshot)
        self.assertEqual(paused_snapshot.get_table("unit_training_orders")["status"][0], "paused")
        self.assertAlmostEqual(paused_snapshot.get_table("unit_training_orders")["progress"][0], 0.5)

        for state in (original, restored):
            state.events = []
            state.current_actions = [ActionSetUnitTrainingPaused("player", "USA-1", False)]
            MilitaryCapabilitySystem().update(state, 0.0)
            state.current_actions = []
            state.events = [EventRealSecond(15 * 24 * 60 * 60, False)]
            MilitaryCapabilitySystem().update(state, 0.0)
        completed_snapshot = GameState.from_ipc(original.to_ipc())
        ensure_base_tables(completed_snapshot)
        completed_order = completed_snapshot.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual(completed_order["status"], "completed")
        self.assertEqual(completed_order["last_event"], "completed")
        self.assertAlmostEqual(completed_order["progress"], 1.0)
        self.assertEqual(original.get_table("unit_training_orders").to_dicts(), restored.get_table("unit_training_orders").to_dicts())

    def _state(self) -> GameState:
        unit = UnitFactory().create("USA-1", "USA", "army", 100, 1, GeoCoordinate(10.0, 20.0), 0)
        unit["readiness_status"] = "ready"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "countries": pl.DataFrame({"id": ["USA"], "money_reserves": [1000.0], "military_count": [100]}),
            "regions": pl.DataFrame({
                "id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0],
            }),
        })
        ensure_base_tables(state)
        state.update_table("unit_training_facilities", pl.DataFrame([{
            "id": "site-usa-1", "country_id": "USA", "region_id": 1,
            "supported_domains": ["land"], "capacity": 1, "instructor_count": 1, "enabled": True,
        }], schema=state.get_table("unit_training_facilities").schema))
        state.globals["player_country_map"] = {"player": "USA"}
        return state


if __name__ == "__main__":
    unittest.main()
