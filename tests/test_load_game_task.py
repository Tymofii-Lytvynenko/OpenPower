from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.client.tasks.load_game_task import LoadGameTask


def _task(current_session=None):
    factory = Mock()
    window = SimpleNamespace(session_factory=factory, session=current_session)
    config = object()
    return LoadGameTask(window, config, "autosave-1"), factory, config


def test_load_game_uses_injected_factory_with_save_name() -> None:
    task, factory, config = _task()
    session = SimpleNamespace(shutdown=Mock())

    with (
        patch("src.client.tasks.load_game_task.create_session_until_ready", return_value=session) as start_session,
        patch("src.client.tasks.load_game_task.wait_for_initial_state"),
    ):
        assert task.run() is session

    start_session.assert_called_once()
    assert start_session.call_args.args == (factory, config)
    assert start_session.call_args.kwargs["save_name"] == "autosave-1"
    session.shutdown.assert_not_called()


def test_load_game_cleans_new_session_when_initial_state_times_out() -> None:
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock())

    with (
        patch("src.client.tasks.load_game_task.create_session_until_ready", return_value=session),
        patch(
            "src.client.tasks.load_game_task.wait_for_initial_state",
            side_effect=TimeoutError("snapshot timeout"),
        ),
        pytest.raises(TimeoutError, match="snapshot timeout"),
    ):
        task.run()

    session.shutdown.assert_called_once_with()


def test_load_game_stops_previous_session_before_creating_replacement() -> None:
    previous = SimpleNamespace(shutdown=Mock())
    task, _, _ = _task(previous)
    new_session = SimpleNamespace(shutdown=Mock())
    calls = []

    def create(*args, **kwargs):
        calls.append("create")
        return new_session

    with (
        patch("src.client.tasks.load_game_task.create_session_until_ready", side_effect=create),
        patch("src.client.tasks.load_game_task.wait_for_initial_state"),
    ):
        task.run()

    previous.shutdown.assert_called_once_with()
    assert calls == ["create"]


def test_load_game_cancellation_after_completion_releases_unclaimed_session() -> None:
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock())
    task._session = session
    task._finished.set()

    task.cancel()
    task.cancel()

    session.shutdown.assert_called_once_with()
