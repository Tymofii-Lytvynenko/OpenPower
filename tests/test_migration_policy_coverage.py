import unittest

import polars as pl

from modules.base.systems.demographics.migration_policy import (
    assess_destination_capacity,
    build_route_index,
    calculate_migrant_cohorts,
    estimate_migration_count,
    evaluate_border_access,
    _finite,
)


class MigrationPolicyCoverageTest(unittest.TestCase):
    def test_route_index_handles_absent_schema_invalid_values_and_self_edges(self) -> None:
        self.assertEqual(build_route_index(None), {})
        self.assertEqual(build_route_index(pl.DataFrame()), {})
        self.assertEqual(build_route_index(pl.DataFrame({"region_id": [1]})), {})

        adjacency = pl.DataFrame(
            {
                "region_id": [1.0, 2.0, float("nan"), float("inf")],
                "neighbor_region_id": [1.0, 3.0, 4.0, 5.0],
            }
        )
        self.assertEqual(build_route_index(adjacency), {2: (3,), 3: (2,)})

    def test_cohort_allocation_obeys_family_limit_and_zero_reunification(self) -> None:
        children_only = {"pop_14": 100, "pop_15_64": 0, "pop_65": 0}
        self.assertEqual(
            calculate_migrant_cohorts(
                10,
                children_only,
                family_reunification_rate=0.0,
            ),
            (0, 0, 0),
        )

        allocation = calculate_migrant_cohorts(
            80,
            {"pop_14": 90, "pop_15_64": 2, "pop_65": 1},
            skilled_worker_preference=0.8,
            family_reunification_rate=0.1,
        )
        self.assertEqual(allocation, (9, 2, 1))
        self.assertEqual(sum(allocation), 12)

    def test_cohort_allocation_skips_dependents_after_zero_family_limit(self) -> None:
        allocation = calculate_migrant_cohorts(
            1,
            {"pop_14": 1, "pop_15_64": 0, "pop_65": 1},
            family_reunification_rate=0.0,
        )
        self.assertEqual(allocation, (0, 0, 1))

    def test_empty_destination_requires_positive_transport_access(self) -> None:
        capacity = assess_destination_capacity(
            {
                "housing_capacity": 500,
                "employment_capacity": 450,
                "service_capacity": 400,
                "transport_capacity": 350,
                "transport_access": 0.0,
            },
            current_population=0,
        )
        self.assertFalse(capacity.eligible)
        self.assertEqual(capacity.reason_code, "no_destination_capacity")

    def test_zero_transport_capacity_uses_the_other_destination_limits(self) -> None:
        capacity = assess_destination_capacity(
            {
                "housing_capacity": 500,
                "employment_capacity": 450,
                "service_capacity": 400,
                "transport_capacity": 0,
                "transport_access": 1.0,
            },
            current_population=0,
        )

        self.assertTrue(capacity.eligible)
        self.assertEqual(capacity.total_capacity, 400)
        self.assertEqual(capacity.available_people, 400)

    def test_movement_sanctions_and_hostile_relations_restrict_access(self) -> None:
        policy = self._policy()
        restriction = pl.DataFrame(
            {
                "country_id": ["AAA"],
                "effect": ["migration_mobility_restriction"],
                "value": [1.0],
                "detail": ["BBB"],
            }
        )
        self.assertEqual(
            evaluate_border_access(
                "AAA", "BBB", policy, policy, treaty_effects=restriction
            ).reason_code,
            "sanction_restricted",
        )

        hostile_relations = pl.DataFrame(
            {"source": ["AAA"], "target": ["BBB"], "value": [-100.0]}
        )
        self.assertEqual(
            evaluate_border_access(
                "AAA", "BBB", policy, policy, relations=hostile_relations
            ).reason_code,
            "hostile_relations",
        )

    def test_relation_lookup_ignores_unrelated_pairs(self) -> None:
        policy = self._policy()
        relations = pl.DataFrame(
            {"source": ["CCC"], "target": ["DDD"], "value": [-100.0]}
        )

        decision = evaluate_border_access(
            "AAA", "BBB", policy, policy, relations=relations
        )

        self.assertTrue(decision.eligible)
        self.assertEqual(decision.reason_code, "eligible_international")

    def test_invalid_numeric_policy_values_use_the_requested_default(self) -> None:
        self.assertEqual(_finite(None, 0.25), 0.25)
        self.assertEqual(_finite("invalid", 0.25), 0.25)

    def test_border_access_handles_identity_restrictions_and_incomplete_tables(self) -> None:
        policy = self._policy()
        self.assertEqual(
            evaluate_border_access("", "BBB", policy, policy).reason_code,
            "unknown_country",
        )
        self.assertEqual(
            evaluate_border_access("AAA", "aaa", policy, policy).reason_code,
            "eligible_domestic",
        )
        self.assertEqual(
            evaluate_border_access(
                "AAA", "BBB", self._policy(exit_rate=0.0), policy
            ).reason_code,
            "exit_restricted",
        )
        self.assertEqual(
            evaluate_border_access(
                "AAA", "BBB", policy, self._policy(entry_rate=0.0)
            ).reason_code,
            "entry_restricted",
        )

        no_relation_contract = pl.DataFrame({"source": ["AAA"]})
        no_effect_contract = pl.DataFrame({"unrelated_column": ["AAA"]})
        decision = evaluate_border_access(
            "AAA",
            "BBB",
            policy,
            policy,
            relations=no_relation_contract,
            treaty_effects=no_effect_contract,
        )
        self.assertTrue(decision.eligible)

    def test_inactive_and_legacy_tagged_wars_are_interpreted_safely(self) -> None:
        policy = self._policy()
        inactive = pl.DataFrame(
            {
                "status": ["concluded"],
                "side_a": [None],
                "side_b": [None],
                "attacker_tag": ["AAA"],
                "defender_tag": ["BBB"],
            }
        )
        self.assertTrue(
            evaluate_border_access("AAA", "BBB", policy, policy, wars=inactive).eligible
        )

        legacy_war = pl.DataFrame(
            {
                "status": ["ongoing"],
                "side_a": [None],
                "side_b": [None],
                "attacker_tag": ["AAA"],
                "defender_tag": ["BBB"],
            }
        )
        self.assertEqual(
            evaluate_border_access("AAA", "BBB", policy, policy, wars=legacy_war).reason_code,
            "at_war",
        )

        unrelated_war = pl.DataFrame(
            {
                "status": ["active"],
                "side_a": [["CCC"]],
                "side_b": [["DDD"]],
            }
        )
        self.assertTrue(
            evaluate_border_access(
                "AAA", "BBB", policy, policy, wars=unrelated_war
            ).eligible
        )

        string_sides = pl.DataFrame(
            {
                "status": ["active"],
                "side_a": ["AAA;CCC"],
                "side_b": ["BBB"],
            }
        )
        self.assertEqual(
            evaluate_border_access(
                "AAA", "BBB", policy, policy, wars=string_sides
            ).reason_code,
            "at_war",
        )

    def test_movement_effects_ignore_irrelevant_inactive_and_foreign_rows(self) -> None:
        policy = self._policy()
        effects = pl.DataFrame(
            {
                "country_id": ["AAA", "AAA", "CCC", "AAA"],
                "effect": [
                    "unrelated_effect",
                    "migration_mobility_restriction",
                    "migration_mobility_restriction",
                    "migration_mobility_access",
                ],
                "value": [1.0, 0.0, 1.0, 0.0],
                "detail": ["BBB", "BBB", "BBB", "BBB"],
            }
        )

        decision = evaluate_border_access(
            "AAA", "BBB", policy, policy, treaty_effects=effects
        )

        self.assertTrue(decision.eligible)
        self.assertFalse(decision.mobility_agreement)

    def test_detail_formats_grant_only_matching_mobility_access(self) -> None:
        policy = self._policy()
        for detail in ("", '"BBB"', '{"target":"BBB"}', "BBB;CCC"):
            with self.subTest(detail=detail):
                effect = pl.DataFrame(
                    {
                        "country_id": ["AAA"],
                        "effect": ["migration_mobility_access"],
                        "value": [1.0],
                        "detail": [detail],
                    }
                )
                decision = evaluate_border_access(
                    "AAA", "BBB", policy, policy, treaty_effects=effect
                )
                self.assertTrue(decision.eligible)
                self.assertTrue(decision.mobility_agreement)

    def test_migration_estimate_returns_zero_without_source_or_capacity(self) -> None:
        empty_result = estimate_migration_count(
            {},
            {},
            {},
            {},
            access_rate=1.0,
            source_available=0,
            destination_available=100,
        )
        self.assertEqual(empty_result, (0, 0.0))

        no_capacity = estimate_migration_count(
            {},
            {},
            {},
            {},
            access_rate=1.0,
            source_available=100,
            destination_available=0,
        )
        self.assertEqual(no_capacity, (0, 0.0))

    @staticmethod
    def _policy(**overrides):
        policy = {
            "migration_policy": "open",
            "border_policy": "open",
            "entry_rate": 1.0,
            "exit_rate": 1.0,
        }
        policy.update(overrides)
        return policy


if __name__ == "__main__":
    unittest.main()
