import unittest

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.server.state_migrations import validate_tactical_combat_state
from src.shared.state import GameState


class TacticalStateValidationTest(unittest.TestCase):
    def test_valid_transition_and_pending_order_links_pass_validation(self) -> None:
        unit = UnitFactory().create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        unit["readiness_transition_id"] = "transition-1"
        unit["readiness_eta_minute"] = 2880
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "unit_readiness_transitions": pl.DataFrame([{
                "id": "transition-1",
                "unit_id": "usa-1",
                "from_status": "parked",
                "target_status": "ready",
                "stage": "parked_to_ready",
                "started_at_minute": 0,
                "completes_at_minute": 2880,
                "progress": 0.5,
                "pending_order_id": "",
            }]),
        })
        self.assertEqual(validate_tactical_combat_state(state), ())

    def test_orphan_and_timing_mismatches_are_reported(self) -> None:
        unit = UnitFactory().create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        unit["readiness_transition_id"] = "missing"
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "unit_readiness_transitions": pl.DataFrame([{
                "id": "transition-1",
                "unit_id": "usa-1",
                "from_status": "parked",
                "target_status": "ready",
                "stage": "parked_to_ready",
                "started_at_minute": 100,
                "completes_at_minute": 50,
                "progress": 1.5,
                "pending_order_id": "",
            }]),
        })
        issues = validate_tactical_combat_state(state)
        self.assertIn("unit_readiness_transitions.invalid_timing:transition-1", issues)
        self.assertIn("unit_readiness_transitions.invalid_progress:transition-1", issues)
        self.assertIn("unit_readiness_transitions.unit_reference_mismatch:transition-1", issues)
        self.assertIn("units.orphan_readiness_transition:usa-1", issues)


if __name__ == "__main__":
    unittest.main()
