"""Read-only, deterministic client queries over persisted historical observations.

This belongs in the client service layer because it performs analytics over snapshots;
the shared layer remains limited to passive cross-process contracts.
"""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Any, Iterable

import polars as pl


class HistoryQueryService:
    def current_value(
        self,
        state,
        subject_type: str,
        subject_id: str,
        indicator_id: str,
    ) -> dict[str, Any]:
        definitions = self._table(state, "history_indicator_definitions")
        definition = None
        if definitions is not None and not definitions.is_empty():
            definition = next(
                (row for row in definitions.to_dicts() if str(row.get("id") or "") == str(indicator_id)),
                None,
            )
        if definition is None:
            return {"available": False, "value": None, "unit": "", "value_kind": "missing"}

        derivation = str(definition.get("derivation") or "")
        if derivation == "gdp_per_capita":
            countries = self._table(state, "countries")
            regions = self._table(state, "regions")
            if countries is None or regions is None or "gdp" not in countries.columns:
                return self._unavailable(definition)
            owner_field = "owner" if "owner" in regions.columns else "owner_tag" if "owner_tag" in regions.columns else ""
            population_fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
            if not owner_field or not population_fields:
                return self._unavailable(definition)
            populations: dict[str, float] = {}
            for row in regions.to_dicts():
                owner = str(row.get(owner_field) or "").strip().upper()
                populations[owner] = populations.get(owner, 0.0) + sum(float(row.get(field) or 0.0) for field in population_fields)
            row = next((row for row in countries.to_dicts() if str(row.get("id") or "").upper() == str(subject_id).upper()), None)
            population = populations.get(str(subject_id).upper(), 0.0)
            if row is None or population <= 0:
                return self._unavailable(definition)
            return {"available": True, "value": float(row.get("gdp") or 0.0) / population,
                    "unit": str(definition.get("unit") or ""), "value_kind": "derived"}
        if derivation == "region_population":
            regions = self._table(state, "regions")
            if regions is None or "id" not in regions.columns:
                return self._unavailable(definition)
            row = next((row for row in regions.to_dicts() if str(row.get("id")) == str(subject_id)), None)
            if row is None:
                return self._unavailable(definition)
            fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
            if not fields:
                return self._unavailable(definition)
            value = sum(float(row.get(field) or 0.0) for field in fields)
            return {"available": True, "value": value, "unit": str(definition.get("unit") or ""),
                    "value_kind": "derived"}
        if derivation == "country_population":
            regions = self._table(state, "regions")
            if regions is None or "owner" not in regions.columns:
                return self._unavailable(definition)
            fields = [name for name in ("pop_14", "pop_15_64", "pop_65") if name in regions.columns]
            if not fields:
                return self._unavailable(definition)
            population = sum(
                sum(float(row.get(field) or 0.0) for field in fields)
                for row in regions.to_dicts()
                if str(row.get("owner") or "").strip().upper() == str(subject_id).upper()
            )
            return {"available": True, "value": population, "unit": str(definition.get("unit") or ""),
                    "value_kind": "derived"}
        if derivation in {"resource_coverage", "treaty_membership_count", "active_war_count", "ruling_party_support"}:
            value = self._current_derived_value(state, derivation, str(subject_id))
            if value is None:
                return self._unavailable(definition)
            return {"available": True, "value": value, "unit": str(definition.get("unit") or ""),
                    "value_kind": "derived"}

        table = self._table(state, str(definition.get("source_table") or ""))
        if table is None or table.is_empty():
            return self._unavailable(definition)
        subject_field = str(definition.get("subject_id_field") or "")
        field = str(definition.get("source_field") or "")
        related_field = str(definition.get("related_id_field") or "")
        filter_field = str(definition.get("filter_field") or "")
        filter_value = str(definition.get("filter_value") or "")
        if not {subject_field, field}.issubset(table.columns):
            return self._unavailable(definition)
        requested = str(subject_id)
        if subject_type == "relationship":
            pair = self._pair_id(*requested.split("|", 1)) if "|" in requested else requested
        else:
            pair = requested
        samples: list[float] = []
        for row in table.to_dicts():
            if filter_field and str(row.get(filter_field) or "") != filter_value:
                continue
            row_subject = str(row.get(subject_field) or "")
            if subject_type == "relationship" and related_field:
                related = str(row.get(related_field) or "")
                row_subject = self._pair_id(row_subject, related) if row_subject and related else ""
            elif subject_type == "region":
                row_subject = str(row_subject)
            if row_subject.upper() != pair.upper():
                continue
            if str(definition.get("aggregation") or "last") == "count":
                samples.append(1.0)
                continue
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                continue
            if value == value and abs(value) != float("inf"):
                samples.append(value)
        if not samples:
            return self._unavailable(definition)
        aggregation = str(definition.get("aggregation") or "last").lower()
        if aggregation in {"sum", "count"}:
            value = sum(samples)
        elif aggregation == "mean":
            value = sum(samples) / len(samples)
        elif aggregation == "max":
            value = max(samples)
        else:
            value = samples[-1]
        return {"available": True, "value": float(value), "unit": str(definition.get("unit") or ""),
                "value_kind": "authoritative"}

    def series(
        self,
        state,
        subject_type: str,
        subject_id: str,
        indicator_id: str,
        *,
        start_minute: int | None = None,
        end_minute: int | None = None,
        granularity_minutes: int = 0,
        include_non_authoritative: bool = True,
    ) -> list[dict[str, Any]]:
        table = self._table(state, "history_snapshots")
        if table is None or table.is_empty():
            return []
        mask = (
            (pl.col("subject_type") == str(subject_type))
            & (pl.col("subject_id") == str(subject_id))
            & (pl.col("indicator_id") == str(indicator_id))
        )
        if start_minute is not None:
            mask &= pl.col("game_minute") >= int(start_minute)
        if end_minute is not None:
            mask &= pl.col("game_minute") <= int(end_minute)
        if not include_non_authoritative and "value_kind" in table.columns:
            mask &= pl.col("value_kind") == "authoritative"
        selected = table.filter(mask).sort(["game_minute", "tick", "id"])
        rows = selected.to_dicts()
        if granularity_minutes <= 0:
            return rows
        return self._bucket_last(rows, int(granularity_minutes))

    def compare(
        self,
        state,
        subject_type: str,
        subject_ids: Iterable[str],
        indicator_id: str,
        *,
        start_minute: int | None = None,
        end_minute: int | None = None,
        granularity_minutes: int = 0,
    ) -> dict[str, Any]:
        subjects = sorted({str(item) for item in subject_ids})
        table = self._table(state, "history_snapshots")
        selected_rows: list[dict[str, Any]] = []
        if table is not None and not table.is_empty() and subjects:
            mask = (
                (pl.col("subject_type") == str(subject_type))
                & (pl.col("indicator_id") == str(indicator_id))
                & pl.col("subject_id").is_in(subjects)
            )
            if start_minute is not None:
                mask &= pl.col("game_minute") >= int(start_minute)
            if end_minute is not None:
                mask &= pl.col("game_minute") <= int(end_minute)
            selected_rows = table.filter(mask).sort(["subject_id", "game_minute", "tick", "id"]).to_dicts()
        grouped: dict[str, list[dict[str, Any]]] = {subject: [] for subject in subjects}
        for row in selected_rows:
            grouped[str(row.get("subject_id") or "")].append(row)
        series_by_subject = {
            subject: (
                self._bucket_last(grouped[subject], int(granularity_minutes))
                if granularity_minutes > 0 else grouped[subject]
            )
            for subject in subjects
        }
        units = sorted({
            str(row.get("unit") or "")
            for rows in series_by_subject.values()
            for row in rows
            if row.get("value") is not None and row.get("completeness") not in {"missing", "stale"}
        })
        compatible = len(units) <= 1
        latest_minutes = [
            int(rows[-1].get("game_minute") or 0)
            for rows in series_by_subject.values()
            if rows
        ]
        evaluation_minute = min(latest_minutes) if latest_minutes else None
        common_values: dict[str, dict[str, Any]] = {}
        normalized_common_values: dict[str, dict[str, Any]] = {}
        if evaluation_minute is not None:
            for subject, rows in series_by_subject.items():
                at_boundary = [row for row in rows if int(row.get("game_minute") or 0) <= evaluation_minute]
                if at_boundary:
                    common_values[subject] = at_boundary[-1]
                valid_rows = [
                    row for row in at_boundary
                    if row.get("value") is not None
                    and row.get("completeness") not in {"missing", "stale"}
                    and self._positive_finite(row.get("value"))
                ]
                current = common_values.get(subject)
                if not valid_rows or current is None or not self._valid_value_row(current):
                    continue
                baseline = valid_rows[0]
                baseline_unit = str(baseline.get("unit") or "").strip().casefold()
                current_unit = str(current.get("unit") or "").strip().casefold()
                if baseline_unit != current_unit:
                    continue
                baseline_value = float(baseline["value"])
                indexed_value = 100.0 * float(current["value"]) / baseline_value
                if not math.isfinite(indexed_value):
                    continue
                normalized_common_values[subject] = {
                    "subject_id": subject,
                    "value": indexed_value,
                    "unit": "index (first positive sample = 100)",
                    "game_minute": int(current.get("game_minute") or 0),
                    "tick": int(current.get("tick") or 0),
                    "baseline_value": baseline_value,
                    "baseline_unit": str(baseline.get("unit") or ""),
                    "baseline_minute": int(baseline.get("game_minute") or 0),
                    "completeness": "complete",
                    "value_kind": "derived",
                }
        return {
            "subject_type": subject_type,
            "indicator_id": indicator_id,
            "unit": units[0] if compatible and units else "",
            "unit_compatible": compatible,
            "series": series_by_subject,
            "unavailable_subjects": [
                subject for subject, rows in series_by_subject.items()
                if not any(
                    row.get("value") is not None and row.get("completeness") not in {"missing", "stale"}
                    for row in rows
                )
            ],
            "evaluation_minute": evaluation_minute,
            "common_values": common_values,
            "normalized_common_values": normalized_common_values,
            "normalization_basis": "Each series' first positive sample in the selected period is indexed to 100; unit transitions are not converted.",
            "normalization_unavailable_subjects": sorted(set(subjects) - set(normalized_common_values)),
            "common_unavailable_subjects": sorted(set(subjects) - set(common_values)),
            "freshness_by_subject": {
                subject: max(0, int(evaluation_minute) - int(row.get("game_minute") or 0))
                for subject, row in common_values.items()
            } if evaluation_minute is not None else {},
            "time_range": (start_minute, end_minute),
            "granularity_minutes": max(0, int(granularity_minutes)),
        }

    def rank(
        self,
        state,
        indicator_id: str,
        *,
        subject_type: str = "country",
        start_minute: int | None = None,
        end_minute: int | None = None,
        descending: bool = True,
    ) -> dict[str, Any]:
        table = self._table(state, "history_snapshots")
        if table is None or table.is_empty():
            return {
                "rows": [], "excluded": [], "incompatible_unit_subjects": [], "ties": [],
                "unit": "", "unit_compatible": True,
                "direction": "descending" if descending else "ascending",
                "tie_rule": "subject_id_ascending",
            }
        mask = (pl.col("indicator_id") == str(indicator_id)) & (pl.col("subject_type") == str(subject_type))
        if start_minute is not None:
            mask &= pl.col("game_minute") >= int(start_minute)
        if end_minute is not None:
            mask &= pl.col("game_minute") <= int(end_minute)
        indexed_result = self._indexed_latest_rank_rows(
            state, table, indicator_id, subject_type, start_minute, end_minute
        )
        if indexed_result is None:
            samples = table.filter(mask)
            evaluation_minute, latest_rows, without_common_sample = (
                self._latest_snapshot_rows_at_common_boundary(samples)
            )
            snapshot_rows = latest_rows.to_dicts()
        else:
            evaluation_minute, snapshot_rows, without_common_sample = indexed_result
        latest_by_subject = {
            str(row.get("subject_id") or ""): row for row in snapshot_rows
        }
        included = [
            row for row in latest_by_subject.values()
            if row.get("value") is not None and row.get("completeness") not in {"missing", "stale"}
        ]
        observed_units = sorted({str(row.get("unit") or "") for row in included})
        unit_compatible = len(observed_units) <= 1
        target_unit = self._indicator_unit(state, indicator_id)
        if not target_unit and observed_units:
            unit_counts = {
                unit: sum(str(row.get("unit") or "") == unit for row in included)
                for unit in observed_units
            }
            target_unit = min(observed_units, key=lambda unit: (-unit_counts[unit], unit))
        incompatible_unit_subjects = sorted(
            str(row.get("subject_id") or "")
            for row in included
            if str(row.get("unit") or "") != target_unit
        )
        included = [row for row in included if str(row.get("unit") or "") == target_unit]
        excluded = sorted(
            set(without_common_sample) | {
                subject for subject, row in latest_by_subject.items()
                if row.get("value") is None or row.get("completeness") in {"missing", "stale"}
            } | set(incompatible_unit_subjects)
        )
        included.sort(
            key=lambda row: (
                float(row["value"]) * (-1.0 if descending else 1.0),
                str(row.get("subject_id") or ""),
            )
        )
        groups: dict[tuple[str, float], list[str]] = {}
        for row in included:
            groups.setdefault((str(row.get("unit") or ""), float(row["value"])), []).append(str(row.get("subject_id") or ""))
        ties = [
            {"value": value, "unit": unit, "subjects": sorted(subjects)}
            for (unit, value), subjects in groups.items()
            if len(subjects) > 1
        ]
        return {
            "rows": included,
            "excluded": excluded,
            "incompatible_unit_subjects": incompatible_unit_subjects,
            "ties": sorted(ties, key=lambda row: (float(row["value"]), str(row["unit"]))),
            "unit": target_unit,
            "unit_compatible": unit_compatible,
            "freshness_minute": evaluation_minute,
            "evaluation_minute": evaluation_minute,
            "freshness_by_subject": {
                subject: max(0, int(evaluation_minute) - int(row.get("game_minute") or 0))
                for subject, row in latest_by_subject.items()
            } if evaluation_minute is not None else {},
            "direction": "descending" if descending else "ascending",
            "tie_rule": "subject_id_ascending",
        }

    @staticmethod
    def _positive_finite(value: Any) -> bool:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(numeric) and numeric > 0.0

    @classmethod
    def _valid_value_row(cls, row: dict[str, Any]) -> bool:
        if row.get("value") is None or row.get("completeness") in {"missing", "stale"}:
            return False
        try:
            return math.isfinite(float(row["value"]))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _indicator_unit(state, indicator_id: str) -> str:
        definitions = HistoryQueryService._table(state, "history_indicator_definitions")
        if definitions is None or definitions.is_empty() or not {"id", "unit"}.issubset(definitions.columns):
            return ""
        return next(
            (
                str(row.get("unit") or "")
                for row in definitions.to_dicts()
                if str(row.get("id") or "") == str(indicator_id)
            ),
            "",
        )

    @classmethod
    def _indexed_latest_rank_rows(
        cls,
        state,
        snapshots: pl.DataFrame,
        indicator_id: str,
        subject_type: str,
        start_minute: int | None,
        end_minute: int | None,
    ) -> tuple[int | None, list[dict[str, Any]], list[str]] | None:
        series = cls._table(state, "history_series_state")
        required = {
            "subject_type", "subject_id", "indicator_id", "unit", "latest_value",
            "latest_snapshot_id", "latest_source_boundary", "latest_confidence",
            "latest_value_kind", "last_sample_minute", "last_sample_tick", "sample_count",
            "completeness",
        }
        if series is None or not required.issubset(series.columns):
            return None

        table_revisions = getattr(state, "table_revisions", None)
        if table_revisions is not None:
            globals_table = getattr(state, "globals", {})
            indexed_revision = globals_table.get("history_series_snapshot_revision")
            current_revision = int(table_revisions.get("history_snapshots", 0))
            if indexed_revision is None or int(indexed_revision) != current_revision:
                return None

        recorded_count = series.get_column("sample_count").sum() or 0
        if int(recorded_count) != snapshots.height:
            return None

        candidates = series.filter(
            (pl.col("subject_type") == str(subject_type))
            & (pl.col("indicator_id") == str(indicator_id))
            & (pl.col("sample_count") > 0)
        )
        if candidates.is_empty():
            return (None, [], [])
        if end_minute is not None and candidates.filter(
            pl.col("last_sample_minute") > int(end_minute)
        ).height:
            return None
        if start_minute is not None:
            candidates = candidates.filter(
                pl.col("last_sample_minute") >= int(start_minute)
            )
        if candidates.is_empty():
            return (None, [], [])

        rows = candidates.to_dicts()
        boundaries = {int(row.get("last_sample_minute") or 0) for row in rows}
        if len(boundaries) != 1 or any(not row.get("latest_snapshot_id") for row in rows):
            return None

        evaluation_minute = next(iter(boundaries))
        snapshot_rows = [
            {
                "id": row["latest_snapshot_id"],
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "indicator_id": row["indicator_id"],
                "value": row["latest_value"],
                "unit": row["unit"],
                "game_minute": evaluation_minute,
                "tick": row["last_sample_tick"],
                "source_boundary": row["latest_source_boundary"],
                "confidence": row["latest_confidence"],
                "completeness": row["completeness"],
                "value_kind": row["latest_value_kind"],
                "schema_version": row.get("schema_version", 1),
            }
            for row in rows
        ]
        return evaluation_minute, snapshot_rows, []

    @staticmethod
    def _latest_snapshot_rows_at_common_boundary(
        samples: pl.DataFrame,
    ) -> tuple[int | None, pl.DataFrame, list[str]]:
        if samples.is_empty():
            return None, samples.head(0), []

        latest_minutes = samples.group_by("subject_id").agg(
            pl.col("game_minute").max().alias("_latest_minute")
        )
        evaluation_minute = latest_minutes.select(
            pl.col("_latest_minute").min()
        ).item()
        if evaluation_minute is None:
            return None, samples.head(0), []

        all_subjects = set(samples.get_column("subject_id").unique().to_list())
        row_fields = [column for column in samples.columns if column != "subject_id"]
        latest_rows = (
            samples.filter(pl.col("game_minute") <= int(evaluation_minute))
            .group_by("subject_id")
            .agg(
                pl.struct(row_fields)
                .sort_by(["game_minute", "tick", "id"])
                .last(ignore_nulls=False)
                .alias("_latest_snapshot")
            )
            .unnest("_latest_snapshot")
            .sort("subject_id")
        )
        selected_subjects = set(latest_rows.get_column("subject_id").to_list())
        return (
            int(evaluation_minute),
            latest_rows,
            sorted(all_subjects - selected_subjects),
        )

    def relationship_timeline(self, state, country_a: str, country_b: str) -> list[dict[str, Any]]:
        pair = self._pair_id(country_a, country_b)
        # The persisted series uses a namespaced indicator ID; the old short alias returned no relation samples.
        values = self.series(state, "relationship", pair, "relationship.relation_value")
        events_by_id = {
            str(row.get("id") or ""): row
            for country in (country_a, country_b)
            for row in self.event_timeline(state, country_ids=[country])
        }
        events = list(events_by_id.values())
        return sorted(
            [
                *({**row, "timeline_kind": "relation_value"} for row in values),
                *({**row, "timeline_kind": "event"} for row in events),
            ],
            key=lambda row: (int(row.get("game_minute") or 0), int(row.get("tick") or 0), str(row.get("id") or "")),
        )

    def event_timeline(
        self,
        state,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        country_ids: Iterable[str] = (),
        start_minute: int | None = None,
        end_minute: int | None = None,
    ) -> list[dict[str, Any]]:
        table = self._table(state, "history_events")
        if table is None or table.is_empty():
            return []
        rows = table.to_dicts()
        requested_countries = {str(item).strip().upper() for item in country_ids if str(item).strip()}
        selected = []
        for row in rows:
            if subject_type is not None and row.get("subject_type") != subject_type:
                continue
            if subject_id is not None and str(row.get("subject_id") or "") != str(subject_id):
                related = self._json_ids(row.get("related_country_ids_json"))
                if str(subject_id).strip().upper() not in related:
                    continue
            if requested_countries:
                related = self._json_ids(row.get("related_country_ids_json"))
                subject = str(row.get("subject_id") or "").strip().upper()
                if not requested_countries.issubset(related | {subject}):
                    continue
            minute = int(row.get("game_minute") or 0)
            if start_minute is not None and minute < int(start_minute):
                continue
            if end_minute is not None and minute > int(end_minute):
                continue
            selected.append(row)
        return sorted(selected, key=lambda row: (int(row.get("game_minute") or 0), int(row.get("tick") or 0), str(row.get("id") or "")))

    def cause_trail(self, state, subject_type: str, subject_id: str, game_minute: int) -> list[dict[str, Any]]:
        events = self.event_timeline(
            state,
            subject_type=subject_type,
            subject_id=subject_id,
            start_minute=max(0, int(game_minute) - 1440),
            end_minute=int(game_minute),
        )
        return [
            event for event in events
            if event.get("cause_source_type") or event.get("source_type")
        ]

    def export_csv(self, records: Iterable[dict[str, Any]]) -> str:
        rows = [dict(row) for row in records]
        if not rows:
            return ""
        columns = sorted({str(key) for row in rows for key in row})
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: self._csv_value(row.get(key)) for key in columns})
        return output.getvalue()

    @staticmethod
    def _bucket_last(rows: list[dict[str, Any]], granularity_minutes: int) -> list[dict[str, Any]]:
        if not rows:
            return []
        buckets: dict[int, dict[str, Any]] = {}
        for row in rows:
            minute = int(row.get("game_minute") or 0)
            buckets[minute // granularity_minutes] = row
        return [buckets[key] for key in sorted(buckets)]

    @staticmethod
    def _pair_id(country_a: str, country_b: str) -> str:
        a, b = sorted((str(country_a).strip().upper(), str(country_b).strip().upper()))
        return f"{a}|{b}"

    @staticmethod
    def _table(state, table_name: str) -> pl.DataFrame | None:
        return getattr(state, "tables", {}).get(table_name)

    @staticmethod
    def _json_ids(value: Any) -> set[str]:
        try:
            parsed = json.loads(value or "[]") if isinstance(value, str) else value
        except (TypeError, ValueError):
            return set()
        if not isinstance(parsed, (list, tuple, set)):
            return set()
        return {str(item).strip().upper() for item in parsed if str(item).strip()}

    @staticmethod
    def _csv_value(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return value

    @staticmethod
    def _unavailable(definition: dict[str, Any]) -> dict[str, Any]:
        return {"available": False, "value": None, "unit": str(definition.get("unit") or ""), "value_kind": "missing"}

    def _current_derived_value(self, state, derivation: str, subject_id: str) -> float | None:
        country = str(subject_id).strip().upper()
        if derivation == "resource_coverage":
            ledger = self._table(state, "resource_ledger")
            if ledger is None or not {"country_id", "consumption_usd", "balance_usd"}.issubset(ledger.columns):
                return None
            rows = [row for row in ledger.to_dicts() if str(row.get("country_id") or "").upper() == country]
            if not rows:
                return None
            demand = sum(max(0.0, float(row.get("consumption_usd") or 0.0)) for row in rows)
            shortage = sum(abs(float(row.get("balance_usd") or 0.0)) for row in rows if float(row.get("balance_usd") or 0.0) < 0.0)
            return 1.0 if demand <= 0.0 else max(0.0, min(1.0, 1.0 - shortage / demand))
        if derivation == "treaty_membership_count":
            treaties = self._table(state, "countries_treaties")
            if treaties is None or "members" not in treaties.columns:
                return None
            count = 0
            for row in treaties.to_dicts():
                if str(row.get("status") or "active").lower() != "active":
                    continue
                members = row.get("members") or []
                if isinstance(members, str):
                    try:
                        members = json.loads(members)
                    except (TypeError, ValueError):
                        members = []
                if isinstance(members, (list, tuple, set)) and country in {str(item).upper() for item in members}:
                    count += 1
            return float(count)
        if derivation == "active_war_count":
            wars = self._table(state, "countries_wars")
            if wars is None or not {"side_a", "side_b", "status"}.issubset(wars.columns):
                return None
            count = 0
            for row in wars.to_dicts():
                if str(row.get("status") or "active").lower() != "active":
                    continue
                for side in (row.get("side_a") or [], row.get("side_b") or []):
                    if isinstance(side, str):
                        try:
                            side = json.loads(side)
                        except (TypeError, ValueError):
                            side = [side]
                    if isinstance(side, (list, tuple, set)) and country in {str(item).upper() for item in side}:
                        count += 1
                        break
            return float(count)
        if derivation == "ruling_party_support":
            parties = self._table(state, "political_parties")
            governments = self._table(state, "country_governments")
            if parties is None or not {"country_id", "party_id", "support_share"}.issubset(parties.columns):
                return None
            ruling = ""
            if governments is not None and {"country_id", "ruling_party_id"}.issubset(governments.columns):
                ruling = next((str(row.get("ruling_party_id") or "").casefold() for row in governments.to_dicts()
                               if str(row.get("country_id") or "").upper() == country), "")
            matches = [row for row in parties.to_dicts()
                       if str(row.get("country_id") or "").upper() == country
                       and (str(row.get("party_id") or "").casefold() == ruling if ruling else bool(row.get("is_ruling")))]
            if not matches:
                return None
            return float(matches[0].get("support_share") or 0.0)
        return None
