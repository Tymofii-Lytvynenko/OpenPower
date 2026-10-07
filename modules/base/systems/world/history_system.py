"""Incremental, deterministic recording for historical observations and events."""

from __future__ import annotations

import json
import math
import re
from typing import Any

import polars as pl

from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


_COUNTRY_INDICATORS = {
    "gdp": "USD/year",
    "human_dev": "index",
    "money_reserves": "USD",
    "military_count": "units",
    "economic_health": "index",
    "inflation_rate": "ratio",
    "unemployment_rate": "ratio",
    "employment_rate": "ratio",
    "underemployment_rate": "ratio",
    "domestic_debt": "USD",
    "foreign_debt": "USD",
    "annual_debt_service": "USD/year",
    "arrears": "USD",
    "poverty_rate": "ratio",
    "infrastructure_index": "index",
    "telecom_index": "index",
    "public_service_index": "index",
    "industrial_access_index": "index",
    "migration_pressure": "index",
    "nominal_income_index": "index",
    "real_income_index": "index",
    "total_annual_revenue": "USD/year",
    "total_annual_expense": "USD/year",
    "budget_research_ratio": "ratio",
    "budget_edu_ratio": "ratio",
    "budget_health_ratio": "ratio",
    "budget_infra_ratio": "ratio",
}

_TABLES_READ = frozenset({
    "countries", "regions", "countries_relations", "units", "strategic_weapons",
    "regional_infrastructure", "regional_production", "domestic_production",
    "countries_wars", "countries_treaties", "political_history", "economic_cause_records",
    "research_tracks", "country_governments", "political_parties", "country_laws", "resource_ledger",
    "battle_participants", "battles", "occupations", "migration_flows", "migration_signals",
    "infrastructure_projects", "random_events", "random_event_effects", "trade_routes",
    "history_indicator_definitions", "history_series_state", "history_snapshots", "history_events",
})
_TABLES_WRITTEN = frozenset({
    "history_indicator_definitions", "history_series_state", "history_snapshots", "history_events",
})


class HistorySystem(ISystem):
    """Records only due observations, changed configured metrics, and new journal events."""

    access = SystemAccess(reads=_TABLES_READ, writes=_TABLES_WRITTEN, phase=SystemPhase.POST_PROCESS)

    @property
    def id(self) -> str:
        return "base.history"

    @property
    def dependencies(self) -> list[str]:
        return ["base.campaign"]

    def update(self, state: GameState, delta_time: float) -> None:
        self._ensure_defaults(state)
        self._record_observations(state)
        self._record_journal_events(state)
        self._record_economic_causes(state)

    def _ensure_defaults(self, state: GameState) -> None:
        table = state.tables.get("history_indicator_definitions")
        if table is None:
            return
        existing = {str(row.get("id") or "") for row in table.to_dicts()}
        defaults: list[dict[str, Any]] = []
        countries = state.tables.get("countries")
        if countries is not None:
            for field, unit in _COUNTRY_INDICATORS.items():
                if field not in countries.columns:
                    continue
                defaults.append(self._definition(
                    f"country.{field}", "country", "countries", field, "id", unit,
                ))
            for field, unit in (("gvt_approval", "index"), ("gvt_stability", "index")):
                if field in countries.columns:
                    defaults.append(self._definition(
                        f"politics.{field}", "country", "countries", field, "id", unit,
                    ))
            if "gdp" in countries.columns:
                defaults.append(self._definition(
                    "country.gdp_per_capita", "country", "countries", "gdp", "id",
                    "USD/person/year", derivation="gdp_per_capita",
                ))
                defaults.append(self._definition(
                    "country.population", "country", "regions", "id", "owner", "people",
                    aggregation="sum", derivation="country_population",
                ))
        ledger = state.tables.get("resource_ledger")
        if ledger is not None and {"country_id", "consumption_usd", "balance_usd"}.issubset(ledger.columns):
            defaults.append(self._definition(
                "country.resource_coverage", "country", "resource_ledger", "balance_usd", "country_id",
                "ratio", derivation="resource_coverage",
            ))
        governments = state.tables.get("country_governments")
        if governments is not None:
            for field, unit in (("election_risk", "ratio"), ("ideology_balance", "ratio")):
                if field in governments.columns:
                    defaults.append(self._definition(
                        f"politics.{field}", "country", "country_governments", field, "country_id", unit,
                    ))
        parties = state.tables.get("political_parties")
        if parties is not None and {"country_id", "party_id", "support_share"}.issubset(parties.columns):
            defaults.append(self._definition(
                "politics.ruling_party_support", "country", "political_parties", "support_share",
                "country_id", "ratio", derivation="ruling_party_support",
            ))
        research = state.tables.get("research_tracks")
        if research is not None and "country_id" in research.columns:
            if "research_level" in research.columns:
                defaults.append(self._definition(
                    "research.total_level", "country", "research_tracks", "research_level", "country_id",
                    "levels", aggregation="sum",
                ))
            if "progress" in research.columns:
                defaults.append(self._definition(
                    "research.total_progress", "country", "research_tracks", "progress", "country_id",
                    "progress", aggregation="sum",
                ))
        treaties = state.tables.get("countries_treaties")
        if treaties is not None and "members" in treaties.columns:
            defaults.append(self._definition(
                "diplomacy.active_treaties", "country", "countries_treaties", "members", "id", "treaties",
                derivation="treaty_membership_count",
            ))
        wars = state.tables.get("countries_wars")
        if wars is not None and {"side_a", "side_b", "status"}.issubset(wars.columns):
            defaults.append(self._definition(
                "military.active_wars", "country", "countries_wars", "side_a", "id", "wars",
                derivation="active_war_count",
            ))
        production = state.tables.get("domestic_production")
        if production is not None and {"country_id", "domestic_production"}.issubset(production.columns):
            defaults.append(self._definition(
                "country.resource_production", "country", "domestic_production", "domestic_production",
                "country_id", "USD/year", aggregation="sum",
            ))
        regions = state.tables.get("regions")
        if regions is not None:
            for field, unit in (("pop_14", "people"), ("pop_15_64", "people"), ("pop_65", "people")):
                if field in regions.columns:
                    defaults.append(self._definition(
                        f"region.{field}", "region", "regions", field, "id", unit,
                    ))
            population_fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
            if population_fields:
                defaults.append(self._definition(
                    "region.population", "region", "regions", population_fields[0], "id", "people",
                    derivation="region_population",
                ))
        relations = state.tables.get("countries_relations")
        if relations is not None and {"source", "target", "value"}.issubset(relations.columns):
            defaults.append(self._definition(
                "relationship.relation_value", "relationship", "countries_relations", "value",
                "source", "relation points", related_id_field="target",
            ))
        units = state.tables.get("units")
        if units is not None:
            # Production unit rows use `owner`; retain support for older custom schemas.
            subject_field = "owner" if "owner" in units.columns else "country_id"
        else:
            subject_field = ""
        if units is not None and subject_field in units.columns:
            defaults.append(self._definition(
                "military.unit_count", "country", "units", "id", subject_field, "units",
                aggregation="count",
            ))
            if "strength" in units.columns:
                defaults.append(self._definition(
                    "military.total_strength", "country", "units", "strength", subject_field,
                    "strength", aggregation="sum",
                ))
        weapons = state.tables.get("strategic_weapons")
        if weapons is not None and {"country_id", "quantity"}.issubset(weapons.columns):
            defaults.append(self._definition(
                "strategic.weapon_quantity", "country", "strategic_weapons", "quantity",
                "country_id", "weapons", aggregation="sum",
            ))
        infrastructure = state.tables.get("regional_infrastructure")
        if infrastructure is not None and {"region_id", "category", "level"}.issubset(infrastructure.columns):
            for category in sorted({str(value) for value in infrastructure.get_column("category").drop_nulls().to_list()}):
                defaults.append(self._definition(
                    f"infrastructure.{self._slug(category)}.level", "region", "regional_infrastructure",
                    "level", "region_id", "level", filter_field="category", filter_value=category,
                    aggregation="mean",
                ))
        missing = [row for row in defaults if row["id"] not in existing]
        if missing:
            state.update_table("history_indicator_definitions", self._append(table, missing))

    @staticmethod
    def _definition(
        indicator_id: str,
        subject_type: str,
        source_table: str,
        source_field: str,
        subject_id_field: str,
        unit: str,
        *,
        related_id_field: str = "",
        aggregation: str = "last",
        derivation: str = "",
        filter_field: str = "",
        filter_value: str = "",
    ) -> dict[str, Any]:
        return {
            "id": indicator_id, "subject_type": subject_type, "source_table": source_table,
            "source_field": source_field, "subject_id_field": subject_id_field,
            "related_id_field": related_id_field, "unit": unit,
            "sample_interval_minutes": 1440, "retention_window_minutes": 5_256_000,
            "max_samples_per_series": 3650, "aggregation": aggregation,
            "derivation": derivation, "filter_field": filter_field, "filter_value": filter_value,
            "missing_data_policy": "mark_gap", "enabled": True, "schema_version": 1,
        }

    def _record_observations(self, state: GameState) -> None:
        definitions = state.tables.get("history_indicator_definitions")
        series_table = state.tables.get("history_series_state")
        snapshots_table = state.tables.get("history_snapshots")
        if definitions is None or series_table is None or snapshots_table is None:
            return
        enabled = [row for row in definitions.to_dicts() if row.get("enabled", True)]
        if not enabled:
            return
        previous_revisions = state.globals.get("history_source_revisions")
        previous_revisions = previous_revisions if isinstance(previous_revisions, dict) else {}
        current_revisions = {name: int(state.table_revisions.get(name, 0)) for name in _TABLES_READ}
        initial = not series_table.height
        changed_tables = {
            name for name, revision in current_revisions.items()
            if previous_revisions.get(name) != revision
        }
        now = int(state.time.total_minutes)
        tick = int(state.globals.get("tick", 0))
        series_rows = series_table.to_dicts()
        series_by_key = {str(row.get("id") or ""): row for row in series_rows}
        new_series: list[dict[str, Any]] = []
        new_snapshots: list[dict[str, Any]] = []

        for definition in enabled:
            source_table = str(definition.get("source_table") or "")
            dependencies = self._definition_sources(definition)
            definition_changed = "history_indicator_definitions" in changed_tables
            if not initial and not definition_changed and not (dependencies & changed_tables) and now < self._next_due(series_by_key, definition):
                continue
            values, kinds = self._measure_definition(state, definition)
            indicator_id = str(definition.get("id") or "")
            interval = max(1, int(definition.get("sample_interval_minutes") or 1440))
            retention = max(interval, int(definition.get("retention_window_minutes") or 5_256_000))
            limit = max(1, int(definition.get("max_samples_per_series") or 3650))
            subject_type = str(definition.get("subject_type") or "world")
            known = {
                str(row.get("subject_id") or "")
                for row in series_rows
                if row.get("indicator_id") == indicator_id and row.get("subject_type") == subject_type
            }
            subjects = set(values) | known
            for subject_id in sorted(subjects):
                key = self._series_id(subject_type, subject_id, indicator_id)
                previous = series_by_key.get(key)
                due = previous is None or now >= int(previous.get("next_sample_at_minute") or 0)
                value = values.get(subject_id)
                completeness = "complete" if value is not None else "missing"
                changed = previous is None or not self._same_value(previous.get("latest_value"), value)
                if value is None and str(definition.get("missing_data_policy") or "mark_gap") == "omit":
                    continue
                if not due and not changed:
                    continue
                if value is None and not due and previous is None:
                    continue
                boundary = "initial" if previous is None else ("interval" if due else "change")
                snapshot = self._row_defaults(state, "history_snapshots")
                snapshot.update({
                    "id": f"history:{indicator_id}:{subject_type}:{subject_id}:{now}:{tick}",
                    "subject_type": subject_type, "subject_id": subject_id,
                    "indicator_id": indicator_id, "value": value, "unit": str(definition.get("unit") or ""),
                    "game_minute": now, "tick": tick, "source_boundary": boundary,
                    "confidence": 0.9 if kinds.get(subject_id) == "derived" else 1.0,
                    "completeness": completeness,
                    "value_kind": kinds.get(subject_id, "authoritative"),
                })
                new_snapshots.append(snapshot)
                next_sample = int(previous.get("next_sample_at_minute") or 0) if previous else self._next_boundary(now, interval)
                if due:
                    next_sample = self._next_boundary(now, interval)
                updated = self._row_defaults(state, "history_series_state")
                updated.update({
                    "id": key, "subject_type": subject_type, "subject_id": subject_id,
                    "indicator_id": indicator_id, "unit": str(definition.get("unit") or ""),
                    "latest_value": value, "latest_snapshot_id": snapshot["id"],
                    "latest_source_boundary": boundary,
                    "latest_confidence": snapshot["confidence"],
                    "latest_value_kind": snapshot["value_kind"],
                    "last_sample_minute": now, "last_sample_tick": tick,
                    "next_sample_at_minute": next_sample,
                    "sample_count": (int(previous.get("sample_count") or 0) if previous else 0) + 1,
                    "last_compacted_at_minute": int(previous.get("last_compacted_at_minute") or now) if previous else now,
                    "completeness": completeness,
                    "source_revision": int(state.table_revisions.get(source_table, 0)),
                    "schema_version": 1,
                })
                new_series.append(updated)
                series_by_key[key] = updated
            for removed_subject in sorted(known - set(values)):
                key = self._series_id(subject_type, removed_subject, indicator_id)
                previous = series_by_key.get(key)
                if previous is None or previous.get("latest_value") is None:
                    continue
                snapshot = self._row_defaults(state, "history_snapshots")
                snapshot.update({
                    "id": f"history:{indicator_id}:{subject_type}:{removed_subject}:{now}:{tick}",
                    "subject_type": subject_type, "subject_id": removed_subject,
                    "indicator_id": indicator_id, "value": None, "unit": str(definition.get("unit") or ""),
                    "game_minute": now, "tick": tick, "source_boundary": "entity_removed",
                    "confidence": 1.0, "completeness": "missing", "value_kind": "authoritative",
                })
                new_snapshots.append(snapshot)
                previous.update({"latest_value": None, "last_sample_minute": now,
                                 "latest_snapshot_id": snapshot["id"],
                                 "latest_source_boundary": "entity_removed",
                                 "latest_confidence": 1.0,
                                 "latest_value_kind": "authoritative",
                                 "last_sample_tick": tick, "completeness": "missing",
                                 "sample_count": int(previous.get("sample_count") or 0) + 1})
                new_series.append(previous)

        if new_snapshots:
            state.update_table("history_snapshots", self._append(snapshots_table, new_snapshots))
        if new_series:
            merged = {str(row.get("id") or ""): row for row in series_rows}
            merged.update({str(row["id"]): row for row in new_series})
            state.update_table("history_series_state", self._frame(series_table, list(merged.values())))
        if new_snapshots:
            touched_keys = {
                self._series_id(str(row["subject_type"]), str(row["subject_id"]), str(row["indicator_id"]))
                for row in new_snapshots
            }
            self._compact(state, enabled, touched_keys, now)
        state.globals["history_series_snapshot_revision"] = int(
            state.table_revisions.get("history_snapshots", 0)
        )
        state.globals["history_source_revisions"] = current_revisions

    def _measure_definition(self, state: GameState, definition: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
        derivation = str(definition.get("derivation") or "")
        if derivation == "gdp_per_capita":
            return self._gdp_per_capita(state)
        if derivation == "country_population":
            return self._country_population(state)
        if derivation == "region_population":
            table = state.tables.get("regions")
            if table is None:
                return {}, {}
            rows = table.to_dicts()
            fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in table.columns]
            values = {
                str(row.get("id")): sum(float(row.get(field) or 0.0) for field in fields)
                for row in rows if row.get("id") is not None
            }
            return values, {subject: "derived" for subject in values}
        if derivation == "resource_coverage":
            return self._resource_coverage(state)
        if derivation == "treaty_membership_count":
            return self._treaty_membership_count(state)
        if derivation == "active_war_count":
            return self._active_war_count(state)
        if derivation == "ruling_party_support":
            return self._ruling_party_support(state)

        table = state.tables.get(str(definition.get("source_table") or ""))
        if table is None or table.is_empty():
            return {}, {}
        field = str(definition.get("source_field") or "")
        subject_field = str(definition.get("subject_id_field") or "")
        related_field = str(definition.get("related_id_field") or "")
        filter_field = str(definition.get("filter_field") or "")
        filter_value = str(definition.get("filter_value") or "")
        if not {field, subject_field}.issubset(table.columns):
            return {}, {}
        aggregation = str(definition.get("aggregation") or "last").lower()
        grouped: dict[str, list[float]] = {}
        for row in table.to_dicts():
            if filter_field and str(row.get(filter_field) or "") != filter_value:
                continue
            subject = str(row.get(subject_field) or "").strip()
            if not subject:
                continue
            if definition.get("subject_type") == "relationship" and related_field:
                related = str(row.get(related_field) or "").strip()
                if not related:
                    continue
                subject = "|".join(sorted((subject.upper(), related.upper())))
            value = row.get(field)
            if aggregation == "count":
                grouped.setdefault(subject, []).append(1.0)
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                grouped.setdefault(subject, []).append(number)
        values = {subject: self._aggregate(samples, aggregation) for subject, samples in grouped.items()}
        return values, {subject: "authoritative" for subject in values}

    @staticmethod
    def _aggregate(values: list[float], aggregation: str) -> float:
        if aggregation == "sum" or aggregation == "count":
            return float(sum(values))
        if aggregation == "mean":
            return float(sum(values) / len(values)) if values else 0.0
        if aggregation == "max":
            return float(max(values)) if values else 0.0
        return float(values[-1])

    def _gdp_per_capita(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        countries = state.tables.get("countries")
        regions = state.tables.get("regions")
        if countries is None or regions is None or "gdp" not in countries.columns:
            return {}, {}
        owner_field = "owner" if "owner" in regions.columns else "owner_tag" if "owner_tag" in regions.columns else ""
        population_fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
        if not owner_field or not population_fields:
            return {}, {}
        population: dict[str, float] = {}
        for row in regions.to_dicts():
            owner = str(row.get(owner_field) or "").strip().upper()
            if not owner:
                continue
            population[owner] = population.get(owner, 0.0) + sum(float(row.get(field) or 0.0) for field in population_fields)
        values: dict[str, float] = {}
        for row in countries.to_dicts():
            country = str(row.get("id") or "").strip().upper()
            people = population.get(country, 0.0)
            try:
                gdp = float(row.get("gdp"))
            except (TypeError, ValueError):
                continue
            if country and people > 0 and math.isfinite(gdp):
                values[country] = gdp / people
        return values, {subject: "derived" for subject in values}

    def _country_population(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        regions = state.tables.get("regions")
        if regions is None or "owner" not in regions.columns:
            return {}, {}
        fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
        if not fields:
            return {}, {}
        totals: dict[str, float] = {}
        for row in regions.to_dicts():
            owner = self._tag(row.get("owner"))
            if owner:
                totals[owner] = totals.get(owner, 0.0) + sum(float(row.get(field) or 0.0) for field in fields)
        return totals, {subject: "derived" for subject in totals}

    def _resource_coverage(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        ledger = state.tables.get("resource_ledger")
        if ledger is None or not {"country_id", "consumption_usd", "balance_usd"}.issubset(ledger.columns):
            return {}, {}
        totals: dict[str, list[float]] = {}
        for row in ledger.to_dicts():
            country = self._tag(row.get("country_id"))
            if not country:
                continue
            values = totals.setdefault(country, [0.0, 0.0])
            values[0] += max(0.0, float(row.get("consumption_usd") or 0.0))
            balance = float(row.get("balance_usd") or 0.0)
            if balance < 0:
                values[1] += abs(balance)
        coverage = {
            country: 1.0 if consumption <= 0 else max(0.0, min(1.0, 1.0 - shortage / consumption))
            for country, (consumption, shortage) in totals.items()
        }
        return coverage, {subject: "derived" for subject in coverage}

    def _treaty_membership_count(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        treaties = state.tables.get("countries_treaties")
        if treaties is None or "members" not in treaties.columns:
            return {}, {}
        counts: dict[str, float] = {}
        for row in treaties.to_dicts():
            if str(row.get("status") or "active").strip().lower() != "active":
                continue
            members = row.get("members") or []
            if isinstance(members, str):
                try:
                    members = json.loads(members)
                except (TypeError, ValueError):
                    members = []
            if isinstance(members, (list, tuple, set)):
                for country in {self._tag(item) for item in members if self._tag(item)}:
                    counts[country] = counts.get(country, 0.0) + 1.0
        return counts, {subject: "derived" for subject in counts}

    def _active_war_count(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        wars = state.tables.get("countries_wars")
        if wars is None or not {"side_a", "side_b", "status"}.issubset(wars.columns):
            return {}, {}
        counts: dict[str, float] = {}
        for row in wars.to_dicts():
            if str(row.get("status") or "active").strip().lower() != "active":
                continue
            for side in (row.get("side_a") or [], row.get("side_b") or []):
                if isinstance(side, str):
                    try:
                        side = json.loads(side)
                    except (TypeError, ValueError):
                        side = [side]
                if isinstance(side, (list, tuple, set)):
                    for country in {self._tag(item) for item in side if self._tag(item)}:
                        counts[country] = counts.get(country, 0.0) + 1.0
        return counts, {subject: "derived" for subject in counts}

    def _ruling_party_support(self, state: GameState) -> tuple[dict[str, float], dict[str, str]]:
        parties = state.tables.get("political_parties")
        if parties is None or not {"country_id", "party_id", "support_share"}.issubset(parties.columns):
            return {}, {}
        government_table = state.tables.get("country_governments")
        ruling_by_country = {
            self._tag(row.get("country_id")): str(row.get("ruling_party_id") or "").strip().casefold()
            for row in (government_table.to_dicts() if government_table is not None else [])
        }
        rows: dict[str, float] = {}
        for row in parties.to_dicts():
            country = self._tag(row.get("country_id"))
            party = str(row.get("party_id") or "").strip().casefold()
            if country and (party == ruling_by_country.get(country) or (not ruling_by_country.get(country) and bool(row.get("is_ruling")))):
                value = float(row.get("support_share") or 0.0)
                if math.isfinite(value):
                    rows[country] = value
        return rows, {subject: "derived" for subject in rows}

    def _record_journal_events(self, state: GameState) -> None:
        table = state.tables.get("history_events")
        if table is None:
            return
        records = state.journal.domain_events
        cursor = int(state.globals.get("history_journal_cursor", 0))
        if cursor > len(records):
            cursor = len(records)
        existing = {str(row.get("id") or "") for row in table.to_dicts()}
        additions: list[dict[str, Any]] = []
        for record in records[cursor:]:
            event_id = str(record.get("event_id") or "")
            if not event_id or f"journal:{event_id}" in existing:
                continue
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            related = self._country_ids(payload)
            country = next((self._tag(payload.get(key)) for key in ("country_id", "country_tag", "source_country_tag", "attacker_tag") if payload.get(key)), "")
            subject_type = "country" if country else "region" if payload.get("region_id") else "world"
            subject_id = country or str(payload.get("region_id") or "world")
            minute = int(record.get("game_minute") or self._event_minute(payload, int(state.time.total_minutes)))
            row = self._row_defaults(state, "history_events")
            row.update({
                "id": f"journal:{event_id}", "event_type": str(record.get("event_type") or "DomainEvent"),
                "subject_type": subject_type, "subject_id": subject_id,
                "related_country_ids_json": json.dumps(sorted(related), separators=(",", ":")),
                "region_id": int(payload.get("region_id") or 0),
                "title": self._humanize(str(record.get("event_type") or "Domain event")),
                "details_json": json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
                "source_type": str(record.get("source") or "simulation"), "source_id": event_id,
                "cause_source_type": str(payload.get("cause_source_type") or payload.get("source_type") or ""),
                "cause_source_id": str(payload.get("cause_source_id") or payload.get("source_id") or ""),
                "game_minute": minute, "tick": int(record.get("tick") or state.globals.get("tick", 0)),
                "confidence": 1.0, "completeness": "authoritative", "schema_version": 1,
            })
            additions.append(row)
            existing.add(f"journal:{event_id}")
        state.globals["history_journal_cursor"] = len(records)
        if additions:
            state.update_table("history_events", self._append(table, additions))

    def _record_economic_causes(self, state: GameState) -> None:
        causes = state.tables.get("economic_cause_records")
        events = state.tables.get("history_events")
        if causes is None or events is None or causes.is_empty():
            return
        previous_revision = int(state.globals.get("history_economic_cause_revision", -1))
        revision = int(state.table_revisions.get("economic_cause_records", 0))
        if revision == previous_revision:
            return
        known = {str(row.get("id") or "") for row in events.to_dicts()}
        additions: list[dict[str, Any]] = []
        for cause in causes.to_dicts():
            cause_id = str(cause.get("id") or "")
            event_id = f"economic-cause:{cause_id}"
            if not cause_id or event_id in known:
                continue
            country = self._tag(cause.get("country_id"))
            row = self._row_defaults(state, "history_events")
            row.update({
                "id": event_id, "event_type": "EconomicCauseRecorded", "subject_type": "country",
                "subject_id": country, "related_country_ids_json": json.dumps([country] if country else []),
                "title": f"{self._humanize(str(cause.get('indicator') or 'Economic'))} changed",
                "details_json": json.dumps(cause, sort_keys=True, separators=(",", ":"), default=str),
                "source_type": str(cause.get("source_type") or "economic"),
                "source_id": str(cause.get("source_id") or cause_id),
                "cause_source_type": str(cause.get("source_type") or ""),
                "cause_source_id": str(cause.get("source_id") or ""),
                "game_minute": int(cause.get("game_minute") or state.time.total_minutes),
                "tick": int(state.globals.get("tick", 0)), "confidence": float(cause.get("confidence") or 1.0),
                "completeness": str(cause.get("completeness") or "complete"), "schema_version": 1,
            })
            additions.append(row)
            known.add(event_id)
        state.globals["history_economic_cause_revision"] = revision
        if additions:
            state.update_table("history_events", self._append(events, additions))

    def _compact(
        self,
        state: GameState,
        definitions: list[dict[str, Any]],
        touched_keys: set[str],
        now: int,
    ) -> None:
        snapshots = state.tables.get("history_snapshots")
        series_table = state.tables.get("history_series_state")
        if snapshots is None or snapshots.is_empty() or series_table is None or not touched_keys:
            return
        definition_by_id = {str(row.get("id") or ""): row for row in definitions}
        series_rows = series_table.to_dicts()
        series_by_key = {str(row.get("id") or ""): row for row in series_rows}
        compact_keys: set[str] = set()
        for key in touched_keys:
            series_row = series_by_key.get(key, {})
            indicator_id = str(series_row.get("indicator_id") or "")
            definition = definition_by_id.get(indicator_id, {})
            cap = max(1, int(definition.get("max_samples_per_series") or 3650))
            retention = max(1, int(definition.get("retention_window_minutes") or 5_256_000))
            last_compaction = int(series_row.get("last_compacted_at_minute") or 0)
            if int(series_row.get("sample_count") or 0) > cap * 2 or int(now) - last_compaction >= retention:
                compact_keys.add(key)
        if not compact_keys:
            return

        key_expr = pl.concat_str(
            [pl.col("subject_type"), pl.col("subject_id"), pl.col("indicator_id")],
            separator="\u001f",
        )
        encoded_keys = {
            "\u001f".join((
                str(series_by_key[key].get("subject_type") or ""),
                str(series_by_key[key].get("subject_id") or ""),
                str(series_by_key[key].get("indicator_id") or ""),
            ))
            for key in compact_keys
        }
        affected_mask = key_expr.is_in(sorted(encoded_keys))
        affected = snapshots.filter(affected_mask)
        unaffected = snapshots.filter(~affected_mask)
        groups = affected.partition_by(
            ["subject_type", "subject_id", "indicator_id"],
            maintain_order=False,
            as_dict=True,
        )
        kept_groups: list[pl.DataFrame] = []
        for key in sorted(compact_keys):
            series_row = series_by_key[key]
            subject_type = str(series_row.get("subject_type") or "")
            subject_id = str(series_row.get("subject_id") or "")
            indicator_id = str(series_row.get("indicator_id") or "")
            group = groups.get((subject_type, subject_id, indicator_id), snapshots.head(0))
            definition = definition_by_id.get(indicator_id, {})
            cap = max(1, int(definition.get("max_samples_per_series") or 3650))
            retention = max(1, int(definition.get("retention_window_minutes") or 5_256_000))
            compacted_group = self._compact_group(group, now, retention, cap)
            if compacted_group.height:
                kept_groups.append(compacted_group)
            series_row["sample_count"] = compacted_group.height
            series_row["last_compacted_at_minute"] = int(now)
        frames = [unaffected, *kept_groups]
        non_empty = [frame for frame in frames if frame.height]
        compacted = pl.concat(non_empty, how="vertical") if non_empty else snapshots.head(0)
        state.update_table("history_snapshots", compacted)
        state.update_table("history_series_state", self._frame(series_table, series_rows))

    @staticmethod
    def _compact_group(group: pl.DataFrame, now: int, retention: int, cap: int) -> pl.DataFrame:
        recent = group.filter(pl.col("game_minute") >= int(now) - int(retention)).sort(
            ["game_minute", "tick", "id"]
        )
        if recent.height <= cap:
            return recent

        if cap <= 1:
            indices = [recent.height - 1]
        elif cap == 2:
            indices = [0, recent.height - 1]
        else:
            indices = sorted({
                round(index * (recent.height - 1) / (cap - 1))
                for index in range(cap)
            })
        return (
            recent.with_row_index("_history_row_index")
            .filter(pl.col("_history_row_index").is_in(indices))
            .drop("_history_row_index")
        )

    @staticmethod
    def _downsample(rows: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
        ordered = sorted(rows, key=lambda row: (int(row.get("game_minute") or 0), int(row.get("tick") or 0), str(row.get("id") or "")))
        if cap <= 1:
            return ordered[-cap:]
        if cap == 2:
            return [ordered[0], ordered[-1]]
        indices = {round(index * (len(ordered) - 1) / (cap - 1)) for index in range(cap)}
        return [ordered[index] for index in sorted(indices)]

    @staticmethod
    def _next_due(series_by_key: dict[str, dict[str, Any]], definition: dict[str, Any]) -> int:
        matching = [
            int(row.get("next_sample_at_minute") or 0)
            for row in series_by_key.values()
            if row.get("indicator_id") == definition.get("id")
        ]
        return min(matching, default=2**63 - 1)

    @staticmethod
    def _definition_sources(definition: dict[str, Any]) -> set[str]:
        sources = {str(definition.get("source_table") or "")}
        derivation = str(definition.get("derivation") or "")
        if derivation in {"gdp_per_capita", "region_population"}:
            sources.add("regions")
        if derivation == "resource_coverage":
            sources.add("resource_ledger")
        if derivation == "treaty_membership_count":
            sources.add("countries_treaties")
        if derivation == "active_war_count":
            sources.add("countries_wars")
        if derivation == "ruling_party_support":
            sources.update({"political_parties", "country_governments"})
        return sources

    @staticmethod
    def _next_boundary(now: int, interval: int) -> int:
        return (int(now) // max(1, int(interval)) + 1) * max(1, int(interval))

    @staticmethod
    def _same_value(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return left is right
        try:
            return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return left == right

    @staticmethod
    def _series_id(subject_type: str, subject_id: str, indicator_id: str) -> str:
        return f"{subject_type}:{subject_id}:{indicator_id}"

    @staticmethod
    def _row_defaults(state: GameState, table_name: str) -> dict[str, Any]:
        registry = state.schema_registry
        schema = registry.get(table_name) if registry is not None else None
        if schema is not None:
            return {name: column.default for name, column in schema.columns.items()}
        table = state.tables.get(table_name)
        return {name: None for name in table.columns} if table is not None else {}

    @staticmethod
    def _append(table: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return table
        return pl.concat([table, pl.DataFrame(rows, schema=table.schema)], how="vertical")

    @staticmethod
    def _frame(table: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return table.head(0)
        return pl.DataFrame(rows, schema=table.schema)

    @staticmethod
    def _country_ids(payload: dict[str, Any]) -> set[str]:
        ids: set[str] = set()
        for key in (
            "country_id", "country_tag", "source_country_tag", "target_country_tag", "attacker_tag",
            "defender_tag", "leader_a", "leader_b", "responder_country_tag", "claimant_id",
            "former_owner_id", "victor_tag", "previous_controller", "controller",
        ):
            if payload.get(key):
                ids.add(HistorySystem._tag(payload[key]))
        for key in ("side_a_countries", "side_b_countries", "country_ids", "participant_countries", "countries", "participants"):
            value = payload.get(key)
            if isinstance(value, (list, tuple, set)):
                ids.update(HistorySystem._tag(item) for item in value if item)
        return {item for item in ids if item}

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _event_minute(payload: dict[str, Any], fallback: int) -> int:
        for key in ("at_minute", "started_at_minute", "updated_at_minute", "completed_at_minute", "concluded_at_minute", "effective_at_minute", "deadline_at_minute"):
            if payload.get(key) is not None:
                try:
                    return int(payload[key])
                except (TypeError, ValueError):
                    continue
        return int(fallback)

    @staticmethod
    def _humanize(value: str) -> str:
        words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").strip()
        return words or "Recorded event"

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return normalized or "other"
