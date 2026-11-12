import polars as pl
from hypothesis import given, strategies as st

from src.shared.determinism import DeterministicRuntime
from src.shared.state import GameState
from src.simulation.fingerprint import state_fingerprint
from tests.property.strategies.tables import valid_tables


@given(valid_tables(), valid_tables(), st.lists(st.integers(-1000, 1000), max_size=8))
def test_checkpoint_restores_persistent_state_and_revisions(first, second, values):
    state = GameState(tables={'first': first, 'second': second})
    state.globals['nested'] = {'values': values.copy()}
    state.system_state['system'] = {'nested': [values.copy()]}
    before = state_fingerprint(state)
    revisions = dict(state.table_revisions)
    checkpoint = state.create_checkpoint()
    assert state_fingerprint(state) == before
    state.globals['nested']['values'].append(999)
    state.system_state['system']['nested'][0].append(888)
    DeterministicRuntime(state.determinism).next_u64()
    state.update_table('first', pl.DataFrame({'changed': [1]}))
    state.remove_table('second')
    state.restore_checkpoint(checkpoint)
    assert state_fingerprint(state) == before
    assert state.table_revisions == revisions
    assert state.globals['nested']['values'] == values
    assert state.system_state['system']['nested'][0] == values
