from __future__ import annotations

import os
import platform
import time
import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.shared.state import GameState


@unittest.skipUnless(
    os.environ.get("RUN_INFRASTRUCTURE_BENCHMARKS") == "1",
    "Set RUN_INFRASTRUCTURE_BENCHMARKS=1 to run controlled scale gates.",
)
class InfrastructurePerformanceTest(unittest.TestCase):
    def test_incrementally_updates_one_percent_changes_in_one_hundred_thousand_profiles(self):
        region_count = 25_000
        categories = ("transport", "utilities", "industrial", "telecom")
        country_ids = [f"C{index:03d}" for index in range(50)]
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {"id": country_ids, "money_reserves": [1_000_000.0] * len(country_ids)}
                ),
                "regions": pl.DataFrame(
                    {
                        "id": list(range(1, region_count + 1)),
                        "owner": [country_ids[index % len(country_ids)] for index in range(region_count)],
                        "population": [10_000] * region_count,
                        "area_km2": [1_000.0] * region_count,
                    }
                ),
            }
        )
        ensure_base_tables(state)
        profiles = [
            {
                "region_id": region_id,
                "category": category,
                "level": 0.5,
                "condition": 0.9,
                "capacity": 0.45,
                "baseline": 0.2,
                "maximum": 1.0,
                "maintenance_level": 0.5,
                "maintenance_cost_per_level_month": 1_000.0,
                "last_change_minute": 0,
                "last_source_type": "benchmark",
                "last_source_id": "",
            }
            for region_id in range(1, region_count + 1)
            for category_index, category in enumerate(categories)
        ]
        self.assertEqual(len(profiles), 100_000)
        state.update_table("regional_infrastructure", pl.DataFrame(profiles))
        state.globals["infrastructure_last_update_minute"] = 0
        system = InfrastructureSystem()
        system.update(state, 0.0)
        before_regions = state.get_table("regions").select(
            "id", "transport_access", "utilities_capacity", "industrial_access", "telecom_capacity"
        )
        changed = state.get_table("regional_infrastructure").with_columns(
            pl.when(pl.col("region_id") <= 250).then(0.45).otherwise(pl.col("level")).alias("level"),
            pl.when(pl.col("region_id") <= 250).then(0.405).otherwise(pl.col("capacity")).alias("capacity"),
        )
        state.update_table("regional_infrastructure", changed)
        self.assertEqual(
            changed.filter(pl.col("region_id") <= 250).height,
            1_000,
        )

        started = time.perf_counter()
        system.update(state, 0.0)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.0, f"1,000 changed profiles took {elapsed:.3f}s to update")
        self.assertEqual(state.get_table("regions").height, region_count)
        self.assertEqual(state.get_table("countries").height, len(country_ids))
        after_regions = state.get_table("regions").select(
            "id",
            pl.col("transport_access").alias("transport_access_new"),
            pl.col("utilities_capacity").alias("utilities_capacity_new"),
            pl.col("industrial_access").alias("industrial_access_new"),
            pl.col("telecom_capacity").alias("telecom_capacity_new"),
        )
        comparison = before_regions.join(after_regions, on="id", how="inner")
        changed_regions = comparison.filter(
            pl.any_horizontal(
                (pl.col(column) - pl.col(f"{column}_new")).abs() > 1e-9
                for column in (
                    "transport_access",
                    "utilities_capacity",
                    "industrial_access",
                    "telecom_capacity",
                )
            )
        ).height
        self.assertEqual(changed_regions, 250)
        print(
            "Infrastructure performance gate: 100,000 category profiles, "
            f"1,000 changed (1%), {changed_regions:,} affected regions, {elapsed:.3f}s; "
            f"Python {platform.python_version()} on {platform.platform()}"
        )


if __name__ == "__main__":
    unittest.main()
