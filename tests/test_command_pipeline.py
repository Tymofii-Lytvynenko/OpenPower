import unittest
from pathlib import Path

from modules.base.systems.world.time_system import TimeSystem
from src.engine.command_pipeline import CommandPipeline
from src.engine.simulator import Engine
from src.server.session import GameSession
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused, ActionSetTax
from src.shared.commands import CommandEnvelope, CommandStatus
from src.shared.config import GameConfig
from src.shared.state import GameState


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def command(command_id: str, sequence: int, action, target_tick: int | None = None):
    return CommandEnvelope(
        command_id=command_id,
        actor_id=action.player_id,
        sequence=sequence,
        action=action,
        target_tick=target_tick,
    )


class TestCommandPipeline(unittest.TestCase):
    def test_sequences_duplicates_and_target_ticks_are_authoritative(self):
        state = GameState()
        pipeline = CommandPipeline()
        future = command("future", 1, ActionSetPaused("player", True), target_tick=3)
        behind_future = command("behind", 2, ActionSetPaused("player", False))
        pipeline.submit(future)
        pipeline.submit(behind_future)

        first = pipeline.prepare(state, tick=1)
        self.assertEqual(first.ready, ())
        self.assertEqual(first.rejected, ())

        due = pipeline.prepare(state, tick=3)
        self.assertEqual(due.ready, (future, behind_future))

        pipeline.submit(command("future", 3, ActionSetPaused("player", False)))
        duplicate = pipeline.prepare(state, tick=4)
        self.assertEqual(duplicate.rejected[0].status, CommandStatus.REJECTED)
        self.assertEqual(duplicate.rejected[0].code, "protocol_error")
        self.assertIn("Duplicate", duplicate.rejected[0].message)

        pipeline.submit(command("gap", 4, ActionSetPaused("player", False)))
        gap = pipeline.prepare(state, tick=5)
        self.assertIn("expected 3", gap.rejected[0].message)

    def test_policy_rejection_consumes_a_valid_transport_sequence(self):
        def reject_speed(command_envelope, state):
            if isinstance(command_envelope.action, ActionSetGameSpeed):
                return "Speed changes are disabled."
            return None

        pipeline = CommandPipeline(validators=(reject_speed,))
        state = GameState()
        pipeline.submit(command("one", 1, ActionSetGameSpeed("player", 2)))
        rejected = pipeline.prepare(state, tick=1)
        self.assertEqual(rejected.rejected[0].code, "validation_error")

        second = command("two", 2, ActionSetPaused("player", True))
        pipeline.submit(second)
        self.assertEqual(pipeline.prepare(state, tick=2).ready, (second,))

    def test_session_rejects_actions_without_a_registered_consumer(self):
        engine = Engine()
        engine.register_systems([TimeSystem()])
        session = GameSession(
            GameConfig(PROJECT_ROOT),
            None,
            None,
            engine,
            None,
            GameState(),
        )

        session.receive_action(ActionSetTax("player", "USA", 0.3))
        session.tick(0.1)
        rejected = session.state.journal.command_results[-1]
        self.assertEqual(rejected["status"], CommandStatus.REJECTED.value)
        self.assertIn("No simulation system handles ActionSetTax", rejected["message"])

        session.receive_action(ActionSetPaused("player", True))
        session.tick(0.1)
        accepted = session.state.journal.command_results[-1]
        self.assertEqual(accepted["status"], CommandStatus.EXECUTED.value)
        self.assertTrue(session.state.time.is_paused)
        self.assertEqual(session.state.determinism.id_sequence, 0)


if __name__ == "__main__":
    unittest.main()
