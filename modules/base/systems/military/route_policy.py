"""Deterministic region routing for military movement orders."""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from src.core.map.geo import EquirectangularProjection, GeoCoordinate


@dataclass(frozen=True)
class RoutePlan:
    region_ids: tuple[int, ...]
    travel_cost: float
    rejection_reason: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.rejection_reason and bool(self.region_ids)


class MilitaryRoutePlanner:
    """Finds a least-cost legal path with stable tie-breaking."""

    def plan(
        self,
        source_region_id: int,
        destination_region_id: int,
        regions: Iterable[dict[str, Any]],
        adjacency_rows: Iterable[dict[str, Any]] | None,
        can_enter: Callable[[dict[str, Any], bool], bool],
        segment_cost: Callable[[dict[str, Any], dict[str, Any]], float] | None = None,
        explicit_waypoints: Iterable[int] | None = None,
    ) -> RoutePlan:
        region_by_id = {
            self._integer(row.get("id")): row
            for row in regions
            if self._integer(row.get("id")) > 0
        }
        source, destination = int(source_region_id), int(destination_region_id)
        if source not in region_by_id or destination not in region_by_id:
            return RoutePlan((), 0.0, "The source or destination region is invalid.")
        if source == destination:
            return RoutePlan((source,), 0.0)
        if not can_enter(region_by_id[destination], True):
            return RoutePlan((), 0.0, "The destination does not permit this force to station.")

        graph = self._adjacency(region_by_id, adjacency_rows)
        if explicit_waypoints is not None:
            path = (source, *(self._integer(item) for item in explicit_waypoints), destination)
            return self._validate_explicit(path, region_by_id, graph, can_enter, segment_cost)
        if not graph:
            path = (source, destination)
            return self._validate_explicit(path, region_by_id, graph, can_enter, segment_cost)

        default_cost = segment_cost or self._geographic_cost
        first = (source,)
        queue: list[tuple[float, tuple[int, ...], int]] = [(0.0, first, source)]
        best: dict[int, tuple[float, tuple[int, ...]]] = {source: (0.0, first)}
        while queue:
            cost, path, current = heapq.heappop(queue)
            if best.get(current) != (cost, path):
                continue
            if current == destination:
                return RoutePlan(path, cost)
            for neighbor in graph.get(current, ()):
                if neighbor == source:
                    continue
                is_destination = neighbor == destination
                region = region_by_id[neighbor]
                if not can_enter(region, is_destination):
                    continue
                step_cost = self._valid_cost(default_cost(region_by_id[current], region))
                next_path = (*path, neighbor)
                candidate = (cost + step_cost, next_path)
                if neighbor not in best or candidate < best[neighbor]:
                    best[neighbor] = candidate
                    heapq.heappush(queue, (candidate[0], candidate[1], neighbor))
        return RoutePlan((), 0.0, "No legal route connects the source and destination.")

    def _validate_explicit(
        self,
        path: tuple[int, ...],
        region_by_id: dict[int, dict[str, Any]],
        graph: dict[int, set[int]],
        can_enter: Callable[[dict[str, Any], bool], bool],
        segment_cost: Callable[[dict[str, Any], dict[str, Any]], float] | None,
    ) -> RoutePlan:
        if any(region_id not in region_by_id for region_id in path):
            return RoutePlan((), 0.0, "The route includes an invalid region.")
        if graph and any(right not in graph.get(left, set()) for left, right in zip(path, path[1:])):
            return RoutePlan((), 0.0, "The requested route crosses non-adjacent regions.")
        for index, region_id in enumerate(path[1:], start=1):
            final = index == len(path) - 1
            if not can_enter(region_by_id[region_id], final):
                reason = "The destination does not permit this force to station." if final else "The route crosses a region without transit rights."
                return RoutePlan((), 0.0, reason)
        cost_fn = segment_cost or self._geographic_cost
        cost = sum(self._valid_cost(cost_fn(region_by_id[left], region_by_id[right])) for left, right in zip(path, path[1:]))
        return RoutePlan(path, cost)

    def _adjacency(
        self,
        region_by_id: dict[int, dict[str, Any]],
        adjacency_rows: Iterable[dict[str, Any]] | None,
    ) -> dict[int, set[int]]:
        graph: dict[int, set[int]] = {region_id: set() for region_id in region_by_id}
        has_edges = False
        for row in adjacency_rows or ():
            left = self._integer(row.get("region_id"))
            right = self._integer(row.get("neighbor_region_id"))
            if left in graph and right in graph and left != right:
                graph[left].add(right)
                graph[right].add(left)
                has_edges = True
        for region_id, row in region_by_id.items():
            for neighbor in self._ids(row.get("adjacent_region_ids")):
                if neighbor in graph and neighbor != region_id:
                    graph[region_id].add(neighbor)
                    graph[neighbor].add(region_id)
                    has_edges = True
        return graph if has_edges else {}

    def _geographic_cost(self, left: dict[str, Any], right: dict[str, Any]) -> float:
        if all(key in left and key in right for key in ("latitude", "longitude")):
            projection = EquirectangularProjection(360.0, 180.0)
            return projection.geo_distance_km(
                GeoCoordinate(float(left["latitude"]), float(left["longitude"])),
                GeoCoordinate(float(right["latitude"]), float(right["longitude"])),
            )
        if all(key in left and key in right for key in ("center_x", "center_y")):
            return math.hypot(
                float(left["center_x"]) - float(right["center_x"]),
                float(left["center_y"]) - float(right["center_y"]),
            )
        return 1.0

    def _valid_cost(self, value: Any) -> float:
        try:
            cost = float(value)
        except (TypeError, ValueError, OverflowError):
            return 1.0
        return max(1e-9, cost) if math.isfinite(cost) else 1.0

    def _ids(self, value: Any) -> tuple[int, ...]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return ()
        if not isinstance(value, (list, tuple, set)):
            return ()
        return tuple(self._integer(item) for item in value if self._integer(item) > 0)

    def _integer(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
