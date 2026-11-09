from __future__ import annotations

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import polars as pl

import src.client.tasks.new_game_task as task_module
from src.client.tasks.new_game_task import NewGameTask
from src.client.tasks.session_startup import TaskCancelledError


def _task():
    factory = Mock()
    window = SimpleNamespace(session_factory=factory, session=None)
    config = object()
    return NewGameTask(window, config, "USA", "open_sandbox"), factory, config


def _install_successful_campaign_run(monkeypatch, task, state, session, client, *, report_progress=False):
    def create_session(_factory, _config, **kwargs):
        if report_progress:
            kwargs["on_progress"](0.25, "Loading campaign data")
        return session

    monkeypatch.setattr(task_module, "create_session_until_ready", create_session)
    monkeypatch.setattr(
        task_module,
        "wait_for_initial_state",
        lambda _session, **_kwargs: state,
    )
    monkeypatch.setattr(
        "src.client.services.network_client_service.NetworkClient",
        lambda _session: client,
    )
    monkeypatch.setattr(task, "_warmup_file", Mock())


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


def test_new_game_stops_previous_session_and_reports_startup_progress(monkeypatch) -> None:
    task, _, _ = _task()
    previous_session = SimpleNamespace(shutdown=Mock())
    task.window.session = previous_session
    state = SimpleNamespace(
        tables={
            "campaigns": pl.DataFrame(
                [{"scenario_id": "open_sandbox", "actor_country_id": "USA"}]
            ),
            "regions": pl.DataFrame([{"owner": "USA"}, {"owner": "CAN"}]),
        },
        journal=SimpleNamespace(command_results=[]),
    )
    session = SimpleNamespace(
        shutdown=Mock(),
        tick=Mock(),
        get_state_snapshot=Mock(return_value=state),
        map_data=SimpleNamespace(height=256, width=512),
    )
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    centroid = (42.0, 84.0)
    _install_successful_campaign_run(
        monkeypatch,
        task,
        state,
        session,
        client,
        report_progress=True,
    )
    monkeypatch.setattr(task_module, "calculate_centroid", Mock(return_value=centroid))

    result = task.run()

    previous_session.shutdown.assert_called_once_with()
    task_module.calculate_centroid.assert_called_once()
    assert task_module.calculate_centroid.call_args.args[1:] == (256, 512)
    assert result.start_pos == centroid
    assert result.session is session
    assert task.progress == 1.0
    assert task.status_text == "Ready."
    assert task._finished.is_set()
    assert [call.args for call in task._warmup_file.call_args_list] == [
        ("map/regions.png",),
        ("map/terrain.png",),
    ]


def test_new_game_keeps_campaign_running_when_centroid_calculation_fails(
    monkeypatch, capsys
) -> None:
    task, _, _ = _task()
    state = SimpleNamespace(
        tables={
            "campaigns": pl.DataFrame(
                [{"scenario_id": "open_sandbox", "actor_country_id": "USA"}]
            ),
            "regions": pl.DataFrame([{"owner": "USA"}]),
        },
        journal=SimpleNamespace(command_results=[]),
    )
    session = SimpleNamespace(
        shutdown=Mock(),
        tick=Mock(),
        get_state_snapshot=Mock(return_value=state),
        map_data=SimpleNamespace(height=256, width=512),
    )
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    _install_successful_campaign_run(monkeypatch, task, state, session, client)
    monkeypatch.setattr(
        task_module,
        "calculate_centroid",
        Mock(side_effect=ValueError("invalid region coordinates")),
    )

    result = task.run()

    assert result.start_pos is None
    assert "Error calculating centroid: invalid region coordinates" in capsys.readouterr().out
    session.shutdown.assert_not_called()


@pytest.mark.parametrize(
    "results,reason",
    [
        (
            [{"action_type": "ActionStartCampaign", "status": "rejected", "reason": "invalid scenario"}],
            "invalid scenario",
        ),
        ([{"action_type": "ActionSetPaused", "status": "rejected", "reason": "unrelated"}],
         "The server did not confirm campaign setup."),
    ],
)
def test_new_game_explains_unconfirmed_campaign_and_releases_session(
    monkeypatch, results, reason
) -> None:
    task, _, _ = _task()
    state = SimpleNamespace(
        tables={"campaigns": pl.DataFrame(schema={"scenario_id": pl.String, "actor_country_id": pl.String})},
        journal=SimpleNamespace(command_results=results),
    )
    session = SimpleNamespace(
        shutdown=Mock(),
        tick=Mock(),
        get_state_snapshot=Mock(return_value=state),
    )
    client = SimpleNamespace(player_id="player-1", send_action=Mock())
    _install_successful_campaign_run(monkeypatch, task, state, session, client)
    monkeypatch.setattr(
        task_module,
        "time",
        SimpleNamespace(perf_counter=Mock(side_effect=(0.0, 0.0, 61.0))),
    )

    with pytest.raises(RuntimeError, match=f"Could not start campaign 'open_sandbox': {reason}"):
        task.run()

    session.shutdown.assert_called_once_with()
    assert task._finished.is_set()


def test_warmup_file_reads_existing_asset_and_skips_missing_asset(tmp_path) -> None:
    task, _, _ = _task()
    asset = tmp_path / "regions.png"
    asset.write_bytes(b"map data")
    task.config = SimpleNamespace(get_asset_path=Mock(return_value=asset))

    task._warmup_file("map/regions.png")
    task.config.get_asset_path.assert_called_once_with("map/regions.png")

    task.config.get_asset_path.return_value = None
    task._warmup_file("map/terrain.png")
    task.config.get_asset_path.assert_called_with("map/terrain.png")
