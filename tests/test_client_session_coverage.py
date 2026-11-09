from __future__ import annotations

from queue import Queue
from unittest.mock import Mock

from src.client.client_session import ClientSessionProxy
from src.shared.events import EventSystemError
from src.shared.state import GameState


class _SnapshotInboxProbe:
    def __init__(self) -> None:
        self.latest: GameState | None = None

    def take_latest(self) -> GameState | None:
        latest, self.latest = self.latest, None
        return latest

    def close(self) -> None:
        return None


def _make_proxy() -> ClientSessionProxy:
    proxy = ClientSessionProxy(
        map_data=None,
        action_queue=Queue(),
        state_queue=Queue(),
        progress_queue=Queue(),
        snapshot_ack_queue=Queue(),
        process=Mock(),
    )
    proxy._snapshot_inbox.close()
    proxy._snapshot_inbox = _SnapshotInboxProbe()
    return proxy


def test_proxy_polling_clock_and_empty_state_helpers():
    proxy = _make_proxy()
    proxy.save_map_changes()
    assert proxy.action_queue.get_nowait() == "SAVE_MAP_CHANGES"

    proxy._hydrate_command_sequences()
    proxy._capture_system_errors()
    assert proxy.get_state_snapshot() is None
    assert proxy.get_display_date_text() is None
    assert proxy.get_display_total_minutes() is None

    proxy.tick(0.01)
    assert proxy.state is None
    proxy.tick(0.04)
    assert proxy.state is None

    snapshot = GameState()
    proxy._snapshot_inbox.latest = snapshot
    proxy.tick(0.0)

    assert proxy.get_state_snapshot() is snapshot
    assert proxy.get_display_date_text() is not None
    assert proxy.get_display_total_minutes() == 0.0
    proxy._snapshot_inbox.close()


def test_proxy_records_duplicate_system_errors_only_once_per_tick():
    proxy = _make_proxy()
    snapshot = GameState()
    snapshot.globals["tick"] = 7
    snapshot.events = [
        EventSystemError("base.economy", "failed", "traceback"),
        EventSystemError("base.economy", "failed", "traceback"),
    ]
    proxy._snapshot_inbox.latest = snapshot

    proxy.tick(0.0)

    assert proxy.system_errors == [
        {
            "system_id": "base.economy",
            "message": "failed",
            "traceback": "traceback",
            "tick": 7,
        }
    ]
    proxy._snapshot_inbox.close()
