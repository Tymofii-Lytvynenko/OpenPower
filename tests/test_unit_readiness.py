import unittest

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.readiness_system import ReadinessSystem
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit, ActionSetUnitReadiness
from src.shared.events import EventUnitReadinessCanceled, EventUnitReadinessCompleted, EventUnitReadinessStarted
from src.shared.state import GameState


class UnitReadinessTest(unittest.TestCase):
    def _state(self) -> GameState:
        unit = UnitFactory().create("USA-army-001", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        return GameState(tables={"units": pl.DataFrame([unit], schema=UNIT_SCHEMA)})

    def test_transition_exposes_progress_and_completes(self) -> None:
        state = self._state()
        system = ReadinessSystem()
        state.current_actions = [ActionSetUnitReadiness("USA", "USA-army-001", "fortified")]
        system.update(state, 0)
        self.assertEqual(state.get_table("units")["readiness_status"][0], "parked")
        self.assertEqual(state.get_table("units")["readiness_progress"][0], 0.0)
        self.assertTrue(any(isinstance(event, EventUnitReadinessStarted) for event in state.events))

        state.current_actions = []
        state.time.total_minutes = ReadinessPolicy.PARKED_TO_READY_MINUTES
        system.update(state, 0)
        self.assertEqual(state.get_table("units")["readiness_status"][0], "ready")
        self.assertGreater(state.get_table("units")["readiness_progress"][0], 0.9)

        state.time.total_minutes = ReadinessPolicy.PARKED_TO_READY_MINUTES + ReadinessPolicy.READY_TO_FORTIFIED_MINUTES
        system.update(state, 0)
        self.assertEqual(state.get_table("units")["readiness_status"][0], "fortified")
        self.assertTrue(any(isinstance(event, EventUnitReadinessCompleted) for event in state.events))

    def test_combat_order_cancels_transition_before_due_boundary(self) -> None:
        state = self._state()
        system = ReadinessSystem()
        state.current_actions = [ActionSetUnitReadiness("USA", "USA-army-001", "ready")]
        system.update(state, 0)
        state.time.total_minutes = ReadinessPolicy.PARKED_TO_READY_MINUTES
        state.current_actions = [ActionAttackUnit("USA", "USA-army-001", "CAN-army-001")]
        system.update(state, 0)
        self.assertEqual(state.get_table("unit_readiness_transitions").height, 0)
        self.assertTrue(any(isinstance(event, EventUnitReadinessCanceled) for event in state.events))

    def test_invalid_target_is_rejected_without_mutating_status(self) -> None:
        state = self._state()
        ReadinessSystem().update(state, 0)
        state.current_actions = [ActionSetUnitReadiness("USA", "USA-army-001", "invalid")]
        ReadinessSystem().update(state, 0)
        self.assertEqual(state.get_table("units")["readiness_status"][0], "parked")
        self.assertEqual(state.get_table("unit_readiness_transitions").height, 0)

    def test_local_admin_can_request_readiness_for_local_session(self) -> None:
        state = self._state()
        state.current_actions = [ActionSetUnitReadiness("local_admin", "USA-army-001", "ready")]
        ReadinessSystem().update(state, 0)
        self.assertEqual(state.get_table("units")["readiness_status"][0], "parked")
        self.assertTrue(state.get_table("units")["readiness_transition_id"][0])

    def test_idle_update_does_not_churn_unit_revision(self) -> None:
        state = self._state()
        system = ReadinessSystem()
        system.update(state, 0)
        revisions = dict(state.table_revisions)

        system.update(state, 0)

        self.assertEqual(dict(state.table_revisions), revisions)


if __name__ == "__main__":
    unittest.main()
