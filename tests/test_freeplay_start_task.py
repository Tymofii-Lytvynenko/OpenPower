from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

import src.client.tasks.freeplay_start_task as task_module
from src.client.tasks.freeplay_start_task import FreeplayStartTask
from src.client.tasks.session_startup import TaskCancelledError


def _state(*, country_rows=None, player_tag="USA", party_id="party-1"):
    return SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                country_rows or [{"id": "USA", "is_playable": True}]
            ),
            "regions": pl.DataFrame({"id": [1], "owner": ["USA"]}),
            "political_parties": pl.DataFrame(
                [{"country_id": "USA", "party_id": party_id}]
            ),
        },
        globals={"player_tag": player_tag, "player_party_id": party_id},
    )


def _task():
    factory = Mock()
    window = SimpleNamespace(
        session_factory=factory,
        session=None,
    )
    config = SimpleNamespace(get_asset_path=Mock(return_value=None))
    return FreeplayStartTask(window, config, "usa", "party-1"), factory, config


def _install_startup(monkeypatch, task, session, state):
    create_session = Mock(return_value=session)
    monkeypatch.setattr(task_module, "create_session_until_ready", create_session)
    monkeypatch.setattr(task_module, "wait_for_initial_state", Mock(return_value=state))
    monkeypatch.setattr(task, "_warmup_file", Mock())
    return create_session


def test_freeplay_starts_from_initial_authoritative_world_without_campaign_data(monkeypatch):
    task, factory, config = _task()
    state = _state()
    session = SimpleNamespace(shutdown=Mock(), map_data=SimpleNamespace(height=256, width=512))
    create_session = _install_startup(monkeypatch, task, session, state)
    monkeypatch.setattr(task_module, "calculate_centroid", Mock(return_value=(23.0, 42.0)))

    result = task.run()

    assert create_session.call_args.args == (factory, config)
    assert create_session.call_args.kwargs["player_tag"] == "USA"
    assert set(state.tables) == {"countries", "regions", "political_parties"}
    assert result.session is session
    assert result.player_tag == "USA"
    assert result.player_party_id == "party-1"
    assert result.start_pos == (23.0, 42.0)
    assert task.progress == 1.0
    assert task.status_text == "Ready."
    assert [call.args[0] for call in task._warmup_file.call_args_list] == [
        "map/regions.png",
        "map/terrain.png",
    ]
    assert config.get_asset_path.call_count == 0


@pytest.mark.parametrize(
    "state,reason",
    [
        (_state(country_rows=[{"id": "CAN", "is_playable": True}]), "not a playable country"),
        (_state(country_rows=[{"id": "USA", "is_playable": False}]), "not a playable country"),
        (_state(player_tag="CAN"), "did not confirm 'USA'"),
    ],
)
def test_freeplay_rejects_invalid_authoritative_player_context_and_cleans_session(
    monkeypatch,
    state,
    reason,
):
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock(), map_data=SimpleNamespace(height=256, width=512))
    _install_startup(monkeypatch, task, session, state)

    with pytest.raises(RuntimeError, match=reason):
        task.run()

    session.shutdown.assert_called_once_with()
    assert task._finished.is_set()


def test_freeplay_cleans_session_when_initial_snapshot_fails(monkeypatch):
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock())
    monkeypatch.setattr(task_module, "create_session_until_ready", Mock(return_value=session))
    monkeypatch.setattr(
        task_module,
        "wait_for_initial_state",
        Mock(side_effect=TimeoutError("initial snapshot timeout")),
    )

    with pytest.raises(TimeoutError, match="initial snapshot timeout"):
        task.run()

    session.shutdown.assert_called_once_with()


def test_freeplay_cancel_before_start_does_not_create_session():
    task, factory, _ = _task()
    task.cancel()

    with pytest.raises(TaskCancelledError):
        task.run()

    factory.assert_not_called()


def test_freeplay_cancellation_after_completion_releases_unclaimed_session():
    task, _, _ = _task()
    session = SimpleNamespace(shutdown=Mock())
    task._session = session
    task._finished.set()

    task.cancel()
    task.cancel()

    session.shutdown.assert_called_once_with()
