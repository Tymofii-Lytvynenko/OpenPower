from hypothesis import strategies as st

from src.shared.actions import ActionSetPaused
from src.shared.commands import CommandEnvelope

actors = st.sampled_from(("alpha", "beta", "gamma"))

def command(command_id, actor, sequence, target_tick=None):
    return CommandEnvelope(command_id, actor, sequence, ActionSetPaused(actor, True), target_tick=target_tick)
