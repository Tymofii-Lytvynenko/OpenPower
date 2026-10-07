from __future__ import annotations

from queue import Empty, Queue
from threading import Event
from unittest.mock import Mock

import pytest

from src.client.tasks.session_startup import (
    TaskCancelledError,
    create_session_until_ready,
    wait_for_initial_state,
)


class FakeSession:
    def __init__(self, messages=()):
        self.progress_queue = Queue()
        for message in messages:
            self.progress_queue.put(message)
        self.state = None
        self.tick = Mock()
        self.shutdown = Mock()

    def receive_action(self, action):
        raise NotImplementedError

    def get_state_snapshot(self):
        return self.state

    def save_map_changes(self):
        pass


def test_session_startup_reports_progress_and_returns_on_ready() -> None:
    session = FakeSession([
        ("PROGRESS", 0.4, "Loading world"),
        ("READY", 1.0, "Ready"),
    ])
    progress = Mock()

    result = create_session_until_ready(
        lambda config, **kwargs: session,
        object(),
        cancel_event=Event(),
        on_progress=progress,
    )

    assert result is session
    progress.assert_called_once_with(0.4, "Loading world")
    session.shutdown.assert_not_called()


@pytest.mark.parametrize("failure", ["server error", "timeout"])
def test_session_startup_cleans_child_on_server_error_or_timeout(failure: str) -> None:
    messages = [("ERROR", 0.0, "server error")] if failure == "server error" else []
    session = FakeSession(messages)

    with pytest.raises(RuntimeError if failure == "server error" else TimeoutError):
        create_session_until_ready(
            lambda config, **kwargs: session,
            object(),
            cancel_event=Event(),
            timeout=0.01,
        )

    session.shutdown.assert_called_once_with()


def test_session_startup_cleans_child_when_cancelled_during_queue_poll() -> None:
    cancellation = Event()
    session = FakeSession()

    def cancel_after_poll(timeout):
        cancellation.set()
        raise Empty

    session.progress_queue.get = cancel_after_poll
    with pytest.raises(TaskCancelledError):
        create_session_until_ready(
            lambda config, **kwargs: session,
            object(),
            cancel_event=cancellation,
        )

    session.shutdown.assert_called_once_with()


def test_initial_state_wait_is_cancellable_and_times_out() -> None:
    session = FakeSession()
    cancellation = Event()
    session.tick.side_effect = lambda delta_time: cancellation.set()

    with pytest.raises(TaskCancelledError):
        wait_for_initial_state(
            session,
            cancel_event=cancellation,
            timeout=1.0,
        )

    session.tick.assert_called_once_with(0.0)

    session.tick.reset_mock(side_effect=True)
    with pytest.raises(TimeoutError):
        wait_for_initial_state(session, cancel_event=Event(), timeout=0.01, poll_interval=0.001)
