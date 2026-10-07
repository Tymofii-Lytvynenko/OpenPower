from __future__ import annotations

import json
import os
import time
import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.strategic_warfare_system import StrategicWarfareSystem
from src.shared.state import GameState


class StrategicWarfarePerformanceTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("OPENPOWER_PERFORMANCE_TESTS") == "1",
        "Set OPENPOWER_PERFORMANCE_TESTS=1 to run controlled performance gates.",
    )
    def test_resolves_one_thousand_pending_strikes_with_two_thousand_defense_evaluations(self) -> None:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "money_reserves": [1_000.0, 1_000.0],
                "gdp": [1_000.0, 900.0], "military_count": [10, 8],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["USA", "CAN"], "controller": ["USA", "CAN"],
                "latitude": [0.0, 0.0], "longitude": [0.0, 50.0],
            }),
        })
        ensure_base_tables(state)
        state.tables["countries_relations"] = pl.DataFrame(schema={
            "source": pl.Utf8,
            "target": pl.Utf8,
            "value": pl.Float64,
        })
        state.globals["missile_defense_readiness_cost"] = 0.0
        state.update_table("research_tracks", pl.DataFrame([
            {"id": "can-program", "country_id": "CAN", "branch": "strategic_program", "research_level": 1},
            {"id": "can-defense", "country_id": "CAN", "branch": "strategic_defense", "research_level": 1},
        ], schema=state.get_table("research_tracks").schema))
        state.update_table("missile_defense_layers", pl.DataFrame([
            {
                "id": "can-long", "country_id": "CAN", "layer": "long_range", "researched": True,
                "operational": True, "coverage_region_ids": [2], "readiness": 1.0,
                "first_attempt_probability": 0.0, "second_attempt_probability": 0.0,
            },
            {
                "id": "can-short", "country_id": "CAN", "layer": "short_range", "researched": True,
                "operational": True, "coverage_region_ids": [2], "readiness": 1.0,
                "first_attempt_probability": 0.0, "second_attempt_probability": 0.0,
            },
        ], schema=state.get_table("missile_defense_layers").schema))
        state.update_table("strategic_launch_orders", pl.DataFrame([
            {
                "id": f"strike-{index:04d}", "country_id": "USA", "weapon_id": f"weapon-{index:04d}",
                "weapon_type": "icbm", "target_country_id": "CAN", "target_region_id": 2,
                "target_mode": "military", "payload_level": 1, "yield_kt": 100.0,
                "blast_radius_km": 3.25, "launched_at_minute": 0, "resolves_at_minute": 0,
                "status": "pending", "launch_detected": False,
            }
            for index in range(1000)
        ], schema=state.get_table("strategic_launch_orders").schema))

        started = time.perf_counter()
        StrategicWarfareSystem().update(state, 0.0)
        elapsed = time.perf_counter() - started

        resolved = state.get_table("strategic_launch_orders").filter(pl.col("status") == "impact")
        evaluations = sum(len(json.loads(value)) for value in resolved["defense_result_json"].to_list())
        self.assertEqual(resolved.height, 1000)
        self.assertEqual(evaluations, 2000)
        self.assertEqual(state.get_table("messages").height, 2000)
        relation_values = state.get_table("countries_relations")["value"].to_list()
        self.assertEqual(relation_values, [-100.0, -100.0])
        print(f"SC-007: 1000 pending strikes and 2000 layer evaluations in {elapsed * 1000:.2f} ms")
        self.assertLess(elapsed, 0.5, f"1000 strikes / 2000 layer evaluations took {elapsed * 1000:.2f} ms")


if __name__ == "__main__":
    unittest.main()
