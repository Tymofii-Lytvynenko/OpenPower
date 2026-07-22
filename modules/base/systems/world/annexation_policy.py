"""Annexation invalidation rules that depend on regional control and borders."""

from __future__ import annotations

import json
from typing import Any, Iterable

import polars as pl

from src.shared.state import GameState


class AnnexationPolicy:
    """Keeps delayed annexations valid only while their control footprint is stable."""

    def invalidated_claim_regions(self, state: GameState, claims: pl.DataFrame) -> set[int]:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty():
            return set()
        by_id = {int(row.get("id") or 0): row for row in regions.iter_rows(named=True)}
        changed: set[int] = set()
        for claim in claims.iter_rows(named=True):
            if str(claim.get("status") or "") != "pending":
                continue
            region_id = int(claim.get("region_id") or 0)
            region = by_id.get(region_id)
            if region is None or not self._matches_claim_control(region, claim):
                changed.add(region_id)
        return changed | self._neighbor_regions(state, changed)

    def _matches_claim_control(self, region: dict[str, Any], claim: dict[str, Any]) -> bool:
        return (
            self._tag(region.get("owner")) == self._tag(claim.get("political_owner_id"))
            and self._tag(region.get("controller")) == self._tag(claim.get("annexing_country_id"))
        )

    def _neighbor_regions(self, state: GameState, region_ids: Iterable[int]) -> set[int]:
        targets = {int(region_id) for region_id in region_ids if int(region_id) > 0}
        if not targets:
            return set()
        adjacency = state.tables.get("region_adjacency")
        if adjacency is not None and {"region_id", "neighbor_region_id"}.issubset(adjacency.columns):
            neighbors: set[int] = set()
            for row in adjacency.iter_rows(named=True):
                region_id, neighbor_id = int(row["region_id"]), int(row["neighbor_region_id"])
                if region_id in targets:
                    neighbors.add(neighbor_id)
                if neighbor_id in targets:
                    neighbors.add(region_id)
            return neighbors
        return self._inline_neighbors(state.tables.get("regions"), targets)

    def _inline_neighbors(self, regions: pl.DataFrame | None, targets: set[int]) -> set[int]:
        if regions is None or "adjacent_region_ids" not in regions.columns:
            return set()
        neighbors: set[int] = set()
        for row in regions.iter_rows(named=True):
            if int(row.get("id") or 0) not in targets:
                continue
            neighbors.update(self._ids(row.get("adjacent_region_ids")))
        return neighbors

    def _ids(self, value: Any) -> set[int]:
        if isinstance(value, (list, tuple, set)):
            values = value
        else:
            try:
                values = json.loads(str(value or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                values = []
        return {int(item) for item in values if str(item).strip().lstrip("-").isdigit()}

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()
