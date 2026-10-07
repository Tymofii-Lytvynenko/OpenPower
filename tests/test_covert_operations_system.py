from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from modules.base.systems.military.covert_operations_system import MISSION_PROFILES, CovertOperationsSystem
from modules.base.systems.military.covert_policy import domestic_security_coverage
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionCreateCovertCell, ActionStartCovertMission, ActionTrainCovertCell
from src.shared.config import GameConfig
from src.shared.events import EventUnitReadinessStarted
from src.shared.state import GameState


class CovertOperationsSystemTest(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "gdp": [1000.0, 900.0],
                "money_reserves": [1000.0, 1000.0], "security_upkeep": [0.0, 0.0],
                "military_count": [100, 80],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"],
                "latitude": [40.0, 45.0], "longitude": [-100.0, -75.0],
            }),
        })
        ensure_base_tables(state)
        state.globals["covert_transit_minutes"] = 60
        state.globals["covert_training_minutes_per_level"] = 60
        state.globals["covert_civilian_espionage_preparation_minutes"] = 60
        return state

    def test_cell_transit_training_mission_and_intelligence_are_persisted(self) -> None:
        state = self._state()
        system = CovertOperationsSystem()
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "CAN", "North Cell")]
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual(cell["status"], "transit")

        state.time.total_minutes = cell["available_at_minute"]
        state.current_actions = []
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual(cell["status"], "active")
        self.assertEqual(cell["location_country_id"], "CAN")

        state.current_actions = [ActionTrainCovertCell("USA", cell["id"], 100.0)]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("covert_cells")["skill_level"][0], "Recruit")
        state.time.total_minutes += 60
        state.current_actions = []
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual(cell["skill_level"], "Regular")

        state.current_actions = [ActionStartCovertMission("USA", cell["id"], "civilian_espionage", "CAN")]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("covert_missions")["status"][0], "preparation")
        state.time.total_minutes += 60
        state.current_actions = []
        system.update(state, 0.0)
        mission = state.get_table("covert_missions").to_dicts()[0]
        self.assertEqual(mission["status"], "executing")
        state.time.total_minutes += 1
        system.update(state, 0.0)
        mission = state.get_table("covert_missions").to_dicts()[0]
        self.assertEqual(mission["status"], "cleanup")
        self.assertIn(mission["result"], {"success", "partial_success", "failure", "captured"})
        if mission["result"] in {"success", "partial_success"}:
            self.assertEqual(state.get_table("covert_findings").height, 1)
        self.assertEqual(state.get_table("covert_incidents").height, 1)
        state.time.total_minutes = mission["cleanup_until_minute"]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("covert_missions")["status"][0], "resolved")

    def test_invalid_owner_cannot_create_cell_or_spend_funds(self) -> None:
        state = self._state()
        before = state.get_table("countries")["money_reserves"][0]
        state.current_actions = [ActionCreateCovertCell("CAN", "USA", "CAN", "Unauthorized")]
        CovertOperationsSystem().update(state, 0.0)
        self.assertTrue(state.get_table("covert_cells").is_empty())
        self.assertEqual(state.get_table("countries")["money_reserves"][0], before)

    def test_capacity_and_funding_rejections_do_not_consume_cells_or_budget(self) -> None:
        state = self._state()
        state.globals["covert_cell_capacity"] = 1
        state.current_actions = [
            ActionCreateCovertCell("USA", "USA", "USA", "First"),
            ActionCreateCovertCell("USA", "USA", "USA", "Over capacity"),
        ]
        CovertOperationsSystem().update(state, 0.0)
        self.assertEqual(state.get_table("covert_cells").height, 1)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 990.0)

        underfunded = self._state()
        underfunded.update_table(
            "countries",
            underfunded.get_table("countries").with_columns(
                pl.when(pl.col("id") == "USA").then(5.0).otherwise(pl.col("money_reserves")).alias("money_reserves")
            ),
        )
        underfunded.current_actions = [ActionCreateCovertCell("USA", "USA", "USA", "Unaffordable")]
        CovertOperationsSystem().update(underfunded, 0.0)
        self.assertTrue(underfunded.get_table("covert_cells").is_empty())
        self.assertEqual(underfunded.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 5.0)

    def test_duplicate_mission_and_unfunded_preparation_are_rejected_without_side_effects(self) -> None:
        state = self._state()
        system = CovertOperationsSystem()
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "USA", "Mission Cell")]
        system.update(state, 0.0)
        cell_id = state.get_table("covert_cells")["id"][0]
        state.update_table(
            "covert_cells",
            state.get_table("covert_cells").with_columns(
                pl.lit("Regular").alias("skill_level"), pl.lit(1.0).alias("readiness")
            ),
        )
        action = ActionStartCovertMission("USA", cell_id, "civilian_espionage", "USA")
        state.current_actions = [action, action]
        system.update(state, 0.0)
        self.assertEqual(state.get_table("covert_missions").height, 1)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 988.0)

        no_funds = self._state()
        no_funds.current_actions = [ActionCreateCovertCell("USA", "USA", "USA", "Unfunded Mission Cell")]
        system.update(no_funds, 0.0)
        no_funds_cell_id = no_funds.get_table("covert_cells")["id"][0]
        no_funds.update_table(
            "covert_cells",
            no_funds.get_table("covert_cells").with_columns(pl.lit("Regular").alias("skill_level")),
        )
        no_funds.update_table(
            "countries",
            no_funds.get_table("countries").with_columns(
                pl.when(pl.col("id") == "USA").then(1.0).otherwise(pl.col("money_reserves")).alias("money_reserves")
            ),
        )
        no_funds.current_actions = [
            ActionStartCovertMission("USA", no_funds_cell_id, "civilian_espionage", "USA")
        ]
        system.update(no_funds, 0.0)
        self.assertTrue(no_funds.get_table("covert_missions").is_empty())
        self.assertEqual(no_funds.get_table("covert_cells")["status"][0], "active")
        self.assertEqual(no_funds.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 1.0)

    def test_mission_profiles_are_distinct_and_resolve_deterministically(self) -> None:
        state = self._state()
        system = CovertOperationsSystem()
        cell = {
            "id": "cell-1", "country_id": "USA", "skill_level": "Elite",
            "readiness": 1.0, "concealment": 0.79, "communications_ready": True,
        }
        target = {"id": "CAN", "gdp": 900.0, "security_upkeep": 0.0}
        self.assertEqual(len({profile[0] for profile in MISSION_PROFILES.values()}), 8)
        self.assertEqual(len({profile[1] for profile in MISSION_PROFILES.values()}), 8)

        for mission_type in MISSION_PROFILES:
            with self.subTest(mission_type=mission_type):
                mission = {
                    "id": f"mission-{mission_type}", "owner_country_id": "USA",
                    "target_country_id": "CAN", "mission_type": mission_type,
                    "resolves_at_minute": 12_345, "preparation_required": 10_080,
                }
                first = system._resolve(state, cell, mission, target, [], [])[0:4]
                second = system._resolve(state, cell, mission, target, [], [])[0:4]
                self.assertEqual(first, second)

    def test_pending_covert_mission_survives_snapshot_and_save_load_continuation(self) -> None:
        state = self._state()
        system = CovertOperationsSystem()
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "USA", "Persisted Cell")]
        system.update(state, 0.0)
        cell_id = state.get_table("covert_cells")["id"][0]
        state.update_table(
            "covert_cells",
            state.get_table("covert_cells").with_columns(
                pl.lit("Regular").alias("skill_level"),
                pl.lit(0.43).alias("concealment"),
                pl.lit(1.0).alias("readiness"),
            ),
        )
        state.current_actions = [ActionStartCovertMission("USA", cell_id, "civilian_espionage", "USA")]
        system.update(state, 0.0)
        state.current_actions = []

        covert_tables = (
            "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents",
        )
        registry = build_base_schema_registry()
        snapshot = GameState.from_ipc(state.to_ipc())
        registry.ensure_state(snapshot)
        for table_name in covert_tables:
            self.assertEqual(snapshot.get_table(table_name).to_dicts(), state.get_table(table_name).to_dicts())

        with TemporaryDirectory() as temporary_directory:
            config = GameConfig(Path(temporary_directory))
            self.assertTrue(SaveWriter(config).save_game(state, "covert-pending"))
            loaded = DataLoader(config, schema_registry=registry).load_save("covert-pending")
            for table_name in covert_tables:
                self.assertEqual(loaded.get_table(table_name).to_dicts(), state.get_table(table_name).to_dicts())

            for candidate in (state, loaded):
                candidate.time.total_minutes += 60
                system.update(candidate, 0.0)
                candidate.time.total_minutes += 1
                system.update(candidate, 0.0)

            for table_name in covert_tables:
                self.assertEqual(loaded.get_table(table_name).to_dicts(), state.get_table(table_name).to_dicts())

    def test_idle_update_does_not_materialize_units_or_revise_covert_tables(self) -> None:
        state = self._state()
        units = pl.DataFrame({"id": ["CAN-private-unit"], "owner": ["CAN"]})
        state.update_table("units", units)
        findings = state.get_table("covert_findings")
        covert_tables = (
            "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents",
        )
        before = {name: state.table_revisions[name] for name in covert_tables}
        original_to_dicts = pl.DataFrame.to_dicts

        def fail_on_units(frame, *args, **kwargs):
            if frame is units or frame is findings:
                raise AssertionError("Idle intelligence processing must not materialize force or finding rows.")
            return original_to_dicts(frame, *args, **kwargs)

        with patch.object(pl.DataFrame, "to_dicts", new=fail_on_units):
            CovertOperationsSystem().update(state, 0.0)

        self.assertEqual({name: state.table_revisions[name] for name in covert_tables}, before)

    def test_military_intelligence_is_shared_only_with_eligible_allies_and_confidence_is_capped(self) -> None:
        state = self._state()
        state.update_table("covert_findings", pl.DataFrame([{
            "id": "finding-1", "owner_country_id": "CAN", "target_country_id": "USA",
            "category": "military", "value_json": "{\"unit_count_estimate\":4}",
            "confidence": 0.95, "freshness": 1.0,
            "discovered_at_minute": 0, "expires_at_minute": 1000,
        }], schema=state.get_table("covert_findings").schema))
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "alliance", "country_id": "CAN",
            "effect": "military_intelligence_sharing", "value": 1.0, "detail": '["USA"]',
        }], schema=state.get_table("treaty_effects").schema))

        finding = MilitaryPresenter().covert_findings_for_country(state, "USA")[0]

        self.assertEqual(finding["source_country_id"], "CAN")
        self.assertLessEqual(finding["confidence"], 0.95)
        self.assertLess(finding["confidence"], 0.95)
        state.update_table("treaty_effects", pl.DataFrame(schema=state.get_table("treaty_effects").schema))
        self.assertEqual(MilitaryPresenter().covert_findings_for_country(state, "USA"), [])

    def test_military_espionage_snapshot_records_role_composition_without_unit_identity(self) -> None:
        state = self._state()
        state.update_table("units", pl.DataFrame({
            "id": ["can-tank-1", "can-tank-2", "can-fighter-1"],
            "owner": ["CAN", "CAN", "CAN"],
            "unit_type": ["tanks", "tank", "fighters"],
            "strength": [100, 50, 40],
            "readiness_status": ["ready", "parked", "ready"],
            "design_id": ["", "", ""],
        }))

        output = CovertOperationsSystem()._intelligence_snapshot(
            state,
            {"id": "CAN"},
            {"mission_type": "military_espionage"},
            0.7,
        )

        self.assertEqual(output["unit_role_count_estimates"], {"fighters": 1, "tanks": 2})
        self.assertNotIn("can-tank-1", str(output))
        self.assertNotIn("can-fighter-1", str(output))

    def test_military_espionage_records_bounded_confidence_factors_without_exact_cell_counts(self) -> None:
        state = self._state()
        countries = state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "USA").then(0.7).otherwise(0.5).alias("budget_telecom_ratio")
        )
        regions = state.get_table("regions").with_columns(pl.Series("telecom_capacity", [0.3, 0.8]))
        state.update_table("countries", countries)
        state.update_table("regions", regions)
        state.update_table("units", pl.DataFrame({
            "id": ["can-tank-1"], "owner": ["CAN"], "unit_type": ["tank"], "strength": [100],
        }))
        cell = {
            "id": "cell-1", "skill_level": "Regular", "readiness": 1.0,
            "concealment": 0.2, "communications_ready": True,
        }
        mission = {
            "id": "mission-1", "owner_country_id": "USA", "target_country_id": "CAN",
            "mission_type": "military_espionage", "resolves_at_minute": 10,
            "preparation_required": 10080,
        }
        all_cells = [
            {**cell, "assignment": "espionage", "country_id": "USA", "target_country_id": "CAN", "status": "active"},
            {**cell, "id": "cell-2", "assignment": "espionage", "country_id": "USA", "target_country_id": "CAN", "status": "preparing"},
        ]
        fake_digest = type("Digest", (), {"hexdigest": lambda self: "0" * 64})

        with patch("modules.base.systems.military.covert_operations_system.hashlib.sha256", return_value=fake_digest()):
            result, _, _, _, output = CovertOperationsSystem()._resolve(
                state, cell, mission, {"id": "CAN", "gdp": 900.0, "security_upkeep": 0.0}, all_cells, [],
            )

        self.assertEqual(result, "success")
        self.assertEqual(output["confidence_factors"], {
            "observer_telecom": 0.7,
            "target_telecom": 0.8,
            "intelligence_coverage": "sustained",
        })
        self.assertNotIn("active_target_coverage", output["confidence_factors"])

    def test_eligible_espionage_cells_receive_deterministic_mobilization_signals_without_unit_identity(self) -> None:
        state = self._state()
        state.update_table("countries", state.get_table("countries").with_columns(
            pl.Series("budget_telecom_ratio", [0.9, 0.8]),
        ))
        state.update_table("units", pl.DataFrame({
            "id": ["can-unit-private-id"], "owner": ["CAN"], "unit_type": ["tanks"],
            "unit_domain": ["land"], "strength": [100],
        }))
        state.update_table("covert_cells", pl.DataFrame([{
            "id": "cell-private-id", "country_id": "USA", "target_country_id": "CAN",
            "location_country_id": "CAN", "assignment": "espionage", "status": "active", "skill_level": "Elite",
            "readiness": 1.0, "concealment": 0.8, "communications_ready": True,
        }], schema=state.get_table("covert_cells").schema, strict=False))
        state.events = [EventUnitReadinessStarted(
            unit_id="can-unit-private-id", transition_id="readiness-can-unit-private-id-1",
            from_status="parked", target_status="ready", stage="parked_to_ready",
            started_at_minute=1, completes_at_minute=2881,
        )]
        fake_digest = type("Digest", (), {"hexdigest": lambda self: "0" * 64})

        with patch("modules.base.systems.military.covert_operations_system.hashlib.sha256", return_value=fake_digest()):
            system = CovertOperationsSystem()
            system.update(state, 0.0)
            first = state.get_table("covert_findings").to_dicts()
            state.events = [EventUnitReadinessStarted(
                unit_id="can-unit-private-id", transition_id="readiness-can-unit-private-id-1",
                from_status="parked", target_status="ready", stage="parked_to_ready",
                started_at_minute=1, completes_at_minute=2881,
            )]
            system.update(state, 0.0)

        self.assertEqual(len(first), 1)
        self.assertEqual(state.get_table("covert_findings").height, 1)
        finding = state.get_table("covert_findings").to_dicts()[0]
        self.assertEqual(finding["category"], "military_mobilization")
        self.assertEqual(finding["owner_country_id"], "USA")
        self.assertEqual(finding["target_country_id"], "CAN")
        self.assertEqual(finding["confidence"], first[0]["confidence"])
        self.assertNotIn("can-unit-private-id", finding["id"] + finding["value_json"])
        self.assertNotIn("cell-private-id", finding["id"] + finding["value_json"])
        signal = json.loads(finding["value_json"])
        self.assertEqual(signal["from_readiness"], "parked")
        self.assertEqual(signal["to_readiness"], "ready")
        self.assertEqual(signal["domain"], "land")
        self.assertEqual(signal["confidence_factors"]["intelligence_coverage"], "limited")

    def test_readiness_signal_requires_foreign_active_espionage_coverage(self) -> None:
        state = self._state()
        state.update_table("units", pl.DataFrame({
            "id": ["can-unit"], "owner": ["CAN"], "unit_type": ["tanks"], "unit_domain": ["land"],
        }))
        state.events = [EventUnitReadinessStarted(
            unit_id="can-unit", transition_id="transition-1", from_status="parked",
            target_status="ready", stage="parked_to_ready", started_at_minute=1, completes_at_minute=2,
        )]

        CovertOperationsSystem().update(state, 0.0)

        self.assertTrue(state.get_table("covert_findings").is_empty())

    def test_targets_only_see_detected_operations_and_detection_reveals_details_not_attribution(self) -> None:
        state = self._state()
        mission = {
            "id": "mission-1", "cell_id": "cell-1", "owner_country_id": "USA",
            "target_country_id": "CAN", "mission_type": "civilian_espionage",
            "status": "cleanup", "result": "partial_success", "discovered_by_target": False,
            "attributed_to_owner": False, "confidence": 0.8, "output_json": '{"secret":"value"}',
        }
        table = state.get_table("covert_missions")
        state.update_table("covert_missions", pl.DataFrame([mission], schema=table.schema, strict=False))
        presenter = MilitaryPresenter()

        self.assertEqual(presenter.covert_missions_for_country(state, "CAN"), [])

        state.update_table(
            "covert_missions",
            state.get_table("covert_missions").with_columns(pl.lit(True).alias("discovered_by_target")),
        )
        visible = presenter.covert_missions_for_country(state, "CAN")
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["mission_type"], "civilian_espionage")
        self.assertEqual(visible[0]["result"], "partial_success")
        self.assertEqual(visible[0]["owner_country_id"], "Unknown")
        self.assertEqual(visible[0]["cell_id"], "")
        self.assertEqual(visible[0]["output_json"], "{}")
        self.assertEqual(visible[0]["confidence"], 0.0)

    def test_detected_operation_message_discloses_type_and_result_without_unattributed_owner(self) -> None:
        state = self._state()
        mission = {
            "id": "mission-1", "owner_country_id": "USA", "target_country_id": "CAN",
            "mission_type": "civilian_espionage",
        }
        system = CovertOperationsSystem()

        system._publish_messages(state, mission, "partial_success", False, False)
        self.assertEqual(set(state.get_table("messages")["country_id"].to_list()), {"USA"})

        state.update_table("messages", pl.DataFrame(schema=state.get_table("messages").schema))
        system._publish_messages(state, mission, "partial_success", True, False)
        target_message = state.get_table("messages").filter(pl.col("country_id") == "CAN").row(0, named=True)
        self.assertIn("Civilian Espionage", target_message["body"])
        self.assertIn("partial_success", target_message["body"])
        self.assertIn("Attribution: unknown", target_message["body"])
        self.assertNotIn("USA", target_message["body"])

    def test_foreign_cell_uses_accessible_region_route_and_waits_when_access_is_revoked(self) -> None:
        state = self._state()
        state.update_table("countries", pl.DataFrame({
            "id": ["USA", "MEX", "CAN"], "gdp": [1000.0, 500.0, 900.0],
            "money_reserves": [1000.0, 1000.0, 1000.0], "security_upkeep": [0.0, 0.0, 0.0],
            "military_count": [100, 50, 80],
        }))
        state.update_table("regions", pl.DataFrame({
            "id": [1, 2, 3], "owner": ["USA", "MEX", "CAN"],
            "latitude": [0.0, 0.0, 0.0], "longitude": [0.0, 5.0, 10.0],
        }))
        state.tables["region_adjacency"] = pl.DataFrame({
            "region_id": [1, 2], "neighbor_region_id": [2, 3],
        })
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "passage", "country_id": "USA", "effect": "transit_rights",
            "value": 1.0, "detail": '["MEX"]',
        }], schema=state.get_table("treaty_effects").schema))
        system = CovertOperationsSystem()
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "CAN", "Route Cell")]
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        route = state.get_table("covert_cell_routes").to_dicts()[0]
        self.assertEqual(route["route_region_ids"], [1, 2, 3])

        state.update_table("treaty_effects", pl.DataFrame(schema=state.get_table("treaty_effects").schema))
        state.time.total_minutes = route["arrival_at_minute"]
        state.current_actions = []
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual(cell["status"], "transit_blocked")
        self.assertNotEqual(cell["location_country_id"], "CAN")

        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "passage", "country_id": "USA", "effect": "transit_rights",
            "value": 1.0, "detail": '["MEX"]',
        }], schema=state.get_table("treaty_effects").schema))
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual(cell["status"], "transit")
        self.assertNotEqual(cell["location_country_id"], "CAN")

    def test_skill_progression_changes_capability_concealment_and_maintenance_cost(self) -> None:
        state = self._state()
        state.globals["covert_cell_upkeep"] = 0.4
        state.globals["covert_coup_attempt_preparation_minutes"] = 100
        system = CovertOperationsSystem()
        state.current_actions = [ActionCreateCovertCell("USA", "USA", "USA", "Domestic")]
        system.update(state, 0.0)
        cell = state.get_table("covert_cells").to_dicts()[0]
        self.assertEqual((cell["skill_level"], cell["concealment"]), ("Recruit", 0.25))
        self.assertAlmostEqual(cell["upkeep"], 0.3)

        for expected_level, expected_concealment, expected_upkeep in (
            ("Regular", 0.43, 0.4),
            ("Veteran", 0.61, 0.5),
            ("Elite", 0.79, 0.6),
        ):
            state.current_actions = [ActionTrainCovertCell("USA", cell["id"], 100.0)]
            system.update(state, 0.0)
            state.time.total_minutes += 60
            state.current_actions = []
            system.update(state, 0.0)
            cell = state.get_table("covert_cells").to_dicts()[0]
            self.assertEqual(cell["skill_level"], expected_level)
            self.assertAlmostEqual(cell["concealment"], expected_concealment)
            self.assertAlmostEqual(cell["upkeep"], expected_upkeep)

            if expected_level == "Veteran":
                state.current_actions = [
                    ActionStartCovertMission("USA", cell["id"], "coup_attempt", "USA")
                ]
                system.update(state, 0.0)
                self.assertTrue(state.get_table("covert_missions").is_empty())

        state.current_actions = [ActionStartCovertMission("USA", cell["id"], "coup_attempt", "USA")]
        system.update(state, 0.0)
        mission = state.get_table("covert_missions").to_dicts()[0]
        self.assertEqual(mission["preparation_required"], 80.0)

    def test_domestic_security_coverage_is_scenario_configurable_and_diminishing(self) -> None:
        defaults = {}
        one_cell = domestic_security_coverage(1, 100_000.0, defaults)
        two_cells = domestic_security_coverage(2, 100_000.0, defaults)
        three_cells = domestic_security_coverage(3, 100_000.0, defaults)
        custom = domestic_security_coverage(
            2, 100_000.0, {"covert_security_base_coverage": 0.6}
        )

        self.assertGreater(one_cell, 0.0)
        self.assertGreater(two_cells, one_cell)
        self.assertLess(three_cells - two_cells, two_cells - one_cell)
        self.assertGreater(custom, two_cells)
        self.assertLess(custom, 1.0)

    def test_transit_security_cell_adds_no_detection_and_active_coverage_is_not_certain(self) -> None:
        state = self._state()
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(pl.Series("population", [1_000_000.0, 1_000_000.0])),
        )
        cell = {
            "id": "attacker", "country_id": "USA", "skill_level": "Elite",
            "readiness": 1.0, "concealment": 0.0, "communications_ready": True,
        }
        mission = {
            "id": "same-mission", "owner_country_id": "USA", "target_country_id": "CAN",
            "mission_type": "civilian_espionage", "resolves_at_minute": 100,
            "preparation_required": 1440,
        }
        target = {"id": "CAN", "gdp": 900.0, "security_upkeep": 0.0}
        transit_guard = {
            "id": "guard", "country_id": "CAN", "assignment": "domestic_security",
            "status": "transit", "location_country_id": "CAN",
        }
        active_guard = {**transit_guard, "status": "active"}
        detection_hash = "47ae147ae147ae14" + "0" * 48

        class FixedDigest:
            def __init__(self, value: str):
                self.value = value

            def hexdigest(self) -> str:
                return self.value

        def fixed_hash(payload: bytes) -> FixedDigest:
            return FixedDigest(detection_hash if payload.endswith(b":detection") else "0" * 64)

        with patch("modules.base.systems.military.covert_operations_system.hashlib.sha256", side_effect=fixed_hash):
            no_guard = CovertOperationsSystem()._resolve(state, cell, mission, target, [], [])[1]
            in_transit = CovertOperationsSystem()._resolve(state, cell, mission, target, [transit_guard], [])[1]
            active = CovertOperationsSystem()._resolve(state, cell, mission, target, [active_guard], [])[1]

        self.assertFalse(no_guard)
        self.assertEqual(in_transit, no_guard)
        self.assertTrue(active)


if __name__ == "__main__":
    unittest.main()
