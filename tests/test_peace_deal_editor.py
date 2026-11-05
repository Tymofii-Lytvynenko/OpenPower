from types import SimpleNamespace

from src.client.services.journal_cursor import JournalCursor
from src.client.ui.panels.military.peace_deal_editor import PeaceDealEditor
from src.shared.events import JournalState


def test_submission_feedback_retains_rejected_draft_and_clears_applied_draft():
    journal = JournalState()
    state = SimpleNamespace(journal=journal)
    editor = PeaceDealEditor()
    editor._journal_cursor = JournalCursor(journal.command_results)
    editor._pending_submission = ("war-1", "USA", "player-1")
    clause = {"type": "white_peace"}
    editor._offered = [clause]
    editor._requested = []

    journal.append_command_result(
        {
            "action_type": "ActionSubmitPeaceDeal",
            "actor_id": "player-1",
            "status": "executed",
            "war_id": "war-1",
            "country_id": "USA",
        }
    )
    editor._consume_submission_results(state)

    assert editor._pending_submission == ("war-1", "USA", "player-1")
    assert editor._offered == [clause]

    journal.append_command_result(
        {
            "action_type": "ActionSubmitPeaceDeal",
            "actor_id": "player-1",
            "status": "rejected",
            "reason": "The war is no longer active.",
            "war_id": "war-1",
            "country_id": "USA",
        }
    )
    editor._consume_submission_results(state)

    assert editor._pending_submission is None
    assert editor._offered == [clause]
    assert editor._requested == []
    assert editor._submission_feedback == "The war is no longer active."
    assert editor._submission_rejected is True

    editor._pending_submission = ("war-1", "USA", "player-1")
    journal.append_command_result(
        {
            "action_type": "ActionSubmitPeaceDeal",
            "actor_id": "player-1",
            "status": "applied",
            "reason": "Peace package submitted.",
            "war_id": "war-1",
            "country_id": "USA",
            "deal_id": "peace-1",
        }
    )
    editor._consume_submission_results(state)

    assert editor._pending_submission is None
    assert editor._offered == []
    assert editor._requested == []
    assert editor._submission_feedback == "Peace package submitted."
    assert editor._submission_rejected is False


def test_failed_transport_result_releases_pending_editor_and_preserves_draft():
    journal = JournalState()
    state = SimpleNamespace(journal=journal)
    editor = PeaceDealEditor()
    editor._journal_cursor = JournalCursor(journal.command_results)
    editor._pending_submission = ("war-1", "USA", "player-1")
    clause = {"type": "white_peace"}
    editor._offered = [clause]

    journal.append_command_result(
        {
            "action_type": "ActionSubmitPeaceDeal",
            "actor_id": "player-1",
            "status": "failed",
            "message": "The simulation step failed.",
        }
    )
    editor._consume_submission_results(state)

    assert editor._pending_submission is None
    assert editor._offered == [clause]
    assert editor._submission_feedback == "The simulation step failed."
    assert editor._submission_rejected is True
