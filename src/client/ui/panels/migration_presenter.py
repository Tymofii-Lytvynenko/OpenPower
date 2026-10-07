from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import polars as pl


@dataclass(frozen=True, slots=True)
class MigrationRouteView:
    origin_region_id: int
    destination_region_id: int
    population_count: int
    status: str
    reason_code: str
    reason_label: str


@dataclass(frozen=True, slots=True)
class MigrationCountrySummary:
    country_id: str
    migration_policy: str
    border_policy: str
    entry_rate: float
    exit_rate: float
    asylum_rate: float
    family_reunification_rate: float
    skilled_worker_preference: float
    enforcement_strength: float
    gross_inflow: int
    gross_outflow: int
    net_flow: int
    working_age_delta: int
    service_pressure: float
    political_pressure: float
    law_pressure: float
    signal_window_start_minute: int
    recent_trend: str
    status_counts: tuple[tuple[str, int], ...]
    top_routes: tuple[MigrationRouteView, ...]
    recent_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MigrationRegionSummary:
    region_id: int
    owner: str
    incoming_population: int
    outgoing_population: int
    pending_population: int
    net_migration: int
    capacity_pressure: float | None
    top_routes: tuple[MigrationRouteView, ...]
    recent_reasons: tuple[str, ...]


class MigrationPresenter:
    """Projects policy and movement tables into immutable, read-only UI summaries."""

    _STATUS_ORDER = ("pending", "completed", "redirected", "rejected", "cancelled")
    _REASON_LABELS = {
        "eligible_domestic": "Eligible domestic movement",
        "eligible_mobility_agreement": "Allowed by mobility agreement",
        "eligible_capacity": "Destination capacity available",
        "border_closed": "Border is closed",
        "border_changed": "Border policy changed before completion",
        "hostile_relations": "Relations are below the permitted threshold",
        "active_war": "Active conflict blocks movement",
        "movement_sanction": "Movement-specific restriction is active",
        "no_destination_capacity": "Destination lacks available capacity",
        "capacity_changed": "Destination capacity changed before arrival",
        "redirected_capacity": "Rerouted because the original destination is full",
        "source_cohort_limit": "Origin lacks the authorized cohort size",
        "authority_changed": "Region ownership changed before completion",
        "policy_restricted": "Effective migration policy does not permit this flow",
    }

    def present_country(
        self,
        state: Any,
        country_id: str,
        *,
        route_limit: int = 5,
        reason_limit: int = 5,
    ) -> MigrationCountrySummary | None:
        tables = getattr(state, "tables", {})
        tag = str(country_id or "").strip().upper()
        countries = tables.get("countries")
        if not tag or countries is None or "id" not in countries.columns:
            return None
        if countries.filter(pl.col("id").cast(pl.Utf8).str.to_uppercase() == tag).is_empty():
            return None

        policy = self._find_row(tables.get("migration_policies"), "country_id", tag) or {}
        signal = self._find_row(tables.get("migration_signals"), "country_id", tag) or {}
        flows = self._country_flows(tables.get("migration_flows"), tag)
        net_flow = self._integer(signal.get("net_flow"))
        trend = "net inflow" if net_flow > 0 else "net outflow" if net_flow < 0 else "balanced"
        status_counts = self._status_counts(flows)
        return MigrationCountrySummary(
            country_id=tag,
            migration_policy=str(policy.get("migration_policy") or "managed"),
            border_policy=str(policy.get("border_policy") or "managed"),
            entry_rate=self._bounded(policy.get("entry_rate"), 0.0, 1.0, 0.5),
            exit_rate=self._bounded(policy.get("exit_rate"), 0.0, 1.0, 0.5),
            asylum_rate=self._bounded(policy.get("asylum_rate"), 0.0, 1.0, 0.25),
            family_reunification_rate=self._bounded(policy.get("family_reunification_rate"), 0.0, 1.0, 0.5),
            skilled_worker_preference=self._bounded(policy.get("skilled_worker_preference"), 0.0, 1.0),
            enforcement_strength=self._bounded(policy.get("enforcement_strength"), 0.0, 1.0, 0.5),
            gross_inflow=max(0, self._integer(signal.get("gross_inflow"))),
            gross_outflow=max(0, self._integer(signal.get("gross_outflow"))),
            net_flow=net_flow,
            working_age_delta=self._integer(signal.get("working_age_delta")),
            service_pressure=self._bounded(signal.get("service_pressure"), 0.0, 1.0),
            political_pressure=self._bounded(signal.get("political_pressure"), 0.0, 1.0),
            law_pressure=self._bounded(signal.get("law_pressure"), 0.0, 1.0),
            signal_window_start_minute=max(0, self._integer(signal.get("window_start_minute"))),
            recent_trend=trend,
            status_counts=status_counts,
            top_routes=self._top_routes(flows, max(0, int(route_limit))),
            recent_reasons=self._recent_reasons(flows, max(0, int(reason_limit))),
        )

    def present_region(
        self,
        state: Any,
        region_id: int,
        *,
        route_limit: int = 5,
        reason_limit: int = 5,
    ) -> MigrationRegionSummary | None:
        tables = getattr(state, "tables", {})
        regions = tables.get("regions")
        if regions is None or not {"id", "owner"}.issubset(regions.columns):
            return None
        selected = regions.filter(pl.col("id") == int(region_id))
        if selected.is_empty():
            return None
        region = selected.row(0, named=True)
        owner = str(region.get("owner") or "").strip().upper()
        flows_frame = tables.get("migration_flows")
        flows = []
        if flows_frame is not None and {"origin_region_id", "destination_region_id"}.issubset(flows_frame.columns):
            flows = [
                row for row in flows_frame.to_dicts()
                if self._integer(row.get("origin_region_id")) == int(region_id)
                or self._integer(row.get("destination_region_id")) == int(region_id)
            ]

        incoming = sum(
            max(0, self._integer(row.get("population_count")))
            for row in flows
            if self._integer(row.get("destination_region_id")) == int(region_id)
            and str(row.get("status") or "") == "completed"
        )
        outgoing = sum(
            max(0, self._integer(row.get("population_count")))
            for row in flows
            if self._integer(row.get("origin_region_id")) == int(region_id)
            and str(row.get("status") or "") == "completed"
        )
        pending_incoming = sum(
            max(0, self._integer(row.get("population_count")))
            for row in flows
            if self._integer(row.get("destination_region_id")) == int(region_id)
            and str(row.get("status") or "") == "pending"
        )
        return MigrationRegionSummary(
            region_id=int(region_id),
            owner=owner,
            incoming_population=incoming,
            outgoing_population=outgoing,
            pending_population=pending_incoming,
            net_migration=incoming - outgoing,
            capacity_pressure=self._capacity_pressure(region, pending_incoming),
            top_routes=self._top_routes(flows, max(0, int(route_limit))),
            recent_reasons=self._recent_reasons(flows, max(0, int(reason_limit))),
        )

    def _country_flows(self, frame: pl.DataFrame | None, country_id: str) -> list[dict[str, Any]]:
        if frame is None or not {"origin_country_id", "destination_country_id"}.issubset(frame.columns):
            return []
        return [
            row for row in frame.to_dicts()
            if str(row.get("origin_country_id") or "").strip().upper() == country_id
            or str(row.get("destination_country_id") or "").strip().upper() == country_id
        ]

    def _top_routes(self, flows: list[dict[str, Any]], limit: int) -> tuple[MigrationRouteView, ...]:
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in flows:
            key = (
                self._integer(row.get("origin_region_id")),
                self._integer(row.get("destination_region_id")),
            )
            grouped.setdefault(key, []).append(row)
        views: list[MigrationRouteView] = []
        for (origin, destination), rows in grouped.items():
            ordered = sorted(
                rows,
                key=lambda row: (self._integer(row.get("created_at_minute")), str(row.get("id") or "")),
                reverse=True,
            )
            latest = ordered[0]
            code = str(latest.get("reason_code") or "")
            views.append(MigrationRouteView(
                origin_region_id=origin,
                destination_region_id=destination,
                population_count=sum(max(0, self._integer(row.get("population_count"))) for row in rows),
                status=str(latest.get("status") or "unknown"),
                reason_code=code,
                reason_label=self._reason_label(code),
            ))
        views.sort(key=lambda view: (-view.population_count, view.origin_region_id, view.destination_region_id))
        return tuple(views[:limit])

    def _recent_reasons(self, flows: list[dict[str, Any]], limit: int) -> tuple[str, ...]:
        recent = sorted(
            flows,
            key=lambda row: (self._integer(row.get("created_at_minute")), str(row.get("id") or "")),
            reverse=True,
        )
        return tuple(
            self._reason_label(str(row.get("reason_code") or ""))
            for row in recent[:limit]
        )

    def _status_counts(self, flows: list[dict[str, Any]]) -> tuple[tuple[str, int], ...]:
        counts = {status: 0 for status in self._STATUS_ORDER}
        for flow in flows:
            status = str(flow.get("status") or "")
            if status in counts:
                counts[status] += 1
        return tuple((status, counts[status]) for status in self._STATUS_ORDER)

    def _capacity_pressure(self, region: dict[str, Any], pending_population: int) -> float | None:
        population = sum(
            max(0, self._integer(region.get(column)))
            for column in ("pop_14", "pop_15_64", "pop_65")
        )
        capacities = [
            self._integer(region.get(column))
            for column in ("housing_capacity", "employment_capacity", "service_capacity", "transport_capacity")
            if column in region
        ]
        positive = [capacity for capacity in capacities if capacity > 0]
        if not positive:
            return None
        return self._bounded((population + max(0, pending_population)) / min(positive), 0.0, 1.0)

    def _reason_label(self, reason_code: str) -> str:
        return self._REASON_LABELS.get(
            reason_code,
            reason_code.replace("_", " ").capitalize() if reason_code else "Unspecified",
        )

    def _find_row(self, frame: pl.DataFrame | None, key: str, value: str) -> dict[str, Any] | None:
        if frame is None or key not in frame.columns:
            return None
        matched = frame.filter(pl.col(key).cast(pl.Utf8).str.to_uppercase() == value)
        return matched.row(0, named=True) if not matched.is_empty() else None

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return int(numeric) if math.isfinite(numeric) else 0

    @staticmethod
    def _bounded(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(numeric):
            return default
        return min(max(numeric, minimum), maximum)
