from __future__ import annotations

from typing import Any, Iterable

from src.shared.state import GameState


class DemilitarizationPolicy:
    """Provides one authoritative force-cap calculation for all force entry points."""

    ACTIVE_ORDER_STATUSES = frozenset(
        {"queued", "paused", "in_production", "completed", "held_by_demilitarization"}
    )

    def maximum_strength(self, state: GameState, country_id: str) -> int | None:
        limits = state.tables.get("demilitarization_limits")
        if limits is None or limits.is_empty():
            return None
        country = self._tag(country_id)
        now = max(0, int(state.time.total_minutes))
        active = [
            max(0, int(row.get("maximum_strength") or 0))
            for row in limits.to_dicts()
            if self._tag(row.get("country_id")) == country
            and str(row.get("status") or "active").lower() == "active"
            and int(row.get("effective_at_minute") or 0) <= now
            and int(row.get("expires_at_minute") or 0) > now
        ]
        return min(active) if active else None

    def current_strength(
        self,
        state: GameState,
        country_id: str,
        unit_rows: Iterable[dict[str, Any]] | None = None,
    ) -> int:
        country = self._tag(country_id)
        units = state.tables.get("units")
        rows = list(unit_rows) if unit_rows is not None else (
            [] if units is None else units.to_dicts()
        )
        represented = sum(
            max(0, int(row.get("strength") or 0))
            for row in rows
            if self._tag(row.get("owner")) == country
        )
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return represented
        country_row = next(
            (row for row in countries.to_dicts() if self._tag(row.get("id")) == country),
            None,
        )
        if country_row is None or "military_count" not in countries.columns:
            return represented
        declared = max(0, int(country_row.get("military_count") or 0))
        return max(represented, declared)

    def committed_production(
        self,
        state: GameState,
        country_id: str,
        orders: Iterable[dict[str, Any]] | None = None,
    ) -> int:
        production = state.tables.get("production_orders")
        rows = list(orders) if orders is not None else (
            [] if production is None else production.to_dicts()
        )
        country = self._tag(country_id)
        return sum(
            max(0, int(row.get("quantity") or 0))
            for row in rows
            if self._tag(row.get("country_id")) == country
            and str(row.get("status") or "").lower() in self.ACTIVE_ORDER_STATUSES
        )

    def can_add(
        self,
        state: GameState,
        country_id: str,
        quantity: int,
        *,
        unit_rows: Iterable[dict[str, Any]] | None = None,
        production_orders: Iterable[dict[str, Any]] | None = None,
        include_production: bool = False,
    ) -> bool:
        limit = self.maximum_strength(state, country_id)
        if limit is None:
            return True
        committed = self.committed_production(state, country_id, production_orders) if include_production else 0
        return self.current_strength(state, country_id, unit_rows) + committed + max(0, int(quantity)) <= limit

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()
