from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from main import create_local_session


def _bundle(process):
    return SimpleNamespace(
        map_data=object(),
        action_queue=Mock(),
        state_queue=Mock(),
        progress_queue=Mock(),
        snapshot_ack_queue=Mock(),
        process=process,
    )


def test_composition_root_cleans_spawned_process_when_proxy_creation_fails() -> None:
    process = Mock()
    process.is_alive.return_value = True
    bundle = _bundle(process)

    with (
        patch("src.server.launcher.spawn_local_server", return_value=bundle) as spawn,
        patch("src.client.client_session.ClientSessionProxy", side_effect=RuntimeError("proxy failed")),
        pytest.raises(RuntimeError, match="proxy failed"),
    ):
        create_local_session(object(), save_name="save-a", player_tag="USA")

    spawn.assert_called_once()
    process.terminate.assert_called_once_with()
    process.join.assert_called_once_with(timeout=5.0)
    bundle.action_queue.close.assert_called_once_with()
    bundle.state_queue.close.assert_called_once_with()
    bundle.progress_queue.close.assert_called_once_with()
    bundle.snapshot_ack_queue.close.assert_called_once_with()


def test_composition_root_passes_ipc_channels_into_proxy() -> None:
    bundle = _bundle(Mock())
    proxy = object()

    with (
        patch("src.server.launcher.spawn_local_server", return_value=bundle),
        patch("src.client.client_session.ClientSessionProxy", return_value=proxy) as client_proxy,
    ):
        result = create_local_session(object())

    assert result is proxy
    assert client_proxy.call_args.kwargs["process"] is bundle.process
    assert client_proxy.call_args.kwargs["progress_queue"] is bundle.progress_queue
