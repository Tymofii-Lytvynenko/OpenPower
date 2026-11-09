import unittest
from types import SimpleNamespace
from unittest.mock import patch

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.demographics.migration_policy import (
    BorderAccessDecision,
    DestinationCapacity,
)
from modules.base.systems.demographics.migration_system import MigrationSystem
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import EventMigrationFlowResolved
from src.shared.state import GameState


class MigrationSystemCoverageTest(unittest.TestCase):
    def test_system_contract_and_missing_table_guard(self) -> None:
        system = MigrationSystem()

        self.assertEqual(system.id, "base.migration")
        self.assertEqual(
            system.dependencies,
            ["base.population", "base.ai", "base.diplomacy"],
        )
        system.update(GameState(), 1.0)

    def test_normalization_helpers_handle_invalid_values_and_compose_war_tags(self) -> None:
        system = MigrationSystem()

        self.assertEqual(system._policy_source("server"), "scenario")
        self.assertIsNone(system._requested_minute(object(), now=25))
        self.assertEqual(system._integer(object()), 0)
        self.assertEqual(system._bounded_ratio(float("nan"), default=0.4), 0.4)
        self.assertEqual(
            system._country_side_tags(
                {
                    "side_a": "aaa;bbb",
                    "side_b": ["ccc", ""],
                    "attackers": ("ddd",),
                    "defenders": {"eee"},
                    "attacker_tag": "fff",
                    "defender_tag": None,
                }
            ),
            {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF"},
        )

    def test_reason_factor_extension_recovers_invalid_and_non_object_json(self) -> None:
        system = MigrationSystem()

        self.assertEqual(
            system._extend_reason_factors("not-json", source="legacy"),
            '{"source":"legacy"}',
        )
        self.assertEqual(
            system._extend_reason_factors("[]", source="legacy"),
            '{"source":"legacy"}',
        )

    def test_policy_target_uses_defaults_and_rejects_non_numeric_rates(self) -> None:
        system = MigrationSystem()
        base = system._default_policy("AAA", 0)
        default_action = ActionUpdateMigrationPolicy("AAA", "AAA", "open", "open")
        target, reason = system._policy_target(default_action, base)
        self.assertEqual(reason, "")
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target["entry_rate"], base["entry_rate"])

        invalid_action = ActionUpdateMigrationPolicy(
            "AAA", "AAA", "open", "open", entry_rate="not-a-number"
        )
        invalid_target, reason = system._policy_target(invalid_action, base)
        self.assertIsNone(invalid_target)
        self.assertEqual(reason, "invalid_policy_value")

    def test_policy_actions_record_unknown_country_and_invalid_effective_time(self) -> None:
        state = GameState(tables={"countries": pl.DataFrame({"id": ["AAA"]})})
        build_base_schema_registry().ensure_state(state)
        state.current_actions = [
            object(),
            ActionUpdateMigrationPolicy("AAA", "UNKNOWN", "open", "open"),
            ActionUpdateMigrationPolicy(
                "AAA", "AAA", "open", "open", effective_at_minute="invalid"
            ),
        ]

        MigrationSystem()._apply_policy_actions(state, now=25)

        reasons = state.get_table("migration_policy_transitions")["reason_code"].to_list()
        self.assertEqual(reasons, ["unknown_country", "invalid_effective_time"])

    def test_policy_snapshot_applies_prior_scheduled_transition(self) -> None:
        current = {
            "country_id": "AAA",
            "migration_policy": "open",
            "border_policy": "open",
            "entry_rate": 1.0,
            "exit_rate": 0.5,
            "asylum_rate": 0.25,
            "family_reunification_rate": 0.5,
            "skilled_worker_preference": 0.0,
            "enforcement_strength": 0.5,
            "effective_at_minute": 0,
        }
        future = {
            "id": "transition-1",
            "country_id": "AAA",
            "status": "scheduled",
            "effective_at_minute": 150,
            "requested_at_minute": 100,
            "migration_policy": "restricted",
            "border_policy": "closed",
            "entry_rate": 0.0,
        }
        state = GameState(
            tables={
                "migration_policies": pl.DataFrame([current]),
                "migration_policy_transitions": pl.DataFrame([future]),
            }
        )

        snapshot = MigrationSystem()._policy_snapshot(state, "AAA", effective=200)

        self.assertEqual(snapshot["migration_policy"], "restricted")
        self.assertEqual(snapshot["border_policy"], "closed")
        self.assertEqual(snapshot["entry_rate"], 0.0)

    def test_missing_endpoint_authority_and_border_decision_are_rejected(self) -> None:
        system = MigrationSystem()
        batch = SimpleNamespace(country_ids={"AAA", "BBB"})
        endpoints = SimpleNamespace(
            origin_region_id=1,
            destination_region_id=2,
            origin={"owner": "AAA"},
            destination={"owner": "BBB"},
            origin_country_id="AAA",
            destination_country_id="BBB",
        )

        for changed in (
            SimpleNamespace(**{**endpoints.__dict__, "origin": None}),
            SimpleNamespace(**{**endpoints.__dict__, "origin_region_id": 2}),
            SimpleNamespace(**{**endpoints.__dict__, "origin": {"owner": "CCC"}}),
            SimpleNamespace(**{**endpoints.__dict__, "destination": {"owner": "CCC"}}),
            SimpleNamespace(
                **{
                    **endpoints.__dict__,
                    "origin": {"owner": "CCC"},
                    "origin_country_id": "CCC",
                }
            ),
            SimpleNamespace(
                **{
                    **endpoints.__dict__,
                    "destination": {"owner": "CCC"},
                    "destination_country_id": "CCC",
                }
            ),
        ):
            self.assertFalse(system._has_current_flow_authority(batch, changed))

        closed_policy = {
            "migration_policy": "open",
            "border_policy": "closed",
            "entry_rate": 1.0,
            "exit_rate": 1.0,
        }
        open_policy = {**closed_policy, "border_policy": "open"}
        border_batch = SimpleNamespace(
            state=GameState(),
            current_policies={"AAA": closed_policy, "BBB": open_policy},
        )
        self.assertFalse(
            system._flow_border_is_eligible(
                border_batch,
                {"transition_rule": "revalidate"},
                endpoints,
            )
        )

    def test_due_flow_is_cancelled_when_authority_or_border_changes(self) -> None:
        system = MigrationSystem()
        flow = {
            "id": "flow-1",
            "origin_region_id": 1,
            "destination_region_id": 2,
            "origin_country_id": "AAA",
            "destination_country_id": "BBB",
            "population_count": 10,
            "transition_rule": "revalidate",
        }
        closed_policy = self._policy(border_policy="closed")
        open_policy = self._policy()
        batch = SimpleNamespace(
            state=GameState(),
            now=200,
            regions={1: {"id": 1, "owner": "CCC"}, 2: {"id": 2, "owner": "BBB"}},
            country_ids={"AAA", "BBB", "CCC"},
            current_policies={"AAA": closed_policy, "BBB": open_policy},
            updates=[],
        )

        system._process_due_flow(batch, flow)
        self.assertEqual(batch.updates[-1]["reason_code"], "authority_changed")

        batch.regions[1]["owner"] = "AAA"
        batch.updates.clear()
        system._process_due_flow(batch, flow)
        self.assertEqual(batch.updates[-1]["reason_code"], "border_changed")

    def test_cancelled_flow_batch_persists_a_resolution_event(self) -> None:
        system = MigrationSystem()
        regions = pl.DataFrame({"id": [1]})
        flows = pl.DataFrame(
            {
                "id": ["flow-1"],
                "status": ["pending"],
                "population_count": [10],
                "reason_code": ["eligible_international"],
            }
        )
        state = GameState(tables={"regions": regions, "migration_flows": flows})
        batch = SimpleNamespace(
            state=state,
            now=200,
            regions_frame=regions,
            region_rows=regions.to_dicts(),
            updates=[
                {
                    "id": "flow-1",
                    "status": "cancelled",
                    "population_count": 10,
                    "reason_code": "authority_changed",
                }
            ],
            redirected_flows=[],
        )

        system._persist_due_flow_batch(batch)

        self.assertEqual(state.get_table("migration_flows")["status"].to_list(), ["cancelled"])
        self.assertTrue(any(isinstance(event, EventMigrationFlowResolved) for event in state.events))

    def test_redirect_attempt_without_alternate_leaves_flow_unredirected(self) -> None:
        system = MigrationSystem()
        availability = SimpleNamespace(
            capacity=DestinationCapacity(False, 10, 10, "no_destination_capacity"),
            planned_count=20,
            available_total=40,
        )
        batch = SimpleNamespace(
            regions={1: {"id": 1, "owner": "AAA"}},
            state=GameState(),
            country_ids={"AAA"},
            current_policies={},
            reserved_in={},
            pending_routes=set(),
            now=200,
        )
        endpoints = SimpleNamespace(origin_region_id=1, destination_region_id=2)
        with patch.object(system, "_find_redirect_destination", return_value=None):
            self.assertFalse(
                system._redirect_due_flow(batch, {"id": "flow-1"}, endpoints, availability)
            )

        fallback = system._redirected_cohorts(
            {"dependent_count": 1, "working_age_count": 1, "elderly_count": 0},
            SimpleNamespace(
                planned_count=20,
                available_source={"pop_14": 10, "pop_15_64": 15, "pop_65": 5},
            ),
        )
        self.assertEqual(sum(fallback), 20)

    def test_completion_cancellation_reasons_cover_source_and_capacity_changes(self) -> None:
        system = MigrationSystem()
        flow = {"id": "flow-1", "population_count": 10}
        endpoints = SimpleNamespace(origin_region_id=1, destination_region_id=2)
        batch = SimpleNamespace(now=200, updates=[])

        system._complete_available_flow(
            batch,
            flow,
            endpoints,
            SimpleNamespace(count=0, available_total=0, capacity=DestinationCapacity(True, 10, 10, "ok")),
        )
        system._complete_available_flow(
            batch,
            flow,
            endpoints,
            SimpleNamespace(count=0, available_total=5, capacity=DestinationCapacity(True, 10, 10, "ok")),
        )
        self.assertEqual(
            [row["reason_code"] for row in batch.updates],
            ["source_cohort_limit", "capacity_changed"],
        )
        self.assertEqual(system._completed_flow_reason(5, 10, 12), "capacity_changed")

        system._complete_available_flow(
            batch,
            flow,
            endpoints,
            SimpleNamespace(
                count=1,
                available_total=5,
                available_source={"pop_14": 0, "pop_15_64": 0, "pop_65": 0},
                capacity=DestinationCapacity(True, 10, 10, "ok"),
            ),
        )
        self.assertEqual(batch.updates[-1]["reason_code"], "source_cohort_limit")

    def test_redirect_destination_skips_unknown_closed_and_under_capacity_regions(self) -> None:
        state = GameState(
            tables={
                "region_adjacency": pl.DataFrame(
                    {"region_id": [1, 1, 1, 1], "neighbor_region_id": [2, 3, 4, 5]}
                )
            }
        )
        origin = self._region(1, "AAA", 0, 100, 0, 200)
        regions = {
            1: origin,
            2: self._region(2, "", 0, 0, 0, 100),
            3: self._region(3, "BBB", 0, 0, 0, 100),
            4: self._region(4, "CCC", 0, 95, 0, 100),
            5: self._region(5, "BBB", 0, 0, 0, 100),
        }
        policies = {"AAA": self._policy(), "BBB": self._policy(border_policy="closed"), "CCC": self._policy()}

        result = MigrationSystem()._find_redirect_destination(
            state,
            origin,
            excluded_destination_id=99,
            requested_population=20,
            regions=regions,
            country_ids={"AAA", "BBB", "CCC"},
            policies=policies,
            reserved_in={},
            pending_routes={(1, 5)},
        )

        self.assertIsNone(result)

    def test_route_candidate_and_pair_reject_duplicates_and_invalid_endpoints(self) -> None:
        system = MigrationSystem()
        batch = SimpleNamespace(
            region_map={},
            country_map={},
            now=1,
            known_flow_ids=set(),
            policies={},
            pending_routes=set(),
            state=GameState(),
        )
        self.assertIsNone(system._route_candidate(batch, 1, 2))

        batch.region_map = {1: {"owner": ""}, 2: {"owner": "BBB"}}
        self.assertIsNone(system._route_candidate(batch, 1, 2))
        batch.region_map = {1: {"owner": "AAA"}, 2: {"owner": "BBB"}}
        self.assertIsNone(system._route_candidate(batch, 1, 2))
        batch.country_map = {"AAA": {}, "BBB": {}}
        batch.known_flow_ids = {"migration-000000000001-1-2"}
        self.assertIsNone(system._route_candidate(batch, 1, 2))

        batch.pending_routes = {(1, 2)}
        system._evaluate_route_pair(batch, 1, 2)
        batch.pending_routes.clear()
        with patch.object(system, "_route_candidate", return_value=None):
            system._evaluate_route_pair(batch, 1, 2)

        candidate = SimpleNamespace(origin_country_id="AAA", destination_country_id="BBB")
        with (
            patch.object(system, "_route_candidate", return_value=candidate),
            patch.object(system, "_border_decision", return_value=BorderAccessDecision(False, "border_closed")),
            patch.object(system, "_record_rejected_route") as record_rejected,
        ):
            system._evaluate_route_pair(batch, 1, 2)
        record_rejected.assert_called_once_with(batch, candidate, "border_closed")

    def test_route_record_stops_when_estimate_or_cohort_allocation_is_empty(self) -> None:
        system = MigrationSystem()
        candidate = SimpleNamespace(flow_id="route-1", destination_policy={})
        border = BorderAccessDecision(True, "eligible_international", 1.0)
        availability = SimpleNamespace(cohorts={"pop_14": 1, "pop_15_64": 10, "pop_65": 0})

        with patch.object(system, "_route_migration_estimate", return_value=SimpleNamespace(count=0)):
            self.assertIsNone(system._route_flow_record(SimpleNamespace(), candidate, border, availability))

        estimate = SimpleNamespace(count=2, access_rate=1.0, opportunity=0.5, displacement=0.0, event_effect=0.0)
        with (
            patch.object(system, "_route_migration_estimate", return_value=estimate),
            patch("modules.base.systems.demographics.migration_system.calculate_migrant_cohorts", return_value=(0, 0, 0)),
        ):
            self.assertIsNone(system._route_flow_record(SimpleNamespace(now=10), candidate, border, availability))

    def test_diplomacy_signature_includes_war_membership(self) -> None:
        state = GameState(
            tables={
                "countries_wars": pl.DataFrame(
                    {"id": ["war-1"], "side_a": [["AAA"]], "side_b": [["BBB"]]}
                )
            }
        )

        signature = MigrationSystem()._country_diplomacy_signature(state, "AAA")

        self.assertEqual(len(signature), 1)
        self.assertEqual(signature[0]["type"], "war")

    def test_route_batch_without_incident_pairs_and_empty_record_helpers(self) -> None:
        state = GameState(
            tables={
                "regions": pl.DataFrame({"id": [1], "owner": ["AAA"]}),
                "countries": pl.DataFrame({"id": ["AAA"]}),
            }
        )
        build_base_schema_registry().ensure_state(state)
        system = MigrationSystem()
        self.assertIsNone(system._build_route_evaluation_batch(state, 0))

        empty_country_state = GameState(tables={"countries": pl.DataFrame({"id": [""]})})
        build_base_schema_registry().ensure_state(empty_country_state)
        self.assertEqual(system._dirty_region_ids(empty_country_state, [], {}), set())

        system._append_records(empty_country_state, "missing", [{"id": "row"}])
        system._replace_records(empty_country_state, "missing", [{"id": "row"}], "id")
        system._set_table_rows(empty_country_state, "missing", [])
        row_state = GameState(tables={"sample": pl.DataFrame({"id": [1]})})
        system._set_table_rows(row_state, "sample", [{"id": 2}])
        self.assertEqual(row_state.get_table("sample")["id"].to_list(), [2])

    def test_initial_region_signatures_invalidate_only_route_endpoints(self) -> None:
        state = GameState(tables={"countries": pl.DataFrame({"id": ["AAA", "BBB", "CCC"]})})
        build_base_schema_registry().ensure_state(state)
        system = MigrationSystem()
        regions = [
            self._region(1, "AAA", 10, 20, 5, 100),
            self._region(2, "BBB", 10, 20, 5, 100),
            self._region(3, "CCC", 10, 20, 5, 100),
        ]

        dirty = system._dirty_region_ids(state, regions, {1: (2,), 2: (1,)})

        self.assertEqual(dirty, {1, 2})

    @staticmethod
    def _region(region_id: int, owner: str, children: int, working: int, elderly: int, capacity: int):
        return {
            "id": region_id,
            "owner": owner,
            "pop_14": children,
            "pop_15_64": working,
            "pop_65": elderly,
            "transport_access": 1.0,
            "housing_capacity": capacity,
            "employment_capacity": capacity,
            "service_capacity": capacity,
            "transport_capacity": capacity,
        }

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
