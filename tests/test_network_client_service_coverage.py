from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.services.network_client_service import NetworkClient
from src.shared.actions import ActionSaveGame, ActionSetPaused


def test_system_error_access_preserves_session_queue_and_supports_sessions_without_one() -> None:
    errors = ["simulation warning"]
    client = NetworkClient(SimpleNamespace(system_errors=errors))

    assert client.get_system_errors() is errors
    assert NetworkClient(SimpleNamespace()).get_system_errors() == []


def test_clear_system_errors_clears_queue_and_supports_sessions_without_one() -> None:
    errors = ["simulation warning"]
    NetworkClient(SimpleNamespace(system_errors=errors)).clear_system_errors()
    NetworkClient(SimpleNamespace()).clear_system_errors()

    assert errors == []


def test_send_action_uses_local_player_and_reads_authoritative_snapshot() -> None:
    state = object()
    session = SimpleNamespace(
        receive_action=Mock(return_value="command-42"),
        get_state_snapshot=Mock(return_value=state),
    )
    client = NetworkClient(session)
    action = ActionSetPaused(player_id="USA", is_paused=True)

    assert client.send_action(action) == "command-42"
    assert session.receive_action.call_args.args[0] == ActionSetPaused(
        player_id="local_admin", is_paused=True
    )
    assert action.player_id == "USA"
    assert client.get_state() is state


def test_display_date_uses_session_interpolation_when_available() -> None:
    session = SimpleNamespace(get_display_date_text=Mock(return_value="1848-06-15"))

    assert NetworkClient(session).get_display_date_text() == "1848-06-15"
    session.get_display_date_text.assert_called_once_with()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (SimpleNamespace(time=SimpleNamespace(date_str="1848-06-15")), "1848-06-15"),
        (SimpleNamespace(), None),
    ],
    ids=["snapshot-date", "snapshot-without-time"],
)
def test_display_date_falls_back_to_snapshot(
    state: SimpleNamespace,
    expected: str | None,
) -> None:
    session = SimpleNamespace(get_state_snapshot=lambda: state)

    assert NetworkClient(session).get_display_date_text() == expected


def test_display_total_minutes_uses_session_interpolation_when_available() -> None:
    session = SimpleNamespace(get_display_total_minutes=Mock(return_value=12.5))

    assert NetworkClient(session).get_display_total_minutes() == 12.5
    session.get_display_total_minutes.assert_called_once_with()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (SimpleNamespace(time=SimpleNamespace(total_minutes=12)), 12.0),
        (SimpleNamespace(time=SimpleNamespace()), 0.0),
        (SimpleNamespace(), None),
    ],
    ids=["snapshot-minutes", "missing-minutes-defaults-to-zero", "snapshot-without-time"],
)
def test_display_total_minutes_falls_back_to_snapshot(
    state: SimpleNamespace,
    expected: float | None,
) -> None:
    session = SimpleNamespace(get_state_snapshot=lambda: state)

    assert NetworkClient(session).get_display_total_minutes() == expected


def test_request_save_saves_map_changes_for_editor() -> None:
    session = SimpleNamespace(save_map_changes=Mock(), receive_action=Mock())

    NetworkClient(session).request_save(is_editor=True)

    session.save_map_changes.assert_called_once_with()
    session.receive_action.assert_not_called()


def test_request_save_sends_quicksave_action_for_gameplay() -> None:
    session = SimpleNamespace(receive_action=Mock(return_value="save-command"))

    NetworkClient(session).request_save()

    session.receive_action.assert_called_once_with(
        ActionSaveGame(player_id="local_admin", save_name="quicksave")
    )
