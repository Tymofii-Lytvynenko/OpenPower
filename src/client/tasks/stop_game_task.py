from __future__ import annotations

from threading import Event, Lock

from src.client.tasks.session_startup import (
    check_cancelled,
    create_session_until_ready,
    shutdown_session,
    wait_for_initial_state,
)
from src.shared.config import GameConfig


class StopGameTask:
    """Stop a campaign and prepare the clean session used by the main menu."""

    def __init__(self, window, config: GameConfig) -> None:
        self.window = window
        self.config = config
        self.progress = 0.0
        self.status_text = "Stopping current game..."
        self._cancel_event = Event()
        self._finished = Event()
        self._lifecycle_lock = Lock()
        self._session_lock = Lock()
        self._session = None
        self._session_released = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lifecycle_lock:
            finished = self._finished.is_set()
        if finished:
            self._release_session()

    def _release_session(self) -> None:
        with self._session_lock:
            if self._session_released:
                return
            self._session_released = True
            session, self._session = self._session, None
        shutdown_session(session)

    def run(self):
        session = None
        try:
            check_cancelled(self._cancel_event)
            previous_session = getattr(self.window, "session", None)
            if previous_session is not None:
                previous_session.shutdown()
                if getattr(self.window, "session", None) is previous_session:
                    self.window.session = None

            self.status_text = "Starting a clean world session..."
            self.progress = 0.2
            session = create_session_until_ready(
                self.window.session_factory,
                self.config,
                cancel_event=self._cancel_event,
                on_progress=self._report_progress,
            )
            self._session = session

            self.status_text = "Synchronizing the main menu world..."
            self.progress = 0.9
            wait_for_initial_state(session, cancel_event=self._cancel_event)
            self.status_text = "Ready."
            self.progress = 1.0
            return session
        except Exception:
            if session is not None:
                self._release_session()
            raise
        finally:
            with self._lifecycle_lock:
                self._finished.set()
                cancelled_after_work = self._cancel_event.is_set()
            if cancelled_after_work:
                self._release_session()

    def _report_progress(self, progress: float, text: str) -> None:
        self.progress = 0.2 + max(0.0, min(1.0, float(progress))) * 0.65
        self.status_text = f"Server: {text}"
