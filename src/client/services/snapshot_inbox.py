"""Receive and decode simulation snapshots without blocking the render loop."""

from queue import Empty, Full
from threading import Event, Lock, Thread

from src.shared.snapshots import SnapshotProtocolError, StateSnapshotDecoder
from src.shared.state import GameState


class SnapshotInbox:
    def __init__(self, state_queue, acknowledgement_queue, telemetry=None):
        self._telemetry = telemetry
        self._queue = state_queue
        self._acknowledgements = acknowledgement_queue
        self._decoder = StateSnapshotDecoder()
        self._lock = Lock()
        self._latest: GameState | None = None
        self._stop = Event()
        self._thread = Thread(target=self._receive, name="simulation-snapshots", daemon=True)
        self._thread.start()

    def take_latest(self) -> GameState | None:
        with self._lock:
            latest, self._latest = self._latest, None
        return latest

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _receive(self) -> None:
        while not self._stop.is_set():
            try:
                packet = self._queue.get(timeout=0.1)
            except Empty:
                continue
            except (EOFError, OSError, ValueError):
                return
            try:
                if self._telemetry and self._telemetry.enabled:
                    with self._telemetry.measure("ipc.snapshot.decode_ms"):
                        state = self._decoder.decode(packet)
                    self._telemetry.increment("ipc.snapshots.received")
                else:
                    state = self._decoder.decode(packet)
            except SnapshotProtocolError as exc:
                print(f"[SnapshotInbox] Snapshot protocol error: {exc}")
                continue
            if self._telemetry and self._telemetry.enabled:
                with self._telemetry.measure("ipc.snapshot.publish_ms"):
                    with self._lock:
                        self._latest = state
            else:
                with self._lock:
                    self._latest = state
            try:
                self._acknowledgements.put_nowait(self._decoder.sequence)
            except Full:
                pass
