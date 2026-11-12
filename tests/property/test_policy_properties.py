from hypothesis import given, strategies as st

from src.engine.command_pipeline import CommandPipeline
from src.server.command_policy import authorize_country_scope, validate_finite_payload
from src.shared.actions import ActionSetTax
from src.shared.commands import CommandEnvelope
from src.shared.state import GameState


@given(st.sampled_from(('AAA', 'BBB', 'CCC')), st.sets(st.sampled_from(('AAA', 'BBB', 'CCC'))), st.floats(allow_nan=False, allow_infinity=False, width=32))
def test_country_permissions_cannot_be_bypassed(country, allowed, tax):
    state = GameState()
    state.globals['command_permissions'] = {'player': list(allowed)}
    pipeline = CommandPipeline(validators=(authorize_country_scope, validate_finite_payload))
    action = ActionSetTax('player', country, tax)
    cmd = CommandEnvelope('test', 'player', 1, action)
    pipeline.submit(cmd)
    prepared = pipeline.prepare(state, 0)
    assert (cmd in prepared.ready) == (country in allowed)
    assert len(prepared.rejected) == (country not in allowed)
