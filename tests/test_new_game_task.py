from __future__ import annotations

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import polars as pl

from src.client.tasks.new_game_task import NewGameTask
from src.client.tasks.session_startup import TaskCancelledError


def _task():
    factory = Mock()
    window = SimpleNamespace(session_factory=factory, session=None)
    config = object()
    return NewGameTask(window, config, "USA", "open_sandbox"), factory, config


def test_new_game_uses_injected_factory_for_startup() -> None:
    task, factory, config = _task()
    task.cancel()

    with pytest.raises(TaskCancelledError):
        task.run()

    factory.assert_not_called()


def test_new_game_cleans_created_session_when_state_sync_fails() -> None:
    task, factory, config = _task()
    session = SimpleNamespace(shutdown=Mock())

    with (
        patch("src.client.tasks.new_game_task.create_session_until_ready", return_value=session) as start_session,
        patch(
            "src.client.tasks.new_game_task.wait_for_initial_state",
            side_effect=TimeoutError("state timeout"),
        ),
        pytest.raises(TimeoutError, match="state timeout"),
    ):
        task.run()

    start_session.assert_called_once()
    assert start_session.call_args.args == (factory, config)
    session.shutdown.assert_called_once_with()


def test_new_game_start_action_includes_selected_party() -> None:
    task, factory, config = _task()
    task.player_party_id = "usa-opposition"
    session = SimpleNamespace(
        shutdown=Mock(),
        tick=Mock(),
        get_state_snapshot=Mock(),
    )
    state = SimpleNamespace(
        tables={
            "campaigns": pl.DataFrame(
                [{"scenario_id": "open_sandbox", "actor_country_id": "USA"}]
            )
        },
        journal=SimpleNamespace(command_results=[]),
    )
    session.get_state_snapshot.return_value = state
    client = SimpleNamespace(player_id="player-1", send_action=Mock())

    with (
        patch("src.client.tasks.new_game_task.create_session_until_ready", return_value=session),
        patch("src.client.tasks.new_game_task.wait_for_initial_state", return_value=state),
        patch("src.client.services.network_client_service.NetworkClient", return_value=client),
        patch.object(task, "_warmup_file"),
    ):
        result = task.run()

    action = client.send_action.call_args.args[0]
    assert action.player_id == "player-1"
    assert action.scenario_id == "open_sandbox"
    assert action.country_tag == "USA"
    assert action.player_party_id == "usa-opposition"
    assert result.session is session
    assert factory is task.window.session_factory


def test_new_game_cancellation_after_completion_releases_unclaimed_session() -> None:
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock())
    task._session = session
    task._finished.set()

    task.cancel()
    task.cancel()

    session.shutdown.assert_called_once_with()
