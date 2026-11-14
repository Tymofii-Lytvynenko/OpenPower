"""Receive and decode simulation snapshots without blocking the render loop."""

from collections.abc import Callable
from queue import Empty, Full
from threading import Event, Lock, Thread
from typing import Any

from src.shared.snapshots import SnapshotProtocolError, StateSnapshotDecoder
from src.shared.state import GameState


class SnapshotInbox:
    """Publish decoded states; preparation may reuse the preceding append-only journal.

    The preparation callback receives a true continuity flag only after a
    successful prior preparation and successful decoding of the current delta.
    """

    def __init__(
        self, state_queue, acknowledgement_queue, telemetry=None, *,
        prepare: Callable[[GameState, bool], Any] | None = None,
    ):
        self._telemetry = telemetry
        self._queue = state_queue
        self._acknowledgements = acknowledgement_queue
        self._decoder = StateSnapshotDecoder()
        self._prepare = prepare if prepare is not None else (lambda state, _is_delta: state)
        self._lock = Lock()
        self._latest: Any | None = None
        self._stop = Event()
        self._prepared_continuity = False
        self._thread = Thread(target=self._receive, name="simulation-snapshots", daemon=True)
        self._thread.start()

    def take_latest(self) -> Any | None:
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
                self._prepared_continuity = False
                print(f"[SnapshotInbox] Snapshot protocol error: {exc}")
                continue
            is_delta = (
                self._prepared_continuity
                and isinstance(packet, dict)
                and packet.get("kind") == "delta"
            )
            try:
                # Building a read-only client snapshot can traverse a large journal;
                # keep this work off the render thread and acknowledge only after success.
                if self._telemetry and self._telemetry.enabled:
                    with self._telemetry.measure("ipc.snapshot.prepare_ms"):
                        prepared = self._prepare(state, is_delta)
                else:
                    prepared = self._prepare(state, is_delta)
            except Exception as exc:
                self._prepared_continuity = False
                print(f"[SnapshotInbox] Snapshot preparation error: {exc}")
                continue
            self._prepared_continuity = True
            if self._telemetry and self._telemetry.enabled:
                with self._telemetry.measure("ipc.snapshot.publish_ms"):
                    with self._lock:
                        self._latest = prepared
            else:
                with self._lock:
                    self._latest = prepared
            try:
                self._acknowledgements.put_nowait(self._decoder.sequence)
            except Full:
                pass
