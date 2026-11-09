from unittest.mock import Mock

import polars as pl

from modules.base.systems.military.attack_order_service import MilitaryAttackOrderService
from src.shared.actions import ActionAttackUnit
from src.shared.state import GameState


def _service(readiness, workflow):
    return MilitaryAttackOrderService(
        readiness_preparer=readiness,
        unit_movement=Mock(),
        hostility_policy=lambda _wars: {frozenset(("USA", "CAN"))},
        unit_order_workflow=workflow,
        units_from_rows=pl.DataFrame,
    )


def test_noncombatant_targets_and_missing_hostile_units_are_rejected():
    service = _service(Mock(), Mock())
    hostilities = {frozenset(("USA", "CAN"))}

    assert not service._is_valid_target_pair(
        {"id": "USA-1", "owner": "USA", "strength": 0},
        {"id": "CAN-1", "owner": "CAN", "strength": 100},
        hostilities,
    )
    assert not service._is_valid_target_pair(
        {"id": "USA-1", "owner": "USA", "strength": 100},
        {"id": "CAN-1", "owner": "CAN", "strength": 0},
        hostilities,
    )
    assert not service._are_hostile(
        None,
        {"id": "CAN-1", "owner": "CAN", "strength": 100},
        hostilities,
    )


def test_unready_attacker_is_queued_without_changing_the_unit_frame():
    readiness = Mock()
    readiness.prepare_order.return_value = False
    workflow = Mock()
    workflow.release_fortified_for_order.return_value = False
    service = _service(readiness, workflow)
    state = GameState()
    state.current_actions = [ActionAttackUnit("USA", "USA-1", "CAN-1")]
    units = pl.DataFrame(
        [
            {"id": "USA-1", "owner": "USA", "strength": 100},
            {"id": "CAN-1", "owner": "CAN", "strength": 100},
        ]
    )

    result = service.process(state, units)

    assert result is units
    readiness.prepare_order.assert_called_once_with(state, "USA-1")
    workflow.queue_attack.assert_called_once_with(state, state.current_actions[0])
