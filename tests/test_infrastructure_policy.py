from __future__ import annotations

import unittest

from modules.base.systems.world.infrastructure_policy import (
    DEFAULT_CATEGORY_POLICIES,
    aggregate_weighted_values,
    apply_infrastructure_damage,
    calculate_infrastructure_capacity,
    configured_category_policies,
    depreciate_infrastructure_condition,
    quote_infrastructure_cost,
    reconstruct_infrastructure_capacity,
)


class InfrastructurePolicyTest(unittest.TestCase):
    def test_category_configuration_and_quote_are_bounded_and_deterministic(self):
        self.assertEqual(
            set(DEFAULT_CATEGORY_POLICIES),
            {"transport", "utilities", "industrial", "telecom"},
        )
        quote = quote_infrastructure_cost("transport", 0.2, 0.5)
        self.assertGreater(quote, 0.0)
        self.assertEqual(quote, quote_infrastructure_cost("transport", 0.2, 0.5))
        self.assertGreater(quote_infrastructure_cost("transport", 0.2, 0.5, regional_scale=2.0), quote)
        with self.assertRaises(ValueError):
            quote_infrastructure_cost("transport", 0.5, 0.4)

    def test_scenario_can_define_an_additional_fully_configured_category(self):
        policies = configured_category_policies(
            {
                "airports": {
                    "baseline": 0.1,
                    "maximum": 0.8,
                    "construction_cost_per_level": 200_000,
                    "construction_minutes_per_level": 10_000,
                    "maintenance_cost_per_level_month": 400,
                    "annual_depreciation": 0.02,
                },
                "invalid": {"baseline": 0.2},
            }
        )

        self.assertIn("airports", policies)
        self.assertNotIn("invalid", policies)
        self.assertEqual(quote_infrastructure_cost("airports", 0.1, 0.2, policies=policies), 20_000)

    def test_capacity_depreciation_and_reconstruction_stay_within_bounds(self):
        self.assertAlmostEqual(calculate_infrastructure_capacity(0.8, 0.5, 1.0), 0.4)
        self.assertEqual(calculate_infrastructure_capacity(2.0, 2.0, 1.0), 1.0)
        self.assertEqual(
            depreciate_infrastructure_condition(0.01, 525_600, annual_rate=0.2, maintenance_ratio=0.0),
            0.0,
        )
        self.assertEqual(reconstruct_infrastructure_capacity(0.7, 0.5, restoration_ceiling=0.8), 0.8)

    def test_aggregation_uses_positive_weights_and_has_deterministic_empty_value(self):
        self.assertAlmostEqual(aggregate_weighted_values([0.2, 0.8], [3.0, 1.0]), 0.35)
        self.assertEqual(aggregate_weighted_values([0.2, 0.8], [0.0, -1.0]), 0.0)

    def test_damage_is_source_idempotent_and_records_recovery_ceiling(self):
        profile = {"level": 0.8, "condition": 1.0, "capacity": 0.8}
        damaged, record = apply_infrastructure_damage(
            profile,
            source_id="impact-1",
            source_type="strategic",
            severity=0.25,
            now_minute=120,
        )
        self.assertLess(damaged["condition"], profile["condition"])
        self.assertEqual(record["restoration_ceiling"], profile["capacity"])
        repeated, duplicate_record = apply_infrastructure_damage(
            damaged,
            source_id="impact-1",
            source_type="strategic",
            severity=0.25,
            now_minute=120,
        )
        self.assertEqual(repeated, damaged)
        self.assertIsNone(duplicate_record)


if __name__ == "__main__":
    unittest.main()
