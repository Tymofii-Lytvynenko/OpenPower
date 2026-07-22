from __future__ import annotations

from collections import Counter
from typing import Any

import polars as pl

from src.shared.state import GameState, TimeData
from src.simulation.diagnostics import DiagnosticIssue, issue_counts
from src.simulation.serialization import to_plain_data

NUMERIC_DTYPES = {
    "Int8",
    "Int16",
    "Int32",
    "Int64",
    "UInt8",
    "UInt16",
    "UInt32",
    "UInt64",
    "Float32",
    "Float64",
}


class StateSnapshotBuilder:
    def __init__(self, table_sample_limit: int = 12):
        self.table_sample_limit = max(0, int(table_sample_limit))

    def build_snapshot(
        self,
        state: GameState,
        step_index: int,
        elapsed_real_seconds: float,
        diagnostics: list[DiagnosticIssue],
    ) -> dict[str, Any]:
        return {
            "step": step_index,
            "elapsed_real_seconds": round(elapsed_real_seconds, 6),
            "time": self._time_data(state.time),
            "globals": to_plain_data(state.globals),
            "player": self._player_summary(state),
            "events": self._event_summary(state),
            "journal": {
                "domain_event_count": len(state.journal.domain_events),
                "command_result_count": len(state.journal.command_results),
                "recent_domain_events": to_plain_data(state.journal.domain_events[-20:]),
                "recent_command_results": to_plain_data(state.journal.command_results[-20:]),
            },
            "determinism": {
                "seed": state.determinism.seed,
                "rng_state": state.determinism.rng_state,
                "id_sequence": state.determinism.id_sequence,
            },
            "diagnostics": {
                "counts": issue_counts(diagnostics),
                "issues": [to_plain_data(issue) for issue in diagnostics],
            },
            "world": self._world_metrics(state),
            "countries": self._countries_digest(state),
            "tables": {
                table_name: self._table_summary(frame)
                for table_name, frame in sorted(state.tables.items())
            },
        }

    def build_timeline_record(
        self,
        state: GameState,
        step_index: int,
        elapsed_real_seconds: float,
        diagnostics: list[DiagnosticIssue],
    ) -> dict[str, Any]:
        return {
            "step": step_index,
            "elapsed_real_seconds": round(elapsed_real_seconds, 6),
            "tick": state.globals.get("tick", 0),
            "date": state.time.date_str,
            "total_minutes": state.time.total_minutes,
            "player_tag": state.globals.get("player_tag"),
            "diagnostics": issue_counts(diagnostics),
            "events": self._event_summary(state),
            "world": self._world_metrics(state),
            "player": self._player_summary(state),
        }

    def _time_data(self, time_data: TimeData) -> dict[str, Any]:
        return {
            "total_minutes": time_data.total_minutes,
            "year": time_data.year,
            "month": time_data.month,
            "day": time_data.day,
            "hour": time_data.hour,
            "minute": time_data.minute,
            "date_str": time_data.date_str,
            "speed_level": time_data.speed_level,
            "is_paused": time_data.is_paused,
        }

    def _event_summary(self, state: GameState) -> dict[str, Any]:
        names = [type(event).__name__ for event in state.events]
        return {
            "count": len(names),
            "by_type": dict(Counter(names)),
            "items": [to_plain_data(event) | {"type": type(event).__name__} for event in state.events[:20]],
        }
    def _table_summary(self, frame: pl.DataFrame) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "rows": frame.height,
            "columns": frame.width,
            "schema": {column: str(dtype) for column, dtype in frame.schema.items()},
            "sample": frame.head(self.table_sample_limit).to_dicts() if self.table_sample_limit else [],
        }
        if frame.width == 0:
            return summary

        null_counts = frame.null_count().to_dicts()[0] if frame.width else {}
        summary["null_counts"] = {key: int(value or 0) for key, value in null_counts.items()}

        numeric_columns = [column for column, dtype in frame.schema.items() if str(dtype) in NUMERIC_DTYPES]
        numeric_summary: dict[str, Any] = {}
        for column in numeric_columns[:24]:
            numeric_summary[column] = self._numeric_stats(frame, column)
        if numeric_summary:
            summary["numeric"] = numeric_summary
        return summary

    def _numeric_stats(self, frame: pl.DataFrame, column: str) -> dict[str, Any]:
        stats = frame.select(
            pl.col(column).min().alias("min"),
            pl.col(column).max().alias("max"),
            pl.col(column).mean().alias("mean"),
            pl.col(column).sum().alias("sum"),
        ).to_dicts()[0]
        return {key: self._rounded(value) for key, value in stats.items()}

    def _world_metrics(self, state: GameState) -> dict[str, Any]:
        countries = state.tables.get("countries")
        regions = state.tables.get("regions")
        metrics: dict[str, Any] = {
            "table_count": len(state.tables),
            "country_count": countries.height if countries is not None else 0,
            "region_count": regions.height if regions is not None else 0,
        }

        if countries is not None and not countries.is_empty():
            for column in ("gdp", "money_reserves", "military_count", "total_annual_revenue", "total_annual_expense"):
                if column in countries.columns:
                    metrics[f"total_{column}"] = self._rounded(countries[column].sum())
            if "money_reserves" in countries.columns:
                metrics["negative_reserve_countries"] = int(countries.filter(pl.col("money_reserves") < 0).height)

        if regions is not None and not regions.is_empty():
            pop_columns = [column for column in ("pop_14", "pop_15_64", "pop_65") if column in regions.columns]
            if pop_columns:
                metrics["total_population"] = self._rounded(regions.select(pl.sum_horizontal(pop_columns).sum()).item())

        return metrics

    def _countries_digest(self, state: GameState) -> dict[str, Any]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return {"player_country": None, "top_reserves": [], "top_gdp": []}

        return {
            "player_country": self._player_country_row(state, countries),
            "top_reserves": self._top_country_rows(countries, "money_reserves"),
            "top_gdp": self._top_country_rows(countries, "gdp"),
            "lowest_reserves": self._top_country_rows(countries, "money_reserves", descending=False),
        }
    def _player_summary(self, state: GameState) -> dict[str, Any]:
        countries = state.tables.get("countries")
        player_tag = state.globals.get("player_tag")
        return {
            "tag": player_tag,
            "country": self._player_country_row(state, countries) if countries is not None else None,
        }

    def _player_country_row(self, state: GameState, countries: pl.DataFrame | None) -> dict[str, Any] | None:
        player_tag = state.globals.get("player_tag")
        if not player_tag or countries is None or countries.is_empty() or "id" not in countries.columns:
            return None

        rows = countries.filter(pl.col("id") == str(player_tag))
        if rows.is_empty():
            return None
        return self._compact_country_row(rows.to_dicts()[0])

    def _top_country_rows(self, countries: pl.DataFrame, column: str, descending: bool = True) -> list[dict[str, Any]]:
        if column not in countries.columns:
            return []
        rows = countries.sort(column, descending=descending, nulls_last=True).head(10).to_dicts()
        return [self._compact_country_row(row) for row in rows]

    def _compact_country_row(self, row: dict[str, Any]) -> dict[str, Any]:
        keep = (
            "id",
            "name",
            "money_reserves",
            "gdp",
            "gdp_per_capita",
            "military_count",
            "gvt_approval",
            "gvt_stability",
            "human_dev",
            "total_annual_revenue",
            "total_annual_expense",
        )
        return {key: self._rounded(row.get(key)) for key in keep if key in row}

    def _rounded(self, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 6)
        return value