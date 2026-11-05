"""Translate authoritative command outcomes into presentation-only notices."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.services.journal_cursor import JournalCursor


class CommandFeedback:
    def __init__(self, dialog: GenericMessageDialog, initial_records: Iterable[Mapping] = ()):
        self._dialog = dialog
        self._cursor = JournalCursor(initial_records)

    def update(self, records: list[dict], player_id: str, quiet_save_result_ids=()) -> None:
        # Saves contain old outcomes. Replaying them on load would reopen already
        # acknowledged errors; a replaced or truncated journal starts a new cursor.
        fresh = self._cursor.consume(records)
        for record in fresh:
            actor = str(record.get("actor_id") or record.get("player_id") or "")
            if actor != str(player_id):
                continue
            status = str(record.get("status") or "").lower()
            action = str(record.get("action_type") or "")
            title = re.sub(r"(?<!^)(?=[A-Z])", " ", action.removeprefix("Action")) or "Command"
            message = str(record.get("message") or record.get("reason") or "").strip()
            if status in {"rejected", "failed"}:
                if action == "ActionSaveGame" and str(record.get("command_id") or "") in quiet_save_result_ids:
                    continue
                self._dialog.enqueue(title, message or "The command could not be completed.", severity="error")
            elif (status == "executed" and action == "ActionSaveGame"
                  and str(record.get("command_id") or "") not in quiet_save_result_ids):
                # Executed transport records are not proof of domain acceptance.
                # Saving is handled directly by the session and has a final outcome.
                self._dialog.enqueue("Save game", message or "Game saved successfully.")
