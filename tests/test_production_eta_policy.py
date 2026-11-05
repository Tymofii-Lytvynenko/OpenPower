from __future__ import annotations

import unittest

from modules.base.systems.military.production_policy import initial_production_eta_days


class InitialProductionEtaPolicyTests(unittest.TestCase):
    def test_eta_matches_the_priority_used_when_an_order_is_queued(self):
        for priority, expected in ((100, 1), (50, 1), (7, 4), (1, 30)):
            with self.subTest(priority=priority):
                self.assertEqual(initial_production_eta_days(priority), expected)

    def test_invalid_and_nonpositive_priorities_use_the_lowest_priority(self):
        for priority in (0, -1, None, "invalid"):
            with self.subTest(priority=priority):
                self.assertEqual(initial_production_eta_days(priority), 30)


if __name__ == "__main__":
    unittest.main()
