from collections import defaultdict

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from src.engine.command_pipeline import CommandPipeline
from src.shared.commands import COMMAND_SCHEMA_VERSION
from src.shared.state import GameState
from tests.property.strategies.commands import actors, command


class CommandMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.pipeline = CommandPipeline(validators=(lambda c, s: 'denied' if c.command_id.endswith('deny') else None,))
        self.state = GameState()
        self.pending = []
        self.seen = set()
        self.last = defaultdict(int)
        self.tick = 0
        self.serial = 0
        self.ready_ids = set()

    @rule(actor=actors, kind=st.sampled_from(('valid', 'gap', 'future', 'bad_version', 'mismatch', 'deny', 'duplicate')))
    def submit(self, actor, kind):
        self.serial += 1
        cid = str(self.serial) + ('deny' if kind == 'deny' else '')
        if kind == 'duplicate' and self.seen:
            cid = sorted(self.seen)[0]
        seq = self.last.get(actor, 0) + (2 if kind == 'gap' else 1)
        cmd = command(cid, actor, seq, self.tick + 2 if kind == 'future' else None)
        if kind == 'bad_version':
            from dataclasses import replace
            cmd = replace(cmd, schema_version=COMMAND_SCHEMA_VERSION + 1)
        if kind == 'mismatch':
            from dataclasses import replace
            cmd = replace(cmd, actor_id=actor + '_other')
        self.pipeline.submit(cmd)
        self.pending.append(cmd)

    @rule(delta=st.integers(0, 3))
    def advance(self, delta):
        self.tick += delta
        self.check_prepare()

    @rule()
    def process(self):
        self.check_prepare()

    def check_prepare(self):
        ready, rejected, deferred = [], [], []
        blocked = set()
        for cmd in self.pending:
            if cmd.actor_id in blocked or (cmd.target_tick is not None and cmd.target_tick > self.tick):
                blocked.add(cmd.actor_id)
                deferred.append(cmd)
                continue
            invalid = (cmd.schema_version != COMMAND_SCHEMA_VERSION or not cmd.command_id
                       or cmd.command_id in self.seen or not cmd.actor_id
                       or cmd.action.player_id != cmd.actor_id
                       or cmd.sequence != self.last.get(cmd.actor_id, 0) + 1)
            self.seen.add(cmd.command_id)
            if invalid:
                rejected.append((cmd.command_id, 'protocol_error'))
                continue
            self.last[cmd.actor_id] = cmd.sequence
            if cmd.command_id.endswith('deny'):
                rejected.append((cmd.command_id, 'validation_error'))
            else:
                assert cmd.command_id not in self.ready_ids
                self.ready_ids.add(cmd.command_id)
                ready.append(cmd)
        result = self.pipeline.prepare(self.state, self.tick)
        assert list(result.ready) == ready
        assert [(r.command_id, r.code) for r in result.rejected] == rejected
        self.pending = deferred

    @invariant()
    def queue_and_sequences_match(self):
        assert self.pipeline._pending == self.pending
        assert dict(self.pipeline._last_sequence) == dict(self.last)


TestCommandMachine = CommandMachine.TestCase
