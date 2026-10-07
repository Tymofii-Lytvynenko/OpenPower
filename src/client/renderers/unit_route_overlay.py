"""Presentation models for selected military route overlays."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import polars as pl

from src.client.utils.diplomacy_utils import get_military_allies, get_military_enemies
from src.client.visualization.map_modes.empire_mode import EmpireMapMode
from src.core.map.engagement_geometry import interpolate_geo
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


AFFILIATION_OWN = "own"
AFFILIATION_ALLIED = "allied"
AFFILIATION_HOSTILE = "hostile"
AFFILIATION_NEUTRAL = "neutral"

ROUTE_COLORS = {
    AFFILIATION_OWN: (*[value / 255.0 for value in EmpireMapMode.SELECTED[:3]], 0.96),
    AFFILIATION_ALLIED: (*[value / 255.0 for value in EmpireMapMode.ALLY[:3]], 0.96),
    AFFILIATION_HOSTILE: (*[value / 255.0 for value in EmpireMapMode.ENEMY[:3]], 0.96),
    AFFILIATION_NEUTRAL: (0.56, 0.59, 0.64, 0.86),
}

ROUTE_DASH_LENGTHS = {
    AFFILIATION_OWN: None,
    AFFILIATION_ALLIED: (10.0, 4.0),
    AFFILIATION_HOSTILE: (7.0, 3.0),
    AFFILIATION_NEUTRAL: (3.0, 4.0),
}

MAX_ROUTE_OVERLAYS = 8
MAX_SAMPLED_POINTS_PER_ROUTE = 256


@dataclass(frozen=True, slots=True)
class UnitRouteOverlay:
    unit_id: str
    owner: str
    affiliation: str
    action_label: str
    status_label: str
    waypoints: tuple[GeoCoordinate, ...]

    @property
    def color(self) -> tuple[float, float, float, float]:
        return ROUTE_COLORS[self.affiliation]

    @property
    def dash_lengths(self) -> tuple[float, float] | None:
        return ROUTE_DASH_LENGTHS[self.affiliation]

    @property
    def label(self) -> str:
        return f"{self.action_label} · {self.owner}"


def selected_unit_route_overlays(
    state: GameState | None,
    selected_unit_ids: Iterable[str],
    viewer_country_tag: str | None,
) -> list[UnitRouteOverlay]:
    """Resolve accepted route snapshots without mutating simulation state."""

    if state is None:
        return []
    selected: list[str] = []
    seen: set[str] = set()
    for unit_id in selected_unit_ids:
        clean_id = str(unit_id or "").strip()
        if clean_id and clean_id not in seen:
            selected.append(clean_id)
            seen.add(clean_id)
    if not selected:
        return []
    selected_ids = selected[:MAX_ROUTE_OVERLAYS]
    selected_set = set(selected_ids)

    units = state.tables.get("units")
    routes = state.tables.get("unit_movement_routes")
    regions = state.tables.get("regions")
    if units is None or routes is None or regions is None:
        return []
    if not {"id", "owner"}.issubset(units.columns):
        return []
    if not {"unit_id", "route_region_ids"}.issubset(routes.columns):
        return []
    if not {"id", "latitude", "longitude"}.issubset(regions.columns):
        return []

    selected_routes = routes.filter(pl.col("unit_id").is_in(selected_ids)).to_dicts()
    unit_by_id = {
        str(row.get("id") or ""): row
        for row in units.filter(pl.col("id").is_in(selected_ids)).to_dicts()
        if str(row.get("id") or "") in selected_set
    }
    route_region_ids = {
        int(region_id)
        for route in selected_routes
        for region_id in (route.get("route_region_ids") or [])
        if region_id is not None
    }
    region_by_id = {
        int(row["id"]): row
        for row in regions.filter(pl.col("id").is_in(sorted(route_region_ids)))
        .select(["id", "latitude", "longitude"])
        .to_dicts()
        if row.get("id") is not None
    }
    active_country = str(viewer_country_tag or "").strip().upper()
    allies = {str(tag).strip().upper() for tag in get_military_allies(state, active_country)}
    enemies = {str(tag).strip().upper() for tag in get_military_enemies(state, active_country)}

    overlays: list[UnitRouteOverlay] = []
    for route in selected_routes:
        unit_id = str(route.get("unit_id") or "")
        unit = unit_by_id.get(unit_id)
        if unit is None:
            continue
        status = str(route.get("status") or "").strip().lower()
        if status not in {"in_transit", "blocked", "interrupted", "retreating"}:
            continue
        owner = str(unit.get("owner") or route.get("owner_country_id") or "").strip().upper()
        waypoints = _route_waypoints(unit, route, region_by_id)
        if len(waypoints) < 2:
            continue
        if owner == active_country:
            affiliation = AFFILIATION_OWN
        elif owner in enemies:
            affiliation = AFFILIATION_HOSTILE
        elif owner in allies:
            affiliation = AFFILIATION_ALLIED
        else:
            affiliation = AFFILIATION_NEUTRAL

        invasion = bool(route.get("is_naval_invasion"))
        engagement = str(unit.get("engagement_mode") or "").strip().lower()
        action = "Naval landing" if invasion else "Move and attack" if engagement == "assault" else "Move"
        if status == "blocked":
            status_label = "Blocked"
        elif status == "interrupted":
            status_label = "Interrupted"
        elif status == "retreating":
            status_label = "Retreating"
        else:
            status_label = "In transit"
        overlays.append(UnitRouteOverlay(
            unit_id=unit_id,
            owner=owner,
            affiliation=affiliation,
            action_label=action,
            status_label=status_label,
            waypoints=tuple(waypoints),
        ))
    return overlays


def sample_route_waypoints(
    waypoints: Iterable[GeoCoordinate],
    samples_per_leg: int = 8,
) -> list[GeoCoordinate]:
    """Sample short great-circle segments so a drawn line follows the globe."""

    points = list(waypoints)
    if len(points) < 2:
        return points
    if len(points) > MAX_SAMPLED_POINTS_PER_ROUTE:
        last_point = points[-1]
        stride = math.ceil((len(points) - 1) / (MAX_SAMPLED_POINTS_PER_ROUTE - 1))
        points = points[::stride]
        if points[-1] != last_point:
            points.append(last_point)
    steps = max(1, int(samples_per_leg))
    segment_count = len(points) - 1
    effective_steps = min(steps, max(1, (MAX_SAMPLED_POINTS_PER_ROUTE - 1) // segment_count))
    sampled: list[GeoCoordinate] = [points[0]]
    for start, end in zip(points, points[1:]):
        sampled.extend(
            interpolate_geo(start, end, step / effective_steps)
            for step in range(1, effective_steps + 1)
        )
    return sampled


def _route_waypoints(
    unit: dict,
    route: dict,
    region_by_id: dict[int, dict],
) -> list[GeoCoordinate]:
    route_ids = [int(region_id) for region_id in (route.get("route_region_ids") or [])]
    route_index = max(0, int(route.get("route_index") or 0))
    points: list[GeoCoordinate] = []
    current = _coordinate(unit.get("latitude"), unit.get("longitude"))
    if current is None and route_ids:
        fallback_index = min(max(0, route_index - 1), len(route_ids) - 1)
        current = _region_coordinate(region_by_id.get(route_ids[fallback_index]))
    if current is not None:
        points.append(current)

    for region_id in route_ids[route_index:]:
        geo = _region_coordinate(region_by_id.get(region_id))
        if geo is not None and (not points or _different(points[-1], geo)):
            points.append(geo)

    if bool(route.get("has_custom_destination")) and points:
        custom = _coordinate(route.get("destination_latitude"), route.get("destination_longitude"))
        if custom is not None:
            points[-1] = custom
    return points


def _region_coordinate(row: dict | None) -> GeoCoordinate | None:
    if row is None:
        return None
    return _coordinate(row.get("latitude"), row.get("longitude"))


def _coordinate(latitude: object, longitude: object) -> GeoCoordinate | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return GeoCoordinate(lat, lon)


def _different(left: GeoCoordinate, right: GeoCoordinate) -> bool:
    return abs(left.latitude - right.latitude) > 1e-9 or abs(left.longitude - right.longitude) > 1e-9
