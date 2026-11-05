import unittest

from src.client.ui.components.shared.gml_value_repeat import GMLValueRepeat, GMLValueRepeatPair


class GMLValueRepeatTests(unittest.TestCase):
    def test_arrow_pair_keeps_independent_timers_and_resets_both(self):
        pair = GMLValueRepeatPair()
        value, _ = pair["up"].advance(
            5, active=True, clicked=False, direction=1, now=0.0, minimum=0, maximum=10
        )
        self.assertEqual(value, 6)
        self.assertTrue(pair["up"].active)
        self.assertFalse(pair["down"].active)
        pair["down"].advance(
            value, active=True, clicked=False, direction=-1, now=0.2, minimum=0, maximum=10
        )
        pair.reset()
        self.assertFalse(pair["up"].active)
        self.assertFalse(pair["down"].active)
        with self.assertRaises(KeyError):
            pair["invalid"]

    def test_click_changes_once_and_release_does_not_repeat(self):
        repeat = GMLValueRepeat()

        value, changed = repeat.advance(
            4, active=True, clicked=False, direction=1, now=0.0, minimum=1, maximum=48
        )
        self.assertEqual((value, changed), (5, True))

        value, changed = repeat.advance(
            value, active=False, clicked=True, direction=1, now=0.1, minimum=1, maximum=48
        )
        self.assertEqual((value, changed), (5, False))

    def test_held_arrow_accelerates_after_the_source_repeat_threshold(self):
        repeat = GMLValueRepeat()
        value, _ = repeat.advance(
            1, active=True, clicked=False, direction=1, now=0.0, minimum=1, maximum=48
        )

        now = 0.5
        value_at_initial_delay, changed = repeat.advance(
            value, active=True, clicked=False, direction=1, now=now, minimum=1, maximum=48
        )
        self.assertFalse(changed)
        self.assertEqual(value_at_initial_delay, 2)

        for _ in range(10):
            now = repeat.next_repeat_at + 0.001
            value, changed = repeat.advance(
                value, active=True, clicked=False, direction=1, now=now,
                minimum=1, maximum=48,
            )
            self.assertTrue(changed)

        self.assertEqual(value, 21)
        self.assertEqual(repeat.repeat_count, 10)

    def test_repeat_respects_quantity_bounds_and_resets_on_release(self):
        repeat = GMLValueRepeat()
        value, _ = repeat.advance(
            47, active=True, clicked=False, direction=1, now=0.0, minimum=1, maximum=48
        )
        self.assertEqual(value, 48)

        value, changed = repeat.advance(
            value, active=True, clicked=False, direction=1, now=1.0, minimum=1, maximum=48
        )
        self.assertEqual((value, changed), (48, False))
        self.assertEqual(repeat.repeat_count, 1)

        value, changed = repeat.advance(
            value, active=False, clicked=False, direction=1, now=1.1, minimum=1, maximum=48
        )
        self.assertEqual((value, changed), (48, False))
        self.assertFalse(repeat.active)

    def test_hold_repeat_uses_source_increment_thresholds(self):
        repeat = GMLValueRepeat()
        value, _ = repeat.advance(
            1, active=True, clicked=False, direction=1, now=0.0,
            minimum=1, maximum=2000,
        )

        increments = []
        now = 0.0
        for _ in range(100):
            now = repeat.next_repeat_at + 0.001
            previous = value
            value, changed = repeat.advance(
                value, active=True, clicked=False, direction=1, now=now,
                minimum=1, maximum=2000,
            )
            self.assertTrue(changed)
            increments.append(value - previous)

        self.assertEqual(increments[:9], [1] * 9)
        self.assertEqual(increments[9:99], [10] * 90)
        self.assertEqual(increments[99], 100)
        self.assertEqual(value, 1011)

    def test_two_rate_steps_switch_after_ten_repeats(self):
        repeat = GMLValueRepeat()
        value, _ = repeat.advance(
            50, active=True, clicked=False, direction=1, now=0.0,
            minimum=0, maximum=500, step_tiers=((10, 10),),
        )

        now = 0.0
        for _ in range(10):
            now = repeat.next_repeat_at + 0.001
            previous = value
            value, changed = repeat.advance(
                value, active=True, clicked=False, direction=1, now=now,
                minimum=0, maximum=500, step_tiers=((10, 10),),
            )
            self.assertTrue(changed)
            self.assertEqual(value - previous, 1)

        now = repeat.next_repeat_at + 0.001
        value, changed = repeat.advance(
            value, active=True, clicked=False, direction=1, now=now,
            minimum=0, maximum=500, step_tiers=((10, 10),),
        )
        self.assertTrue(changed)
        self.assertEqual(value, 71)


if __name__ == "__main__":
    unittest.main()
