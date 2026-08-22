import time
import unittest

import polars as pl

from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState


class ClientSnapshotPerformanceTest(unittest.TestCase):
    def test_bounded_snapshot_roundtrip_for_tactical_tables(self) -> None:
        rows = 2000
        state = GameState(tables={
            "units": pl.DataFrame({
                "id": [f"unit-{i}" for i in range(rows)],
                "owner": ["USA" if i % 2 else "CAN" for i in range(rows)],
                "strength": [100] * rows,
                "readiness_status": ["ready"] * rows,
                "readiness_progress": [0.0] * rows,
            }),
            "battles": pl.DataFrame({
                "id": ["battle-1"], "region_id": [1], "status": ["active"],
                "balance": [0.5], "side_a_strength": [100000.0], "side_b_strength": [100000.0],
            }),
        })
        encoder = StateSnapshotEncoder()
        started = time.perf_counter()
        packet = encoder.encode(state, force_full=True)
        decoded = StateSnapshotDecoder().decode(packet)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 1.5)
        self.assertEqual(decoded.get_table("units").height, rows)
        self.assertLess(sum(len(payload) for payload in packet["tables"].values()), 2_000_000)


if __name__ == "__main__":
    unittest.main()
