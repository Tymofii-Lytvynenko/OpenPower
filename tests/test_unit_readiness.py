import unittest

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.readiness_system import (
    PENDING_SCHEMA,
    PENDING_TABLE,
    TRANSITION_SCHEMA,
    TRANSITIONS_TABLE,
    ReadinessSystem,
    cancel_readiness_for_contact,
)
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit, ActionMoveUnit, ActionSetUnitReadiness
from src.shared.events import EventUnitReadinessCanceled, EventUnitReadinessCompleted, EventUnitReadinessStarted
from src.shared.state import GameState


class UnitReadinessTest(unittest.TestCase):
    def _state(self) -> GameState:
        unit = UnitFactory().create("USA-army-001", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        return GameState(tables={"units": pl.DataFrame([unit], schema=UNIT_SCHEMA)})

    def _state_with_status(self, status: str) -> GameState:
        state = self._state()
        units = state.get_table("units").to_dicts()
        units[0]["readiness_status"] = status
        state.update_table("units", pl.DataFrame(units, schema=UNIT_SCHEMA))
        return state

    def _transition_row(
        self,
        unit_id: str = "USA-army-001",
        target_status: str = "ready",
        stage: str = "parked_to_ready",
        started_at: int = 0,
        completes_at: int = 100,
        pending_order_id: str = "",
    ) -> dict[str, object]:
        return {
            "id": f"readiness-{unit_id}-{started_at}-{stage}",
            "unit_id": unit_id,
            "from_status": "parked",
            "target_status": target_status,
            "stage": stage,
            "started_at_minute": started_at,
            "completes_at_minute": completes_at,
            "progress": 0.0,
            "pending_order_id": pending_order_id,
        }

    def _pending_order_row(
        self,
        order_type: str = "move",
        unit_id: str = "USA-army-001",
        status: str = "queued",
    ) -> dict[str, object]:
        return {
            "id": "order-1",
            "unit_id": unit_id,
            "player_id": "USA",
            "order_type": order_type,
            "target_region_id": 2,
            "target_latitude": 1.5,
            "target_longitude": 2.5,
            "target_unit_id": "CAN-army-001",
            "via_region_ids": [5],
            "created_at_minute": 0,
            "status": status,
        }

    def test_readiness_policy_covers_noop_staged_direct_and_progress_transitions(self) -> None:
        policy = ReadinessPolicy()

        self.assertIsNone(policy.transition("ready", "ready"))
        self.assertEqual(
            policy.transition("parked", "ready").stage,
            "parked_to_ready",
        )
        fortified = policy.transition("ready", "fortified")
        self.assertEqual(fortified.stage, "ready_to_fortified")
        self.assertEqual(fortified.duration_minutes, policy.READY_TO_FORTIFIED_MINUTES)
        direct = policy.transition("fortified", "ready")
        self.assertEqual(direct.stage, "direct")
        self.assertEqual(direct.duration_minutes, 0)
        self.assertEqual(policy.progress(10, 20, 5), 0.0)
        self.assertEqual(policy.progress(10, 20, 15), 0.5)
        self.assertEqual(policy.progress(10, 20, 25), 1.0)

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
        self.assertEqual(state.get_table("units")["readiness_progress"][0], 0.0)
        self.assertEqual(
            state.get_table("unit_readiness_transitions")["target_status"][0],
            "fortified",
        )

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
        # An invalid attack target must not cancel a valid readiness transition.
        self.assertFalse(any(isinstance(event, EventUnitReadinessCanceled) for event in state.events))

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

    def test_transition_progress_is_persisted_at_minute_zero(self) -> None:
        state = self._state()
        system = ReadinessSystem()
        state.current_actions = [ActionSetUnitReadiness("USA", "USA-army-001", "ready")]
        system.update(state, 0)
        transition = state.get_table("unit_readiness_transitions").to_dicts()[0]
        self.assertEqual(transition["started_at_minute"], 0)
        self.assertEqual(transition["progress"], 0.0)
        state.time.total_minutes = 1
        state.current_actions = []
        system.update(state, 0)
        self.assertGreater(state.get_table("unit_readiness_transitions")["progress"][0], 0.0)

    def test_system_metadata_and_empty_unit_transition_update(self) -> None:
        system = ReadinessSystem()
        self.assertEqual(system.id, "base.readiness")
        self.assertEqual(system.dependencies, ["base.time", "base.diplomacy"])

        units = system._ensure_units(pl.DataFrame(schema=UNIT_SCHEMA))
        transitions = system._ensure_transitions(None)
        updated_units, updated_transitions = system._advance_transitions(
            GameState(), units, transitions, 0
        )

        self.assertTrue(updated_units.is_empty())
        self.assertTrue(updated_transitions.is_empty())

    def test_ensure_helpers_fill_missing_readiness_schema_defaults(self) -> None:
        system = ReadinessSystem()
        empty_units = system._ensure_units(None)
        self.assertTrue(empty_units.is_empty())
        self.assertIn("readiness_status", empty_units.columns)

        partial_units = system._ensure_units(pl.DataFrame({"id": ["USA-army-001"]}))
        partial_unit = partial_units.to_dicts()[0]
        self.assertEqual(partial_unit["readiness_status"], "ready")
        self.assertEqual(partial_unit["strength"], 0)
        self.assertEqual(partial_unit["readiness_progress"], 0.0)

        partial_transitions = system._ensure_transitions(pl.DataFrame({"unit_id": ["USA-army-001"]}))
        self.assertEqual(partial_transitions.height, 1)
        self.assertEqual(partial_transitions["completes_at_minute"][0], 0)
        self.assertEqual(partial_transitions["pending_order_id"][0], "")

    def test_prepare_order_handles_missing_ready_pending_and_fortified_units(self) -> None:
        system = ReadinessSystem()
        state = self._state()
        self.assertFalse(system.prepare_order(state, "missing-unit"))

        ready_state = self._state_with_status("ready")
        self.assertTrue(system.prepare_order(ready_state, "USA-army-001"))

        parked_state = self._state()
        parked_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([self._transition_row()], schema=TRANSITION_SCHEMA),
        )
        self.assertFalse(system.prepare_order(parked_state, "USA-army-001", "order-2"))
        self.assertEqual(
            parked_state.get_table(TRANSITIONS_TABLE)["pending_order_id"][0],
            "order-2",
        )

        fortified_state = self._state_with_status("fortified")
        self.assertTrue(system.prepare_order(fortified_state, "USA-army-001"))
        unit = fortified_state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["readiness_status"], "ready")
        self.assertEqual(unit["readiness_transition_id"], "")

    def test_prepare_order_cancels_superseded_fortification_transition(self) -> None:
        state = self._state_with_status("ready")
        state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame(
                [self._transition_row(target_status="fortified", stage="ready_to_fortified")],
                schema=TRANSITION_SCHEMA,
            ),
        )

        self.assertTrue(ReadinessSystem().prepare_order(state, "USA-army-001"))

        self.assertEqual(state.get_table(TRANSITIONS_TABLE).height, 0)
        self.assertTrue(any(isinstance(event, EventUnitReadinessCanceled) for event in state.events))

    def test_prepare_order_handles_unit_disappearing_during_transition_cancellation(self) -> None:
        state = self._state_with_status("ready")
        state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame(
                [self._transition_row(target_status="fortified", stage="ready_to_fortified")],
                schema=TRANSITION_SCHEMA,
            ),
        )
        system = ReadinessSystem()

        def remove_unit(target_state, _unit_id: str, _reason: str) -> None:
            target_state.update_table("units", target_state.get_table("units").clear())

        system.cancel_transition_for_unit = remove_unit

        self.assertFalse(system.prepare_order(state, "USA-army-001"))

    def test_cancel_transition_clears_unit_and_pending_order_orphan(self) -> None:
        state = self._state()
        state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([self._transition_row()], schema=TRANSITION_SCHEMA),
        )
        state.update_table(
            PENDING_TABLE,
            pl.DataFrame([self._pending_order_row()], schema=PENDING_SCHEMA),
        )

        ReadinessSystem().cancel_transition_for_unit(state, "USA-army-001", "test_cancel")

        self.assertEqual(state.get_table(TRANSITIONS_TABLE).height, 0)
        self.assertEqual(state.get_table(PENDING_TABLE).height, 0)
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["readiness_transition_id"], "")
        self.assertEqual(unit["readiness_eta_minute"], 0)
        self.assertTrue(any(isinstance(event, EventUnitReadinessCanceled) for event in state.events))

        orphan_state = self._state()
        orphan_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame(
                [self._transition_row(unit_id="missing-unit")],
                schema=TRANSITION_SCHEMA,
            ),
        )
        ReadinessSystem().cancel_transition_for_unit(orphan_state, "missing-unit", "orphan")
        self.assertEqual(orphan_state.get_table(TRANSITIONS_TABLE).height, 0)
        self.assertFalse(any(isinstance(event, EventUnitReadinessCanceled) for event in orphan_state.events))

    def test_noop_request_and_contact_cancellation(self) -> None:
        system = ReadinessSystem()
        ready_state = self._state_with_status("ready")
        system._request_transition(
            ready_state,
            system._ensure_units(ready_state.get_table("units")),
            system._ensure_transitions(None),
            ActionSetUnitReadiness("USA", "USA-army-001", "ready"),
            0,
        )
        self.assertEqual(ready_state.get_table("units")["readiness_status"][0], "ready")
        self.assertIsNone(ready_state.tables.get(TRANSITIONS_TABLE))

        contact_state = self._state()
        contact_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([self._transition_row()], schema=TRANSITION_SCHEMA),
        )
        cancel_readiness_for_contact(
            contact_state,
            ["USA-army-001", "", "USA-army-001"],
        )
        self.assertEqual(contact_state.get_table(TRANSITIONS_TABLE).height, 0)
        self.assertEqual(
            sum(isinstance(event, EventUnitReadinessCanceled) for event in contact_state.events),
            1,
        )
        system.cancel_transition_for_unit(contact_state, "USA-army-001", "already_canceled")

    def test_request_transition_rejects_unauthorized_and_duplicate_requests(self) -> None:
        system = ReadinessSystem()
        state = self._state()
        units = system._ensure_units(state.get_table("units"))
        transitions = system._ensure_transitions(None)

        system._request_transition(
            state,
            units,
            transitions,
            ActionSetUnitReadiness("CAN", "USA-army-001", "ready"),
            0,
        )
        self.assertIsNone(state.tables.get(TRANSITIONS_TABLE))

        existing = self._transition_row()
        duplicate_state = self._state()
        duplicate_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([existing], schema=TRANSITION_SCHEMA),
        )
        system._request_transition(
            duplicate_state,
            system._ensure_units(duplicate_state.get_table("units")),
            system._ensure_transitions(duplicate_state.get_table(TRANSITIONS_TABLE)),
            ActionSetUnitReadiness("USA", "USA-army-001", "ready"),
            0,
        )
        self.assertEqual(duplicate_state.get_table(TRANSITIONS_TABLE).to_dicts(), [existing])

    def test_request_transition_replaces_target_and_applies_direct_completion(self) -> None:
        system = ReadinessSystem()
        state = self._state()
        previous = self._transition_row()
        state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([previous], schema=TRANSITION_SCHEMA),
        )
        system._request_transition(
            state,
            system._ensure_units(state.get_table("units")),
            system._ensure_transitions(state.get_table(TRANSITIONS_TABLE)),
            ActionSetUnitReadiness("USA", "USA-army-001", "fortified"),
            0,
        )
        replacement = state.get_table(TRANSITIONS_TABLE).to_dicts()
        self.assertEqual(len(replacement), 1)
        self.assertEqual(replacement[0]["target_status"], "fortified")
        self.assertEqual(replacement[0]["stage"], "parked_to_fortified")
        self.assertTrue(any(isinstance(event, EventUnitReadinessCanceled) for event in state.events))

        direct_state = self._state_with_status("fortified")
        system._request_transition(
            direct_state,
            system._ensure_units(direct_state.get_table("units")),
            system._ensure_transitions(None),
            ActionSetUnitReadiness("USA", "USA-army-001", "ready"),
            12,
        )
        unit = direct_state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["readiness_status"], "ready")
        self.assertEqual(unit["readiness_progress"], 1.0)
        self.assertIsNone(direct_state.tables.get(TRANSITIONS_TABLE))
        self.assertTrue(any(isinstance(event, EventUnitReadinessCompleted) for event in direct_state.events))

    def test_advance_transitions_preserves_orphans_and_starts_fortification_stage(self) -> None:
        system = ReadinessSystem()
        orphan_state = self._state()
        orphan = self._transition_row(unit_id="missing-unit")
        orphan_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([orphan], schema=TRANSITION_SCHEMA),
        )
        system.update(orphan_state, 0)
        self.assertEqual(orphan_state.get_table(TRANSITIONS_TABLE).to_dicts(), [orphan])

        staged_state = self._state()
        staged = self._transition_row(
            target_status="fortified",
            stage="parked_to_fortified",
            started_at=0,
            completes_at=10,
            pending_order_id="order-1",
        )
        staged_state.update_table(
            TRANSITIONS_TABLE,
            pl.DataFrame([staged], schema=TRANSITION_SCHEMA),
        )
        staged_state.time.total_minutes = 10
        system.update(staged_state, 0)

        next_transition = staged_state.get_table(TRANSITIONS_TABLE).to_dicts()[0]
        self.assertEqual(next_transition["stage"], "ready_to_fortified")
        self.assertEqual(next_transition["from_status"], "ready")
        self.assertEqual(next_transition["pending_order_id"], "order-1")
        self.assertEqual(staged_state.get_table("units")["readiness_status"][0], "ready")

    def test_release_pending_order_handles_move_attack_and_unselected_rows(self) -> None:
        system = ReadinessSystem()
        for order_type, expected_type in (
            ("move", ActionMoveUnit),
            ("attack", ActionAttackUnit),
            ("unknown", None),
        ):
            with self.subTest(order_type=order_type):
                state = self._state()
                state.update_table(
                    PENDING_TABLE,
                    pl.DataFrame(
                        [self._pending_order_row(order_type=order_type)],
                        schema=PENDING_SCHEMA,
                    ),
                )
                system._release_pending_order(state, "USA-army-001", "order-1")
                if expected_type is None:
                    self.assertEqual(state.current_actions, [])
                else:
                    self.assertIsInstance(state.current_actions[0], expected_type)
                self.assertEqual(state.get_table(PENDING_TABLE).height, 0)

        missing_state = self._state()
        system._release_pending_order(missing_state, "USA-army-001", "")
        missing_state.update_table(
            PENDING_TABLE,
            pl.DataFrame(
                [self._pending_order_row(status="completed")],
                schema=PENDING_SCHEMA,
            ),
        )
        system._release_pending_order(missing_state, "USA-army-001", "")
        self.assertEqual(missing_state.get_table(PENDING_TABLE).height, 1)


if __name__ == "__main__":
    unittest.main()
