import unittest

from src.client.services.client_game_clock import ClientGameClock
from src.shared.state import TimeData


class ClientGameClockTest(unittest.TestCase):
    def test_clock_advances_every_render_frame_between_snapshots(self) -> None:
        clock = ClientGameClock()
        clock.sync(TimeData(total_minutes=100, speed_level=1, is_paused=False))

        clock.advance(1.0 / 60.0)

        self.assertAlmostEqual(clock.display_minutes, 100.5)

    def test_paused_clock_remains_stationary(self) -> None:
        clock = ClientGameClock()
        clock.sync(TimeData(total_minutes=100, speed_level=3, is_paused=True))

        clock.advance(0.5)

        self.assertEqual(clock.display_minutes, 100.0)

    def test_small_reconciliation_never_reverses_running_clock(self) -> None:
        clock = ClientGameClock()
        clock.sync(TimeData(total_minutes=100, speed_level=1, is_paused=False))
        clock.advance(0.1)
        before_sync = clock.display_minutes
        clock.sync(TimeData(total_minutes=102, speed_level=1, is_paused=False))

        clock.advance(1.0 / 60.0)

        self.assertGreater(clock.display_minutes, before_sync)

    def test_speed_change_reanchors_to_authoritative_time(self) -> None:
        clock = ClientGameClock()
        clock.sync(TimeData(total_minutes=100, speed_level=1, is_paused=False))
        clock.advance(0.1)

        clock.sync(TimeData(total_minutes=104, speed_level=4, is_paused=False))

        self.assertEqual(clock.display_minutes, 104.0)


if __name__ == "__main__":
    unittest.main()
