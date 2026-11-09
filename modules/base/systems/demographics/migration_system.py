"""Authoritative deterministic lifecycle for regional migration flows."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Mapping

import polars as pl

from modules.base.systems.demographics.migration_policy import (
    BorderAccessDecision,
    DestinationCapacity,
    assess_destination_capacity,
    build_route_index,
    calculate_migrant_cohorts,
    estimate_migration_count,
    evaluate_border_access,
)
from modules.base.systems.demographics.migration_signal_policy import (
    DeterministicMigrationSignalCalculator,
    MigrationSignalCalculator,
)
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from modules.base.systems.politics.political_effect_policy import aggregate_political_effects_by_type
from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import (
    EventMigrationFlowCreated,
    EventMigrationFlowResolved,
    EventMigrationPolicyUpdated,
    EventNewDay,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER


MINUTES_PER_DAY = 1_440
FLOW_EVALUATION_DAY = 1
FLOW_EVALUATION_PERIOD_MINUTES = 30 * MINUTES_PER_DAY
SIGNAL_WINDOW_MINUTES = 30 * MINUTES_PER_DAY
FLOW_STATUS_PENDING = "pending"
FLOW_STATUS_COMPLETED = "completed"
FLOW_STATUS_REDIRECTED = "redirected"
FLOW_STATUS_REJECTED = "rejected"
FLOW_STATUS_CANCELLED = "cancelled"


@dataclass(frozen=True)
class MigrationFlowEndpoints:
    flow_id: str
    origin_region_id: int
    destination_region_id: int
    origin_country_id: str
    destination_country_id: str
    origin: dict[str, Any] | None
    destination: dict[str, Any] | None


@dataclass(frozen=True)
class MigrationFlowAvailability:
    source_cohorts: tuple[int, int, int]
    available_source: dict[str, int]
    available_total: int
    planned_count: int
    count: int
    other_destination_reservation: int
    capacity: DestinationCapacity


@dataclass
class MigrationFlowCompletionBatch:
    state: GameState
    now: int
    due_flows: pl.DataFrame
    regions_frame: pl.DataFrame
    region_rows: list[dict[str, Any]]
    regions: dict[int, dict[str, Any]]
    country_ids: set[str]
    reserved_out: dict[int, tuple[int, int, int]]
    reserved_in: dict[int, int]
    pending_routes: set[tuple[int, int]]
    current_policies: dict[str, dict[str, Any]]
    completed: list[dict[str, Any]] = dataclass_field(default_factory=list)
    updates: list[dict[str, Any]] = dataclass_field(default_factory=list)
    redirected_flows: list[dict[str, Any]] = dataclass_field(default_factory=list)


@dataclass
class RouteEvaluationBatch:
    state: GameState
    now: int
    region_map: dict[int, dict[str, Any]]
    country_map: dict[str, dict[str, Any]]
    event_migration: Mapping[tuple[str, str, str], Any]
    pairs: list[tuple[int, int]]
    policies: dict[str, dict[str, Any]]
    reserved_out: dict[int, tuple[int, int, int]]
    reserved_in: dict[int, int]
    pending_routes: set[tuple[int, int]]
    known_flow_ids: set[str]
    new_flows: list[dict[str, Any]] = dataclass_field(default_factory=list)


@dataclass(frozen=True)
class RouteEvaluationCandidate:
    origin_region_id: int
    destination_region_id: int
    origin_country_id: str
    destination_country_id: str
    flow_id: str
    origin: dict[str, Any]
    destination: dict[str, Any]
    destination_policy: dict[str, Any]


@dataclass(frozen=True)
class RouteSourceAvailability:
    cohorts: dict[str, int]
    source_available: int
    reserved_source: tuple[int, int, int]
    destination_capacity: DestinationCapacity


@dataclass(frozen=True)
class RouteMigrationEstimate:
    count: int
    opportunity: float
    access_rate: float
    displacement: float
    event_effect: float


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
        "_signal_calculator": SYSTEM_STATE_HELPER,
        "_route_index": SYSTEM_STATE_CACHE,
        "_adjacency_revision": SYSTEM_STATE_CACHE,
        "_region_signatures": SYSTEM_STATE_CACHE,
        "_country_signatures": SYSTEM_STATE_CACHE,
    }

    def __init__(self, signal_calculator: MigrationSignalCalculator | None = None) -> None:
        self._signal_calculator = (
            signal_calculator
            if signal_calculator is not None
            else DeterministicMigrationSignalCalculator()
        )
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
        batch = self._build_due_flow_batch(state, now)
        if batch is None:
            return []

        for flow in batch.due_flows.iter_rows(named=True):
            self._process_due_flow(batch, flow)

        self._persist_due_flow_batch(batch)
        return batch.completed

    def _build_due_flow_batch(
        self,
        state: GameState,
        now: int,
    ) -> MigrationFlowCompletionBatch | None:
        flows = state.get_table("migration_flows")
        due_flows = flows.filter(
            (pl.col("status") == FLOW_STATUS_PENDING)
            & (pl.col("expected_completion_at_minute") <= now)
        ).sort(["expected_completion_at_minute", "id"])
        if due_flows.is_empty():
            return None

        regions_frame = state.get_table("regions")
        region_rows = regions_frame.to_dicts()
        regions = {self._integer(row.get("id")): row for row in region_rows}
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
        return MigrationFlowCompletionBatch(
            state=state,
            now=now,
            due_flows=due_flows,
            regions_frame=regions_frame,
            region_rows=region_rows,
            regions=regions,
            country_ids=country_ids,
            reserved_out=reserved_out,
            reserved_in=reserved_in,
            pending_routes=pending_routes,
            current_policies=self._policy_map(state, now),
        )

    def _process_due_flow(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: dict[str, Any],
    ) -> None:
        endpoints = self._flow_endpoints(batch, flow)
        if not self._has_current_flow_authority(batch, endpoints):
            self._record_flow_cancellation(batch, flow, "authority_changed")
            return
        if not self._flow_border_is_eligible(batch, flow, endpoints):
            self._record_flow_cancellation(batch, flow, "border_changed")
            return

        availability = self._flow_availability(batch, flow, endpoints)
        if self._redirect_due_flow(batch, flow, endpoints, availability):
            return
        self._complete_available_flow(batch, flow, endpoints, availability)

    def _flow_endpoints(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
    ) -> MigrationFlowEndpoints:
        origin_region_id = self._integer(flow.get("origin_region_id"))
        destination_region_id = self._integer(flow.get("destination_region_id"))
        return MigrationFlowEndpoints(
            flow_id=str(flow.get("id") or ""),
            origin_region_id=origin_region_id,
            destination_region_id=destination_region_id,
            origin_country_id=self._tag(flow.get("origin_country_id")),
            destination_country_id=self._tag(flow.get("destination_country_id")),
            origin=batch.regions.get(origin_region_id),
            destination=batch.regions.get(destination_region_id),
        )

    def _has_current_flow_authority(
        self,
        batch: MigrationFlowCompletionBatch,
        endpoints: MigrationFlowEndpoints,
    ) -> bool:
        if endpoints.origin is None or endpoints.destination is None:
            return False
        if endpoints.origin_region_id == endpoints.destination_region_id:
            return False
        if self._tag(endpoints.origin.get("owner")) != endpoints.origin_country_id:
            return False
        if self._tag(endpoints.destination.get("owner")) != endpoints.destination_country_id:
            return False
        if endpoints.origin_country_id not in batch.country_ids:
            return False
        if endpoints.destination_country_id not in batch.country_ids:
            return False
        return True

    def _flow_border_is_eligible(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
    ) -> bool:
        if str(flow.get("transition_rule") or "finish_authorized") == "finish_authorized":
            return True
        border = self._border_decision(
            batch.state,
            endpoints.origin_country_id,
            endpoints.destination_country_id,
            batch.current_policies,
        )
        return border.eligible

    def _record_flow_cancellation(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        reason: str,
    ) -> None:
        batch.updates.append(
            self._resolve_row(flow, FLOW_STATUS_CANCELLED, reason, batch.now)
        )

    def _flow_availability(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
    ) -> MigrationFlowAvailability:
        origin = batch.regions[endpoints.origin_region_id]
        destination = batch.regions[endpoints.destination_region_id]
        source_cohorts = self._cohort_counts(origin)
        other_source_reservations = self._reservation_without(
            batch.reserved_out.get(endpoints.origin_region_id, (0, 0, 0)),
            flow,
        )
        available_source = {
            "pop_14": max(0, source_cohorts[0] - other_source_reservations[0]),
            "pop_15_64": max(0, source_cohorts[1] - other_source_reservations[1]),
            "pop_65": max(0, source_cohorts[2] - other_source_reservations[2]),
        }
        planned_count = max(0, self._integer(flow.get("population_count")))
        available_total = sum(available_source.values())
        count = min(planned_count, available_total)
        other_destination_reservation = max(
            0,
            batch.reserved_in.get(endpoints.destination_region_id, 0)
            - self._integer(flow.get("population_count")),
        )
        capacity = assess_destination_capacity(
            destination,
            current_population=self._population(destination),
            reserved_population=other_destination_reservation,
        )
        return MigrationFlowAvailability(
            source_cohorts=source_cohorts,
            available_source=available_source,
            available_total=available_total,
            planned_count=planned_count,
            count=count,
            other_destination_reservation=other_destination_reservation,
            capacity=capacity,
        )

    def _redirect_due_flow(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
        availability: MigrationFlowAvailability,
    ) -> bool:
        if not (
            availability.capacity.available_people < availability.planned_count
            <= availability.available_total
        ):
            return False

        origin = batch.regions[endpoints.origin_region_id]
        alternate = self._find_redirect_destination(
            batch.state,
            origin,
            endpoints.destination_region_id,
            availability.planned_count,
            batch.regions,
            batch.country_ids,
            batch.current_policies,
            batch.reserved_in,
            batch.pending_routes,
        )
        if alternate is None:
            return False

        alternate_id, alternate_region, _ = alternate
        planned_cohorts = self._redirected_cohorts(flow, availability)
        redirected, pending_redirect = self._redirect_flow_records(
            flow,
            alternate_id,
            self._tag(alternate_region.get("owner")),
            planned_cohorts,
            batch.now,
        )
        batch.updates.append(redirected)
        batch.redirected_flows.append(pending_redirect)
        self._update_redirect_reservations(
            batch,
            flow,
            endpoints,
            availability,
            alternate_id,
            planned_cohorts,
        )
        self._emit_redirect_events(
            batch,
            endpoints,
            availability,
            alternate_id,
            pending_redirect,
        )
        return True

    def _redirected_cohorts(
        self,
        flow: Mapping[str, Any],
        availability: MigrationFlowAvailability,
    ) -> tuple[int, int, int]:
        planned_cohorts = tuple(
            self._integer(flow.get(field))
            for field in ("dependent_count", "working_age_count", "elderly_count")
        )
        cohorts_match_plan = sum(planned_cohorts) == availability.planned_count
        cohorts_fit_source = all(
            planned_cohorts[index] <= availability.available_source[field]
            for index, field in enumerate(("pop_14", "pop_15_64", "pop_65"))
        )
        if cohorts_match_plan and cohorts_fit_source:
            return planned_cohorts
        return calculate_migrant_cohorts(
            availability.planned_count,
            availability.available_source,
        )

    def _update_redirect_reservations(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
        availability: MigrationFlowAvailability,
        alternate_id: int,
        planned_cohorts: tuple[int, int, int],
    ) -> None:
        self._subtract_reservation(batch.reserved_out, endpoints.origin_region_id, flow)
        remaining_reservation = batch.reserved_out.get(endpoints.origin_region_id, (0, 0, 0))
        batch.reserved_out[endpoints.origin_region_id] = tuple(
            remaining_reservation[index] + planned_cohorts[index]
            for index in range(3)
        )
        batch.reserved_in[endpoints.destination_region_id] = (
            availability.other_destination_reservation
        )
        batch.reserved_in[alternate_id] = (
            batch.reserved_in.get(alternate_id, 0) + availability.planned_count
        )
        batch.pending_routes.discard((endpoints.origin_region_id, endpoints.destination_region_id))
        batch.pending_routes.add((endpoints.origin_region_id, alternate_id))

    @staticmethod
    def _emit_redirect_events(
        batch: MigrationFlowCompletionBatch,
        endpoints: MigrationFlowEndpoints,
        availability: MigrationFlowAvailability,
        alternate_id: int,
        pending_redirect: Mapping[str, Any],
    ) -> None:
        batch.state.events.append(
            EventMigrationFlowResolved(
                flow_id=endpoints.flow_id,
                status=FLOW_STATUS_REDIRECTED,
                population_count=availability.planned_count,
                reason_code="redirected_capacity",
                at_minute=batch.now,
            )
        )
        batch.state.events.append(
            EventMigrationFlowCreated(
                flow_id=str(pending_redirect["id"]),
                origin_region_id=endpoints.origin_region_id,
                destination_region_id=alternate_id,
                population_count=availability.planned_count,
                reason_code="redirected_capacity",
                at_minute=batch.now,
            )
        )

    def _complete_available_flow(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
        availability: MigrationFlowAvailability,
    ) -> None:
        count = min(availability.count, availability.capacity.available_people)
        if count <= 0:
            reason = "source_cohort_limit" if availability.available_total <= 0 else "capacity_changed"
            self._record_flow_cancellation(batch, flow, reason)
            return

        cohorts = self._completion_cohorts(flow, availability, count)
        actual = sum(cohorts)
        if actual <= 0:
            self._record_flow_cancellation(batch, flow, "source_cohort_limit")
            return
        self._apply_completed_flow(batch, flow, endpoints, availability, cohorts, actual)

    def _completion_cohorts(
        self,
        flow: Mapping[str, Any],
        availability: MigrationFlowAvailability,
        count: int,
    ) -> tuple[int, int, int]:
        planned_cohorts = tuple(
            self._integer(flow.get(field))
            for field in ("dependent_count", "working_age_count", "elderly_count")
        )
        # Keep the authorized mix unless live cohorts changed enough to make it unsafe.
        if all(
            planned_cohorts[index] <= availability.available_source[field]
            for index, field in enumerate(("pop_14", "pop_15_64", "pop_65"))
        ) and sum(planned_cohorts) == count:
            return planned_cohorts
        return calculate_migrant_cohorts(count, availability.available_source)

    def _apply_completed_flow(
        self,
        batch: MigrationFlowCompletionBatch,
        flow: Mapping[str, Any],
        endpoints: MigrationFlowEndpoints,
        availability: MigrationFlowAvailability,
        cohorts: tuple[int, int, int],
        actual: int,
    ) -> None:
        origin = batch.regions[endpoints.origin_region_id]
        destination = batch.regions[endpoints.destination_region_id]
        origin["pop_14"] = max(0, availability.source_cohorts[0] - cohorts[0])
        origin["pop_15_64"] = max(0, availability.source_cohorts[1] - cohorts[1])
        origin["pop_65"] = max(0, availability.source_cohorts[2] - cohorts[2])
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
            "completed_at_minute": batch.now,
            "status": FLOW_STATUS_COMPLETED,
            "reason_code": self._completed_flow_reason(
                actual,
                availability.planned_count,
                availability.available_total,
            ),
        })
        batch.updates.append(updated)
        batch.completed.append(updated)
        self._subtract_reservation(batch.reserved_out, endpoints.origin_region_id, flow)
        batch.reserved_in[endpoints.destination_region_id] = (
            availability.other_destination_reservation
        )
        batch.state.events.append(
            EventMigrationFlowResolved(
                flow_id=endpoints.flow_id,
                status=FLOW_STATUS_COMPLETED,
                population_count=actual,
                reason_code=str(updated["reason_code"]),
                at_minute=batch.now,
            )
        )

    @staticmethod
    def _completed_flow_reason(actual: int, planned_count: int, available_total: int) -> str:
        if actual >= planned_count:
            return "completed"
        if available_total < planned_count:
            return "source_cohort_limit"
        return "capacity_changed"

    def _persist_due_flow_batch(self, batch: MigrationFlowCompletionBatch) -> None:
        batch.state.update_table(
            "regions",
            pl.DataFrame(batch.region_rows, schema=batch.regions_frame.schema, strict=False),
        )
        self._replace_records(batch.state, "migration_flows", batch.updates, "id")
        self._append_records(batch.state, "migration_flows", batch.redirected_flows)
        for row in batch.updates:
            if row.get("status") == FLOW_STATUS_CANCELLED:
                batch.state.events.append(
                    EventMigrationFlowResolved(
                        flow_id=str(row.get("id") or ""),
                        status=FLOW_STATUS_CANCELLED,
                        population_count=max(0, self._integer(row.get("population_count"))),
                        reason_code=str(row.get("reason_code") or "cancelled"),
                        at_minute=batch.now,
                    )
                )

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
        batch = self._build_route_evaluation_batch(state, now)
        if batch is None:
            return

        for origin_id, destination_id in batch.pairs:
            self._evaluate_route_pair(batch, origin_id, destination_id)
        self._append_records(state, "migration_flows", batch.new_flows)

    def _build_route_evaluation_batch(
        self,
        state: GameState,
        now: int,
    ) -> RouteEvaluationBatch | None:
        regions = state.get_table("regions")
        countries = state.get_table("countries")
        if regions.is_empty() or countries.is_empty():
            return None

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
            return None

        policies = self._effective_policy_map(state, now)
        flows = state.get_table("migration_flows")
        flow_rows = flows.to_dicts()
        pending_rows = [row for row in flow_rows if row.get("status") == FLOW_STATUS_PENDING]
        reserved_out = self._reserved_cohorts(pending_rows)
        reserved_in = self._reserved_incoming(pending_rows)
        pending_routes = {
            (
                self._integer(row.get("origin_region_id")),
                self._integer(row.get("destination_region_id")),
            )
            for row in pending_rows
        }
        known_flow_ids = {str(row.get("id") or "") for row in flow_rows}
        return RouteEvaluationBatch(
            state=state,
            now=now,
            region_map=region_map,
            country_map=country_map,
            event_migration=event_migration,
            pairs=pairs,
            policies=policies,
            reserved_out=reserved_out,
            reserved_in=reserved_in,
            pending_routes=pending_routes,
            known_flow_ids=known_flow_ids,
        )

    def _evaluate_route_pair(
        self,
        batch: RouteEvaluationBatch,
        origin_region_id: int,
        destination_region_id: int,
    ) -> None:
        route = (origin_region_id, destination_region_id)
        if route in batch.pending_routes:
            return

        candidate = self._route_candidate(batch, origin_region_id, destination_region_id)
        if candidate is None:
            return

        border = self._border_decision(
            batch.state,
            candidate.origin_country_id,
            candidate.destination_country_id,
            batch.policies,
        )
        if not border.eligible:
            self._record_rejected_route(batch, candidate, border.reason_code)
            return

        availability = self._route_source_availability(batch, candidate)
        if availability is None:
            return
        if not availability.destination_capacity.eligible:
            self._record_rejected_route(batch, candidate, "no_destination_capacity")
            return

        record = self._route_flow_record(batch, candidate, border, availability)
        if record is not None:
            self._record_new_route(batch, candidate, availability, record)

    def _route_candidate(
        self,
        batch: RouteEvaluationBatch,
        origin_region_id: int,
        destination_region_id: int,
    ) -> RouteEvaluationCandidate | None:
        origin = batch.region_map.get(origin_region_id)
        destination = batch.region_map.get(destination_region_id)
        if origin is None or destination is None:
            return None

        origin_country_id = self._tag(origin.get("owner"))
        destination_country_id = self._tag(destination.get("owner"))
        if not origin_country_id or not destination_country_id:
            return None
        if origin_country_id not in batch.country_map or destination_country_id not in batch.country_map:
            return None

        flow_id = f"migration-{batch.now:012d}-{origin_region_id}-{destination_region_id}"
        if flow_id in batch.known_flow_ids:
            return None
        destination_policy = batch.policies.get(
            destination_country_id,
            self._default_policy(destination_country_id, batch.now),
        )
        return RouteEvaluationCandidate(
            origin_region_id=origin_region_id,
            destination_region_id=destination_region_id,
            origin_country_id=origin_country_id,
            destination_country_id=destination_country_id,
            flow_id=flow_id,
            origin=origin,
            destination=destination,
            destination_policy=destination_policy,
        )

    def _record_rejected_route(
        self,
        batch: RouteEvaluationBatch,
        candidate: RouteEvaluationCandidate,
        reason_code: str,
    ) -> None:
        batch.new_flows.append(
            self._rejected_flow(
                candidate.flow_id,
                candidate.origin_region_id,
                candidate.destination_region_id,
                candidate.origin_country_id,
                candidate.destination_country_id,
                batch.now,
                reason_code,
            )
        )
        batch.known_flow_ids.add(candidate.flow_id)

    def _route_source_availability(
        self,
        batch: RouteEvaluationBatch,
        candidate: RouteEvaluationCandidate,
    ) -> RouteSourceAvailability | None:
        origin_cohorts = self._cohort_counts(candidate.origin)
        reserved_source = batch.reserved_out.get(candidate.origin_region_id, (0, 0, 0))
        available_cohorts = {
            "pop_14": max(0, origin_cohorts[0] - reserved_source[0]),
            "pop_15_64": max(0, origin_cohorts[1] - reserved_source[1]),
            "pop_65": max(0, origin_cohorts[2] - reserved_source[2]),
        }
        source_available = sum(available_cohorts.values())
        if source_available <= 0:
            return None

        destination_capacity = assess_destination_capacity(
            candidate.destination,
            current_population=self._population(candidate.destination),
            reserved_population=batch.reserved_in.get(candidate.destination_region_id, 0),
        )
        return RouteSourceAvailability(
            cohorts=available_cohorts,
            source_available=source_available,
            reserved_source=reserved_source,
            destination_capacity=destination_capacity,
        )

    def _route_migration_estimate(
        self,
        batch: RouteEvaluationBatch,
        candidate: RouteEvaluationCandidate,
        border: BorderAccessDecision,
        availability: RouteSourceAvailability,
    ) -> RouteMigrationEstimate:
        migration_effect = batch.event_migration.get(
            ("region", str(candidate.origin_region_id), "migration"),
            0.0,
        )
        access_rate = border.access_rate
        displacement = self._bounded_ratio(candidate.origin.get("displacement_pressure"))
        access_rate *= (1.0 - displacement) + (
            displacement * self._bounded_ratio(candidate.destination_policy.get("asylum_rate"), 0.25)
        )
        count, opportunity = estimate_migration_count(
            candidate.origin,
            candidate.destination,
            batch.country_map[candidate.origin_country_id],
            batch.country_map[candidate.destination_country_id],
            access_rate=access_rate,
            source_available=availability.source_available,
            destination_available=availability.destination_capacity.available_people,
        )
        count = min(
            availability.source_available,
            availability.destination_capacity.available_people,
            max(0, int(round(count * (1.0 + min(0.5, max(-0.5, migration_effect))))))
        )
        return RouteMigrationEstimate(
            count=count,
            opportunity=opportunity,
            access_rate=access_rate,
            displacement=displacement,
            event_effect=migration_effect,
        )

    def _route_flow_record(
        self,
        batch: RouteEvaluationBatch,
        candidate: RouteEvaluationCandidate,
        border: BorderAccessDecision,
        availability: RouteSourceAvailability,
    ) -> dict[str, Any] | None:
        estimate = self._route_migration_estimate(batch, candidate, border, availability)
        if estimate.count <= 0:
            return None

        cohorts = calculate_migrant_cohorts(
            estimate.count,
            availability.cohorts,
            skilled_worker_preference=self._bounded_ratio(
                candidate.destination_policy.get("skilled_worker_preference")
            ),
            family_reunification_rate=self._bounded_ratio(
                candidate.destination_policy.get("family_reunification_rate"),
                0.5,
            ),
        )
        actual_count = sum(cohorts)
        if actual_count <= 0:
            return None

        return {
            "id": candidate.flow_id,
            "origin_region_id": candidate.origin_region_id,
            "destination_region_id": candidate.destination_region_id,
            "origin_country_id": candidate.origin_country_id,
            "destination_country_id": candidate.destination_country_id,
            "dependent_count": cohorts[0],
            "working_age_count": cohorts[1],
            "elderly_count": cohorts[2],
            "population_count": actual_count,
            "reason_code": border.reason_code,
            "reason_factors_json": self._reason_factors(
                access_rate=estimate.access_rate,
                opportunity=estimate.opportunity,
                displacement_pressure=estimate.displacement,
                capacity=availability.destination_capacity.available_people,
                event_migration_effect=estimate.event_effect,
            ),
            "created_at_minute": batch.now,
            "authorized_at_minute": batch.now,
            "expected_completion_at_minute": batch.now + FLOW_EVALUATION_PERIOD_MINUTES,
            "completed_at_minute": 0,
            "transition_rule": "finish_authorized",
            "status": FLOW_STATUS_PENDING,
        }

    def _record_new_route(
        self,
        batch: RouteEvaluationBatch,
        candidate: RouteEvaluationCandidate,
        availability: RouteSourceAvailability,
        record: dict[str, Any],
    ) -> None:
        batch.new_flows.append(record)
        batch.known_flow_ids.add(candidate.flow_id)
        batch.pending_routes.add((candidate.origin_region_id, candidate.destination_region_id))
        cohorts = (record["dependent_count"], record["working_age_count"], record["elderly_count"])
        batch.reserved_out[candidate.origin_region_id] = tuple(
            availability.reserved_source[index] + cohorts[index]
            for index in range(3)
        )
        batch.reserved_in[candidate.destination_region_id] = (
            batch.reserved_in.get(candidate.destination_region_id, 0) + record["population_count"]
        )
        batch.state.events.append(
            EventMigrationFlowCreated(
                flow_id=candidate.flow_id,
                origin_region_id=candidate.origin_region_id,
                destination_region_id=candidate.destination_region_id,
                population_count=record["population_count"],
                reason_code=record["reason_code"],
                at_minute=batch.now,
            )
        )

    def _update_signals(
        self,
        state: GameState,
        now: int,
        completed_flows: list[dict[str, Any]],
    ) -> None:
        projection = self._signal_calculator.calculate(
            current_records=state.get_table("migration_signals").to_dicts(),
            country_ids=state.get_table("countries")["id"].to_list(),
            region_records=state.get_table("regions").to_dicts(),
            completed_flows=completed_flows,
            policies=self._effective_policy_map(state, now),
            health_effects=aggregate_active_effects(
                state.tables.get("random_event_effects"),
                now,
                categories={"health"},
                subject_type="region",
            ),
            political_effects=aggregate_active_effects(
                state.tables.get("random_event_effects"),
                now,
                categories={"political_pressure"},
                subject_type="country",
            ),
            now=now,
            window_minutes=SIGNAL_WINDOW_MINUTES,
        )
        state.events.extend(projection.events)
        self._replace_records(
            state,
            "migration_signals",
            list(projection.changed_records),
            "country_id",
        )

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
