"""Client-side proxy for the authoritative simulation process."""

import multiprocessing as mp
from collections import defaultdict
from typing import Optional

from src.core.map_data import RegionMapData
from src.client.services.client_game_clock import ClientGameClock
from src.shared.actions import GameAction
from src.shared.commands import CommandEnvelope, command_id_for
from src.shared.events import EventSystemError
from src.client.services.snapshot_inbox import SnapshotInbox
from src.shared.state import GameState


class ClientSessionProxy:
    def __init__(
        self,
        map_data: RegionMapData,
        action_queue: mp.Queue,
        state_queue: mp.Queue,
        progress_queue: mp.Queue,
        snapshot_ack_queue: mp.Queue,
        process: mp.Process,
    ) -> None:
        self.map_data = map_data
        self.action_queue = action_queue
        self.state_queue = state_queue
        self.progress_queue = progress_queue
        self.snapshot_ack_queue = snapshot_ack_queue
        self.process = process

        self.state: Optional[GameState] = None
        self.system_errors: list[dict[str, object]] = []
        self._known_system_errors: set[tuple[str, str, int]] = set()
        self._command_sequences: dict[str, int] = defaultdict(int)
        self._snapshot_inbox = SnapshotInbox(state_queue, snapshot_ack_queue)
        self._state_poll_accumulator = 0.0
        self._state_poll_interval = 1.0 / 30.0
        self._display_clock = ClientGameClock()

    def save_map_changes(self) -> None:
        self.action_queue.put("SAVE_MAP_CHANGES")

    def receive_action(self, action: GameAction) -> str:
        actor_id = str(action.player_id)
        self._command_sequences[actor_id] += 1
        sequence = self._command_sequences[actor_id]
        command_id = command_id_for(actor_id, sequence)
        self.action_queue.put(
            CommandEnvelope(
                command_id=command_id,
                actor_id=actor_id,
                sequence=sequence,
                action=action,
            )
        )
        return command_id

    def tick(self, delta_time: float) -> None:
        self._display_clock.advance(delta_time)
        if delta_time > 0.0:
            self._state_poll_accumulator += delta_time
            if self._state_poll_accumulator < self._state_poll_interval:
                return
            self._state_poll_accumulator = min(
                self._state_poll_accumulator - self._state_poll_interval,
                self._state_poll_interval,
            )

        latest = self._snapshot_inbox.take_latest()
        if latest is not None:
            self.state = latest
            self._display_clock.sync(self.state.time)
            self._hydrate_command_sequences()
            self._capture_system_errors()

    def _hydrate_command_sequences(self) -> None:
        if self.state is None:
            return
        for result in self.state.journal.command_results:
            actor = str(result.get("actor_id", ""))
            if actor:
                self._command_sequences[actor] = max(
                    self._command_sequences[actor],
                    int(result.get("sequence", 0)),
                )

    def _capture_system_errors(self) -> None:
        if self.state is None:
            return
        tick = int(self.state.globals.get("tick", 0))
        for event in self.state.events:
            if not isinstance(event, EventSystemError):
                continue
            identity = (event.system_id, event.error_message, tick)
            if identity in self._known_system_errors:
                continue
            self._known_system_errors.add(identity)
            self.system_errors.append(
                {
                    "system_id": event.system_id,
                    "message": event.error_message,
                    "traceback": event.traceback_text,
                    "tick": tick,
                }
            )

    def get_state_snapshot(self) -> Optional[GameState]:
        return self.state

    def get_display_date_text(self) -> str | None:
        return self._display_clock.date_text()

    def get_display_total_minutes(self) -> float | None:
        return self._display_clock.display_minutes

    def shutdown(self) -> None:
        self._snapshot_inbox.close()
        self.action_queue.put("SHUTDOWN")
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.terminate()
            # Termination is asynchronous; reap the process before returning to the UI.
            self.process.join(timeout=2.0)
