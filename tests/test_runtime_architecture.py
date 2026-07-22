import unittest
from graphlib import CycleError

import polars as pl

from src.engine.clock import FixedStepClock
from src.engine.journal import DomainEventJournal
from src.engine.simulator import Engine
from src.shared.determinism import DeterminismState, DeterministicRuntime
from src.shared.events import EventBudgetChanged, EventSystemError
from src.shared.numeric import stable_total
from src.shared.state import GameState
from src.shared.system_interfaces import SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE


class _System:
    runtime_state_contract = {
        "_system_id": SYSTEM_STATE_CACHE,
        "_dependencies": SYSTEM_STATE_CACHE,
        "access": SYSTEM_STATE_CACHE,
    }

    def __init__(self, system_id: str, dependencies: list[str], phase: int = 100):
        self._system_id = system_id
        self._dependencies = dependencies
        self.access = SystemAccess(phase=phase)

    @property
    def id(self) -> str:
        return self._system_id

    @property
    def dependencies(self) -> list[str]:
        return self._dependencies

    def update(self, state: GameState, delta_time: float) -> None:
        return None


class _FailingSystem:
    access = SystemAccess(writes=frozenset({"numbers"}), phase=SystemPhase.ECONOMY)
    runtime_state_contract = {"cache": SYSTEM_STATE_CACHE}

    def __init__(self):
        self.cache = ["before"]

    @property
    def id(self) -> str:
        return "test.failure"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        self.cache.append("mutated")
        state.update_table("numbers", pl.DataFrame({"value": [999]}))
        state.globals["mutated"] = True
        DeterministicRuntime(state.determinism).random()
        raise RuntimeError("intentional failure")


class TestRuntimeArchitecture(unittest.TestCase):
    def test_fixed_step_clock_caps_catch_up_and_retains_fraction(self):
        clock = FixedStepClock(step_seconds=0.1, max_catch_up_steps=3)

        self.assertEqual(clock.consume(0.25), (0.1, 0.1))
        self.assertAlmostEqual(clock.accumulator, 0.05)
        self.assertEqual(clock.consume(2.0), (0.1, 0.1, 0.1))
        self.assertAlmostEqual(clock.accumulator, 0.0)

    def test_float_reduction_is_independent_of_partition_order(self):
        left = stable_total([1e16, 1.0, -1e16, 3.0])
        right = stable_total([-1e16, 3.0, 1e16, 1.0])

        self.assertEqual(left, right)
        self.assertEqual(left, 4.0)

    def test_rng_and_ids_are_repeatable_from_the_same_seed(self):
        left = DeterministicRuntime(DeterminismState(seed=42))
        right = DeterministicRuntime(DeterminismState(seed=42))

        self.assertEqual([left.next_u64() for _ in range(5)], [right.next_u64() for _ in range(5)])
        self.assertEqual(left.next_id("battle", 7), right.next_id("battle", 7))

    def test_domain_events_are_promoted_with_deterministic_ids(self):
        state = GameState()
        state.globals["tick"] = 9
        state.events.append(EventBudgetChanged("USA"))

        captured = DomainEventJournal().capture(state)

        self.assertEqual(captured[0]["event_id"], "event-000000009-000000001")
        self.assertEqual(captured[0]["event_type"], "EventBudgetChanged")
        self.assertEqual(captured[0]["payload"], {"country_tag": "USA"})

    def test_system_graph_is_strict_and_phase_stable(self):
        first = _System("test.first", [], SystemPhase.POPULATION)
        second = _System("test.second", [], SystemPhase.CLOCK)
        engine = Engine()
        engine.register_systems([first, second])
        engine._rebuild_execution_order()
        self.assertEqual([system.id for system in engine.execution_order], ["test.second", "test.first"])

        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            engine.register_systems([_System("test.first", [])])

        missing = Engine()
        missing.register_systems([_System("test.child", ["test.absent"])])
        with self.assertRaisesRegex(RuntimeError, "missing dependencies"):
            missing._rebuild_execution_order()

        cycle = Engine()
        cycle.register_systems(
            [_System("test.a", ["test.b"]), _System("test.b", ["test.a"])]
        )
        with self.assertRaises(CycleError):
            cycle._rebuild_execution_order()

    def test_failed_tick_rolls_back_world_rng_and_system_state(self):
        state = GameState(tables={"numbers": pl.DataFrame({"value": [1]})})
        initial_rng_state = state.determinism.rng_state
        system = _FailingSystem()
        engine = Engine(dev_mode=False)
        engine.register_systems([system])

        result = engine.step(state, [], 0.1)

        self.assertFalse(result.success)
        self.assertEqual(state.globals["tick"], 0)
        self.assertNotIn("mutated", state.globals)
        self.assertEqual(state.get_table("numbers")["value"].to_list(), [1])
        self.assertEqual(state.determinism.rng_state, initial_rng_state)
        self.assertEqual(system.cache, ["before"])
        self.assertEqual(len(state.events), 1)
        self.assertIsInstance(state.events[0], EventSystemError)


if __name__ == "__main__":
    unittest.main()
