from unittest.mock import Mock

import polars as pl

from modules.base.systems.military.unit_order_workflow import (
    UNIT_PENDING_ORDER_SCHEMA,
    UnitOrderFeedbackEntry,
    UnitOrderWorkflowService,
)
from src.shared.actions import ActionAttackUnit
from src.shared.state import GameState


def test_record_feedback_entry_copies_the_entry_into_rows():
    workflow = UnitOrderWorkflowService(Mock())
    rows = []
    entry = UnitOrderFeedbackEntry(
        unit_id="unit-1",
        owner="USA",
        order_type="move",
        status="rejected",
        reason="Invalid target",
        current_minute=42,
    )

    workflow.record_feedback_entry(rows, entry)

    assert rows == [
        {
            "id": "unit-1-42-1",
            "unit_id": "unit-1",
            "owner_country_id": "USA",
            "order_type": "move",
            "status": "rejected",
            "reason": "Invalid target",
            "created_at_minute": 42,
        }
    ]


def test_release_fortified_for_order_preserves_units_with_pending_transitions():
    readiness = Mock()
    workflow = UnitOrderWorkflowService(readiness)
    state = GameState(
        tables={
            "unit_readiness_transitions": pl.DataFrame({"unit_id": ["unit-1"]})
        }
    )
    unit = {"id": "unit-1", "readiness_status": " FORTIFIED "}

    assert workflow.release_fortified_for_order(state, unit) is False

    assert unit["readiness_status"] == " FORTIFIED "
    readiness.prepare_order.assert_not_called()


def test_release_fortified_for_order_keeps_state_when_preparation_fails():
    readiness = Mock()
    readiness.prepare_order.return_value = False
    workflow = UnitOrderWorkflowService(readiness)
    unit = {
        "id": "unit-1",
        "readiness_status": "fortified",
        "readiness_progress": 0.8,
        "readiness_transition_id": "transition-1",
        "readiness_eta_minute": 55,
    }
    state = GameState()

    assert workflow.release_fortified_for_order(state, unit) is False

    assert unit == {
        "id": "unit-1",
        "readiness_status": "fortified",
        "readiness_progress": 0.8,
        "readiness_transition_id": "transition-1",
        "readiness_eta_minute": 55,
    }
    readiness.prepare_order.assert_called_once_with(state, "unit-1")


def test_release_fortified_for_order_resets_readiness_after_preparation():
    readiness = Mock()
    readiness.prepare_order.return_value = True
    workflow = UnitOrderWorkflowService(readiness)
    unit = {
        "id": "unit-1",
        "readiness_status": "FORTIFIED",
        "readiness_progress": 0.8,
        "readiness_transition_id": "transition-1",
        "readiness_eta_minute": 55,
    }
    state = GameState()

    assert workflow.release_fortified_for_order(state, unit) is True

    assert unit == {
        "id": "unit-1",
        "readiness_status": "ready",
        "readiness_progress": 0.0,
        "readiness_transition_id": "",
        "readiness_eta_minute": 0,
    }
    readiness.prepare_order.assert_called_once_with(state, "unit-1")


def test_queue_attack_replaces_the_attacker_order_and_preserves_other_units():
    workflow = UnitOrderWorkflowService(Mock())
    state = GameState()
    state.time.total_minutes = 42
    state.update_table(
        "unit_pending_orders",
        pl.DataFrame(
            [
                {
                    "id": "old-order",
                    "unit_id": "attacker",
                    "player_id": "player",
                    "order_type": "move",
                    "target_region_id": 3,
                    "target_latitude": 1.0,
                    "target_longitude": 2.0,
                    "target_unit_id": "",
                    "via_region_ids": [2],
                    "created_at_minute": 10,
                    "status": "queued",
                },
                {
                    "id": "other-order",
                    "unit_id": "other-unit",
                    "player_id": "player",
                    "order_type": "move",
                    "target_region_id": 4,
                    "target_latitude": 3.0,
                    "target_longitude": 4.0,
                    "target_unit_id": "",
                    "via_region_ids": [],
                    "created_at_minute": 11,
                    "status": "queued",
                },
            ],
            schema=UNIT_PENDING_ORDER_SCHEMA,
        ),
    )

    order_id = workflow.queue_attack(
        state,
        ActionAttackUnit("player", "attacker", "defender"),
    )

    assert order_id == "pending-attacker-attack-42"
    orders = state.get_table("unit_pending_orders").to_dicts()
    assert [row["unit_id"] for row in orders] == ["other-unit", "attacker"]
    assert orders[-1] == {
        "id": order_id,
        "unit_id": "attacker",
        "player_id": "player",
        "order_type": "attack",
        "target_region_id": 0,
        "target_latitude": 0.0,
        "target_longitude": 0.0,
        "target_unit_id": "defender",
        "via_region_ids": [],
        "created_at_minute": 42,
        "status": "queued",
    }


def test_ensure_pending_table_backfills_missing_columns_with_schema_defaults():
    workflow = UnitOrderWorkflowService(Mock())

    pending = workflow.ensure_pending_table(pl.DataFrame({"id": ["legacy"]}))

    assert pending.columns == list(UNIT_PENDING_ORDER_SCHEMA)
    assert pending.item(0, "id") == "legacy"
    assert pending.item(0, "target_region_id") == 0
    assert pending.item(0, "target_latitude") == 0.0
    assert pending.get_column("via_region_ids").to_list() == [[]]


def test_attach_pending_to_transition_updates_only_the_matching_unit():
    workflow = UnitOrderWorkflowService(Mock())
    state = GameState(
        tables={
            "unit_readiness_transitions": pl.DataFrame(
                {
                    "unit_id": ["unit-1", "unit-2"],
                    "pending_order_id": ["", "existing-order"],
                }
            )
        }
    )

    workflow.attach_pending_to_transition(state, "unit-1", "pending-order")

    assert state.get_table("unit_readiness_transitions").to_dicts() == [
        {"unit_id": "unit-1", "pending_order_id": "pending-order"},
        {"unit_id": "unit-2", "pending_order_id": "existing-order"},
    ]
