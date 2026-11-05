from src.client.ui.components.shared.command_feedback import CommandFeedback
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog


def result(status="rejected", **fields):
    return dict(actor_id="local", action_type="ActionMoveUnit", status=status,
                message="Movement refused.", **fields)


def test_new_local_failure_is_delivered_once():
    dialog = GenericMessageDialog()
    feedback = CommandFeedback(dialog)
    records = [result()]
    feedback.update(records, "local")
    assert dialog._content.message == "Movement refused."
    dialog.acknowledge()
    feedback.update(records, "local")
    assert not dialog.is_open


def test_history_other_players_and_transport_execution_do_not_raise_notices():
    dialog = GenericMessageDialog()
    records = [result()]
    feedback = CommandFeedback(dialog, records)
    records += [dict(result(), actor_id="other"), result("executed")]
    feedback.update(records, "local")
    assert not dialog.is_open


def test_domain_refusal_is_not_hidden_by_transport_success():
    dialog = GenericMessageDialog()
    feedback = CommandFeedback(dialog)
    records = [dict(player_id="local", action_type="ActionCreateUnitDesign",
                    status="rejected", reason="A name is required."),
               result("executed")]
    feedback.update(records, "local")
    assert dialog._content.message == "A name is required."


def test_save_success_and_multiple_failures_are_queued_in_order():
    dialog = GenericMessageDialog()
    feedback = CommandFeedback(dialog)
    records = [dict(result("executed"), action_type="ActionSaveGame", message=""),
               result(), dict(result(), message="Design refused.")]
    feedback.update(records, "local")
    assert dialog._content.message == "Game saved successfully."
    dialog.acknowledge()
    assert dialog._content.message == "Movement refused."
    dialog.acknowledge()
    assert dialog._content.message == "Design refused."
    dialog.acknowledge()
    assert not dialog.is_open


def test_replaced_or_truncated_history_is_not_replayed():
    dialog = GenericMessageDialog()
    feedback = CommandFeedback(dialog, [result(), result()])
    feedback.update([dict(result(), message="Old save failure.")], "local")
    assert not dialog.is_open


def test_queued_callbacks_keep_their_own_callers():
    dialog = GenericMessageDialog()
    calls = []
    dialog.enqueue("One", "First", on_acknowledge=lambda: calls.append(1))
    dialog.enqueue("Two", "Second", on_acknowledge=lambda: calls.append(2))
    dialog.acknowledge()
    assert calls == [1]
    dialog.acknowledge()
    assert calls == [1, 2]


def test_callback_opening_another_dialog_does_not_discard_pending_notice():
    dialog = GenericMessageDialog()
    dialog.enqueue("One", "First", on_acknowledge=lambda: dialog.show("Follow-up", "Callback"))
    dialog.enqueue("Two", "Pending")
    dialog.acknowledge()
    assert dialog._content.message == "Callback"
    dialog.acknowledge()
    assert dialog._content.message == "Pending"
