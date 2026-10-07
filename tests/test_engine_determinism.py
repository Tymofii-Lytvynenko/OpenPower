import unittest
from graphlib import CycleError

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.capability_system import MilitaryCapabilitySystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.engine.simulator import Engine
from src.shared.actions import ActionTrainUnit
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess
from src.shared.system_state import SYSTEM_STATE_HELPER

class DummySystem(ISystem):
    access = SystemAccess()
    runtime_state_contract = {
        "_id": SYSTEM_STATE_HELPER,
        "_deps": SYSTEM_STATE_HELPER,
    }

    def __init__(self, sys_id, deps):
        self._id = sys_id
        self._deps = deps
    @property
    def id(self): return self._id
    @property
    def dependencies(self): return self._deps
    def update(self, state, dt): pass

class TestEngineDeterminism(unittest.TestCase):
    def test_topological_sort_determinism(self):
        engine1 = Engine(dev_mode=True)
        sys_a = DummySystem("sys.a", ["sys.b"])
        sys_b = DummySystem("sys.b", [])
        
        # Register in one order
        engine1.register_systems([sys_a, sys_b])
        engine1._rebuild_execution_order()
        order1 = [s.id for s in engine1.execution_order]

        # Register in another order
        engine2 = Engine(dev_mode=True)
        engine2.register_systems([sys_b, sys_a])
        engine2._rebuild_execution_order()
        order2 = [s.id for s in engine2.execution_order]

        # Both execution orders must resolve to the identical deterministic sequence
        self.assertEqual(order1, order2)
        self.assertEqual(order1, ["sys.b", "sys.a"])

    def test_cycle_failure_logs_the_involved_system_ids(self):
        engine = Engine(dev_mode=True)
        engine.register_systems([
            DummySystem("sys.a", ["sys.b"]),
            DummySystem("sys.b", ["sys.a"]),
        ])

        with self.assertLogs("src.engine.simulator", level="CRITICAL") as captured:
            with self.assertRaisesRegex(CycleError, "sys.a.*sys.b"):
                engine._rebuild_execution_order()

        self.assertIn("sys.a", captured.output[0])
        self.assertIn("sys.b", captured.output[0])

    def test_training_replay_matches_across_equivalent_engine_snapshots(self):
        original = self._military_state()
        restored = GameState.from_ipc(original.to_ipc())
        ensure_base_tables(restored)
        action = ActionTrainUnit("player", "USA", "USA-1", "Regular")

        for state in (original, restored):
            engine = self._engine_with_capability_system()
            result = engine.step(state, [action], 0.0)
            self.assertTrue(result.success)

        for table_name in (
            "units",
            "countries",
            "unit_training_orders",
            "unit_capability_projections",
        ):
            self.assertTrue(
                original.get_table(table_name).equals(restored.get_table(table_name)),
                table_name,
            )

    def _engine_with_capability_system(self) -> Engine:
        engine = Engine(dev_mode=True)
        engine.register_systems([
            DummySystem("base.time", []),
            DummySystem("base.bootstrap", []),
            DummySystem("base.diplomacy", []),
            DummySystem("base.military_programs", []),
            MilitaryCapabilitySystem(),
        ])
        return engine

    def _military_state(self) -> GameState:
        unit = UnitFactory().create(
            "USA-1", "USA", "army", 100, 1, GeoCoordinate(10.0, 20.0), 0,
        )
        state = GameState(tables={
            "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
            "countries": pl.DataFrame({
                "id": ["USA"], "money_reserves": [1000.0], "military_count": [100],
            }),
            "regions": pl.DataFrame({
                "id": [1], "owner": ["USA"], "latitude": [10.0], "longitude": [20.0],
            }),
        })
        ensure_base_tables(state)
        state.update_table("unit_training_facilities", pl.DataFrame([{
            "id": "site-1", "country_id": "USA", "region_id": 1,
            "supported_domains": ["land"], "capacity": 1,
            "instructor_count": 1, "enabled": True,
        }], schema=state.get_table("unit_training_facilities").schema))
        state.globals["player_country_map"] = {"player": "USA"}
        return state
