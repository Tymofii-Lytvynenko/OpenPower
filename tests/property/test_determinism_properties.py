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

@given(valid_tables(), st.integers(1, 10000), st.lists(st.tuples(st.integers(1, 5), st.booleans()), max_size=6))
def test_real_time_system_replay_and_runtime_restore(frame, seed, commands):
    from modules.base.systems.world.time_system import TimeSystem
    from src.shared.actions import ActionSetGameSpeed

    first = GameState(tables={'sample': frame})
    first.determinism.reset(seed)
    first_engine = Engine(dev_mode=True)
    first_engine.register_systems([TimeSystem()])
    for speed, paused in commands[:len(commands) // 2]:
        assert first_engine.step(first, [ActionSetGameSpeed('p', speed), ActionSetPaused('p', paused)], 0.6).success
    first_engine.snapshot_system_state(first)
    second = GameState.from_ipc(first.to_ipc())
    second_engine = Engine(dev_mode=True)
    second_engine.register_systems([TimeSystem()])
    second_engine.restore_system_state(second)
    assert state_fingerprint(first) == state_fingerprint(second)
    for speed, paused in commands[len(commands) // 2:]:
        actions = [ActionSetGameSpeed('p', speed), ActionSetPaused('p', paused)]
        for active_engine, state in ((first_engine, first), (second_engine, second)):
            assert active_engine.step(state, actions, 0.6).success
            active_engine.snapshot_system_state(state)
        assert state_fingerprint(first) == state_fingerprint(second)

import pytest
from hypothesis import settings
from tests.property.strategies.world_state import world_states


@pytest.mark.slow
@settings(max_examples=8, deadline=None)
@given(world_states(), st.lists(st.booleans(), min_size=1, max_size=3))
def test_minimal_world_replay_matches_after_snapshot(state, pauses):
    from modules.base.systems.world.time_system import TimeSystem

    restored = GameState.from_ipc(state.to_ipc())
    engines = (Engine(dev_mode=True), Engine(dev_mode=True))
    for instance in engines:
        instance.register_systems([TimeSystem()])
    for paused in pauses:
        for instance, world in zip(engines, (state, restored)):
            assert instance.step(world, [ActionSetPaused('player', paused)], 0.6).success
            instance.snapshot_system_state(world)
        assert state_fingerprint(state) == state_fingerprint(restored)
