from queue import Full, Queue
from threading import Event
from unittest.mock import Mock

import polars as pl

from src.client.services.snapshot_inbox import SnapshotInbox
from src.shared.snapshots import SnapshotProtocolError, StateSnapshotEncoder
from src.shared.state import GameState


def test_receives_and_acknowledges_without_render_thread_decoding():
    packets, acknowledgements = Queue(), Queue()
    inbox = SnapshotInbox(packets, acknowledgements)
    try:
        state = GameState(tables={"alpha": pl.DataFrame({"value": [10]})})
        encoder = StateSnapshotEncoder()
        packet = encoder.encode(state)
        packets.put(packet)
        assert acknowledgements.get(timeout=5) == packet["sequence"]
        published = inbox.take_latest()
        assert published.get_table("alpha")["value"].to_list() == [10]
        assert inbox.take_latest() is None
        encoder.acknowledge(packet["sequence"])
        state.update_table("alpha", pl.DataFrame({"value": [11]}))
        delta = encoder.encode(state)
        packets.put(delta)
        assert acknowledgements.get(timeout=5) == delta["sequence"]
        assert inbox.take_latest().get_table("alpha")["value"].to_list() == [11]
        assert published.get_table("alpha")["value"].to_list() == [10]
    finally:
        inbox.close()


def test_protocol_errors_are_logged_and_the_receiver_continues(capsys):
    packets, acknowledgements = Queue(), Queue()
    inbox = SnapshotInbox(packets, acknowledgements)
    state = GameState()
    inbox._decoder = Mock(sequence=7)
    inbox._decoder.decode.side_effect = [SnapshotProtocolError("invalid packet"), state]
    try:
        packets.put("invalid")
        packets.put("valid")

        assert acknowledgements.get(timeout=5) == 7
        assert inbox.take_latest() is state
        assert "Snapshot protocol error: invalid packet" in capsys.readouterr().out
    finally:
        inbox.close()


def test_queue_shutdown_errors_stop_the_receiver():
    class ClosedQueue:
        def get(self, timeout):
            raise OSError("queue closed")

    inbox = SnapshotInbox(ClosedQueue(), Queue())
    inbox._thread.join(timeout=1)
    inbox.close()

    assert not inbox._thread.is_alive()


def test_full_acknowledgement_queue_does_not_block_snapshot_publication():
    class FullAcknowledgementQueue:
        def __init__(self):
            self.attempted = Event()

        def put_nowait(self, _sequence):
            self.attempted.set()
            raise Full

    packets = Queue()
    acknowledgements = FullAcknowledgementQueue()
    inbox = SnapshotInbox(packets, acknowledgements)
    try:
        state = GameState(tables={"alpha": pl.DataFrame({"value": [1]})})
        packets.put(StateSnapshotEncoder().encode(state))

        assert acknowledgements.attempted.wait(timeout=5)
        assert inbox.take_latest().get_table("alpha")["value"].to_list() == [1]
    finally:
        inbox.close()
