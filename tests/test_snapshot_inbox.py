from queue import Queue

import polars as pl

from src.client.services.snapshot_inbox import SnapshotInbox
from src.shared.snapshots import StateSnapshotEncoder
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
