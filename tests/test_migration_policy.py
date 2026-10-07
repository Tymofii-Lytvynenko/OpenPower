import unittest

import polars as pl

from modules.base.systems.demographics.migration_policy import (
    assess_destination_capacity,
    build_route_index,
    calculate_migrant_cohorts,
    evaluate_border_access,
)


class TestMigrationPolicy(unittest.TestCase):
    def test_route_index_is_bidirectional_and_stably_sorted(self):
        adjacency = pl.DataFrame({
            "region_id": [2, 1, 3],
            "neighbor_region_id": [3, 2, 2],
        })

        self.assertEqual(
            build_route_index(adjacency),
            {1: (2,), 2: (1, 3), 3: (2,)},
        )

    def test_migrant_cohorts_are_integer_conserved_and_deterministic(self):
        source = {"pop_14": 30, "pop_15_64": 60, "pop_65": 10}

        first = calculate_migrant_cohorts(37, source, skilled_worker_preference=0.5)
        second = calculate_migrant_cohorts(37, source, skilled_worker_preference=0.5)

        self.assertEqual(first, second)
        self.assertEqual(sum(first), 37)
        self.assertTrue(all(type(value) is int and value >= 0 for value in first))
        self.assertEqual(calculate_migrant_cohorts(1, source), (0, 1, 0))
        self.assertEqual(calculate_migrant_cohorts(0, source), (0, 0, 0))

    def test_empty_destination_requires_positive_explicit_capacity_and_access(self):
        unsupported = assess_destination_capacity(
            {"id": 2, "owner": "BBB", "transport_access": 0.8, "health_capacity": 0.8},
            current_population=0,
        )
        supported = assess_destination_capacity(
            {
                "id": 2,
                "owner": "BBB",
                "housing_capacity": 500,
                "employment_capacity": 450,
                "service_capacity": 400,
                "transport_access": 0.8,
                "health_capacity": 0.8,
            },
            current_population=0,
            reserved_population=50,
        )

        self.assertFalse(unsupported.eligible)
        self.assertEqual(unsupported.reason_code, "no_destination_capacity")
        self.assertTrue(supported.eligible)
        self.assertEqual(supported.available_people, 350)

    def test_existing_region_uses_explicit_transport_capacity_for_reserved_arrivals(self):
        capacity = assess_destination_capacity(
            {
                "housing_capacity": 2_000,
                "employment_capacity": 2_000,
                "service_capacity": 2_000,
                "transport_capacity": 2_000,
                "transport_access": 1.0,
            },
            current_population=1_000,
        )

        self.assertTrue(capacity.eligible)
        self.assertEqual(capacity.available_people, 1_000)

    def test_closed_border_rejects_new_international_flow(self):
        closed = self._policy(border_policy="closed")
        decision = evaluate_border_access(
            "AAA", "BBB", self._policy(), closed
        )

        self.assertFalse(decision.eligible)
        self.assertEqual(decision.reason_code, "border_closed")

    def test_hostile_relation_blocks_mobility_unless_explicit_access_agreement_exists(self):
        relations = pl.DataFrame({
            "source": ["AAA", "BBB"],
            "target": ["BBB", "AAA"],
            "value": [-80.0, -75.0],
        })
        access = pl.DataFrame({
            "treaty_id": ["free-movement"],
            "country_id": ["AAA"],
            "effect": ["migration_mobility_access"],
            "value": [1.0],
            "detail": ["BBB"],
        })

        blocked = evaluate_border_access(
            "AAA", "BBB", self._policy(), self._policy(), relations=relations
        )
        permitted = evaluate_border_access(
            "AAA",
            "BBB",
            self._policy(),
            self._policy(),
            relations=relations,
            treaty_effects=access,
        )

        self.assertEqual(blocked.reason_code, "hostile_relations")
        self.assertTrue(permitted.eligible)
        self.assertEqual(permitted.reason_code, "eligible_mobility_agreement")

    def test_active_war_and_explicit_movement_sanction_are_hard_blocks(self):
        access = pl.DataFrame({
            "treaty_id": ["free-movement"],
            "country_id": ["AAA"],
            "effect": ["migration_mobility_access"],
            "value": [1.0],
            "detail": ["BBB"],
        })
        war = pl.DataFrame({
            "id": ["war-1"],
            "side_a": [["AAA"]],
            "side_b": [["BBB"]],
            "status": ["active"],
        })
        sanction = pl.DataFrame({
            "treaty_id": ["sanction-1"],
            "country_id": ["AAA"],
            "effect": ["migration_mobility_restriction"],
            "value": [1.0],
            "detail": ["BBB"],
        })

        at_war = evaluate_border_access(
            "AAA", "BBB", self._policy(), self._policy(), wars=war, treaty_effects=access
        )
        sanctioned = evaluate_border_access(
            "AAA", "BBB", self._policy(), self._policy(), treaty_effects=sanction
        )

        self.assertEqual(at_war.reason_code, "at_war")
        self.assertEqual(sanctioned.reason_code, "sanction_restricted")

    @staticmethod
    def _policy(**overrides):
        policy = {
            "migration_policy": "open",
            "border_policy": "open",
            "entry_rate": 1.0,
            "exit_rate": 1.0,
            "asylum_rate": 1.0,
            "family_reunification_rate": 1.0,
            "skilled_worker_preference": 0.0,
            "enforcement_strength": 0.0,
        }
        policy.update(overrides)
        return policy


if __name__ == "__main__":
    unittest.main()
