from __future__ import annotations

import logging
import time
from queue import Empty
from threading import Event
from typing import Callable

from src.client.interfaces.session_factory import ClientSessionPort, SessionFactory
from src.shared.config import GameConfig
from src.shared.state import GameState


logger = logging.getLogger(__name__)
ProgressCallback = Callable[[float, str], None]


class TaskCancelledError(RuntimeError):
    """Raised when a background client task is cooperatively cancelled."""


def check_cancelled(cancel_event: Event) -> None:
    if cancel_event.is_set():
        raise TaskCancelledError("Operation was cancelled.")


def shutdown_session(session: ClientSessionPort | None) -> None:
    if session is None:
        return
    try:
        session.shutdown()
    except Exception:
        logger.exception("Failed to shut down a client session during cleanup")


def create_session_until_ready(
    session_factory: SessionFactory,
    config: GameConfig,
    *,
    save_name: str | None = None,
    player_tag: str | None = None,
    cancel_event: Event,
    on_progress: ProgressCallback | None = None,
    timeout: float = 120.0,
) -> ClientSessionPort:
    """Create a session and consume boot messages without long blocking waits."""
    session: ClientSessionPort | None = None
    try:
        check_cancelled(cancel_event)
        session = session_factory(config, save_name=save_name, player_tag=player_tag)
        deadline = time.monotonic() + timeout

        while True:
            check_cancelled(cancel_event)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Timed out waiting for the simulation server to become ready.")

            try:
                status, progress, text = session.progress_queue.get(timeout=min(0.1, remaining))
            except Empty:
                continue

            if status == "PROGRESS":
                if on_progress is not None:
                    on_progress(float(progress), str(text))
            elif status == "READY":
                return session
            elif status == "ERROR":
                raise RuntimeError(str(text))

    except Exception:
        shutdown_session(session)
        raise


def wait_for_initial_state(
    session: ClientSessionPort,
    *,
    cancel_event: Event,
    timeout: float = 5.0,
    poll_interval: float = 0.05,
) -> GameState:
    """Pump session IPC while waiting for the first authoritative snapshot."""
    deadline = time.monotonic() + timeout
    while True:
        check_cancelled(cancel_event)
        session.tick(0.0)
        state = session.get_state_snapshot()
        if state is not None:
            return state
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for the initial game state.")
        cancel_event.wait(min(poll_interval, remaining))
