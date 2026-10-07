"""Scenario-driven escort and hostile-fleet checks for amphibious landings."""

from __future__ import annotations

import math
from typing import Any, Iterable

from modules.base.systems.military.war_policy import hostile_country_pairs
from src.core.map.engagement_geometry import interpolate_geo
from src.core.map.geo import GeoCoordinate


CAPITAL_SHIP_TYPES = frozenset({"aircraft_carriers", "battleships", "battlecruisers", "cruisers", "capital_ship"})


class NavalInvasionPolicy:
    """Validates escort proximity and nearby hostile fleets without changing ownership."""

    def validate(
        self,
        state,
        invading_unit: dict[str, Any],
        target_region: dict[str, Any],
        units: Iterable[dict[str, Any]],
        current_position: tuple[float, float],
    ) -> tuple[bool, str]:
        owner = self._tag(invading_unit.get("owner"))
        target = self._tag(target_region.get("owner"))
        if not target or owner == target:
            return False, "A naval landing requires a target region controlled by another country."
        escort_limit = self._positive(state.globals.get("naval_invasion_escort_km"), 750.0)
        hostile_limit = self._positive(state.globals.get("naval_invasion_hostile_fleet_km"), 1500.0)
        target_position = (self._number(target_region.get("latitude")), self._number(target_region.get("longitude")))
        capital_ships = self._capital_ship_types(state)
        escorts = [
            unit for unit in units
            if self._tag(unit.get("owner")) == owner
            and self._unit_domain(unit) == "naval"
            and self._unit_type(unit) in capital_ships
            and int(unit.get("strength") or 0) > 0
        ]
        if not any(self._distance_km(self._position(unit, int(state.time.total_minutes)), target_position) <= escort_limit for unit in escorts):
            return False, f"A capital ship must remain within {escort_limit:g} km of the landing region."
        hostile_pairs = hostile_country_pairs(
            [] if state.tables.get("countries_wars") is None else state.get_table("countries_wars").to_dicts()
        )
        invading_position = (float(current_position[0]), float(current_position[1]))
        for unit in units:
            if self._unit_domain(unit) != "naval" or int(unit.get("strength") or 0) <= 0:
                continue
            if frozenset((owner, self._tag(unit.get("owner")))) in hostile_pairs and self._distance_km(self._position(unit, int(state.time.total_minutes)), invading_position) <= hostile_limit:
                return False, f"A hostile fleet is within the {hostile_limit:g} km exclusion zone."
        return True, ""

    def _capital_ship_types(self, state):
        configured = state.globals.get("naval_capital_ship_types")
        if isinstance(configured, (list, tuple, set)):
            return frozenset(self._unit_type({"unit_type": value}) for value in configured)
        return CAPITAL_SHIP_TYPES

    def _position(self, unit, now):
        if not bool(unit.get("is_moving")):
            return self._number(unit.get("latitude")), self._number(unit.get("longitude"))
        departed_value = unit.get("departed_at_minute")
        arrival_value = unit.get("arrival_at_minute")
        departed = int(departed_value if departed_value is not None else now)
        arrival = int(arrival_value if arrival_value is not None else now)
        progress = max(0.0, min(1.0, (now - departed) / max(1, arrival - departed)))
        interpolated = interpolate_geo(
            GeoCoordinate(
                self._number(unit.get("source_latitude")),
                self._number(unit.get("source_longitude")),
            ),
            GeoCoordinate(
                self._number(unit.get("target_latitude")),
                self._number(unit.get("target_longitude")),
            ),
            progress,
        )
        return interpolated.latitude, interpolated.longitude

    def _unit_domain(self, unit):
        domain = str(unit.get("unit_domain") or "").strip().lower()
        if domain:
            return domain
        return "naval" if self._unit_type(unit) in CAPITAL_SHIP_TYPES | {"frigates", "destroyers", "submarines", "corvettes"} else "land"

    def _unit_type(self, unit):
        return str(unit.get("unit_type") or "").strip().lower().replace(" ", "_")

    def _distance_km(self, left, right):
        lat1, lon1, lat2, lon2 = map(math.radians, (*left, *right))
        delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return 6371.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    def _number(self, value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    def _positive(self, value, default):
        parsed = self._number(value)
        return parsed if parsed > 0.0 else default

    def _tag(self, value):
        return str(value or "").strip().upper()
