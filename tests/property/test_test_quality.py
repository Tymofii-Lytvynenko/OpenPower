import polars as pl
import pytest

from src.engine.command_pipeline import PreparedCommands
from src.shared.state import GameState
from src.simulation.fingerprint import state_fingerprint
from tests.property.strategies.commands import command
from tests.property.test_command_properties import CommandMachine


def test_command_model_detects_dropped_command():
    machine = CommandMachine()
    machine.submit('alpha', 'valid')
    machine.pipeline.prepare = lambda state, tick: PreparedCommands((), ())
    with pytest.raises(AssertionError):
        machine.check_prepare()


def test_fingerprint_oracle_detects_broken_rollback():
    state = GameState(tables={'sample': pl.DataFrame({'id': [1]})})
    checkpoint = state.create_checkpoint()
    expected = state_fingerprint(state)
    state.globals['nested'] = {'corrupted': [1]}
    # This double omits globals when simulating a broken restore.
    state.tables = dict(checkpoint.tables)
    with pytest.raises(AssertionError):
        assert state_fingerprint(state) == expected
