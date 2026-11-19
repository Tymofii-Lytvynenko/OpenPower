from __future__ import annotations

from threading import Event, Lock

from src.client.tasks.session_startup import (
    create_session_until_ready,
    shutdown_session,
    wait_for_initial_state,
)
from src.shared.config import GameConfig


class LoadGameTask:
    """Starts a saved session and waits for its first authoritative snapshot."""

    def __init__(self, window, config: GameConfig, save_name: str) -> None:
        self.window = window
        self.config = config
        self.save_name = save_name
        self.progress = 0.0
        self.status_text = "Preparing to load..."
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
            self.status_text = f"Initializing load for {self.save_name}..."
            self.progress = 0.2

            def update_progress(progress: float, text: str) -> None:
                self.progress = 0.2 + progress * 0.6
                self.status_text = f"Server: {text}"

            session = create_session_until_ready(
                self.window.session_factory,
                self.config,
                save_name=self.save_name,
                cancel_event=self._cancel_event,
                on_progress=update_progress,
            )
            self._session = session
            self.status_text = "Synchronizing game state..."
            self.progress = 0.9
            state = wait_for_initial_state(session, cancel_event=self._cancel_event)
            player_tag = str(state.globals.get("player_tag") or "").strip().upper()
            countries = state.tables.get("countries")
            if (not player_tag or countries is None or "id" not in countries.columns
                    or player_tag not in {str(value or "").strip().upper() for value in countries["id"].to_list()}):
                # Loading as a default country would silently change the player's identity.
                raise ValueError("The save does not contain a valid player country.")
            self.progress = 1.0
            self.status_text = "Ready."
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
