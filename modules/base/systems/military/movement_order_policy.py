"""Reusable policies for validating and costing military movement orders."""

from __future__ import annotations

import math
from typing import Any, Callable

from modules.base.systems.military.movement_domains import (
    domain_route_compatible,
    has_domain_metadata,
    region_is_water,
    unit_domain,
)
from modules.base.systems.military.movement_duration import (
    DEFAULT_MOVE_MINUTES,
    MovementDurationPolicy,
)
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionMoveUnit
from src.shared.state import GameState


class MilitaryMovementOrderPolicy:
    """Apply shared movement-domain, destination, and segment-duration rules."""

    def __init__(self, duration_policy: MovementDurationPolicy) -> None:
        self._duration_policy = duration_policy

    def region_locations(self, regions) -> dict[int, GeoCoordinate]:
        return self._duration_policy.region_locations(regions)

    def route_segment_minutes_for_unit(
        self,
        source: dict[str, Any],
        target: dict[str, Any],
        locations: dict[int, GeoCoordinate],
        unit: dict[str, Any],
        state: GameState,
        capability_speed_multiplier: float = 1.0,
    ) -> int:
        source_geo = locations.get(int(source.get("id") or 0))
        target_geo = locations.get(int(target.get("id") or 0))
        base = (
            DEFAULT_MOVE_MINUTES
            if source_geo is None or target_geo is None
            else self._duration_policy.estimate_between(source_geo, target_geo)
        )
        domain_multiplier = self._domain_duration_multiplier(state, unit)
        size_multiplier = self._force_size_multiplier(state, unit)
        infrastructure_multiplier = self._infrastructure_multiplier(state, target)
        telecom_multiplier = self._telecom_multiplier(state, target)
        territory_multiplier = self._territory_multiplier(state, unit, target)
        speed_multiplier = self._bounded(
            capability_speed_multiplier,
            default=1.0,
            lower=0.5,
            upper=1.5,
        )
        duration = (
            base
            * domain_multiplier
            * size_multiplier
            * infrastructure_multiplier
            * telecom_multiplier
            * territory_multiplier
            / speed_multiplier
        )
        return self._bounded_duration(duration)

    def route_segment_cost_for_unit(
        self,
        locations: dict[int, GeoCoordinate],
        unit: dict[str, Any],
        state: GameState,
        capability_speed_multiplier: float = 1.0,
        edge_distance_km: dict[tuple[int, int], float] | None = None,
    ) -> Callable[[dict[str, Any], dict[str, Any]], int]:
        domain_multiplier = self._domain_duration_multiplier(state, unit)
        size_multiplier = self._force_size_multiplier(state, unit)
        infrastructure_coefficient = self._coefficient(
            state.globals.get("military_infrastructure_duration_coefficient", 0.25),
            0.25,
        )
        telecom_coefficient = self._coefficient(
            state.globals.get("military_telecom_coordination_coefficient", 0.15),
            0.15,
        )
        owner = str(unit.get("owner") or "").strip().upper()
        speed_multiplier = self._bounded(
            capability_speed_multiplier,
            default=1.0,
            lower=0.5,
            upper=1.5,
        )
        target_multipliers: dict[int, tuple[float, float, float]] = {}
        prepared_edge_distances = edge_distance_km or {}

        def cost(source: dict[str, Any], target: dict[str, Any]) -> int:
            source_geo = locations.get(int(source.get("id") or 0))
            target_id = int(target.get("id") or 0)
            target_geo = locations.get(target_id)
            source_id = int(source.get("id") or 0)
            edge_key = (source_id, target_id) if source_id < target_id else (target_id, source_id)
            edge_distance = prepared_edge_distances.get(edge_key)
            if edge_distance is not None:
                base = self._duration_policy.estimate_from_distance(edge_distance)
            elif source_geo is None or target_geo is None:
                base = DEFAULT_MOVE_MINUTES
            else:
                base = self._duration_policy.estimate_between(source_geo, target_geo)

            target_multiplier = target_multipliers.get(target_id)
            if target_multiplier is None:
                infrastructure = self._bounded(
                    self._row_float(target, "infrastructure", 0.0),
                    default=0.0,
                    lower=0.0,
                    upper=1.0,
                )
                telecom = self._bounded(
                    self._row_float(
                        target,
                        "telecom_capacity",
                        self._row_float(target, "communications", 0.0),
                    ),
                    default=0.0,
                    lower=0.0,
                    upper=1.0,
                )
                target_owner = str(target.get("owner") or "").strip().upper()
                territory_key = (
                    "military_domestic_duration_multiplier"
                    if not target_owner or target_owner == owner
                    else "military_foreign_duration_multiplier"
                )
                target_multiplier = (
                    1.0 / (1.0 + infrastructure * infrastructure_coefficient),
                    1.0 / (1.0 + telecom * telecom_coefficient),
                    self._multiplier(state.globals.get(territory_key), 1.0),
                )
                target_multipliers[target_id] = target_multiplier

            infrastructure_multiplier, telecom_multiplier, territory_multiplier = target_multiplier
            duration = base * domain_multiplier
            duration *= size_multiplier
            duration *= infrastructure_multiplier
            duration *= telecom_multiplier
            duration *= territory_multiplier
            duration /= speed_multiplier
            return self._bounded_duration(duration)

        return cost

    def resolve_target_geo(
        self,
        action: ActionMoveUnit,
        target_region_id: int,
        region_locations: dict[int, GeoCoordinate],
    ) -> GeoCoordinate | None:
        if action.target_latitude is not None and action.target_longitude is not None:
            return GeoCoordinate(
                latitude=float(action.target_latitude),
                longitude=float(action.target_longitude),
            )
        return region_locations.get(target_region_id)

    def source_geo_for_order(
        self,
        unit: dict[str, Any],
        deployment_dispatch: bool,
    ) -> GeoCoordinate:
        latitude = (
            self._row_float(unit, "source_latitude", unit.get("latitude"))
            if deployment_dispatch
            else float(unit["latitude"])
        )
        longitude = (
            self._row_float(unit, "source_longitude", unit.get("longitude"))
            if deployment_dispatch
            else float(unit["longitude"])
        )
        return GeoCoordinate(latitude=latitude, longitude=longitude)

    def domain_for_unit(self, unit: dict[str, Any]) -> str:
        return unit_domain(unit)

    def has_domain_metadata(self, regions) -> bool:
        return has_domain_metadata(regions)

    def domain_route_compatible(
        self,
        domain: str,
        region: dict[str, Any],
        final: bool,
        naval_invasion: bool,
        regions,
        *,
        metadata_available: bool | None = None,
    ) -> tuple[bool, str]:
        return domain_route_compatible(
            domain,
            region,
            final,
            naval_invasion,
            regions,
            metadata_available=metadata_available,
        )

    def region_is_water(self, region: dict[str, Any]) -> bool:
        return region_is_water(region)

    def bounded_multiplier(self, value: Any, default: float) -> float:
        return self._multiplier(value, default)

    def _domain_duration_multiplier(self, state: GameState, unit: dict[str, Any]) -> float:
        multipliers = state.globals.get("military_domain_duration_multipliers", {})
        if not isinstance(multipliers, dict):
            return 1.0
        return self._multiplier(multipliers.get(self.domain_for_unit(unit)), 1.0)

    def _force_size_multiplier(self, state: GameState, unit: dict[str, Any]) -> float:
        coefficient = self._coefficient(
            state.globals.get("military_force_size_duration_coefficient"),
            0.0,
        )
        strength = max(1, int(unit.get("strength") or 1))
        return 1.0 + min(1.0, math.log10(strength) / 4.0) * coefficient

    def _infrastructure_multiplier(
        self,
        state: GameState,
        target: dict[str, Any],
    ) -> float:
        infrastructure = self._bounded(
            self._row_float(target, "infrastructure", 0.0),
            default=0.0,
            lower=0.0,
            upper=1.0,
        )
        coefficient = self._coefficient(
            state.globals.get("military_infrastructure_duration_coefficient", 0.25),
            0.25,
        )
        return 1.0 / (1.0 + infrastructure * coefficient)

    def _telecom_multiplier(self, state: GameState, target: dict[str, Any]) -> float:
        telecom = self._bounded(
            self._row_float(
                target,
                "telecom_capacity",
                self._row_float(target, "communications", 0.0),
            ),
            default=0.0,
            lower=0.0,
            upper=1.0,
        )
        coefficient = self._coefficient(
            state.globals.get("military_telecom_coordination_coefficient", 0.15),
            0.15,
        )
        return 1.0 / (1.0 + telecom * coefficient)

    def _territory_multiplier(
        self,
        state: GameState,
        unit: dict[str, Any],
        target: dict[str, Any],
    ) -> float:
        owner = str(unit.get("owner") or "").strip().upper()
        target_owner = str(target.get("owner") or "").strip().upper()
        key = (
            "military_domestic_duration_multiplier"
            if not target_owner or target_owner == owner
            else "military_foreign_duration_multiplier"
        )
        return self._multiplier(state.globals.get(key), 1.0)

    def _coefficient(self, value: Any, default: float) -> float:
        return self._bounded(value, default, 0.0, 0.5)

    def _multiplier(self, value: Any, default: float) -> float:
        return self._bounded(value, default, 0.25, 4.0)

    def _bounded(self, value: Any, default: float, lower: float, upper: float) -> float:
        if value is None:
            return default
        return max(lower, min(upper, self._row_float_from_mapping(value, default)))

    def _bounded_duration(self, value: float) -> int:
        return int(max(360, min(10080, round(value))))

    def _row_float(self, row: dict[str, Any], key: str, fallback: Any = 0.0) -> float:
        value = row.get(key)
        if value is None:
            value = fallback
        try:
            return float(value if value is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _row_float_from_mapping(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return number if math.isfinite(number) else default
