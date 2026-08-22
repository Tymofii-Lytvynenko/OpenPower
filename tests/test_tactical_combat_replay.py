import unittest

from tests.test_tactical_combat_fixtures import run_replay_fixture


class TacticalCombatReplayTest(unittest.TestCase):
    def test_identical_inputs_produce_identical_tables_and_events(self) -> None:
        self.assertEqual(run_replay_fixture(), run_replay_fixture())


if __name__ == "__main__":
    unittest.main()
