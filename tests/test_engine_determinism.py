import unittest
from src.engine.simulator import Engine
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
