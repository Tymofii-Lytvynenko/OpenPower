from hypothesis import strategies as st

from src.shared.actions import ActionSetPaused
from src.shared.commands import CommandEnvelope

actors = st.sampled_from(("alpha", "beta", "gamma"))

def command(command_id, actor, sequence, target_tick=None):
    return CommandEnvelope(command_id, actor, sequence, ActionSetPaused(actor, True), target_tick=target_tick)

from src.shared.actions import ActionSetGameSpeed, ActionSetTax


def valid_actions(actor):
    return st.one_of(
        st.builds(ActionSetPaused, st.just(actor), st.booleans()),
        st.builds(ActionSetGameSpeed, st.just(actor), st.integers(1, 5)),
        st.builds(ActionSetTax, st.just(actor), st.sampled_from(('AAA', 'BBB')), st.floats(0, 1, allow_nan=False)),
    )


@st.composite
def valid_envelopes(draw):
    actor = draw(actors)
    seq = draw(st.integers(1, 100))
    action = draw(valid_actions(actor))
    return CommandEnvelope(f'{actor}-{seq}', actor, seq, action)

@st.composite
def invalid_envelopes(draw):
    """Return an envelope and its expected rejection category."""
    from dataclasses import replace
    from src.shared.commands import COMMAND_SCHEMA_VERSION

    envelope = draw(valid_envelopes())
    kind = draw(st.sampled_from(('sequence', 'actor', 'version')))
    if kind == 'sequence':
        envelope = replace(envelope, sequence=0)
    elif kind == 'actor':
        envelope = replace(envelope, actor_id='different')
    else:
        envelope = replace(envelope, schema_version=COMMAND_SCHEMA_VERSION + 1)
    return envelope, 'protocol_error'
