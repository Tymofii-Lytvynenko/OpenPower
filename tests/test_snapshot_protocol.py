import unittest

import polars as pl

from src.shared.snapshots import (
    SnapshotProtocolError,
    StateSnapshotDecoder,
    StateSnapshotEncoder,
)
from src.shared.state import GameState


class TestSnapshotProtocol(unittest.TestCase):
    def test_history_append_delta_handles_overlapping_acknowledgement_bases(self):
        state = GameState(tables={"history_snapshots": pl.DataFrame({"value": [1]})})
        encoder, decoder = StateSnapshotEncoder(), StateSnapshotDecoder()
        full = encoder.encode(state)
        published = decoder.decode(full)
        encoder.acknowledge(full["sequence"])
        for values in ([1, 2], [1, 2, 3]):
            state.update_table("history_snapshots", pl.DataFrame({"value": values}))
            packet = encoder.encode(state)
            self.assertNotIn("history_snapshots", packet["tables"])
            result = decoder.decode(packet)
            self.assertEqual(result.get_table("history_snapshots")["value"].to_list(), values)
        self.assertEqual(published.get_table("history_snapshots")["value"].to_list(), [1])
        state.update_table("history_snapshots", pl.DataFrame({"value": [3]}))
        compacted = encoder.encode(state)
        self.assertIn("history_snapshots", compacted["tables"])
        self.assertEqual(decoder.decode(compacted).get_table("history_snapshots")["value"].to_list(), [3])

    def test_delta_does_not_mutate_a_published_snapshot(self):
        state = GameState(tables={"alpha": pl.DataFrame({"value": [10]})})
        encoder = StateSnapshotEncoder()
        decoder = StateSnapshotDecoder()
        first = encoder.encode(state)
        published = decoder.decode(first)
        encoder.acknowledge(first["sequence"])
        state.update_table("alpha", pl.DataFrame({"value": [11]}))
        state.journal.command_results.append({"command_id": "new-command"})
        updated = decoder.decode(encoder.encode(state))
        self.assertIsNot(updated, published)
        self.assertEqual(published.get_table("alpha")["value"].to_list(), [10])
        self.assertEqual(published.journal.command_results, [])
        self.assertEqual(updated.get_table("alpha")["value"].to_list(), [11])

    def test_acknowledged_delta_contains_only_changed_tables_and_journal_tail(self):
        state = GameState(
            tables={
                "alpha": pl.DataFrame({"id": [1], "value": [10]}),
                "beta": pl.DataFrame({"id": [2], "value": [20]}),
            }
        )
        encoder = StateSnapshotEncoder()
        decoder = StateSnapshotDecoder()

        full = encoder.encode(state)
        restored = decoder.decode(full)
        self.assertEqual(full["kind"], "full")
        self.assertEqual(set(full["tables"]), {"alpha", "beta"})
        self.assertTrue(restored.get_table("beta").equals(state.get_table("beta")))

        encoder.acknowledge(full["sequence"])
        state.update_table("alpha", pl.DataFrame({"id": [1], "value": [11]}))
        state.journal.command_results.append(
            {
                "command_id": "command-1",
                "actor_id": "player",
                "sequence": 1,
                "tick": 1,
                "action_type": "TestAction",
                "status": "executed",
                "code": "",
                "message": "",
            }
        )

        delta = encoder.encode(state)
        self.assertEqual(delta["kind"], "delta")
        self.assertEqual(set(delta["tables"]), {"alpha"})
        self.assertEqual(len(delta["command_results"]), 1)

        restored = decoder.decode(delta)
        self.assertEqual(restored.get_table("alpha")["value"].to_list(), [11])
        self.assertEqual(restored.get_table("beta")["value"].to_list(), [20])
        self.assertEqual(restored.journal.command_results[-1]["command_id"], "command-1")

        encoder.acknowledge(delta["sequence"])
        unchanged = encoder.encode(state)
        self.assertEqual(unchanged["tables"], {})
        self.assertEqual(unchanged["command_results"], [])

    def test_removed_tables_are_applied_by_the_decoder(self):
        state = GameState(tables={"temporary": pl.DataFrame({"id": [1]})})
        encoder = StateSnapshotEncoder()
        decoder = StateSnapshotDecoder()
        full = encoder.encode(state)
        decoder.decode(full)
        encoder.acknowledge(full["sequence"])

        state.remove_table("temporary")
        delta = encoder.encode(state)
        restored = decoder.decode(delta)

        self.assertEqual(delta["removed_tables"], ["temporary"])
        self.assertNotIn("temporary", restored.tables)

    def test_unknown_acknowledgements_are_ignored(self):
        encoder = StateSnapshotEncoder()

        encoder.acknowledge(42)

        self.assertEqual(encoder.base_sequence, 0)
        self.assertEqual(encoder._sent, {})

    def test_encoder_bounds_unacknowledged_descriptor_history(self):
        encoder = StateSnapshotEncoder()
        state = GameState()

        for _ in range(257):
            encoder.encode(state)

        self.assertEqual(len(encoder._sent), 256)
        self.assertIn(encoder.base_sequence, encoder._sent)
        self.assertNotIn(2, encoder._sent)
        self.assertIn(encoder.sequence, encoder._sent)

    def test_decoder_rejects_unsupported_protocol_versions(self):
        with self.assertRaisesRegex(SnapshotProtocolError, "Unsupported snapshot protocol"):
            StateSnapshotDecoder().decode({"protocol_version": 99, "kind": "full"})

    def test_decoder_rejects_delta_before_full_snapshot(self):
        packet = {"protocol_version": 3, "kind": "delta"}

        with self.assertRaisesRegex(SnapshotProtocolError, "before a full snapshot"):
            StateSnapshotDecoder().decode(packet)

    def test_decoder_rejects_delta_based_on_future_sequence(self):
        decoder = StateSnapshotDecoder()
        full = StateSnapshotEncoder().encode(GameState())
        decoder.decode(full)

        with self.assertRaisesRegex(SnapshotProtocolError, "client has"):
            decoder.decode(
                {
                    "protocol_version": 3,
                    "kind": "delta",
                    "base_sequence": decoder.sequence + 1,
                }
            )

    def test_decoder_rejects_appends_without_a_retained_prefix(self):
        decoder = StateSnapshotDecoder()
        decoder.decode(StateSnapshotEncoder().encode(GameState()))

        with self.assertRaisesRegex(SnapshotProtocolError, "Missing append prefix"):
            decoder.decode(
                {
                    "protocol_version": 3,
                    "kind": "delta",
                    "base_sequence": decoder.sequence,
                    "tables": {},
                    "appended_tables": {
                        "history_snapshots": {"offset": 1, "data": b""}
                    },
                }
            )

    def test_decoder_rejects_unknown_packet_kinds(self):
        with self.assertRaisesRegex(SnapshotProtocolError, "Unknown snapshot kind"):
            StateSnapshotDecoder().decode(
                {"protocol_version": 3, "kind": "unknown"}
            )

    def test_duplicate_journal_identifiers_are_not_appended(self):
        target = [{"event_id": "event-1", "payload": "original"}]
        incoming = [{"event_id": "event-1", "payload": "duplicate"}]

        StateSnapshotDecoder._merge_journal(target, incoming, "event_id")

        self.assertEqual(target, [{"event_id": "event-1", "payload": "original"}])


if __name__ == "__main__":
    unittest.main()
