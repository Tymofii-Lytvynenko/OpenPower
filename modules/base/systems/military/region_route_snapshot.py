"""Lazy region indexes scoped to one system update."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.military.route_policy import MilitaryRoutePlanner, RegionRouteGraph


class RegionRouteSnapshot:
    """Materialize map rows, home regions, and topology once when needed."""

    def __init__(self, regions: pl.DataFrame | None, adjacency: pl.DataFrame | None) -> None:
        self._regions = regions
        self._adjacency = adjacency
        self._rows: list[dict[str, Any]] | None = None
        self._region_by_id: dict[int, dict[str, Any]] | None = None
        self._home_by_owner: dict[str, dict[str, Any]] | None = None
        self._owned_region_by_id: dict[tuple[str, int], dict[str, Any]] = {}
        self._prepared_graph: RegionRouteGraph | None = None

    @property
    def rows(self) -> list[dict[str, Any]]:
        if self._rows is None:
            self._rows = [] if self._regions is None else self._regions.to_dicts()
        return self._rows

    @property
    def region_by_id(self) -> dict[int, dict[str, Any]]:
        if self._region_by_id is None:
            self._region_by_id = {int(row.get("id") or 0): row for row in self.rows}
        return self._region_by_id

    @property
    def prepared_graph(self) -> RegionRouteGraph:
        if self._prepared_graph is None:
            # Rebuilding adjacency for every cell duplicated work on the full
            # world graph, even though its topology is unchanged within an update.
            self._prepared_graph = MilitaryRoutePlanner().prepare(
                self._regions,
                self._adjacency,
                region_rows=self._rows,
            )
        return self._prepared_graph

    def home_region(self, owner: str, capital_region_id: int = 0) -> dict[str, Any] | None:
        if self._home_by_owner is None:
            self._home_by_owner = {}
            for row in self.rows:
                country = str(row.get("owner") or "").strip().upper()
                region_id = int(row.get("id") or 0)
                self._owned_region_by_id.setdefault((country, region_id), row)
                previous = self._home_by_owner.get(country)
                if previous is None or region_id < int(previous.get("id") or 0):
                    self._home_by_owner[country] = row
        country = owner.strip().upper()
        capital = self._owned_region_by_id.get((country, int(capital_region_id)))
        return capital if capital is not None else self._home_by_owner.get(country)
