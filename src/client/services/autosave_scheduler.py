"""Schedule REFERENCE-style real-time autosaves through the authoritative command path."""

from __future__ import annotations

import time

from src.shared.actions import ActionSaveGame


class AutosaveScheduler:
    def __init__(self, settings_service, client, *, clock=time.monotonic):
        self._settings_service = settings_service
        self._client = client
        self._clock = clock
        self._last_completed = clock()
        self._pending_id = None

    def update(self, records, *, game_over: bool = False) -> set[str]:
        now = self._clock()
        quiet_save_results = set()
        if self._pending_id:
            quiet_save_results.add(self._pending_id)
            if any(str(record.get("command_id") or "") == self._pending_id for record in records):
                self._pending_id = None
                self._last_completed = now

        settings = getattr(self._settings_service, "settings", None)
        enabled = bool(settings and settings.autosave_enabled and not game_over)
        if not enabled or self._pending_id or now - self._last_completed < settings.autosave_interval_minutes * 60:
            return quiet_save_results

        name = settings.autosave_name
        if settings.autosave_incremental:
            name += f"{settings.autosave_counter:04d}"
        command_id = self._client.send_action(ActionSaveGame(self._client.player_id, name))
        if command_id:
            self._pending_id = str(command_id)
            quiet_save_results.add(self._pending_id)
            if settings.autosave_incremental:
                self._settings_service.set_autosave_counter(settings.autosave_counter + 1)
        else:
            # Avoid issuing a save every frame if a client cannot provide a
            # command identity for tracking the asynchronous completion.
            self._last_completed = now
        return quiet_save_results
