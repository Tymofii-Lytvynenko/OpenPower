import unittest

import polars as pl

from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState


class TestSnapshotProtocol(unittest.TestCase):
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
