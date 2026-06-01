"""
Client-side IPC proxy for the background simulation process.

This class lives in the main UI thread. It holds the multiprocessing queues
and the process handle, but it knows nothing about how the process was started.
All spawning logic lives in src.server.launcher.spawn_local_server.
"""

import multiprocessing as mp
from typing import Optional

from src.shared.state import GameState
from src.shared.actions import GameAction
from src.core.map_data import RegionMapData


class ClientSessionProxy:
    """
    A proxy object that lives in the main UI thread.

    Responsibilities:
    - Forwarding GameAction objects to the background Simulation Process.
    - Polling the state queue for the latest GameState snapshot.
    - Providing access to the pre-loaded map data for the renderer.
    - Gracefully shutting down the background process on request.

    Construction is intentionally lightweight — all heavy setup (process
    spawning, map loading) is handled by src.server.launcher.spawn_local_server.
    """

    def __init__(
        self,
        map_data: RegionMapData,
        action_queue: mp.Queue,
        state_queue: mp.Queue,
        progress_queue: mp.Queue,
        process: mp.Process,
    ) -> None:
        self.map_data = map_data
        self.action_queue = action_queue
        self.state_queue = state_queue
        self.progress_queue = progress_queue
        self.process = process

        self.state: Optional[GameState] = None
        self.system_errors: list = []
        self._state_poll_accumulator = 0.0
        # Target 30 state updates per second to keep UI smooth without
        # overwhelming the IPC queue with deserialization work.
        self._state_poll_interval = 1.0 / 30.0

    def save_map_changes(self) -> None:
        """Request the server process to persist the current regions data."""
        self.action_queue.put("SAVE_MAP_CHANGES")

    def receive_action(self, action: GameAction) -> None:
        """Sends an action intent to the background simulation process."""
        self.action_queue.put(action)

    def tick(self, delta_time: float) -> None:
        """
        Called by the Window on every frame to drain the latest state snapshot.

        We intentionally drain the entire queue and keep only the most recent
        frame to avoid the UI rendering stale data when the simulation is
        running faster than the UI frame rate.
        """
        if delta_time > 0.0:
            self._state_poll_accumulator += delta_time
            if self._state_poll_accumulator < self._state_poll_interval:
                return
            # Clamp the accumulator to prevent an unbounded backlog of skipped
            # polls from firing all at once after a hitch.
            self._state_poll_accumulator = min(
                self._state_poll_accumulator - self._state_poll_interval,
                self._state_poll_interval,
            )

        try:
            latest_ipc = None
            while not self.state_queue.empty():
                latest_ipc = self.state_queue.get_nowait()

            if latest_ipc:
                self.state = GameState.from_ipc(latest_ipc)
                
                # Check for EventSystemError telemetry
                from src.shared.events import EventSystemError
                for event in self.state.events:
                    if isinstance(event, EventSystemError):
                        self.system_errors.append({
                            "system_id": event.system_id,
                            "message": event.error_message,
                            "traceback": event.traceback_text,
                        })
        except Exception as e:
            # Draining get_nowait raises queue.Empty, which is expected.
            # Other exceptions should be printed for developer visibility.
            import queue
            if not isinstance(e, queue.Empty):
                print(f"[ClientSessionProxy] IPC tick error: {e}")

    def get_state_snapshot(self) -> Optional[GameState]:
        """Returns the most recently received game state, or None if not ready."""
        return self.state

    def shutdown(self) -> None:
        """Requests a graceful shutdown and waits briefly before force-terminating."""
        self.action_queue.put("SHUTDOWN")
        self.process.join(timeout=2.0)
        if self.process.is_alive():
            self.process.terminate()
