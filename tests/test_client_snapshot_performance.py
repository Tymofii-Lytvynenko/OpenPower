import time
import unittest

import polars as pl

from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState
from src.client.ui.panels.military.presenter import MilitaryPresenter


class ClientSnapshotPerformanceTest(unittest.TestCase):
    def test_headless_consumption_of_100_engagement_snapshot_stays_bounded(self) -> None:
        battle_rows = []
        participant_rows = []
        battle_unit_rows = []
        region_rows = {"id": [], "name": []}
        for index in range(100):
            battle_id = f"battle-{index:03d}"
            region_id = index + 1
            battle_rows.append({
                "id": battle_id,
                "region_id": region_id,
                "status": "active",
                "mode": "positional",
                "attacker_side": f"USA{index:03d}",
                "defender_side": f"CAN{index:03d}",
                "balance": 0.5,
                "side_a_strength": 100.0,
                "side_b_strength": 100.0,
                "side_a_losses": 0,
                "side_b_losses": 0,
                "round": 1,
                "started_at_minute": 0,
                "updated_at_minute": 60,
                "concluded_at_minute": 0,
                "victor_side": "",
                "war_id": f"war-{index:03d}",
            })
            region_rows["id"].append(region_id)
            region_rows["name"].append(f"Region {region_id}")
            for owner, side in ((f"USA{index:03d}", "attacker"), (f"CAN{index:03d}", "defender")):
                participant_rows.append({
                    "battle_id": battle_id,
                    "country_id": owner,
                    "side": side,
                    "role": "principal",
                    "unit_count": 1,
                    "weighted_strength": 100.0,
                })
                battle_unit_rows.append({
                    "battle_id": battle_id,
                    "unit_id": f"{owner}-unit",
                    "country_id": owner,
                    "readiness_status": "ready",
                })

        state = GameState(tables={
            "regions": pl.DataFrame(region_rows),
            "battles": pl.DataFrame(battle_rows),
            "battle_participants": pl.DataFrame(participant_rows),
            "battle_units": pl.DataFrame(battle_unit_rows),
        })
        encoder = StateSnapshotEncoder()
        packet = encoder.encode(state, force_full=True)
        payload_size = sum(len(payload) for payload in packet["tables"].values())
        self.assertLessEqual(payload_size, 2_000_000)

        started = time.perf_counter()
        restored = StateSnapshotDecoder().decode(packet)
        presenter = MilitaryPresenter()
        views = [
            presenter.battle_status(restored, f"battle-{index:03d}", f"USA{index:03d}")
            for index in range(100)
        ]
        elapsed = time.perf_counter() - started
        self.assertLessEqual(elapsed, 0.10)
        self.assertTrue(all(view is not None for view in views))

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
