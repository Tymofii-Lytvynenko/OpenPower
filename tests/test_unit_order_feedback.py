from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.components.shared.unit_order_feedback import UnitOrderFeedback


def feedback(record_id, **fields):
    return {
        "id": record_id,
        "unit_id": record_id.split("-")[0],
        "owner_country_id": "USA",
        "order_type": "move",
        "status": "rejected",
        "reason": "No legal route is available.",
        "created_at_minute": 20,
        **fields,
    }


def test_existing_refusals_are_not_replayed_when_ui_mounts():
    dialog = GenericMessageDialog()
    old = feedback("u1-20-1")
    presenter = UnitOrderFeedback(dialog, [old])

    presenter.update([old], "USA")

    assert not dialog.is_open


def test_missing_order_history_does_not_open_a_refusal_notice():
    dialog = GenericMessageDialog()
    presenter = UnitOrderFeedback(dialog)

    presenter.update(None, "USA")

    assert not dialog.is_open


def test_new_local_movement_refusals_are_aggregated_by_reason_across_order_types():
    dialog = GenericMessageDialog()
    presenter = UnitOrderFeedback(dialog)
    rows = [
        feedback("u1-20-1"),
        feedback("u2-21-2", order_type="naval_invasion", created_at_minute=21),
        feedback("u3-20-3", owner_country_id="CAN"),
        feedback("u4-20-4", status="accepted"),
        feedback("u5-20-5", order_type="deployment"),
        feedback("u6-22-6", reason="The unit is unavailable.", created_at_minute=22),
    ]

    presenter.update(rows, "USA")

    assert dialog._content.title == "Movement refused"
    assert dialog._content.message == "2 units could not move. No legal route is available."
    assert len(dialog._pending) == 1
    assert dialog._pending[0][0].message == "1 unit could not move. The unit is unavailable."
    presenter.update(rows, "USA")
    assert len(dialog._pending) == 1


def test_naval_invasion_refusal_uses_the_shared_movement_notice():
    dialog = GenericMessageDialog()
    presenter = UnitOrderFeedback(dialog)

    presenter.update([feedback(
        "u1-20-1", order_type="naval_invasion", reason="No eligible landing is available."
    )], "USA")

    assert dialog._content.title == "Movement refused"
    assert dialog._content.message == "1 unit could not move. No eligible landing is available."
