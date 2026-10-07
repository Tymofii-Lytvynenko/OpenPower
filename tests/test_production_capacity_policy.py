from __future__ import annotations

import unittest

from modules.base.systems.military.production_policy import (
    allocate_production_capacity,
    annual_production_capacity,
)


class ProductionCapacityPolicyTest(unittest.TestCase):
    def test_capacity_uses_output_health_and_coefficient(self) -> None:
        self.assertEqual(annual_production_capacity(100.0, 0.5, 2.0), 100.0)
        self.assertEqual(annual_production_capacity(100.0, 2.0, 2.0), 200.0)
        self.assertEqual(annual_production_capacity(100.0, -1.0, 2.0), 0.0)

    def test_priority_allocation_serves_one_partial_order_then_queues_rest(self) -> None:
        orders = [
            self._order("low-b", 1, 30.0),
            self._order("high", 2, 40.0),
            self._order("low-a", 1, 20.0),
        ]

        result = allocate_production_capacity(orders, {"USA": 100.0}, 0.5)
        by_id = {row["id"]: row for row in result}

        self.assertEqual(by_id["high"]["status"], "completed")
        self.assertEqual(by_id["high"]["remaining_work"], 0.0)
        self.assertEqual(by_id["low-a"]["assigned_capacity"], 10.0)
        self.assertAlmostEqual(by_id["low-a"]["progress"], 0.5)
        self.assertEqual(by_id["low-b"]["assigned_capacity"], 0.0)
        self.assertEqual(by_id["low-b"]["blocking_reason"], "Waiting for higher-priority orders.")

    def test_pause_and_proportional_policy_preserve_remaining_work(self) -> None:
        orders = [self._order("a", 1, 80.0), self._order("b", 1, 20.0)]
        orders[1]["status"] = "paused"
        result = allocate_production_capacity(orders, {"USA": 50.0}, 1.0, "proportional")
        by_id = {row["id"]: row for row in result}

        self.assertEqual(by_id["a"]["assigned_capacity"], 50.0)
        self.assertEqual(by_id["a"]["remaining_work"], 30.0)
        self.assertEqual(by_id["b"]["status"], "paused")
        self.assertEqual(by_id["b"]["remaining_work"], 20.0)
        self.assertEqual(by_id["b"]["blocking_reason"], "Order is paused.")

    def _order(self, order_id: str, priority: int, work: float) -> dict[str, object]:
        return {
            "id": order_id,
            "country_id": "USA",
            "priority": priority,
            "status": "queued",
            "work_required": work,
            "remaining_work": work,
            "progress": 0.0,
        }


if __name__ == "__main__":
    unittest.main()
