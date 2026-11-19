"""Client-side proxy for the authoritative simulation process."""

import multiprocessing as mp
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional

from src.client.client_state import ClientGameStateView, ClientPresentationState
from src.client.services.client_game_clock import ClientGameClock
from src.client.services.snapshot_inbox import SnapshotInbox
from src.client.services.telemetry_service import TelemetryService
from src.core.map_data import RegionMapData
from src.shared.actions import GameAction
from src.shared.commands import COMMAND_PROTOCOL_ERROR, CommandEnvelope, command_id_for
from src.shared.events import EventSystemError
from src.shared.state import GameState, TimeData


@dataclass(frozen=True, slots=True)
class _PreparedClientSnapshot:
    view: ClientGameStateView
    time: TimeData
    sequences: dict[str, int]


class ClientSessionProxy:
    def __init__(
        self,
        map_data: RegionMapData,
        action_queue: mp.Queue,
        state_queue: mp.Queue,
        progress_queue: mp.Queue,
        snapshot_ack_queue: mp.Queue,
        process: mp.Process,
        telemetry_queue=None,
        telemetry_output_dir: Path | None = None,
        client_presentation=None,
    ) -> None:
        self.map_data = map_data
        self.action_queue = action_queue
        self.state_queue = state_queue
        self.progress_queue = progress_queue
        self.snapshot_ack_queue = snapshot_ack_queue
        self._ipc_queues = (action_queue, state_queue, progress_queue, snapshot_ack_queue, telemetry_queue)
        self.process = process
        self._shutdown_lock = Lock()
        self._shutdown_started = False

        self._client_presentation = client_presentation or {}
        self.presentation_state = ClientPresentationState()
        self.state: Optional[ClientGameStateView] = None
        self.system_errors: list[dict[str, object]] = []
        self._known_system_errors: set[tuple[str, str, int]] = set()
        self._process_exit_reported = False
        self._command_sequences: dict[str, int] = defaultdict(int)
        self.telemetry = TelemetryService(action_queue, telemetry_queue, telemetry_output_dir or Path("user_data/telemetry"), process)
        self._prepared_journal = None
        self._prepared_sequences: dict[str, int] = {}
        self._snapshot_inbox = SnapshotInbox(
            state_queue, snapshot_ack_queue, self.telemetry.collector,
            prepare=self._prepare_snapshot,
        )
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
        try:
            self.telemetry.refresh()
        except Exception:
            self.telemetry.collector._log_failure()
        exit_code = getattr(self.process, "exitcode", None)
        if isinstance(exit_code, int):
            if self.state is not None and not self._process_exit_reported:
                self._process_exit_reported = True
                self.system_errors.append({
                    "system_id": "server",
                    "message": f"The simulation process stopped (exit code {exit_code}). Load a save to continue.",
                    "traceback": "",
                    "tick": int(self.state.globals.get("tick", 0)),
                })
        else:
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
            if self.telemetry.collector.enabled:
                with self.telemetry.collector.measure("ipc.snapshot.apply_ms"):
                    self._apply_snapshot(latest)
            else:
                self._apply_snapshot(latest)

    def _prepare_snapshot(self, state: GameState, is_delta: bool = False) -> _PreparedClientSnapshot:
        previous = self._prepared_journal if is_delta else None
        view = ClientGameStateView(
            state, self._client_presentation, self.presentation_state,
            _previous_journal=previous,
        )
        reuse_commands = (
            previous is not None
            and len(state.journal.command_results) >= len(previous.command_results)
        )
        sequences = dict(self._prepared_sequences) if reuse_commands else {}
        start = len(previous.command_results) if reuse_commands else 0
        for result in view.journal.command_results[start:]:
            if result.get("code") == COMMAND_PROTOCOL_ERROR:
                continue
            actor = str(result.get("actor_id", ""))
            if actor:
                sequences[actor] = max(sequences.get(actor, 0), int(result.get("sequence", 0)))
        self._prepared_journal = view.journal
        self._prepared_sequences = sequences
        return _PreparedClientSnapshot(view, state.time, sequences)

    def _apply_snapshot(self, latest: _PreparedClientSnapshot) -> None:
        self.state = latest.view
        self._display_clock.sync(latest.time)
        self._hydrate_command_sequences(latest.sequences)
        self._capture_system_errors()

    def _hydrate_command_sequences(self, sequences: dict[str, int] | None = None) -> None:
        if self.state is None:
            return
        if sequences is None:
            sequences = {}
            for result in self.state.journal.command_results:
                if result.get("code") == COMMAND_PROTOCOL_ERROR:
                    continue
                actor = str(result.get("actor_id", ""))
                if actor:
                    sequences[actor] = max(sequences.get(actor, 0), int(result.get("sequence", 0)))
        for actor, sequence in sequences.items():
            self._command_sequences[actor] = max(self._command_sequences[actor], sequence)

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

    def get_state_snapshot(self) -> Optional[ClientGameStateView]:
        return self.state

    def get_display_date_text(self) -> str | None:
        return self._display_clock.date_text()

    def get_display_total_minutes(self) -> float | None:
        return self._display_clock.display_minutes

    def shutdown(self) -> None:
        with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
        self._snapshot_inbox.close()
        self.telemetry.close()
        if self.process.is_alive():
            self.action_queue.put("SHUTDOWN")
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.terminate()
            # Termination is asynchronous; reap the process before returning to the UI.
            self.process.join(timeout=2.0)
        for channel in self._ipc_queues:
            # A stopped peer cannot drain pending writes from a queue feeder.
            cancel_join = getattr(channel, "cancel_join_thread", None)
            if callable(cancel_join):
                cancel_join()
            close = getattr(channel, "close", None)
            if callable(close):
                close()
