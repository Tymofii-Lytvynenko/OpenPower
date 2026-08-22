import time
import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.events import EventNewHour
from src.shared.state import GameState


class TacticalCombatPerformanceTest(unittest.TestCase):
    def test_one_resolution_tick_handles_100_simultaneous_engagements(self) -> None:
        factory = UnitFactory()
        unit_rows = []
        region_rows = {"id": [], "owner": [], "controller": [], "latitude": [], "longitude": []}
        war_rows = {"id": [], "side_a": [], "side_b": [], "status": []}
        for index in range(100):
            region_id = index + 1
            usa = f"USA{index:03d}"
            can = f"CAN{index:03d}"
            left = factory.create(f"{usa}-unit", usa, "army", 100, region_id, GeoCoordinate(0, 0), 0)
            right = factory.create(f"{can}-unit", can, "army", 100, region_id, GeoCoordinate(0, 0), 0)
            left["readiness_status"] = "ready"
            right["readiness_status"] = "ready"
            unit_rows.extend((left, right))
            region_rows["id"].append(region_id)
            region_rows["owner"].append(can)
            region_rows["controller"].append(can)
            region_rows["latitude"].append(0.0)
            region_rows["longitude"].append(0.0)
            war_rows["id"].append(f"war-{index:03d}")
            war_rows["side_a"].append([usa])
            war_rows["side_b"].append([can])
            war_rows["status"].append("active")

        state = GameState(tables={
            "regions": pl.DataFrame(region_rows),
            "units": pl.DataFrame(unit_rows, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame(war_rows),
        })
        state.events.append(EventNewHour(hour=1, total_minutes=60))
        started = time.perf_counter()
        CombatSystem().update(state, 0.0)
        elapsed = time.perf_counter() - started
        self.assertLessEqual(elapsed, 0.25)
        self.assertEqual(state.get_table("battles").height, 100)

    def test_resolution_scales_linearly_for_large_battle(self) -> None:
        factory = UnitFactory()
        rows = []
        for index in range(1000):
            owner = "USA" if index % 2 == 0 else "CAN"
            rows.append(factory.create(f"u-{index:04d}", owner, "army", 100, 1, GeoCoordinate(0, 0), 0))
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["CAN"], "controller": ["CAN"], "latitude": [0.0], "longitude": [0.0]}),
            "units": pl.DataFrame(rows, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame({"id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}),
        })
        started = time.perf_counter()
        CombatSystem().update(state, 0)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)
        self.assertGreaterEqual(state.get_table("battles").height, 1)

    def test_idle_resolution_does_not_churn_snapshot_revisions(self) -> None:
        unit = UnitFactory().create(
            "usa-1",
            "USA",
            "army",
            100,
            1,
            GeoCoordinate(0, 0),
            0,
        )
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [1],
                "owner": ["USA"],
                "controller": ["USA"],
                "latitude": [0.0],
                "longitude": [0.0],
            }),
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame(schema={
                "id": pl.Utf8,
                "side_a": pl.List(pl.Utf8),
                "side_b": pl.List(pl.Utf8),
                "status": pl.Utf8,
            }),
        })
        system = CombatSystem()
        system.update(state, 0)
        revisions = dict(state.table_revisions)

        system.update(state, 0)

        self.assertEqual(dict(state.table_revisions), revisions)

    def test_active_battle_only_changes_tables_on_resolution_tick(self) -> None:
        factory = UnitFactory()
        units = [
            factory.create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0),
            factory.create("can-1", "CAN", "army", 100, 1, GeoCoordinate(0, 0), 0),
        ]
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [1],
                "owner": ["CAN"],
                "controller": ["CAN"],
                "latitude": [0.0],
                "longitude": [0.0],
            }),
            "units": pl.DataFrame(units, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame({
                "id": ["war-1"],
                "side_a": [["USA"]],
                "side_b": [["CAN"]],
                "status": ["active"],
            }),
        })
        system = CombatSystem()
        system.update(state, 0)
        revisions = dict(state.table_revisions)
        state.events.clear()
        state.time.total_minutes += 1

        system.update(state, 0)

        self.assertEqual(dict(state.table_revisions), revisions)


if __name__ == "__main__":
    unittest.main()
