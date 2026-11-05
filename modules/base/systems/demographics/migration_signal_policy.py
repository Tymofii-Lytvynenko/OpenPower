"""Pure deterministic projection of country-level migration signals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from src.shared.events import EventMigrationSignalUpdated


SignalEffectKey = tuple[str, str, str]


@dataclass(frozen=True)
class MigrationSignalProjection:
    changed_records: tuple[dict[str, Any], ...]
    events: tuple[EventMigrationSignalUpdated, ...]


class MigrationSignalCalculator(Protocol):
    def calculate(
        self,
        *,
        current_records: Sequence[Mapping[str, Any]],
        country_ids: Sequence[Any],
        region_records: Sequence[Mapping[str, Any]],
        completed_flows: Sequence[Mapping[str, Any]],
        policies: Mapping[str, Mapping[str, Any]],
        health_effects: Mapping[SignalEffectKey, Any],
        political_effects: Mapping[SignalEffectKey, Any],
        now: int,
        window_minutes: int,
    ) -> MigrationSignalProjection: ...


class DeterministicMigrationSignalCalculator:
    """Calculate signal records and events without mutating authoritative state."""

    _TRACKED_FIELDS = (
        "gross_inflow",
        "gross_outflow",
        "net_flow",
        "working_age_delta",
        "service_pressure",
        "political_pressure",
        "law_pressure",
        "window_start_minute",
    )

    def calculate(
        self,
        *,
        current_records: Sequence[Mapping[str, Any]],
        country_ids: Sequence[Any],
        region_records: Sequence[Mapping[str, Any]],
        completed_flows: Sequence[Mapping[str, Any]],
        policies: Mapping[str, Mapping[str, Any]],
        health_effects: Mapping[SignalEffectKey, Any],
        political_effects: Mapping[SignalEffectKey, Any],
        now: int,
        window_minutes: int,
    ) -> MigrationSignalProjection:
        signal_rows = self._index_records(current_records)
        window_start = (now // window_minutes) * window_minutes
        updated = self._seed_country_rows(country_ids, signal_rows, window_start, now)
        health_pressure = self._health_pressure_by_country(region_records, health_effects)
        self._apply_completed_flows(updated, completed_flows)
        region_totals, service_capacity = self._region_totals(region_records)
        return self._project_changed_rows(
            updated,
            signal_rows,
            policies,
            political_effects,
            health_pressure,
            region_totals,
            service_capacity,
            now,
        )

    @staticmethod
    def _index_records(
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, Mapping[str, Any]]:
        return {_tag(row.get("country_id")): row for row in records}

    def _seed_country_rows(
        self,
        country_ids: Sequence[Any],
        signal_rows: Mapping[str, Mapping[str, Any]],
        window_start: int,
        now: int,
    ) -> dict[str, dict[str, Any]]:
        updated: dict[str, dict[str, Any]] = {}
        countries = [_tag(country_id) for country_id in country_ids if _tag(country_id)]
        for country_id in sorted(countries):
            current = signal_rows.get(country_id)
            existing = dict(current or {})
            if current is None or _integer(existing.get("window_start_minute")) != window_start:
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
        return updated

    def _health_pressure_by_country(
        self,
        region_records: Sequence[Mapping[str, Any]],
        health_effects: Mapping[SignalEffectKey, Any],
    ) -> dict[str, float]:
        region_owner = {
            str(row.get("id")): _tag(row.get("owner"))
            for row in region_records
        }
        pressure_by_country: dict[str, float] = {}
        for (_, region_id, _), magnitude in health_effects.items():
            owner = region_owner.get(region_id, "")
            if owner:
                pressure_by_country[owner] = (
                    pressure_by_country.get(owner, 0.0) + max(0.0, -magnitude)
                )
        return pressure_by_country

    def _apply_completed_flows(
        self,
        updated: dict[str, dict[str, Any]],
        completed_flows: Sequence[Mapping[str, Any]],
    ) -> None:
        for flow in completed_flows:
            origin = _tag(flow.get("origin_country_id"))
            destination = _tag(flow.get("destination_country_id"))
            total = max(0, _integer(flow.get("population_count")))
            working = max(0, _integer(flow.get("working_age_count")))
            if total <= 0:
                continue
            if origin in updated:
                updated[origin]["gross_outflow"] = (
                    _integer(updated[origin].get("gross_outflow")) + total
                )
                updated[origin]["working_age_delta"] = (
                    _integer(updated[origin].get("working_age_delta")) - working
                )
            if destination in updated:
                updated[destination]["gross_inflow"] = (
                    _integer(updated[destination].get("gross_inflow")) + total
                )
                updated[destination]["working_age_delta"] = (
                    _integer(updated[destination].get("working_age_delta")) + working
                )

    def _region_totals(
        self,
        region_records: Sequence[Mapping[str, Any]],
    ) -> tuple[dict[str, int], dict[str, int]]:
        region_totals: dict[str, int] = {}
        service_capacity: dict[str, int] = {}
        for region in region_records:
            owner = _tag(region.get("owner"))
            if not owner:
                continue
            region_totals[owner] = region_totals.get(owner, 0) + _population(region)
            service = _integer(region.get("service_capacity"))
            service_capacity[owner] = service_capacity.get(owner, 0) + service
        return region_totals, service_capacity

    def _project_changed_rows(
        self,
        updated: dict[str, dict[str, Any]],
        signal_rows: Mapping[str, Mapping[str, Any]],
        policies: Mapping[str, Mapping[str, Any]],
        political_effects: Mapping[SignalEffectKey, Any],
        health_pressure_by_country: Mapping[str, float],
        region_totals: Mapping[str, int],
        service_capacity: Mapping[str, int],
        now: int,
    ) -> MigrationSignalProjection:
        changed: list[dict[str, Any]] = []
        events: list[EventMigrationSignalUpdated] = []
        for country_id, row in updated.items():
            inflow = _integer(row.get("gross_inflow"))
            outflow = _integer(row.get("gross_outflow"))
            row["net_flow"] = inflow - outflow
            population = max(1, region_totals.get(country_id, 0))
            event_political = political_effects.get(
                ("country", country_id, "political_pressure"),
                0.0,
            )
            row["political_pressure"] = _bounded_ratio(
                max(inflow, outflow) / population / 0.05
                + min(0.5, max(-0.5, event_political))
            )
            policy = policies.get(country_id, {})
            row["law_pressure"] = _bounded_ratio(
                row["political_pressure"]
                * _bounded_ratio(policy.get("enforcement_strength"), 0.5)
            )
            capacity = service_capacity.get(country_id, 0)
            if capacity <= 0:
                capacity = max(1, int(population * 0.1))
            health_pressure = min(
                0.5,
                max(0.0, health_pressure_by_country.get(country_id, 0.0)),
            )
            row["service_pressure"] = _bounded_ratio(inflow / capacity + health_pressure)
            row["updated_at_minute"] = now
            current = signal_rows.get(country_id)
            if current is None or any(
                current.get(field) != row.get(field)
                for field in self._TRACKED_FIELDS
            ):
                changed.append(row)
                events.append(
                    EventMigrationSignalUpdated(
                        country_id=country_id,
                        political_pressure=float(row["political_pressure"]),
                        service_pressure=float(row["service_pressure"]),
                        net_flow=int(row["net_flow"]),
                        at_minute=now,
                        law_pressure=float(row["law_pressure"]),
                    )
                )
        return MigrationSignalProjection(tuple(changed), tuple(events))


def _population(region: Mapping[str, Any]) -> int:
    return sum(
        max(0, _integer(region.get(field)))
        for field in ("pop_14", "pop_15_64", "pop_65")
    )


def _integer(value: Any) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return int(numeric) if math.isfinite(numeric) and numeric > 0.0 else 0


def _bounded_ratio(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        numeric = default
    if not math.isfinite(numeric):
        numeric = default
    return min(1.0, max(0.0, numeric))


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
