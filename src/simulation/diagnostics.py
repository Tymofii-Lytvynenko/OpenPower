from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.shared.events import EventSystemError
from src.shared.state import GameState


@dataclass(frozen=True)
class DiagnosticIssue:
    severity: str
    code: str
    message: str
    table: str | None = None
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class SimulationDiagnostics:
    def inspect(self, state: GameState, expected_player_tag: str | None = None) -> list[DiagnosticIssue]:
        issues: list[DiagnosticIssue] = []
        issues.extend(self._system_errors(state))
        issues.extend(self._required_tables(state))
        issues.extend(self._player_country(state, expected_player_tag))
        issues.extend(self._country_ids(state))
        issues.extend(self._region_references(state))
        issues.extend(self._unit_references(state))
        issues.extend(self._finite_country_numbers(state))
        return issues

    def _system_errors(self, state: GameState) -> Iterable[DiagnosticIssue]:
        for event in state.events:
            if isinstance(event, EventSystemError):
                yield DiagnosticIssue(
                    severity="error",
                    code="system_error",
                    message=f"System {event.system_id} failed: {event.error_message}",
                    details={"system_id": event.system_id, "traceback": event.traceback_text},
                )

    def _required_tables(self, state: GameState) -> Iterable[DiagnosticIssue]:
        for table_name in ("countries", "regions"):
            table = state.tables.get(table_name)
            if table is None:
                yield DiagnosticIssue("error", "missing_table", f"Required table '{table_name}' is missing.", table=table_name)
            elif table.is_empty():
                yield DiagnosticIssue("error", "empty_table", f"Required table '{table_name}' is empty.", table=table_name)

    def _player_country(self, state: GameState, expected_player_tag: str | None) -> Iterable[DiagnosticIssue]:
        actual_tag = state.globals.get("player_tag")
        if expected_player_tag:
            if actual_tag != expected_player_tag:
                yield DiagnosticIssue(
                    "error",
                    "player_tag_mismatch",
                    "The loaded player country does not match the expected country.",
                    details={"expected": expected_player_tag, "actual": actual_tag},
                )
            yield from self._country_exists(state, expected_player_tag, "expected_player_missing")
            return

        if actual_tag:
            yield from self._country_exists(state, str(actual_tag), "saved_player_missing")

    def _country_exists(self, state: GameState, country_tag: str, code: str) -> Iterable[DiagnosticIssue]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return

        country_ids = set(str(value) for value in countries["id"].drop_nulls().to_list())
        if country_tag not in country_ids:
            yield DiagnosticIssue(
                "error",
                code,
                f"Country '{country_tag}' is not present in the countries table.",
                table="countries",
                column="id",
                details={"country_tag": country_tag},
            )

    def _country_ids(self, state: GameState) -> Iterable[DiagnosticIssue]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty():
            return
        if "id" not in countries.columns:
            yield DiagnosticIssue("error", "country_id_missing", "Countries table has no 'id' column.", table="countries")
            return

        ids = [str(value) for value in countries["id"].drop_nulls().to_list()]
        duplicates = sorted(tag for tag, count in Counter(ids).items() if count > 1)
        if duplicates:
            yield DiagnosticIssue(
                "error",
                "duplicate_country_ids",
                "Countries table contains duplicate ids.",
                table="countries",
                column="id",
                details={"duplicates": duplicates[:20], "count": len(duplicates)},
            )
    def _region_references(self, state: GameState) -> Iterable[DiagnosticIssue]:
        regions = state.tables.get("regions")
        countries = state.tables.get("countries")
        if regions is None or countries is None or regions.is_empty() or countries.is_empty() or "id" not in countries.columns:
            return

        country_ids = set(str(value) for value in countries["id"].drop_nulls().to_list())
        for column in ("owner", "controller"):
            if column not in regions.columns:
                continue
            unknown = self._unknown_tags(regions[column].drop_nulls().to_list(), country_ids)
            if unknown:
                yield DiagnosticIssue(
                    "error",
                    "unknown_region_country_ref",
                    f"Regions reference unknown countries in '{column}'.",
                    table="regions",
                    column=column,
                    details={"unknown": unknown[:20], "count": len(unknown)},
                )

    def _unit_references(self, state: GameState) -> Iterable[DiagnosticIssue]:
        units = state.tables.get("units")
        if units is None or units.is_empty():
            return

        countries = state.tables.get("countries")
        if countries is not None and not countries.is_empty() and "id" in countries.columns and "owner" in units.columns:
            country_ids = set(str(value) for value in countries["id"].drop_nulls().to_list())
            unknown = self._unknown_tags(units["owner"].drop_nulls().to_list(), country_ids)
            if unknown:
                yield DiagnosticIssue(
                    "error",
                    "unknown_unit_owner",
                    "Units reference unknown owners.",
                    table="units",
                    column="owner",
                    details={"unknown": unknown[:20], "count": len(unknown)},
                )

        regions = state.tables.get("regions")
        if regions is not None and not regions.is_empty() and "id" in regions.columns:
            valid_regions = set(int(value) for value in regions["id"].drop_nulls().to_list())
            for column in ("current_region_id", "target_region_id"):
                if column not in units.columns:
                    continue
                values = [int(value) for value in units[column].drop_nulls().to_list() if int(value) > 0]
                unknown_regions = sorted(set(values) - valid_regions)
                if unknown_regions:
                    yield DiagnosticIssue(
                        "error",
                        "unknown_unit_region_ref",
                        f"Units reference unknown regions in '{column}'.",
                        table="units",
                        column=column,
                        details={"unknown": unknown_regions[:20], "count": len(unknown_regions)},
                    )

    def _finite_country_numbers(self, state: GameState) -> Iterable[DiagnosticIssue]:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty():
            return

        for column, dtype in countries.schema.items():
            if str(dtype) not in {"Float32", "Float64"}:
                continue
            values = countries[column].drop_nulls().to_list()
            bad_count = sum(1 for value in values if not self._is_finite_float(value))
            if bad_count:
                yield DiagnosticIssue(
                    "error",
                    "non_finite_country_value",
                    f"Countries column '{column}' contains non-finite values.",
                    table="countries",
                    column=column,
                    details={"count": bad_count},
                )

    def _unknown_tags(self, values: list[Any], valid_tags: set[str]) -> list[str]:
        ignored = {"", "None", "none", "NULL", "null"}
        tags = {str(value) for value in values if str(value) not in ignored}
        return sorted(tags - valid_tags)

    def _is_finite_float(self, value: Any) -> bool:
        try:
            return value == value and value not in (float("inf"), float("-inf"))
        except TypeError:
            return True


def issue_counts(issues: Iterable[DiagnosticIssue]) -> dict[str, int]:
    return dict(Counter(issue.severity for issue in issues))