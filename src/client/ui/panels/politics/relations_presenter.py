from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from src.client.services.history_query_service import HistoryQueryService
from src.client.ui.panels.shared.panel_data import safe_float, safe_text


@dataclass(frozen=True, slots=True)
class RelationCountryOption:
    tag: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.tag})"


@dataclass(frozen=True, slots=True)
class RelationPairView:
    country_a: RelationCountryOption
    country_b: RelationCountryOption
    current_value: float | None
    history: tuple[tuple[int, float], ...]


class RelationsPresenter:
    """Build read-only bilateral relation data from authoritative snapshots."""

    def __init__(self, history_queries: HistoryQueryService | None = None) -> None:
        self._history_queries = history_queries or HistoryQueryService()

    def countries(self, state) -> tuple[RelationCountryOption, ...]:
        table = state.tables.get("countries")
        if table is None or table.is_empty() or "id" not in table.columns:
            return ()

        name_field = next(
            (name for name in ("name", "country_name", "display_name") if name in table.columns),
            "id",
        )
        options = (
            RelationCountryOption(
                tag=safe_text(row.get("id")).strip().upper(),
                name=safe_text(row.get(name_field), safe_text(row.get("id"))),
            )
            for row in table.to_dicts()
            if safe_text(row.get("id")).strip()
        )
        return tuple(sorted(options, key=lambda item: (item.name.casefold(), item.tag)))

    def build_pair(self, state, country_a: str, country_b: str) -> RelationPairView | None:
        options = {item.tag: item for item in self.countries(state)}
        left = options.get(str(country_a or "").strip().upper())
        right = options.get(str(country_b or "").strip().upper())
        if left is None or right is None or left.tag == right.tag:
            return None

        current_value = self._current_value(state, left.tag, right.tag)
        timeline = self._history_queries.relationship_timeline(state, left.tag, right.tag)
        history = tuple(
            (int(row.get("game_minute") or 0), safe_float(row.get("value"), 0.0))
            for row in timeline
            if row.get("timeline_kind") == "relation_value" and row.get("value") is not None
        )
        return RelationPairView(left, right, current_value, history)

    @staticmethod
    def _current_value(state, country_a: str, country_b: str) -> float | None:
        relations = state.tables.get("countries_relations")
        required = {"source", "target", "value"}
        if relations is None or relations.is_empty() or not required.issubset(relations.columns):
            return None

        matching = relations.filter(
            (pl.col("source").cast(pl.Utf8).str.to_uppercase() == country_a)
            & (pl.col("target").cast(pl.Utf8).str.to_uppercase() == country_b)
        )
        if matching.is_empty():
            return None
        return safe_float(matching.get_column("value")[0], None)
