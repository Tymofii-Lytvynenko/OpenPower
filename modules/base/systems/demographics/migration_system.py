"""Authoritative deterministic lifecycle for regional migration flows."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import polars as pl

from modules.base.systems.demographics.migration_policy import (
    DestinationCapacity,
    assess_destination_capacity,
    build_route_index,
    calculate_migrant_cohorts,
    estimate_migration_count,
    evaluate_border_access,
)
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from modules.base.systems.politics.political_effect_policy import aggregate_political_effects_by_type
from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import (
    EventMigrationFlowCreated,
    EventMigrationFlowResolved,
    EventMigrationPolicyUpdated,
    EventMigrationSignalUpdated,
    EventNewDay,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE


MINUTES_PER_DAY = 1_440
FLOW_EVALUATION_DAY = 1
FLOW_EVALUATION_PERIOD_MINUTES = 30 * MINUTES_PER_DAY
SIGNAL_WINDOW_MINUTES = 30 * MINUTES_PER_DAY
FLOW_STATUS_PENDING = "pending"
FLOW_STATUS_COMPLETED = "completed"
FLOW_STATUS_REDIRECTED = "redirected"
FLOW_STATUS_REJECTED = "rejected"
FLOW_STATUS_CANCELLED = "cancelled"


class MigrationSystem(ISystem):
    """Processes policy changes, authorized flows, cohort transfers, and signals."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "region_adjacency",
                "countries_relations",
                "countries_treaties",
                "countries_wars",
                "treaty_effects",
                "migration_policies",
                "migration_policy_transitions",
                "migration_flows",
                "migration_signals",
                "regional_infrastructure",
                "domestic_production",
                "random_event_effects",
                "political_effects",
            }
        ),
        writes=frozenset(
            {
                "regions",
                "migration_policies",
                "migration_policy_transitions",
                "migration_flows",
                "migration_signals",
            }
        ),
        handles=frozenset({ActionUpdateMigrationPolicy}),
        phase=SystemPhase.MIGRATION,
    )
    runtime_state_contract = {
        "_route_index": SYSTEM_STATE_CACHE,
        "_adjacency_revision": SYSTEM_STATE_CACHE,
        "_region_signatures": SYSTEM_STATE_CACHE,
        "_country_signatures": SYSTEM_STATE_CACHE,
    }

    def __init__(self) -> None:
        self._route_index: dict[int, tuple[int, ...]] = {}
        self._adjacency_revision = -1
        self._region_signatures: dict[int, str] = {}
        self._country_signatures: dict[str, str] = {}

    @property
    def id(self) -> str:
        return "base.migration"

    @property
    def dependencies(self) -> list[str]:
        return ["base.population", "base.ai", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {
            "countries",
            "regions",
            "migration_policies",
            "migration_policy_transitions",
            "migration_flows",
            "migration_signals",
        }
        if not required.issubset(state.tables):
            return

        now = max(0, int(state.time.total_minutes))
        self._seed_missing_policies(state, now)
        self._apply_policy_actions(state, now)
        self._apply_due_policy_transitions(state, now)

        completed_flows: list[dict[str, Any]] = []
        if not state.time.is_paused:
            completed_flows = self._complete_due_flows(state, now)
        self._update_signals(state, now, completed_flows)

        if not state.time.is_paused and self._is_flow_evaluation_boundary(state):
            self._evaluate_routes(state, now)

    def _is_flow_evaluation_boundary(self, state: GameState) -> bool:
        return any(
            isinstance(event, EventNewDay)
            and event.day == FLOW_EVALUATION_DAY
            for event in state.events
        )

    def _seed_missing_policies(self, state: GameState, now: int) -> None:
        policies = state.get_table("migration_policies")
        known = {self._tag(value) for value in policies.get_column("country_id").to_list()}
        records = [
            self._default_policy(self._tag(country_id), now)
            for country_id in sorted(state.get_table("countries").get_column("id").to_list())
            if self._tag(country_id) and self._tag(country_id) not in known
        ]
        self._append_records(state, "migration_policies", records)

    def _apply_policy_actions(self, state: GameState, now: int) -> None:
        for action_index, action in enumerate(state.current_actions):
            if not isinstance(action, ActionUpdateMigrationPolicy):
                continue
            country_id = self._tag(action.country_tag)
            country_ids = {
                self._tag(value) for value in state.get_table("countries")["id"].to_list()
            }
            if country_id not in country_ids:
                self._record_policy_rejection(
                    state, action, country_id, now, action_index, "unknown_country"
                )
                continue
            if not player_controls_country(state, action.player_id, country_id):
                self._record_policy_rejection(
                    state, action, country_id, now, action_index, "authority_denied"
                )
                continue

            effective = self._requested_minute(action.effective_at_minute, now)
            if effective is None:
                self._record_policy_rejection(
                    state, action, country_id, now, action_index, "invalid_effective_time"
                )
                continue
            effective = max(now, effective)
            base = self._policy_snapshot(state, country_id, effective)
            target, reason = self._policy_target(action, base)
            if target is None:
                self._record_policy_rejection(
                    state, action, country_id, now, action_index, reason
                )
                continue

            source = self._policy_source(action.player_id)
            transition_id = self._transition_id(country_id, now, action_index, target)
            status = "applied" if effective <= now else "scheduled"
            record = {
                "id": transition_id,
                "country_id": country_id,
                **target,
                "requested_at_minute": now,
                "effective_at_minute": effective,
                "source": source,
                "status": status,
                "reason_code": "effective" if status == "applied" else "scheduled",
            }
            self._append_records(state, "migration_policy_transitions", [record])
            if status == "applied":
                self._set_policy(state, country_id, target, effective, now, source)
                state.events.append(
                    EventMigrationPolicyUpdated(country_id, effective, source, now)
                )

    def _record_policy_rejection(
        self,
        state: GameState,
        action: ActionUpdateMigrationPolicy,
        country_id: str,
        now: int,
        action_index: int,
        reason_code: str,
    ) -> None:
        current = self._policy_for(state, country_id)
        transition_id = self._transition_id(country_id or "unknown", now, action_index, current)
        record = {
            "id": transition_id,
            "country_id": country_id,
            **self._target_from_record(current),
            "requested_at_minute": now,
            "effective_at_minute": now,
            "source": self._policy_source(action.player_id),
            "status": "rejected",
            "reason_code": reason_code,
        }
        self._append_records(state, "migration_policy_transitions", [record])

    def _apply_due_policy_transitions(self, state: GameState, now: int) -> None:
        transitions = state.get_table("migration_policy_transitions")
        due = transitions.filter(
            (pl.col("status") == "scheduled")
            & (pl.col("effective_at_minute") <= now)
        ).sort(["effective_at_minute", "requested_at_minute", "id"])
        if due.is_empty():
            return

        applied: list[dict[str, Any]] = []
        for transition in due.iter_rows(named=True):
            country_id = self._tag(transition.get("country_id"))
            target = self._target_from_record(transition)
            effective = max(0, int(transition.get("effective_at_minute") or 0))
            source = str(transition.get("source") or "scenario")
            self._set_policy(state, country_id, target, effective, now, source)
            updated = dict(transition)
            updated["status"] = "applied"
            updated["reason_code"] = "effective"
            applied.append(updated)
            state.events.append(
                EventMigrationPolicyUpdated(country_id, effective, source, now)
            )
        self._replace_records(state, "migration_policy_transitions", applied, "id")

    def _complete_due_flows(self, state: GameState, now: int) -> list[dict[str, Any]]:
        flows = state.get_table("migration_flows")
        due = flows.filter(
            (pl.col("status") == FLOW_STATUS_PENDING)
            & (pl.col("expected_completion_at_minute") <= now)
        ).sort(["expected_completion_at_minute", "id"])
        if due.is_empty():
            return []

        regions_frame = state.get_table("regions")
        region_rows = regions_frame.to_dicts()
        regions = {
            self._integer(row.get("id")): row
            for row in region_rows
        }
        country_ids = {
            self._tag(value) for value in state.get_table("countries")["id"].to_list()
        }
        pending_rows = flows.filter(pl.col("status") == FLOW_STATUS_PENDING).to_dicts()
        reserved_out = self._reserved_cohorts(pending_rows)
        reserved_in = self._reserved_incoming(pending_rows)
        pending_routes = {
            (
                self._integer(row.get("origin_region_id")),
                self._integer(row.get("destination_region_id")),
            )
            for row in pending_rows
        }
        current_policies = self._policy_map(state, now)
        completed: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        redirected_flows: list[dict[str, Any]] = []

        for flow in due.iter_rows(named=True):
            flow_id = str(flow.get("id") or "")
            origin_id = self._integer(flow.get("origin_region_id"))
            destination_id = self._integer(flow.get("destination_region_id"))
            origin = regions.get(origin_id)
            destination = regions.get(destination_id)
            origin_country = self._tag(flow.get("origin_country_id"))
            destination_country = self._tag(flow.get("destination_country_id"))
            if (
                origin is None
                or destination is None
                or origin_id == destination_id
                or self._tag(origin.get("owner")) != origin_country
                or self._tag(destination.get("owner")) != destination_country
                or origin_country not in country_ids
                or destination_country not in country_ids
            ):
                updates.append(self._resolve_row(flow, FLOW_STATUS_CANCELLED, "authority_changed", now))
                continue

            if str(flow.get("transition_rule") or "finish_authorized") != "finish_authorized":
                border = self._border_decision(
                    state,
                    origin_country,
                    destination_country,
                    current_policies,
                )
                if not border.eligible:
                    updates.append(self._resolve_row(flow, FLOW_STATUS_CANCELLED, "border_changed", now))
                    continue

            source = self._cohort_counts(origin)
            other_source_reservations = self._reservation_without(
                reserved_out.get(origin_id, (0, 0, 0)), flow
            )
            available_source = {
                "pop_14": max(0, source[0] - other_source_reservations[0]),
                "pop_15_64": max(0, source[1] - other_source_reservations[1]),
                "pop_65": max(0, source[2] - other_source_reservations[2]),
            }
            planned = max(0, self._integer(flow.get("population_count")))
            available_total = sum(available_source.values())
            count = min(planned, available_total)
            other_destination_reservation = max(
                0,
                reserved_in.get(destination_id, 0)
                - self._integer(flow.get("population_count")),
            )
            capacity = assess_destination_capacity(
                destination,
                current_population=self._population(destination),
                reserved_population=other_destination_reservation,
            )
            if capacity.available_people < planned <= available_total:
                alternate = self._find_redirect_destination(
                    state,
                    origin,
                    destination_id,
                    planned,
                    regions,
                    country_ids,
                    current_policies,
                    reserved_in,
                    pending_routes,
                )
                if alternate is not None:
                    alternate_id, alternate_region, _ = alternate
                    planned_cohorts = tuple(
                        self._integer(flow.get(field))
                        for field in ("dependent_count", "working_age_count", "elderly_count")
                    )
                    if not (
                        sum(planned_cohorts) == planned
                        and all(
                            planned_cohorts[index] <= available_source[field]
                            for index, field in enumerate(("pop_14", "pop_15_64", "pop_65"))
                        )
                    ):
                        planned_cohorts = calculate_migrant_cohorts(
                            planned,
                            available_source,
                        )
                    redirected, pending_redirect = self._redirect_flow_records(
                        flow,
                        alternate_id,
                        self._tag(alternate_region.get("owner")),
                        planned_cohorts,
                        now,
                    )
                    updates.append(redirected)
                    redirected_flows.append(pending_redirect)
                    self._subtract_reservation(reserved_out, origin_id, flow)
                    remaining_reservation = reserved_out.get(origin_id, (0, 0, 0))
                    reserved_out[origin_id] = tuple(
                        remaining_reservation[index] + planned_cohorts[index]
                        for index in range(3)
                    )
                    reserved_in[destination_id] = other_destination_reservation
                    reserved_in[alternate_id] = reserved_in.get(alternate_id, 0) + planned
                    pending_routes.discard((origin_id, destination_id))
                    pending_routes.add((origin_id, alternate_id))
                    state.events.append(
                        EventMigrationFlowResolved(
                            flow_id=flow_id,
                            status=FLOW_STATUS_REDIRECTED,
                            population_count=planned,
                            reason_code="redirected_capacity",
                            at_minute=now,
                        )
                    )
                    state.events.append(
                        EventMigrationFlowCreated(
                            flow_id=str(pending_redirect["id"]),
                            origin_region_id=origin_id,
                            destination_region_id=alternate_id,
                            population_count=planned,
                            reason_code="redirected_capacity",
                            at_minute=now,
                        )
                    )
                    continue
            count = min(count, capacity.available_people)
            if count <= 0:
                reason = "source_cohort_limit" if available_total <= 0 else "capacity_changed"
                updates.append(self._resolve_row(flow, FLOW_STATUS_CANCELLED, reason, now))
                continue

            planned_cohorts = tuple(
                self._integer(flow.get(field))
                for field in ("dependent_count", "working_age_count", "elderly_count")
            )
            # Keep the authorized mix unless live cohorts changed enough to make it unsafe.
            if all(
                planned_cohorts[index] <= available_source[field]
                for index, field in enumerate(("pop_14", "pop_15_64", "pop_65"))
            ) and sum(planned_cohorts) == count:
                cohorts = planned_cohorts
            else:
                cohorts = calculate_migrant_cohorts(count, available_source)
            actual = sum(cohorts)
            if actual <= 0:
                updates.append(self._resolve_row(flow, FLOW_STATUS_CANCELLED, "source_cohort_limit", now))
                continue

            origin["pop_14"] = max(0, source[0] - cohorts[0])
            origin["pop_15_64"] = max(0, source[1] - cohorts[1])
            origin["pop_65"] = max(0, source[2] - cohorts[2])
            destination_counts = self._cohort_counts(destination)
            destination["pop_14"] = destination_counts[0] + cohorts[0]
            destination["pop_15_64"] = destination_counts[1] + cohorts[1]
            destination["pop_65"] = destination_counts[2] + cohorts[2]
            updated = dict(flow)
            updated.update({
                "dependent_count": cohorts[0],
                "working_age_count": cohorts[1],
                "elderly_count": cohorts[2],
                "population_count": actual,
                "completed_at_minute": now,
                "status": FLOW_STATUS_COMPLETED,
                "reason_code": (
                    "source_cohort_limit"
                    if actual < planned and available_total < planned
                    else "capacity_changed"
                    if actual < planned
                    else "completed"
                ),
            })
            updates.append(updated)
            completed.append(updated)
            self._subtract_reservation(reserved_out, origin_id, flow)
            reserved_in[destination_id] = other_destination_reservation
            state.events.append(
                EventMigrationFlowResolved(
                    flow_id=flow_id,
                    status=FLOW_STATUS_COMPLETED,
                    population_count=actual,
                    reason_code=str(updated["reason_code"]),
                    at_minute=now,
                )
            )

        state.update_table(
            "regions",
            pl.DataFrame(region_rows, schema=regions_frame.schema, strict=False),
        )
        self._replace_records(state, "migration_flows", updates, "id")
        self._append_records(state, "migration_flows", redirected_flows)
        for row in updates:
            if row.get("status") == FLOW_STATUS_CANCELLED:
                state.events.append(
                    EventMigrationFlowResolved(
                        flow_id=str(row.get("id") or ""),
                        status=FLOW_STATUS_CANCELLED,
                        population_count=max(0, self._integer(row.get("population_count"))),
                        reason_code=str(row.get("reason_code") or "cancelled"),
                        at_minute=now,
                    )
                )
        return completed

    def _find_redirect_destination(
        self,
        state: GameState,
        origin: Mapping[str, Any],
        excluded_destination_id: int,
        requested_population: int,
        regions: Mapping[int, dict[str, Any]],
        country_ids: set[str],
        policies: Mapping[str, Mapping[str, Any]],
        reserved_in: Mapping[int, int],
        pending_routes: set[tuple[int, int]],
    ) -> tuple[int, dict[str, Any], DestinationCapacity] | None:
        origin_id = self._integer(origin.get("id"))
        origin_country = self._tag(origin.get("owner"))
        candidates: list[tuple[int, int, dict[str, Any], DestinationCapacity]] = []
        for destination_id in self._get_route_index(state).get(origin_id, ()):
            destination = regions.get(destination_id)
            if (
                destination is None
                or destination_id in {origin_id, excluded_destination_id}
                or (origin_id, destination_id) in pending_routes
            ):
                continue
            destination_country = self._tag(destination.get("owner"))
            if not destination_country or destination_country not in country_ids:
                continue
            border = self._border_decision(
                state,
                origin_country,
                destination_country,
                policies,
            )
            if not border.eligible:
                continue
            capacity = assess_destination_capacity(
                destination,
                current_population=self._population(destination),
                reserved_population=reserved_in.get(destination_id, 0),
            )
            if not capacity.eligible or capacity.available_people < requested_population:
                continue
            candidates.append(
                (-capacity.available_people, destination_id, destination, capacity)
            )
        if not candidates:
            return None
        _, destination_id, destination, capacity = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1]),
        )
        return destination_id, destination, capacity

    def _redirect_flow_records(
        self,
        flow: Mapping[str, Any],
        destination_id: int,
        destination_country_id: str,
        cohorts: tuple[int, int, int],
        now: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        flow_id = str(flow.get("id") or "")
        redirect_id = f"{flow_id}-redirect-{destination_id}-{now:012d}"
        original = self._resolve_row(
            flow,
            FLOW_STATUS_REDIRECTED,
            "redirected_capacity",
            now,
        )
        original["reason_factors_json"] = self._extend_reason_factors(
            flow.get("reason_factors_json"),
            redirected_to_region_id=destination_id,
            redirect_flow_id=redirect_id,
        )
        redirected = dict(flow)
        redirected.update(
            {
                "id": redirect_id,
                "destination_region_id": destination_id,
                "destination_country_id": destination_country_id,
                "dependent_count": cohorts[0],
                "working_age_count": cohorts[1],
                "elderly_count": cohorts[2],
                "population_count": sum(cohorts),
                "reason_code": "redirected_capacity",
                "reason_factors_json": self._extend_reason_factors(
                    flow.get("reason_factors_json"),
                    redirected_from_flow_id=flow_id,
                    redirected_from_region_id=self._integer(
                        flow.get("destination_region_id")
                    ),
                ),
                "created_at_minute": now,
                "authorized_at_minute": now,
                "expected_completion_at_minute": now + FLOW_EVALUATION_PERIOD_MINUTES,
                "completed_at_minute": 0,
                "transition_rule": "finish_authorized",
                "status": FLOW_STATUS_PENDING,
            }
        )
        return original, redirected

    def _extend_reason_factors(self, value: Any, **additions: Any) -> str:
        try:
            factors = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            factors = {}
        if not isinstance(factors, dict):
            factors = {}
        factors.update(additions)
        return self._stable_json(factors)

    def _evaluate_routes(self, state: GameState, now: int) -> None:
        regions = state.get_table("regions")
        countries = state.get_table("countries")
        if regions.is_empty() or countries.is_empty():
            return
        route_index = self._get_route_index(state)
        region_rows = regions.to_dicts()
        region_map = {self._integer(row.get("id")): row for row in region_rows}
        country_map = {
            self._tag(row.get("id")): row
            for row in countries.to_dicts()
            if self._tag(row.get("id"))
        }
        event_migration = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            now,
            categories={"migration"},
            subject_type="region",
        )
        dirty_regions = self._dirty_region_ids(state, region_rows, route_index)
        dirty_regions.update(
            int(subject_id)
            for (_, subject_id, _), _magnitude in event_migration.items()
            if subject_id.lstrip("-").isdigit()
        )
        pairs = self._incident_pairs(dirty_regions, route_index)
        if not pairs:
            return

        policies = self._effective_policy_map(state, now)
        flows = state.get_table("migration_flows")
        flow_rows = flows.to_dicts()
        pending_rows = [row for row in flow_rows if row.get("status") == FLOW_STATUS_PENDING]
        reserved_out = self._reserved_cohorts(pending_rows)
        reserved_in = self._reserved_incoming(pending_rows)
        pending_routes = {
            (self._integer(row.get("origin_region_id")), self._integer(row.get("destination_region_id")))
            for row in pending_rows
        }
        known_flow_ids = {str(row.get("id") or "") for row in flow_rows}
        new_flows: list[dict[str, Any]] = []
        for origin_id, destination_id in pairs:
            if (origin_id, destination_id) in pending_routes:
                continue
            origin = region_map.get(origin_id)
            destination = region_map.get(destination_id)
            if origin is None or destination is None:
                continue
            origin_country = self._tag(origin.get("owner"))
            destination_country = self._tag(destination.get("owner"))
            if not origin_country or not destination_country:
                continue
            if origin_country not in country_map or destination_country not in country_map:
                continue
            flow_id = f"migration-{now:012d}-{origin_id}-{destination_id}"
            if flow_id in known_flow_ids:
                continue

            origin_policy = policies.get(origin_country, self._default_policy(origin_country, now))
            destination_policy = policies.get(
                destination_country,
                self._default_policy(destination_country, now),
            )
            border = self._border_decision(
                state,
                origin_country,
                destination_country,
                policies,
            )
            if not border.eligible:
                rejected = self._rejected_flow(
                    flow_id,
                    origin_id,
                    destination_id,
                    origin_country,
                    destination_country,
                    now,
                    border.reason_code,
                )
                new_flows.append(rejected)
                known_flow_ids.add(flow_id)
                continue

            origin_cohorts = self._cohort_counts(origin)
            reserved_source = reserved_out.get(origin_id, (0, 0, 0))
            available_cohorts = {
                "pop_14": max(0, origin_cohorts[0] - reserved_source[0]),
                "pop_15_64": max(0, origin_cohorts[1] - reserved_source[1]),
                "pop_65": max(0, origin_cohorts[2] - reserved_source[2]),
            }
            source_available = sum(available_cohorts.values())
            if source_available <= 0:
                continue

            destination_capacity = assess_destination_capacity(
                destination,
                current_population=self._population(destination),
                reserved_population=reserved_in.get(destination_id, 0),
            )
            if not destination_capacity.eligible:
                rejected = self._rejected_flow(
                    flow_id,
                    origin_id,
                    destination_id,
                    origin_country,
                    destination_country,
                    now,
                    "no_destination_capacity",
                )
                new_flows.append(rejected)
                known_flow_ids.add(flow_id)
                continue

            migration_effect = event_migration.get(("region", str(origin_id), "migration"), 0.0)
            access_rate = border.access_rate
            displacement = self._bounded_ratio(origin.get("displacement_pressure"))
            access_rate *= (1.0 - displacement) + (
                displacement * self._bounded_ratio(destination_policy.get("asylum_rate"), 0.25)
            )
            count, opportunity = estimate_migration_count(
                origin,
                destination,
                country_map[origin_country],
                country_map[destination_country],
                access_rate=access_rate,
                source_available=source_available,
                destination_available=destination_capacity.available_people,
            )
            count = min(
                source_available,
                destination_capacity.available_people,
                max(0, int(round(count * (1.0 + min(0.5, max(-0.5, migration_effect))))))
            )
            if count <= 0:
                continue
            cohorts = calculate_migrant_cohorts(
                count,
                available_cohorts,
                skilled_worker_preference=self._bounded_ratio(
                    destination_policy.get("skilled_worker_preference")
                ),
                family_reunification_rate=self._bounded_ratio(
                    destination_policy.get("family_reunification_rate"), 0.5
                ),
            )
            actual_count = sum(cohorts)
            if actual_count <= 0:
                continue

            reason_code = border.reason_code
            record = {
                "id": flow_id,
                "origin_region_id": origin_id,
                "destination_region_id": destination_id,
                "origin_country_id": origin_country,
                "destination_country_id": destination_country,
                "dependent_count": cohorts[0],
                "working_age_count": cohorts[1],
                "elderly_count": cohorts[2],
                "population_count": actual_count,
                "reason_code": reason_code,
                "reason_factors_json": self._reason_factors(
                    access_rate=access_rate,
                    opportunity=opportunity,
                    displacement_pressure=displacement,
                    capacity=destination_capacity.available_people,
                    event_migration_effect=migration_effect,
                ),
                "created_at_minute": now,
                "authorized_at_minute": now,
                "expected_completion_at_minute": now + FLOW_EVALUATION_PERIOD_MINUTES,
                "completed_at_minute": 0,
                "transition_rule": "finish_authorized",
                "status": FLOW_STATUS_PENDING,
            }
            new_flows.append(record)
            known_flow_ids.add(flow_id)
            pending_routes.add((origin_id, destination_id))
            reserved_out[origin_id] = tuple(
                reserved_source[index] + cohorts[index] for index in range(3)
            )
            reserved_in[destination_id] = reserved_in.get(destination_id, 0) + actual_count
            state.events.append(
                EventMigrationFlowCreated(
                    flow_id=flow_id,
                    origin_region_id=origin_id,
                    destination_region_id=destination_id,
                    population_count=actual_count,
                    reason_code=reason_code,
                    at_minute=now,
                )
            )

        self._append_records(state, "migration_flows", new_flows)

    def _update_signals(
        self,
        state: GameState,
        now: int,
        completed_flows: list[dict[str, Any]],
    ) -> None:
        signals = state.get_table("migration_signals")
        signal_rows = {self._tag(row.get("country_id")): row for row in signals.to_dicts()}
        window_start = (now // SIGNAL_WINDOW_MINUTES) * SIGNAL_WINDOW_MINUTES
        countries = [
            self._tag(country_id)
            for country_id in state.get_table("countries")["id"].to_list()
            if self._tag(country_id)
        ]
        policies = self._effective_policy_map(state, now)
        health_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            now,
            categories={"health"},
            subject_type="region",
        )
        political_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            now,
            categories={"political_pressure"},
            subject_type="country",
        )
        region_owner = {
            str(row.get("id")): self._tag(row.get("owner"))
            for row in state.get_table("regions").iter_rows(named=True)
        }
        health_pressure_by_country: dict[str, float] = {}
        for (_, region_id, _), magnitude in health_effects.items():
            owner = region_owner.get(region_id, "")
            if owner:
                health_pressure_by_country[owner] = health_pressure_by_country.get(owner, 0.0) + max(0.0, -magnitude)
        updated: dict[str, dict[str, Any]] = {}
        for country_id in sorted(countries):
            current = signal_rows.get(country_id)
            existing = dict(current or {})
            # An empty table defaults its window to zero, so first-time rows still need their country key seeded.
            if current is None or self._integer(existing.get("window_start_minute")) != window_start:
                existing = {
                    "country_id": country_id,
                    "gross_inflow": 0,
                    "gross_outflow": 0,
                    "net_flow": 0,
                    "working_age_delta": 0,
                    "service_pressure": 0.0,
                    "political_pressure": 0.0,
                    "law_pressure": 0.0,
                    "window_start_minute": window_start,
                    "updated_at_minute": now,
                    "politics_consumed_at_minute": 0,
                    "economy_consumed_at_minute": 0,
                }
            updated[country_id] = existing

        for flow in completed_flows:
            origin = self._tag(flow.get("origin_country_id"))
            destination = self._tag(flow.get("destination_country_id"))
            total = max(0, self._integer(flow.get("population_count")))
            working = max(0, self._integer(flow.get("working_age_count")))
            if total <= 0:
                continue
            if origin in updated:
                updated[origin]["gross_outflow"] = self._integer(updated[origin].get("gross_outflow")) + total
                updated[origin]["working_age_delta"] = self._integer(updated[origin].get("working_age_delta")) - working
            if destination in updated:
                updated[destination]["gross_inflow"] = self._integer(updated[destination].get("gross_inflow")) + total
                updated[destination]["working_age_delta"] = self._integer(updated[destination].get("working_age_delta")) + working

        region_totals: dict[str, int] = {}
        service_capacity: dict[str, int] = {}
        for region in state.get_table("regions").to_dicts():
            owner = self._tag(region.get("owner"))
            if not owner:
                continue
            region_totals[owner] = region_totals.get(owner, 0) + self._population(region)
            service = self._integer(region.get("service_capacity"))
            service_capacity[owner] = service_capacity.get(owner, 0) + service

        changed: list[dict[str, Any]] = []
        for country_id, row in updated.items():
            inflow = self._integer(row.get("gross_inflow"))
            outflow = self._integer(row.get("gross_outflow"))
            row["net_flow"] = inflow - outflow
            population = max(1, region_totals.get(country_id, 0))
            event_political = political_effects.get(("country", country_id, "political_pressure"), 0.0)
            row["political_pressure"] = self._bounded_ratio(
                max(inflow, outflow) / population / 0.05
                + min(0.5, max(-0.5, event_political))
            )
            policy = policies.get(country_id, self._default_policy(country_id, now))
            row["law_pressure"] = self._bounded_ratio(
                row["political_pressure"]
                * self._bounded_ratio(policy.get("enforcement_strength"), 0.5)
            )
            capacity = service_capacity.get(country_id, 0)
            if capacity <= 0:
                capacity = max(1, int(population * 0.1))
            health_pressure = min(0.5, max(0.0, health_pressure_by_country.get(country_id, 0.0)))
            row["service_pressure"] = self._bounded_ratio(inflow / capacity + health_pressure)
            row["updated_at_minute"] = now
            current = signal_rows.get(country_id)
            if current is None or any(
                current.get(field) != row.get(field)
                for field in (
                    "gross_inflow",
                    "gross_outflow",
                    "net_flow",
                    "working_age_delta",
                    "service_pressure",
                    "political_pressure",
                    "law_pressure",
                    "window_start_minute",
                )
            ):
                changed.append(row)
                state.events.append(
                    EventMigrationSignalUpdated(
                        country_id=country_id,
                        political_pressure=float(row["political_pressure"]),
                        service_pressure=float(row["service_pressure"]),
                        net_flow=int(row["net_flow"]),
                        at_minute=now,
                        law_pressure=float(row["law_pressure"]),
                    )
                )
        self._replace_records(state, "migration_signals", changed, "country_id")

    def _get_route_index(self, state: GameState) -> dict[int, tuple[int, ...]]:
        adjacency = state.tables.get("region_adjacency")
        revision = state.table_revisions.get("region_adjacency", 0)
        if revision != self._adjacency_revision:
            self._route_index = build_route_index(adjacency)
            self._adjacency_revision = revision
            self._region_signatures.clear()
        return self._route_index

    def _dirty_region_ids(
        self,
        state: GameState,
        region_rows: list[dict[str, Any]],
        route_index: Mapping[int, tuple[int, ...]],
    ) -> set[int]:
        current_signatures: dict[int, str] = {}
        for row in region_rows:
            region_id = self._integer(row.get("id"))
            current_signatures[region_id] = self._stable_json(
                {
                    key: row.get(key)
                    for key in (
                        "owner", "pop_14", "pop_15_64", "pop_65",
                        "housing_capacity", "employment_capacity", "service_capacity",
                        "transport_capacity", "transport_access", "health_capacity",
                        "displacement_pressure",
                    )
                }
            )
        dirty = {
            region_id
            for region_id, signature in current_signatures.items()
            if self._region_signatures.get(region_id) != signature
        }
        if set(self._region_signatures) != set(current_signatures):
            dirty.update(current_signatures)
        self._region_signatures = current_signatures

        country_rows = state.get_table("countries").to_dicts()
        policy_rows = self._policy_map(state, max(0, int(state.time.total_minutes)))
        owner_regions: dict[str, list[int]] = {}
        for row in region_rows:
            owner = self._tag(row.get("owner"))
            if owner:
                owner_regions.setdefault(owner, []).append(self._integer(row.get("id")))
        changed_countries: set[str] = set()
        current_country_signatures: dict[str, str] = {}
        for row in country_rows:
            country_id = self._tag(row.get("id"))
            if not country_id:
                continue
            diplomacy_signature = self._country_diplomacy_signature(state, country_id)
            signature = self._stable_json({
                "economy": {
                    key: row.get(key)
                    for key in (
                        "human_dev", "economic_health", "employment_rate",
                        "unemployment_rate", "migration_pressure",
                    )
                },
                "policy": policy_rows.get(country_id, self._default_policy(country_id, 0)),
                "diplomacy": diplomacy_signature,
            })
            current_country_signatures[country_id] = signature
            if self._country_signatures.get(country_id) != signature:
                changed_countries.add(country_id)
        self._country_signatures = current_country_signatures
        for country_id in changed_countries:
            dirty.update(owner_regions.get(country_id, ()))

        valid_region_ids = set(current_signatures)
        if not dirty and not self._region_signatures and valid_region_ids:
            dirty.update(valid_region_ids)
        # An explicit endpoint set avoids mapping/set mixing and keeps invalidation route-scoped.
        route_region_ids = set(route_index)
        route_region_ids.update(
            neighbor for values in route_index.values() for neighbor in values
        )
        return dirty & route_region_ids

    def _country_diplomacy_signature(self, state: GameState, country_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        relations = state.tables.get("countries_relations")
        if relations is not None and {"source", "target", "value"}.issubset(relations.columns):
            result.extend(
                {"type": "relation", **row}
                for row in relations.filter(
                    (pl.col("source").cast(pl.Utf8).str.to_uppercase() == country_id)
                    | (pl.col("target").cast(pl.Utf8).str.to_uppercase() == country_id)
                ).to_dicts()
            )
        effects = state.tables.get("treaty_effects")
        if effects is not None and {"country_id", "effect"}.issubset(effects.columns):
            result.extend(
                {"type": "effect", **row}
                for row in effects.filter(
                    pl.col("country_id").cast(pl.Utf8).str.to_uppercase() == country_id
                ).to_dicts()
            )
        wars = state.tables.get("countries_wars")
        if wars is not None:
            for row in wars.to_dicts():
                sides = self._country_side_tags(row)
                if country_id in sides:
                    result.append({"type": "war", **row})
        return sorted(result, key=self._stable_json)

    def _incident_pairs(
        self,
        dirty_regions: set[int],
        route_index: Mapping[int, tuple[int, ...]],
    ) -> list[tuple[int, int]]:
        pairs: set[tuple[int, int]] = set()
        for origin in dirty_regions:
            for destination in route_index.get(origin, ()):
                pairs.add((origin, destination))
                pairs.add((destination, origin))
        return sorted(pairs)

    def _border_decision(
        self,
        state: GameState,
        origin_country: str,
        destination_country: str,
        policies: Mapping[str, Mapping[str, Any]],
    ):
        default = self._default_policy("", max(0, int(state.time.total_minutes)))
        return evaluate_border_access(
            origin_country,
            destination_country,
            policies.get(origin_country, default),
            policies.get(destination_country, default),
            relations=state.tables.get("countries_relations"),
            wars=state.tables.get("countries_wars"),
            treaty_effects=state.tables.get("treaty_effects"),
        )

    def _policy_map(self, state: GameState, now: int) -> dict[str, dict[str, Any]]:
        policies = state.get_table("migration_policies")
        return {
            self._tag(row.get("country_id")): row
            for row in policies.to_dicts()
            if self._tag(row.get("country_id"))
            and self._integer(row.get("effective_at_minute")) <= now
        }

    def _effective_policy_map(self, state: GameState, now: int) -> dict[str, dict[str, Any]]:
        policies = self._policy_map(state, now)
        political_outputs = aggregate_political_effects_by_type(
            state.tables.get("political_effects"),
            now,
            selectors={
                ("migration", "entry_rate"),
                ("migration", "exit_rate"),
                ("migration", "enforcement_strength"),
            },
        )
        deltas = {
            field: {
                country_id: value
                for (country_id, domain, effect), value in political_outputs.items()
                if (domain, effect) == ("migration", field)
            }
            for field in ("entry_rate", "exit_rate", "enforcement_strength")
        }
        if not any(deltas.values()):
            return policies
        for country_id, policy in policies.items():
            for field, effects_by_country in deltas.items():
                if country_id in effects_by_country:
                    policy[field] = self._bounded_ratio(
                        self._bounded_ratio(policy.get(field), 0.5)
                        + effects_by_country[country_id]
                    )
        return policies

    def _policy_for(self, state: GameState, country_id: str) -> dict[str, Any]:
        policy = self._policy_map(state, max(0, int(state.time.total_minutes))).get(
            self._tag(country_id)
        )
        return dict(policy) if policy is not None else self._default_policy(country_id, 0)

    def _policy_snapshot(self, state: GameState, country_id: str, effective: int) -> dict[str, Any]:
        policy = self._policy_for(state, country_id)
        future = state.get_table("migration_policy_transitions").filter(
            (pl.col("country_id") == self._tag(country_id))
            & (pl.col("status") == "scheduled")
            & (pl.col("effective_at_minute") < effective)
        ).sort(["effective_at_minute", "requested_at_minute", "id"])
        for row in future.iter_rows(named=True):
            policy.update(self._target_from_record(row))
        return policy

    def _policy_target(
        self,
        action: ActionUpdateMigrationPolicy,
        base: Mapping[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        migration_policy = self._normalize_posture(action.migration_policy, {"open", "managed", "restricted"})
        border_policy = self._normalize_posture(action.border_policy, {"open", "managed", "closed"})
        if migration_policy is None or border_policy is None:
            return None, "invalid_policy_posture"
        target = {
            "migration_policy": migration_policy,
            "border_policy": border_policy,
        }
        fields = (
            "entry_rate",
            "exit_rate",
            "asylum_rate",
            "family_reunification_rate",
            "skilled_worker_preference",
            "enforcement_strength",
        )
        for field in fields:
            value = getattr(action, field)
            if value is None:
                target[field] = self._bounded_ratio(base.get(field), self._default_policy("", 0)[field])
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError):
                return None, "invalid_policy_value"
            if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                return None, "invalid_policy_value"
            target[field] = numeric
        return target, ""

    def _set_policy(
        self,
        state: GameState,
        country_id: str,
        target: Mapping[str, Any],
        effective: int,
        updated_at: int,
        source: str,
    ) -> None:
        record = {
            "country_id": self._tag(country_id),
            **self._target_from_record(target),
            "effective_at_minute": max(0, int(effective)),
            "updated_at_minute": max(0, int(updated_at)),
            "source": source,
        }
        self._replace_records(state, "migration_policies", [record], "country_id")

    def _target_from_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            field: record.get(field, default)
            for field, default in (
                ("migration_policy", "managed"),
                ("border_policy", "managed"),
                ("entry_rate", 0.5),
                ("exit_rate", 0.5),
                ("asylum_rate", 0.25),
                ("family_reunification_rate", 0.5),
                ("skilled_worker_preference", 0.0),
                ("enforcement_strength", 0.5),
            )
        }

    def _default_policy(self, country_id: str, now: int) -> dict[str, Any]:
        return {
            "country_id": self._tag(country_id),
            "migration_policy": "managed",
            "border_policy": "managed",
            "entry_rate": 0.5,
            "exit_rate": 0.5,
            "asylum_rate": 0.25,
            "family_reunification_rate": 0.5,
            "skilled_worker_preference": 0.0,
            "enforcement_strength": 0.5,
            "effective_at_minute": 0,
            "updated_at_minute": max(0, int(now)),
            "source": "default",
        }

    def _rejected_flow(
        self,
        flow_id: str,
        origin_id: int,
        destination_id: int,
        origin_country: str,
        destination_country: str,
        now: int,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "id": flow_id,
            "origin_region_id": origin_id,
            "destination_region_id": destination_id,
            "origin_country_id": origin_country,
            "destination_country_id": destination_country,
            "dependent_count": 0,
            "working_age_count": 0,
            "elderly_count": 0,
            "population_count": 0,
            "reason_code": reason,
            "reason_factors_json": "{}",
            "created_at_minute": now,
            "authorized_at_minute": 0,
            "expected_completion_at_minute": 0,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": FLOW_STATUS_REJECTED,
        }

    def _resolve_row(
        self,
        flow: Mapping[str, Any],
        status: str,
        reason: str,
        now: int,
    ) -> dict[str, Any]:
        updated = dict(flow)
        updated["status"] = status
        updated["reason_code"] = reason
        updated["completed_at_minute"] = now if status == FLOW_STATUS_COMPLETED else 0
        return updated

    def _reserved_cohorts(self, pending: list[dict[str, Any]]) -> dict[int, tuple[int, int, int]]:
        reserved: dict[int, list[int]] = {}
        for row in pending:
            region_id = self._integer(row.get("origin_region_id"))
            counts = reserved.setdefault(region_id, [0, 0, 0])
            counts[0] += self._integer(row.get("dependent_count"))
            counts[1] += self._integer(row.get("working_age_count"))
            counts[2] += self._integer(row.get("elderly_count"))
        return {region_id: tuple(counts) for region_id, counts in reserved.items()}

    def _reserved_incoming(self, pending: list[dict[str, Any]]) -> dict[int, int]:
        reserved: dict[int, int] = {}
        for row in pending:
            region_id = self._integer(row.get("destination_region_id"))
            reserved[region_id] = reserved.get(region_id, 0) + self._integer(
                row.get("population_count")
            )
        return reserved

    def _reservation_without(
        self,
        reservations: tuple[int, int, int],
        flow: Mapping[str, Any],
    ) -> tuple[int, int, int]:
        return tuple(
            max(0, reservations[index] - self._integer(flow.get(field)))
            for index, field in enumerate(("dependent_count", "working_age_count", "elderly_count"))
        )

    def _subtract_reservation(
        self,
        reservations: dict[int, tuple[int, int, int]],
        region_id: int,
        flow: Mapping[str, Any],
    ) -> None:
        current = reservations.get(region_id, (0, 0, 0))
        reservations[region_id] = tuple(
            max(0, current[index] - self._integer(flow.get(field)))
            for index, field in enumerate(("dependent_count", "working_age_count", "elderly_count"))
        )

    def _append_records(
        self,
        state: GameState,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> None:
        if not records:
            return
        frame = state.tables.get(table_name)
        if frame is None:
            return
        additions = pl.DataFrame(records, schema=frame.schema, strict=False)
        state.update_table(table_name, pl.concat([frame, additions], how="vertical_relaxed"))

    def _replace_records(
        self,
        state: GameState,
        table_name: str,
        records: list[dict[str, Any]],
        key: str,
    ) -> None:
        if not records:
            return
        frame = state.tables.get(table_name)
        if frame is None:
            return
        patch = pl.DataFrame(records, schema=frame.schema, strict=False)
        unaffected = frame.join(patch.select(key).unique(), on=key, how="anti")
        state.update_table(
            table_name,
            pl.concat([unaffected, patch], how="vertical_relaxed").sort(key),
        )

    def _set_table_rows(
        self,
        state: GameState,
        table_name: str,
        rows: list[dict[str, Any]],
    ) -> None:
        frame = state.tables.get(table_name)
        if frame is None:
            return
        state.update_table(table_name, pl.DataFrame(rows, schema=frame.schema, strict=False))

    def _policy_source(self, player_id: Any) -> str:
        actor = self._tag(player_id)
        if actor in {"AI", "AI_SYSTEM"}:
            return "ai"
        if actor == "SERVER":
            return "scenario"
        return "player"

    def _transition_id(
        self,
        country_id: str,
        now: int,
        action_index: int,
        payload: Mapping[str, Any],
    ) -> str:
        digest = hashlib.sha256(self._stable_json(payload).encode("utf-8")).hexdigest()[:10]
        return f"migration-policy-{self._tag(country_id)}-{now:012d}-{action_index:04d}-{digest}"

    def _reason_factors(self, **values: Any) -> str:
        return self._stable_json({key: self._json_number(value) for key, value in values.items()})

    def _stable_json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def _normalize_posture(self, value: Any, allowed: set[str]) -> str | None:
        normalized = str(value or "").strip().lower().replace(" ", "_")
        aliases = {
            "open_borders": "open",
            "managed_borders": "managed",
            "closed_borders": "closed",
            "moderate": "managed",
            "strict": "restricted",
        }
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in allowed else None

    def _requested_minute(self, value: Any, now: int) -> int | None:
        if value is None:
            return now
        try:
            minute = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return max(0, minute)

    def _country_side_tags(self, row: Mapping[str, Any]) -> set[str]:
        countries: set[str] = set()
        for field in ("side_a", "side_b", "attackers", "defenders"):
            value = row.get(field)
            if isinstance(value, str):
                countries.update(
                    self._tag(part)
                    for part in value.replace(";", ",").split(",")
                    if self._tag(part)
                )
            elif isinstance(value, (list, tuple, set)):
                countries.update(self._tag(part) for part in value if self._tag(part))
        countries.update(
            self._tag(row.get(field))
            for field in ("attacker_tag", "defender_tag")
            if self._tag(row.get(field))
        )
        return countries

    def _cohort_counts(self, region: Mapping[str, Any]) -> tuple[int, int, int]:
        return tuple(
            max(0, self._integer(region.get(field)))
            for field in ("pop_14", "pop_15_64", "pop_65")
        )

    def _population(self, region: Mapping[str, Any]) -> int:
        return sum(self._cohort_counts(region))

    def _integer(self, value: Any) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return int(numeric) if math.isfinite(numeric) and numeric > 0.0 else 0

    def _bounded_ratio(self, value: Any, default: float = 0.0) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            numeric = default
        if not math.isfinite(numeric):
            numeric = default
        return min(1.0, max(0.0, numeric))

    def _json_number(self, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 8) if math.isfinite(value) else 0.0
        return value

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()
