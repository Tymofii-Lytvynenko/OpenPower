"""Track one inspected treaty without replaying earlier lifecycle events."""
from src.client.services.journal_cursor import JournalCursor


class TreatyDetailLifecycle:
    def __init__(self, record_id: str, *, proposal: bool, initial_events=()):
        self.record_id = record_id
        self.proposal = proposal
        self._cursor = JournalCursor(initial_events)
        self.message = ""
        self.last_row = None

    def update(self, row, events) -> str:
        if self.message:
            return ""
        # A removed proposal disappears from the snapshot before the notice is
        # acknowledged; retain its last details for the still-open window.
        if row is not None:
            self.last_row = dict(row)
        for event in self._cursor.consume(events):
            payload = event.get("payload") or {}
            if (self.proposal and event.get("event_type") == "EventTreatyLifecycleChanged"
                    and payload.get("proposal_id") == self.record_id
                    and payload.get("transition") == "activated"):
                self.message = "The treaty has been accepted."
                return self.message
        if row is None or (not self.proposal and str(row.get("status") or "active") != "active"):
            self.message = "The treaty is no longer available."
            return self.message
        return ""
