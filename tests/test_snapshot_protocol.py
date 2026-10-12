import unittest

import polars as pl

from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
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


if __name__ == "__main__":
    unittest.main()
