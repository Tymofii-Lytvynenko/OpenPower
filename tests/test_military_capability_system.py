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

    def test_published_training_quote_matches_charge_and_survives_ipc(self):
        state = self._state()
        system = MilitaryCapabilitySystem()
        system.update(state, 0)
        quote = state.get_table("unit_training_quotes").to_dicts()[0]
        self.assertTrue(quote["available"])
        self.assertEqual((quote["cost"], quote["required_days"]), (100, 30))
        restored = GameState.from_ipc(state.to_ipc())
        self.assertTrue(restored.get_table("unit_training_quotes").equals(state.get_table("unit_training_quotes")))
        state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", quote["target_level"],
            expected_cost=quote["cost"], expected_required_days=quote["required_days"], expected_from_level=quote["from_level"])]
        system.update(state, 0)
        order = state.get_table("unit_training_orders").to_dicts()[0]
        self.assertEqual((order["cost"], order["required_days"]), (quote["cost"], quote["required_days"]))
        self.assertFalse(state.get_table("unit_training_quotes")["available"][0])

    def test_changed_confirmation_terms_are_rejected_without_charge(self):
        for fields in ({"expected_cost": 101}, {"expected_required_days": 31},
                       {"expected_from_level": "Veteran"}, {"expected_cost": float("nan")},
                       {"expected_cost": True}):
            with self.subTest(fields=fields):
                state = self._state()
                state.current_actions = [ActionTrainUnit("player", "USA", "USA-1", "Regular", **fields)]
                MilitaryCapabilitySystem().update(state, 0)
                self.assertTrue(state.get_table("unit_training_orders").is_empty())
                self.assertEqual(state.get_table("countries")["money_reserves"][0], 1000)
                self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_unavailable_training_quote_does_not_invent_cost(self):
        state = self._state()
        state.update_table("unit_training_facilities", state.get_table("unit_training_facilities").clear())
        MilitaryCapabilitySystem().update(state, 0)
        quote = state.get_table("unit_training_quotes").to_dicts()[0]
        self.assertFalse(quote["available"])
        self.assertIsNone(quote["cost"])
        self.assertIsNone(quote["required_days"])
        self.assertIn("facility", quote["reason"])

    def test_training_plan_rejects_unavailable_invalid_active_and_battle_units(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        unit = state.get_table("units").to_dicts()[0]
        countries = {"USA": state.get_table("countries").to_dicts()[0]}

        _, reason = system._training_plan(
            state,
            {},
            countries,
            [],
            [],
            ActionTrainUnit("player", "USA", "missing-unit", "Regular"),
        )
        self.assertEqual(reason, "The unit or owning country is unavailable.")

        _, reason = system._training_plan(
            state,
            {"USA-1": unit},
            {},
            [],
            [],
            ActionTrainUnit("player", "USA", "USA-1", "Regular"),
        )
        self.assertEqual(reason, "The unit or owning country is unavailable.")

        _, reason = system._training_plan(
            state,
            {"USA-1": unit},
            countries,
            [],
            [],
            ActionTrainUnit("player", "USA", "USA-1", "Recruit"),
        )
        self.assertEqual(reason, "Training must advance to a supported higher level.")

        _, reason = system._training_plan(
            state,
            {"USA-1": unit},
            countries,
            [{"unit_id": "USA-1", "status": "active"}],
            [],
            ActionTrainUnit("player", "USA", "USA-1", "Regular"),
        )
        self.assertEqual(reason, "The unit already has an active training order.")

        state.update_table(
            "battle_units",
            pl.DataFrame([{"unit_id": "USA-1"}], schema=state.get_table("battle_units").schema, strict=False),
        )
        _, reason = system._training_plan(
            state,
            {"USA-1": unit},
            countries,
            [],
            [],
            ActionTrainUnit("player", "USA", "USA-1", "Regular"),
        )
        self.assertEqual(reason, "A participating battle force cannot begin training.")

    def test_training_action_rejections_cover_missing_authority_and_orders(self) -> None:
        state = self._state()
        state.current_actions = [
            ActionCancelUnitTraining("unauthorized-player", "USA-1"),
            ActionCancelUnitTraining("player", "USA-1"),
            ActionSetUnitTrainingPaused("unauthorized-player", "USA-1", True),
            ActionSetUnitTrainingPaused("player", "USA-1", True),
        ]

        MilitaryCapabilitySystem().update(state, 0.0)

        results = state.journal.command_results
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result["status"] == "rejected" for result in results))

    def test_training_helpers_skip_unmatched_orders_and_resolve_design_domain(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        unit = state.get_table("units").to_dicts()[0]

        self.assertFalse(system._cancel_training(state, {}, [], "USA-1"))
        self.assertFalse(
            system._cancel_training(
                state,
                {"USA-1": unit},
                [
                    {"unit_id": "other-unit", "status": "active"},
                    {"unit_id": "USA-1", "status": "completed"},
                ],
                "USA-1",
            )
        )

        paused_orders = [
            {"unit_id": "other-unit", "status": "active"},
            {"unit_id": "USA-1", "status": "paused"},
        ]
        self.assertTrue(system._set_training_paused(paused_orders, "USA-1", True, 10))
        self.assertFalse(system._set_training_paused([], "USA-1", True, 10))

        unit["design_id"] = "air-design"
        selected, reason = system._select_training_facility(
            state,
            unit,
            "USA",
            [{
                "id": "air-site", "country_id": "USA", "region_id": 1,
                "supported_domains": ["air"], "capacity": 1, "instructor_count": 1, "enabled": True,
            }],
            [],
            designs=pl.DataFrame([{"id": "air-design", "domain": "air"}]),
        )
        self.assertEqual(reason, "")
        self.assertEqual(selected["id"], "air-site")

    def test_advance_training_blocks_missing_units_and_full_facility_slots(self) -> None:
        state = self._state()
        system = MilitaryCapabilitySystem()
        missing_unit_order = {
            "id": "missing-unit-order", "unit_id": "missing-unit", "country_id": "USA",
            "facility_id": "site-usa-1", "training_location_region_id": 1, "status": "active",
        }
        system._advance_training(state, {}, [missing_unit_order], [], 1.0)
        self.assertEqual(missing_unit_order["status"], "blocked")
        self.assertEqual(missing_unit_order["last_event"], "blocked")

        unit = state.get_table("units").to_dicts()[0]
        second_unit = {**unit, "id": "USA-2"}
        orders = [
            {
                "id": f"order-{unit_id}", "unit_id": unit_id, "country_id": "USA",
                "facility_id": "site-usa-1", "training_location_region_id": 1,
                "status": "active", "required_days": 30.0, "progress": 0.0,
            }
            for unit_id in ("USA-1", "USA-2")
        ]
        facility = state.get_table("unit_training_facilities").to_dicts()[0]
        system._advance_training(state, {"USA-1": unit, "USA-2": second_unit}, orders, [facility], 1.0)

        self.assertEqual(orders[0]["status"], "active")
        self.assertEqual(orders[1]["status"], "paused")
        self.assertIn("capacity", orders[1]["blocking_reason"])

    def test_capability_helpers_cover_defaults_decoding_and_coercion(self) -> None:
        system = MilitaryCapabilitySystem()
        frozen = system._freeze_cache_value({"items": [1, 2], "tags": {"beta", "alpha"}})
        self.assertEqual(frozen, (("items", (1, 2)), ("tags", ("alpha", "beta"))))

        unit = system._ensure_unit_columns(pl.DataFrame({"id": ["USA-1"]}))
        self.assertEqual(unit["training_level"][0], "Recruit")
        self.assertEqual(unit["unit_lifecycle"][0], "available")

        ensured = system._ensure_table(
            pl.DataFrame({"id": ["site-1"]}),
            {"id": pl.Utf8, "capacity": pl.Int32, "supported_domains": pl.List(pl.Utf8)},
        )
        self.assertEqual(ensured["capacity"][0], 0)
        self.assertEqual(ensured["supported_domains"].to_list(), [[]])

        self.assertEqual(system._decode_mapping("{invalid"), {})
        self.assertEqual(system._decode_list("[invalid"), [])
        self.assertEqual(system._integer("not-an-integer"), 0)
        self.assertEqual(system._number("not-a-number"), 0.0)

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
