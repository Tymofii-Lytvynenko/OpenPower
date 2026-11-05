"""Authoritative route progression for military units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

import polars as pl

from modules.base.systems.military.movement_access import MovementAccessContext
from modules.base.systems.military.movement_constants import NO_TARGET_REGION
from modules.base.systems.military.movement_domains import (
    domain_route_compatible,
    has_domain_metadata,
    unit_domain,
)
from modules.base.systems.military.movement_duration import MovementDurationPolicy
from modules.base.systems.military.naval_invasion_policy import NavalInvasionPolicy
from modules.base.systems.military.war_policy import hostile_country_pairs
from src.core.map.engagement_geometry import engagement_radius_km, first_zone_contact_fraction, interpolate_geo
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class _MovementAccessProvider(Protocol):
    def for_country(self, state: GameState, unit_owner: str) -> MovementAccessContext: ...


@dataclass
class _MovementUpdateContext:
    state: GameState
    current_minute: int
    capability_speed_by_unit: dict[str, float]
    rows: list[dict[str, Any]]
    route_table: pl.DataFrame | None
    route_by_unit: dict[str, dict[str, Any]]
    regions: pl.DataFrame | None
    region_locations: dict[int, GeoCoordinate]
    region_rows: list[dict[str, Any]]
    has_domain_metadata: bool
    regions_by_id: dict[int, dict[str, Any]]
    contact_candidates: dict[str, list[dict[str, Any]]]
    access_context_by_country: dict[str, MovementAccessContext]


@dataclass
class _MovementLegUpdate:
    row: dict[str, Any]
    route: dict[str, Any] | None
    owner: str
    target_region_id: int
    route_ids: list[int]
    route_index: int
    arrival_at: int
    progress: float
    source_geo: GeoCoordinate
    target_geo: GeoCoordinate
    previous_geo: GeoCoordinate
    next_geo: GeoCoordinate
    is_final_leg: bool


@dataclass(frozen=True)
class _HostileContactCandidate:
    key: tuple[float, int, str]
    defender: dict[str, Any]
    fraction: float


class MovementProgression:
    """Advance authoritative routes while composing movement and access policies."""

    def __init__(
        self,
        access_policy: _MovementAccessProvider,
        duration_policy: MovementDurationPolicy,
        naval_invasion_policy: NavalInvasionPolicy,
        duration_calculator: Callable[..., int],
        route_schema: dict[str, pl.DataType],
    ) -> None:
        self._access_policy = access_policy
        self._duration_policy = duration_policy
        self._naval_invasion_policy = naval_invasion_policy
        self._duration_calculator = duration_calculator
        self._route_schema = route_schema

    def update_rows(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        context = self._build_movement_update_context(
            state,
            units,
            current_minute,
            capability_speed_by_unit or {},
        )
        for row in context.rows:
            self._update_movement_row(context, row)
        self._publish_movement_routes(context)
        return context.rows

    def _build_movement_update_context(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        capability_speed_by_unit: dict[str, float],
    ) -> _MovementUpdateContext:
        war_table = state.tables.get("countries_wars")
        war_rows = [] if war_table is None else war_table.to_dicts()
        hostile_owners = self._hostile_owners_by_country(war_rows)

        rows = units.to_dicts()
        route_table = state.tables.get("unit_movement_routes")
        route_rows = [] if route_table is None else route_table.to_dicts()
        route_by_unit = {str(route.get("unit_id") or ""): route for route in route_rows}
        regions = state.tables.get("regions")
        region_locations = {} if regions is None else self._duration_policy.region_locations(regions)
        region_rows = [] if regions is None else regions.to_dicts()
        regions_by_id = {int(region.get("id") or 0): region for region in region_rows}

        return _MovementUpdateContext(
            state=state,
            current_minute=current_minute,
            capability_speed_by_unit=capability_speed_by_unit,
            rows=rows,
            route_table=route_table,
            route_by_unit=route_by_unit,
            regions=regions,
            region_locations=region_locations,
            region_rows=region_rows,
            has_domain_metadata=has_domain_metadata(region_rows),
            regions_by_id=regions_by_id,
            contact_candidates=self._contact_candidates_by_owner(rows, hostile_owners),
            access_context_by_country={},
        )

    def _hostile_owners_by_country(self, war_rows: list[dict[str, Any]]) -> dict[str, set[str]]:
        hostile_owners: dict[str, set[str]] = {}
        for pair in hostile_country_pairs(war_rows):
            tags = tuple(pair)
            if len(tags) != 2:
                continue
            left, right = tags
            hostile_owners.setdefault(left, set()).add(right)
            hostile_owners.setdefault(right, set()).add(left)
        return hostile_owners

    def _contact_candidates_by_owner(
        self,
        rows: list[dict[str, Any]],
        hostile_owners: dict[str, set[str]],
    ) -> dict[str, list[dict[str, Any]]]:
        ordered_rows = sorted(rows, key=lambda candidate: str(candidate.get("id") or ""))
        moving_owners = {
            str(row.get("owner") or "").strip().upper()
            for row in rows
            if bool(row.get("is_moving"))
        }
        return {
            owner: [
                candidate
                for candidate in ordered_rows
                if str(candidate.get("owner") or "").strip().upper()
                in hostile_owners.get(owner, set())
            ]
            for owner in moving_owners
        }

    def _update_movement_row(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
    ) -> None:
        leg = self._prepare_movement_leg(context, row)
        if leg is None:
            return

        domain_allowed, access_allowed = self._movement_segment_permissions(
            context,
            leg.row,
            leg.owner,
            context.regions_by_id.get(leg.target_region_id),
            leg.is_final_leg,
            bool(leg.route and leg.route.get("is_naval_invasion")),
        )
        if not domain_allowed or not access_allowed:
            self._block_current_route_leg(context, leg.row, leg.route, leg.source_geo, domain_allowed)
            return
        if self._interrupt_movement_for_contact(
            context,
            leg.row,
            leg.route,
            leg.owner,
            leg.previous_geo,
            leg.next_geo,
        ):
            return
        if leg.progress < 1.0:
            self._record_movement_progress(context, leg)
            return
        self._complete_movement_leg(context, leg)

    def _prepare_movement_leg(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
    ) -> _MovementLegUpdate | None:
        target_region_id = self._active_movement_target(row)
        if target_region_id is None:
            row["movement_progress"] = 0.0
            row["is_moving"] = False
            return None
        return self._build_movement_leg(context, row, target_region_id)

    def _active_movement_target(self, row: dict[str, Any]) -> int | None:
        target_region_id = int(row.get("target_region_id") or NO_TARGET_REGION)
        if target_region_id <= 0 or not bool(row.get("is_moving")):
            return None
        return target_region_id

    def _build_movement_leg(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        target_region_id: int,
    ) -> _MovementLegUpdate:
        owner = str(row.get("owner") or "").strip().upper()
        route, route_ids, route_index, is_final_leg = self._movement_route_state(
            context,
            row,
            target_region_id,
        )
        arrival_at, previous_progress, progress = self._movement_timing(
            row,
            context.current_minute,
        )
        source_geo, target_geo = self._movement_coordinates(row)
        return _MovementLegUpdate(
            row=row,
            route=route,
            owner=owner,
            target_region_id=target_region_id,
            route_ids=route_ids,
            route_index=route_index,
            arrival_at=arrival_at,
            progress=progress,
            source_geo=source_geo,
            target_geo=target_geo,
            previous_geo=interpolate_geo(source_geo, target_geo, previous_progress),
            next_geo=interpolate_geo(source_geo, target_geo, progress),
            is_final_leg=is_final_leg,
        )

    def _movement_route_state(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        target_region_id: int,
    ) -> tuple[dict[str, Any] | None, list[int], int, bool]:
        route = context.route_by_unit.get(str(row.get("id") or ""))
        if route is None:
            return None, [], 0, True
        route_ids = [int(value) for value in route.get("route_region_ids") or []]
        route_index = int(route.get("route_index") or 0)
        is_final_leg = int(route.get("destination_region_id") or target_region_id) == target_region_id
        return route, route_ids, route_index, is_final_leg

    def _movement_timing(
        self,
        row: dict[str, Any],
        current_minute: int,
    ) -> tuple[int, float, float]:
        departed_value = row.get("departed_at_minute")
        arrival_value = row.get("arrival_at_minute")
        departed_at = int(departed_value if departed_value is not None else current_minute)
        arrival_at = int(arrival_value if arrival_value is not None else current_minute)
        duration = max(1, arrival_at - departed_at)
        previous_progress = max(0.0, min(1.0, float(row.get("movement_progress") or 0.0)))
        progress = max(0.0, min(1.0, (current_minute - departed_at) / duration))
        return arrival_at, previous_progress, progress

    def _movement_coordinates(
        self,
        row: dict[str, Any],
    ) -> tuple[GeoCoordinate, GeoCoordinate]:
        source_geo = GeoCoordinate(
            latitude=self._row_float(row, "source_latitude", row.get("latitude")),
            longitude=self._row_float(row, "source_longitude", row.get("longitude")),
        )
        target_geo = GeoCoordinate(
            latitude=self._row_float(row, "target_latitude", row.get("latitude")),
            longitude=self._row_float(row, "target_longitude", row.get("longitude")),
        )
        return source_geo, target_geo

    def _record_movement_progress(
        self,
        context: _MovementUpdateContext,
        leg: _MovementLegUpdate,
    ) -> None:
        leg.row["movement_progress"] = leg.progress
        leg.row["is_moving"] = True
        if leg.route is not None:
            leg.route["updated_at_minute"] = context.current_minute

    def _movement_segment_permissions(
        self,
        context: _MovementUpdateContext,
        unit: dict[str, Any],
        owner: str,
        target_region: dict[str, Any] | None,
        is_final_leg: bool,
        is_naval_invasion: bool,
    ) -> tuple[bool, bool]:
        domain_allowed = target_region is not None and domain_route_compatible(
            unit_domain(unit),
            target_region,
            is_final_leg,
            is_naval_invasion,
            context.region_rows,
            metadata_available=context.has_domain_metadata,
        )[0]
        access_context = self._movement_access_context(context, owner)
        access_allowed = target_region is not None and (
            access_context.can_station(target_region)
            if is_final_leg
            else access_context.can_transit(target_region)
        )
        return domain_allowed, access_allowed

    def _movement_access_context(
        self,
        context: _MovementUpdateContext,
        owner: str,
    ) -> MovementAccessContext:
        access_context = context.access_context_by_country.get(owner)
        if access_context is None:
            access_context = self._access_policy.for_country(context.state, owner)
            context.access_context_by_country[owner] = access_context
        return access_context

    def _block_current_route_leg(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        route: dict[str, Any] | None,
        source_geo: GeoCoordinate,
        domain_allowed: bool,
    ) -> None:
        # Revoked rights stop movement at the last legal waypoint instead of allowing a stale route to cross a border.
        self.stop_unit_at(row, source_geo, context.current_minute)
        lifecycle = str(row.get("unit_lifecycle") or "")
        row["unit_lifecycle"] = (
            "deployment_blocked"
            if lifecycle in {"deployment_transit", "in_transit"}
            else "route_blocked"
        )
        if route is None:
            return
        route["status"] = "blocked"
        route["rejection_reason"] = (
            "The current route segment is incompatible with the unit domain."
            if not domain_allowed
            else "The current route segment no longer has valid access rights."
        )
        route["updated_at_minute"] = context.current_minute

    def _interrupt_movement_for_contact(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        route: dict[str, Any] | None,
        owner: str,
        previous_geo: GeoCoordinate,
        next_geo: GeoCoordinate,
    ) -> bool:
        contact = self.first_hostile_contact(
            row,
            context.contact_candidates.get(owner, ()),
            previous_geo,
            next_geo,
            context.current_minute,
        )
        if contact is None:
            return False

        defender, fraction = contact
        contact_geo = interpolate_geo(previous_geo, next_geo, fraction)
        row["current_region_id"] = int(defender.get("current_region_id") or 0)
        self.stop_unit_at(row, contact_geo, context.current_minute)
        row["engagement_mode"] = "positional"
        if route is not None:
            route["status"] = "interrupted"
            route["rejection_reason"] = "Hostile contact interrupted the route."
            route["updated_at_minute"] = context.current_minute
        defender_geo = self.unit_geo_at(defender, context.current_minute)
        self.stop_unit_at(defender, defender_geo, context.current_minute)
        defender["engagement_mode"] = "positional"
        return True

    def _complete_movement_leg(
        self,
        context: _MovementUpdateContext,
        leg: _MovementLegUpdate,
    ) -> None:
        if self._block_invalid_naval_landing(context, leg):
            return

        leg.row["current_region_id"] = leg.target_region_id
        next_index = leg.route_index + 1
        if leg.route is not None and next_index < len(leg.route_ids):
            self._start_next_route_leg(context, leg, next_index)
            return
        self._finish_unit_arrival(context, leg.row, leg.route, leg.target_geo)

    def _block_invalid_naval_landing(
        self,
        context: _MovementUpdateContext,
        leg: _MovementLegUpdate,
    ) -> bool:
        route = leg.route
        if route is None or not bool(route.get("is_naval_invasion")) or not leg.is_final_leg:
            return False
        destination = context.regions_by_id.get(leg.target_region_id)
        if destination is None:
            valid_landing, landing_reason = False, "The landing region is no longer available."
        else:
            valid_landing, landing_reason = self._naval_invasion_policy.validate(
                context.state,
                leg.row,
                destination,
                context.rows,
                (leg.next_geo.latitude, leg.next_geo.longitude),
            )
        if valid_landing:
            return False

        self.stop_unit_at(leg.row, leg.previous_geo, context.current_minute)
        leg.row["unit_lifecycle"] = "landing_blocked"
        route["status"] = "blocked"
        route["rejection_reason"] = landing_reason
        route["updated_at_minute"] = context.current_minute
        return True

    def _start_next_route_leg(
        self,
        context: _MovementUpdateContext,
        leg: _MovementLegUpdate,
        next_index: int,
    ) -> None:
        route = leg.route
        if route is None:
            return
        next_region_id = leg.route_ids[next_index]
        destination = self._resolve_next_route_location(context, next_region_id)
        if destination is None:
            self._block_missing_next_route_location(context, leg.row, route, leg.target_geo)
            return

        next_geo, next_region_row = destination
        final_leg = next_index == len(leg.route_ids) - 1
        domain_allowed, access_allowed = self._movement_segment_permissions(
            context,
            leg.row,
            leg.owner,
            next_region_row,
            final_leg,
            bool(route.get("is_naval_invasion")),
        )
        if not domain_allowed or not access_allowed:
            self._block_next_route_leg(context, leg.row, route, leg.target_geo, domain_allowed)
            return
        self._begin_next_route_leg(
            context,
            leg,
            route,
            next_region_id,
            next_index,
            next_geo,
            next_region_row,
            final_leg,
        )

    def _resolve_next_route_location(
        self,
        context: _MovementUpdateContext,
        next_region_id: int,
    ) -> tuple[GeoCoordinate, dict[str, Any] | None] | None:
        next_geo = context.region_locations.get(next_region_id)
        if next_geo is None or context.regions is None or next_region_id <= 0:
            return None
        return next_geo, context.regions_by_id.get(next_region_id)

    def _begin_next_route_leg(
        self,
        context: _MovementUpdateContext,
        leg: _MovementLegUpdate,
        route: dict[str, Any],
        next_region_id: int,
        next_index: int,
        next_geo: GeoCoordinate,
        next_region_row: dict[str, Any] | None,
        final_leg: bool,
    ) -> None:
        if bool(route.get("has_custom_destination")) and final_leg:
            next_geo = GeoCoordinate(
                float(route.get("destination_latitude") or 0.0),
                float(route.get("destination_longitude") or 0.0),
            )
        leg.row["latitude"] = leg.target_geo.latitude
        leg.row["longitude"] = leg.target_geo.longitude
        leg.row["source_region_id"] = leg.target_region_id
        leg.row["source_latitude"] = leg.target_geo.latitude
        leg.row["source_longitude"] = leg.target_geo.longitude
        if str(leg.row.get("unit_lifecycle") or "") in {"deployment_transit", "in_transit"}:
            leg.row["current_region_id"] = 0
        leg.row["target_region_id"] = next_region_id
        leg.row["target_latitude"] = next_geo.latitude
        leg.row["target_longitude"] = next_geo.longitude
        leg.row["departed_at_minute"] = leg.arrival_at
        duration_locations = dict(context.region_locations)
        duration_locations[leg.target_region_id] = leg.target_geo
        leg.row["arrival_at_minute"] = leg.arrival_at + self._duration_calculator(
            context.regions_by_id[leg.target_region_id],
            next_region_row,
            duration_locations,
            leg.row,
            context.state,
            context.capability_speed_by_unit.get(str(leg.row.get("id") or ""), 1.0),
        )
        leg.row["movement_progress"] = 0.0
        leg.row["is_moving"] = True
        leg.row["engagement_mode"] = ""
        route["route_index"] = next_index
        route["updated_at_minute"] = context.current_minute

    def _block_next_route_leg(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        route: dict[str, Any],
        target_geo: GeoCoordinate,
        domain_allowed: bool,
    ) -> None:
        self.stop_unit_at(row, target_geo, context.current_minute)
        lifecycle = str(row.get("unit_lifecycle") or "")
        if lifecycle in {"deployment_transit", "in_transit"}:
            row["current_region_id"] = 0
        row["unit_lifecycle"] = (
            "deployment_blocked" if lifecycle == "deployment_transit" else "route_blocked"
        )
        route["status"] = "blocked"
        route["rejection_reason"] = (
            "The next route segment is incompatible with the unit domain."
            if not domain_allowed
            else "The next route segment no longer has valid access rights."
        )
        route["updated_at_minute"] = context.current_minute

    def _block_missing_next_route_location(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        route: dict[str, Any],
        target_geo: GeoCoordinate,
    ) -> None:
        self.stop_unit_at(row, target_geo, context.current_minute)
        row["engagement_mode"] = ""
        lifecycle = str(row.get("unit_lifecycle") or "")
        if lifecycle in {"deployment_transit", "in_transit"}:
            row["current_region_id"] = 0
            row["unit_lifecycle"] = (
                "deployment_blocked" if str(row.get("production_order_id") or "") else "route_blocked"
            )
        route["status"] = "blocked"
        route["rejection_reason"] = "The next route region no longer has a valid location."
        route["updated_at_minute"] = context.current_minute

    def _finish_unit_arrival(
        self,
        context: _MovementUpdateContext,
        row: dict[str, Any],
        route: dict[str, Any] | None,
        target_geo: GeoCoordinate,
    ) -> None:
        self.stop_unit_at(row, target_geo, context.current_minute)
        row["engagement_mode"] = ""
        if route is not None:
            route["status"] = "arrived"
            route["rejection_reason"] = ""
            route["updated_at_minute"] = context.current_minute
        if "unit_lifecycle" in row:
            row["unit_lifecycle"] = (
                "battle_regrouping"
                if str(row.get("unit_lifecycle") or "") == "battle_retreating"
                else "available"
            )

    def _publish_movement_routes(self, context: _MovementUpdateContext) -> None:
        if context.route_table is None:
            return
        route_frame = (
            pl.DataFrame(list(context.route_by_unit.values()), schema=self._route_schema)
            if context.route_by_unit
            else pl.DataFrame(schema=self._route_schema)
        )
        if not context.route_table.equals(route_frame):
            context.state.update_table("unit_movement_routes", route_frame)


    def first_hostile_contact(
        self,
        moving_unit: dict[str, Any],
        unit_rows: Iterable[dict[str, Any]],
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> tuple[dict[str, Any], float] | None:
        moving_id = str(moving_unit.get("id") or "")
        best_candidate: _HostileContactCandidate | None = None
        for defender in unit_rows:
            candidate = self._hostile_contact_candidate(
                defender,
                moving_id,
                start,
                end,
                current_minute,
            )
            if candidate is None:
                continue
            if best_candidate is None or candidate.key < best_candidate.key:
                best_candidate = candidate
        if best_candidate is None:
            return None
        return best_candidate.defender, best_candidate.fraction

    def _hostile_contact_candidate(
        self,
        defender: dict[str, Any],
        moving_id: str,
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> _HostileContactCandidate | None:
        if self._defender_cannot_engage(defender, moving_id):
            return None
        fraction = first_zone_contact_fraction(
            start,
            end,
            self.unit_geo_at(defender, current_minute),
            engagement_radius_km(defender),
        )
        if fraction is None:
            return None
        return _HostileContactCandidate(
            key=self._contact_order_key(defender, fraction),
            defender=defender,
            fraction=fraction,
        )

    def _defender_cannot_engage(self, defender: dict[str, Any], moving_id: str) -> bool:
        return (
            str(defender.get("id") or "") == moving_id
            or int(defender.get("strength") or 0) <= 0
        )

    def _contact_order_key(
        self,
        defender: dict[str, Any],
        fraction: float,
    ) -> tuple[float, int, str]:
        region_id = int(defender.get("current_region_id") or 0)
        ordered_region_id = region_id if region_id > 0 else 2**31
        return (
            round(float(fraction), 12),
            ordered_region_id,
            str(defender.get("id") or ""),
        )


    def unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate:
        current_geo = GeoCoordinate(
            latitude=self._row_float(row, "latitude"),
            longitude=self._row_float(row, "longitude"),
        )
        if not bool(row.get("is_moving")) or int(row.get("target_region_id") or NO_TARGET_REGION) <= 0:
            return current_geo
        source_geo = GeoCoordinate(
            latitude=self._row_float(row, "source_latitude", current_geo.latitude),
            longitude=self._row_float(row, "source_longitude", current_geo.longitude),
        )
        target_geo = GeoCoordinate(
            latitude=self._row_float(row, "target_latitude", current_geo.latitude),
            longitude=self._row_float(row, "target_longitude", current_geo.longitude),
        )
        departed_value = row.get("departed_at_minute")
        arrival_value = row.get("arrival_at_minute")
        departed_at = int(departed_value if departed_value is not None else current_minute)
        arrival_at = int(arrival_value if arrival_value is not None else current_minute)
        progress = max(0.0, min(1.0, (current_minute - departed_at) / max(1, arrival_at - departed_at)))
        return interpolate_geo(source_geo, target_geo, progress)


    def stop_unit_at(self, row: dict[str, Any], geo: GeoCoordinate, current_minute: int) -> None:
        region_id = int(row.get("current_region_id") or 0)
        row["latitude"] = float(geo.latitude)
        row["longitude"] = float(geo.longitude)
        row["source_region_id"] = region_id
        row["source_latitude"] = float(geo.latitude)
        row["source_longitude"] = float(geo.longitude)
        row["target_region_id"] = NO_TARGET_REGION
        row["target_latitude"] = float(geo.latitude)
        row["target_longitude"] = float(geo.longitude)
        row["departed_at_minute"] = current_minute
        row["arrival_at_minute"] = current_minute
        row["movement_progress"] = 0.0
        row["is_moving"] = False

    def _row_float(self, row: dict[str, Any], key: str, fallback: Any = 0.0) -> float:
        try:
            return float(row.get(key) if row.get(key) is not None else fallback)
        except (TypeError, ValueError, OverflowError):
            return float(fallback or 0.0)
