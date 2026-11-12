from hypothesis import given, strategies as st

from src.engine.simulator import Engine
from src.shared.actions import ActionSetPaused
from src.shared.determinism import DeterministicRuntime
from src.shared.state import GameState
from src.shared.system_interfaces import SystemAccess
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.simulation.fingerprint import state_fingerprint
from tests.property.strategies.tables import valid_tables


class SampleSystem:
    access = SystemAccess()
    runtime_state_contract = {'name': SYSTEM_STATE_HELPER, 'deps': SYSTEM_STATE_HELPER}

    def __init__(self, name, deps):
        self.name, self.deps = name, deps

    @property
    def id(self):
        return self.name

    @property
    def dependencies(self):
        return self.deps

    def update(self, state, dt):
        state.globals[self.name] = DeterministicRuntime(state.determinism).next_u64()


def engine(order):
    systems = {'a': SampleSystem('a', []), 'b': SampleSystem('b', []), 'c': SampleSystem('c', ['a'])}
    result = Engine(dev_mode=True)
    result.register_systems([systems[name] for name in order])
    return result


@given(valid_tables(), st.integers(1, 10000), st.lists(st.booleans(), max_size=5), st.permutations(('a', 'b', 'c')))
def test_equivalent_graphs_and_restored_state_replay_identically(frame, seed, actions, order):
    first = GameState(tables={'sample': frame})
    first.determinism.reset(seed)
    second = GameState.from_ipc(first.to_ipc())
    one, two = engine(('a', 'b', 'c')), engine(order)
    for paused in actions:
        commands = [ActionSetPaused('player', paused)]
        assert one.step(first, commands, 0.1).success
        assert two.step(second, commands, 0.1).success
        assert state_fingerprint(first) == state_fingerprint(second)
    one._rebuild_execution_order()
    two._rebuild_execution_order()
    assert [s.id for s in one.execution_order] == [s.id for s in two.execution_order]
    assert state_fingerprint(first) == state_fingerprint(second)
