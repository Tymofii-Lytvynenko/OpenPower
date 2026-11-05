import unittest

from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel


class UnitProductionQuantityStepperTests(unittest.TestCase):
    def test_held_up_arrow_uses_source_steps_and_release_stops_repeating(self):
        panel = UnitProductionPanel()
        panel._quantity = 50

        panel._advance_quantity_stepper(
            "up", active=True, clicked=False, direction=1, now=0.0
        )
        self.assertEqual(panel._quantity, 51)

        repeat = panel._quantity_repeat["up"]
        increments = []
        for _ in range(10):
            now = repeat.next_repeat_at + 0.001
            previous = panel._quantity
            panel._advance_quantity_stepper(
                "up", active=True, clicked=False, direction=1, now=now
            )
            increments.append(panel._quantity - previous)

        self.assertEqual(increments[:9], [1] * 9)
        self.assertEqual(increments[9], 10)
        self.assertEqual(panel._quantity, 70)

        panel._advance_quantity_stepper(
            "up", active=False, clicked=True, direction=1,
            now=repeat.next_repeat_at + 0.1,
        )
        self.assertEqual(panel._quantity, 70)

    def test_down_arrow_stops_at_zero(self):
        panel = UnitProductionPanel()
        panel._quantity = 1

        panel._advance_quantity_stepper(
            "down", active=True, clicked=False, direction=-1, now=0.0
        )
        self.assertEqual(panel._quantity, 0)

        repeat = panel._quantity_repeat["down"]
        panel._advance_quantity_stepper(
            "down", active=True, clicked=False, direction=-1,
            now=repeat.next_repeat_at + 0.001,
        )
        self.assertEqual(panel._quantity, 0)


if __name__ == "__main__":
    unittest.main()
