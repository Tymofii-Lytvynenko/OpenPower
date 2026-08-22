import unittest

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, MilitarySystem, UnitFactory
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.readiness_system import ReadinessSystem
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionMoveUnit, ActionSetUnitReadiness
from src.shared.state import GameState


class OrderReadinessTest(unittest.TestCase):
    def _state(self) -> GameState:
        unit = UnitFactory().create("USA-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        return GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "regions": pl.DataFrame({"id": [1, 2], "owner": ["USA", "USA"], "latitude": [0.0, 0.0], "longitude": [0.0, 10.0]}),
            "countries": pl.DataFrame({"id": ["USA"], "military_count": [100], "money_reserves": [0.0]}),
        })

    def test_move_is_queued_and_released_after_readiness(self) -> None:
        state = self._state()
        readiness = ReadinessSystem()
        military = MilitarySystem()
        state.current_actions = [ActionSetUnitReadiness("USA", "USA-1", "ready")]
        readiness.update(state, 0)
        state.current_actions = [ActionMoveUnit("USA", "USA-1", 2, 0.0, 10.0)]
        military.update(state, 0)
        self.assertEqual(state.get_table("unit_pending_orders").height, 1)
        self.assertFalse(state.get_table("units")["is_moving"][0])

        state.current_actions = []
        state.time.total_minutes = ReadinessPolicy.PARKED_TO_READY_MINUTES
        readiness.update(state, 0)
        military.update(state, 0)
        self.assertEqual(state.get_table("unit_pending_orders").height, 0)
        self.assertTrue(state.get_table("units")["is_moving"][0])

    def test_invalid_target_does_not_replace_existing_move(self) -> None:
        state = self._state()
        military = MilitarySystem()
        state.current_actions = [ActionMoveUnit("USA", "USA-1", 2, 0.0, 10.0)]
        military.update(state, 0)
        state.time.total_minutes = 5
        state.current_actions = [ActionMoveUnit("USA", "USA-1", 999, 0.0, 0.0)]
        military.update(state, 0)
        self.assertTrue(state.get_table("units")["is_moving"][0])
        self.assertEqual(state.get_table("units")["target_region_id"][0], 2)


if __name__ == "__main__":
    unittest.main()
