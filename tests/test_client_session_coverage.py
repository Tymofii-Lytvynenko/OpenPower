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
    proxy._snapshot_inbox.latest = proxy._prepare_snapshot(snapshot)
    proxy.tick(0.0)

    client_state = proxy.get_state_snapshot()
    assert client_state is proxy.state
    assert client_state is not snapshot
    assert client_state.time.total_minutes == snapshot.time.total_minutes
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
    proxy._snapshot_inbox.latest = proxy._prepare_snapshot(snapshot)

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


def test_prepared_snapshot_hydrates_sequence_and_preserves_fractional_clock():
    from src.shared.actions import ActionSetGameSpeed
    from src.shared.commands import command_id_for

    proxy = _make_proxy()
    try:
        snapshot = GameState()
        snapshot.time.total_minutes = 12
        snapshot.time._accumulator = 0.25
        snapshot.journal.command_results.extend([
            {"actor_id": "alice", "sequence": 4},
            {"actor_id": "alice", "sequence": 7},
            {"actor_id": "bob", "sequence": 3},
        ])
        proxy.receive_action(ActionSetGameSpeed("alice", 1))
        proxy._snapshot_inbox.latest = proxy._prepare_snapshot(snapshot)
        proxy.tick(0)
        assert proxy.get_display_total_minutes() == 12.25
        assert proxy._command_sequences["alice"] == 7
        assert proxy._command_sequences["bob"] == 3
        assert proxy.receive_action(ActionSetGameSpeed("alice", 1)) == command_id_for("alice", 8)
    finally:
        proxy._snapshot_inbox.close()
        proxy.telemetry.close()


def test_real_proxy_prepares_view_on_receiver_thread(monkeypatch):
    from threading import current_thread

    import src.client.client_session as session_module
    from src.shared.snapshots import StateSnapshotEncoder

    packets, acknowledgements = Queue(), Queue()
    original = session_module.ClientGameStateView
    threads = []

    def record_construction(*args, **kwargs):
        threads.append(current_thread().name)
        return original(*args, **kwargs)

    monkeypatch.setattr(session_module, "ClientGameStateView", record_construction)
    proxy = ClientSessionProxy(None, Queue(), packets, Queue(), acknowledgements, Mock())
    try:
        state = GameState()
        state.journal.domain_events.extend(
            {"event_id": str(index), "payload": {"values": [1, 2, 3]}}
            for index in range(10_000)
        )
        packet = StateSnapshotEncoder().encode(state)
        packets.put(packet)
        assert acknowledgements.get(timeout=10) == packet["sequence"]
        proxy.tick(0)
        assert threads == ["simulation-snapshots"]
        assert len(proxy.state.journal.domain_events) == 10_000
        assert proxy.state.journal.domain_events[-1]["event_id"] == "9999"
    finally:
        proxy._snapshot_inbox.close()
        proxy.telemetry.close()


def test_delta_reuses_frozen_records_but_full_snapshot_resets_them():
    import pytest

    from src.shared.snapshots import StateSnapshotEncoder

    packets, acknowledgements = Queue(), Queue()
    proxy = ClientSessionProxy(None, Queue(), packets, Queue(), acknowledgements, Mock())
    encoder = StateSnapshotEncoder()
    state = GameState()
    state.journal.domain_events.append({"event_id": "one", "payload": {"values": [1]}})
    state.journal.command_results.append({"command_id": "c1", "actor_id": "alice", "sequence": 2})
    try:
        first = encoder.encode(state, force_full=True)
        packets.put(first)
        encoder.acknowledge(acknowledgements.get(timeout=5))
        proxy.tick(0)
        original_view = proxy.state
        frozen_record = original_view.journal.domain_events[0]
        frozen_command = original_view.journal.command_results[0]
        assert proxy._command_sequences["alice"] == 2

        state.journal.command_results.append({"command_id": "c2", "actor_id": "alice", "sequence": 8})
        state.journal.domain_events.append({"event_id": "two", "payload": {"values": [2]}})
        second = encoder.encode(state)
        packets.put(second)
        encoder.acknowledge(acknowledgements.get(timeout=5))
        proxy.tick(0)
        delta_view = proxy.state
        assert delta_view.journal.domain_events[0] is frozen_record
        assert delta_view.journal.command_results[0] is frozen_command
        assert proxy._command_sequences["alice"] == 8
        assert [record["event_id"] for record in delta_view.journal.domain_events] == ["one", "two"]
        assert len(original_view.journal.domain_events) == 1
        with pytest.raises(TypeError):
            frozen_record["payload"]["values"] = ()

        state.journal.domain_events[0]["payload"]["values"].append(9)
        state.journal.command_results = [{"command_id": "c3", "actor_id": "bob", "sequence": 4}]
        full = encoder.encode(state, force_full=True)
        packets.put(full)
        assert acknowledgements.get(timeout=5) == full["sequence"]
        proxy.tick(0)
        assert proxy.state.journal.domain_events[0]["payload"]["values"] == (1, 9)
        assert proxy._command_sequences["bob"] == 4
        assert proxy._command_sequences["alice"] == 8
        assert proxy.state.journal.command_results[0]["command_id"] == "c3"
        assert frozen_record["payload"]["values"] == (1,)
        assert proxy.state.journal.domain_events[0] is not frozen_record
    finally:
        proxy._snapshot_inbox.close()
        proxy.telemetry.close()
