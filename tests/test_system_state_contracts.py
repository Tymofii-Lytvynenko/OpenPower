import unittest
from types import SimpleNamespace

from src.shared.system_interfaces import ICheckpointedSystem, ISystem, SystemAccess
from src.engine.simulator import Engine
from src.shared.system_state import (
    SYSTEM_STATE_CACHE,
    SYSTEM_STATE_CHECKPOINT,
    runtime_state_contract,
    validate_runtime_state_contract,
)
from src.shared.state import GameState


class UndeclaredStateSystem(ISystem):
    access = SystemAccess()
    def __init__(self):
        self._buffer = []

    @property
    def id(self) -> str:
        return "test.undeclared"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return None


class BrokenCheckpointContractSystem(ISystem):
    access = SystemAccess()
    runtime_state_contract = {
        "counter": SYSTEM_STATE_CHECKPOINT,
    }

    def __init__(self):
        self.counter = 1

    @property
    def id(self) -> str:
        return "test.broken-checkpoint"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return None


class CounterCheckpointSystem(ISystem, ICheckpointedSystem):
    access = SystemAccess()
    runtime_state_contract = {
        "counter": SYSTEM_STATE_CHECKPOINT,
    }

    def __init__(self):
        self.counter = 7

    @property
    def id(self) -> str:
        return "test.counter"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        self.counter += 1

    def export_persistent_state(self) -> dict[str, int]:
        return {"counter": self.counter}

    def import_persistent_state(self, data: dict[str, int]) -> None:
        self.counter = int(data.get("counter", 0))


class InvalidCheckpointPayloadSystem(CounterCheckpointSystem):
    def export_persistent_state(self):
        return [self.counter]


class MissingCheckpointFieldsSystem(CounterCheckpointSystem):
    def export_persistent_state(self) -> dict[str, int]:
        return {}


class UnexpectedCheckpointFieldsSystem(CounterCheckpointSystem):
    def export_persistent_state(self) -> dict[str, int]:
        return {"counter": self.counter, "extra": 1}


class LateRuntimeStateSystem(ISystem):
    access = SystemAccess()
    runtime_state_contract = {
        "_buffer": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._buffer: list[int] = []

    @property
    def id(self) -> str:
        return "test.late-runtime"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        self._buffer.append(state.globals.get("tick", 0))
        self.late_value = 1


class TestSystemStateContracts(unittest.TestCase):
    def test_runtime_state_contract_handles_missing_and_invalid_declarations(self):
        self.assertEqual(runtime_state_contract(SimpleNamespace(runtime_state_contract=None)), {})
        with self.assertRaisesRegex(TypeError, "must be a mapping"):
            runtime_state_contract(SimpleNamespace(runtime_state_contract="checkpoint"))
        with self.assertRaisesRegex(RuntimeError, "invalid runtime state policies"):
            runtime_state_contract(SimpleNamespace(runtime_state_contract={"buffer": "unknown"}))

    def test_runtime_state_validation_supports_slotted_systems(self):
        class SlottedCacheSystem:
            __slots__ = ("cache", "callback", "not_initialized")
            runtime_state_contract = {
                "cache": SYSTEM_STATE_CACHE,
                "callback": SYSTEM_STATE_CACHE,
                "not_initialized": SYSTEM_STATE_CACHE,
            }

            def __init__(self):
                self.cache = []
                self.callback = lambda: None

        validate_runtime_state_contract(SlottedCacheSystem())

    def test_checkpoint_validation_checks_export_type_and_exact_keys(self):
        with self.assertRaisesRegex(TypeError, "must return a dict"):
            validate_runtime_state_contract(InvalidCheckpointPayloadSystem())
        with self.assertRaisesRegex(RuntimeError, "missing exported keys"):
            validate_runtime_state_contract(MissingCheckpointFieldsSystem())
        with self.assertRaisesRegex(RuntimeError, "unexpected exported keys"):
            validate_runtime_state_contract(UnexpectedCheckpointFieldsSystem())

    def test_engine_rejects_undeclared_runtime_state(self):
        engine = Engine(dev_mode=False)

        with self.assertRaisesRegex(RuntimeError, "undeclared runtime state"):
            engine.register_systems([UndeclaredStateSystem()])

    def test_engine_rejects_checkpoint_contract_without_protocol(self):
        engine = Engine(dev_mode=False)

        with self.assertRaisesRegex(RuntimeError, "does not implement ICheckpointedSystem"):
            engine.register_systems([BrokenCheckpointContractSystem()])

    def test_engine_snapshots_and_restores_checkpointed_state(self):
        engine = Engine(dev_mode=False)
        system = CounterCheckpointSystem()
        engine.register_systems([system])

        state = GameState()
        engine.snapshot_system_state(state)
        self.assertEqual(state.system_state, {"test.counter": {"counter": 7}})

        system.counter = 0
        engine.restore_system_state(state)
        self.assertEqual(system.counter, 7)

    def test_engine_catches_runtime_state_added_after_registration(self):
        engine = Engine(dev_mode=False)
        engine.register_systems([LateRuntimeStateSystem()])

        with self.assertRaisesRegex(RuntimeError, "undeclared runtime state"):
            engine.step(GameState(), [], 0.0)


if __name__ == "__main__":
    unittest.main()
