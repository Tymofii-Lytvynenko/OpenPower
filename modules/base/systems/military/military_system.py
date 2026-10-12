from __future__ import annotations

import json
import math
from typing import Any, Callable, Iterable

import numpy as np
import polars as pl

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER
from src.shared.state import GameState
from src.shared.actions import (
    ActionAttackUnit,
    ActionBuildUnit,
    ActionBuyMarketUnit,
    ActionDispatchUnitDeployment,
    ActionMoveUnit,
)
from src.shared.actions import ActionSetUnitReadiness
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from modules.base.systems.military.capability_catalog import get_role_profile
from modules.base.systems.military.unit_catalog import MILITARY_UNIT_TYPES
from modules.base.systems.military.naval_invasion_policy import NavalInvasionPolicy
from modules.base.systems.military.readiness_system import ReadinessSystem
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from src.core.map.engagement_geometry import engagement_radius_km, first_zone_contact_fraction, interpolate_geo
from modules.base.systems.military.war_policy import hostile_country_pairs


UNIT_TABLE = "units"
NO_TARGET_REGION = -1
DEFAULT_UNIT_TYPE = "army"
DEFAULT_MOVE_MINUTES = 1440
UNIT_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "owner": pl.Utf8,
    "unit_type": pl.Utf8,
    "design_id": pl.Utf8,
    "unit_domain": pl.Utf8,
    "strength": pl.Int64,
    "equipment_quantity": pl.Int64,
    "current_region_id": pl.Int32,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
    "source_region_id": pl.Int32,
    "source_latitude": pl.Float64,
    "source_longitude": pl.Float64,
    "target_region_id": pl.Int32,
    "target_latitude": pl.Float64,
    "target_longitude": pl.Float64,
    "departed_at_minute": pl.Int64,
    "arrival_at_minute": pl.Int64,
    "movement_progress": pl.Float64,
    "is_moving": pl.Boolean,
    "engagement_mode": pl.Utf8,
    "readiness_status": pl.Utf8,
    "readiness_transition_id": pl.Utf8,
    "readiness_progress": pl.Float64,
    "readiness_eta_minute": pl.Int64,
    "training_level": pl.Utf8,
    "training_state": pl.Utf8,
    "training_progress": pl.Float64,
    "training_facility_id": pl.Utf8,
    "training_location_region_id": pl.Int32,
    "combat_posture": pl.Utf8,
    "combat_strength_modifier": pl.Float64,
    "war_exhaustion_modifier": pl.Float64,
    "combat_casualty_modifier": pl.Float64,
    "combat_defense_modifier": pl.Float64,
    "combat_attack_risk_modifier": pl.Float64,
    "combat_readiness_modifier": pl.Float64,
    "combat_holding_modifier": pl.Float64,
    "combat_counterattack_modifier": pl.Float64,
    "cohesion": pl.Float64,
    "reorganization_until_minute": pl.Int64,
    "production_order_id": pl.Utf8,
    "foreign_order_id": pl.Utf8,
    "original_cost": pl.Float64,
    "unit_lifecycle": pl.Utf8,
}

MOVEMENT_ROUTE_SCHEMA: dict[str, pl.DataType] = {
    "unit_id": pl.Utf8,
    "owner_country_id": pl.Utf8,
    "source_region_id": pl.Int32,
    "destination_region_id": pl.Int32,
    "route_region_ids": pl.List(pl.Int32),
    "route_index": pl.Int32,
    "destination_latitude": pl.Float64,
    "destination_longitude": pl.Float64,
    "has_custom_destination": pl.Boolean,
    "is_naval_invasion": pl.Boolean,
    "status": pl.Utf8,
    "rejection_reason": pl.Utf8,
    "updated_at_minute": pl.Int64,
}

UNIT_ORDER_FEEDBACK_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "unit_id": pl.Utf8,
    "owner_country_id": pl.Utf8,
    "order_type": pl.Utf8,
    "status": pl.Utf8,
    "reason": pl.Utf8,
    "created_at_minute": pl.Int64,
}


class MovementDurationPolicy:
    """Estimates direct movement duration from source and target geolocations."""

    def estimate_minutes(
        self,
        regions: pl.DataFrame,
        source_region_id: int,
        target_region_id: int,
    ) -> int:
        locations = self.region_locations(regions)
        source = locations.get(source_region_id)
        target = locations.get(target_region_id)

        if source is None or target is None:
            return DEFAULT_MOVE_MINUTES

        return self.estimate_between(source, target)

    def estimate_between(self, source: GeoCoordinate, target: GeoCoordinate) -> int:
        projection = EquirectangularProjection(360.0, 180.0)
        distance_km = projection.geo_distance_km(source, target)
        return self.estimate_from_distance(distance_km)

    def estimate_from_distance(self, distance_km: float) -> int:
        return int(max(360, min(10080, 360 + distance_km * 0.45)))

    def region_locations(self, regions: pl.DataFrame) -> dict[int, GeoCoordinate]:
        required = {"id"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        if {"latitude", "longitude"}.issubset(set(regions.columns)):
            return {
                int(row["id"]): GeoCoordinate(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
                for row in regions.select(["id", "latitude", "longitude"]).iter_rows(named=True)
                if row["id"] is not None
            }

        if {"center_x", "center_y"}.issubset(set(regions.columns)):
            projection = EquirectangularProjection(
                max(float(regions["center_x"].max() or 1.0) + 1.0, 1.0),
                max(float(regions["center_y"].max() or 1.0) + 1.0, 1.0),
            )
            return {
                int(row["id"]): projection.pixel_to_geo(
                    MapPixelCoordinate(float(row["center_x"]), float(row["center_y"]))
                )
                for row in regions.select(["id", "center_x", "center_y"]).iter_rows(named=True)
                if row["id"] is not None
            }

        return {}


class UnitFactory:
    """Creates normalized unit records without coupling callers to table details."""

    def create(
        self,
        unit_id: str,
        owner: str,
        unit_type: str,
        strength: int,
        region_id: int,
        geo: GeoCoordinate,
        current_minute: int,
        design_id: str = "",
        training_level: str = "Recruit",
        equipment_quantity: int | None = None,
    ) -> dict[str, Any]:
        safe_strength = max(1, int(strength))
        return {
            "id": unit_id,
            "owner": owner,
            "unit_type": unit_type or DEFAULT_UNIT_TYPE,
            "design_id": str(design_id or ""),
            "unit_domain": get_role_profile(unit_type or DEFAULT_UNIT_TYPE).domain,
            "strength": safe_strength,
            "equipment_quantity": max(
                0,
                int(safe_strength if equipment_quantity is None else equipment_quantity),
            ),
            "current_region_id": int(region_id),
            "latitude": float(geo.latitude),
            "longitude": float(geo.longitude),
            "source_region_id": int(region_id),
            "source_latitude": float(geo.latitude),
            "source_longitude": float(geo.longitude),
            "target_region_id": NO_TARGET_REGION,
            "target_latitude": float(geo.latitude),
            "target_longitude": float(geo.longitude),
            "departed_at_minute": int(current_minute),
            "arrival_at_minute": int(current_minute),
            "movement_progress": 0.0,
            "is_moving": False,
            "engagement_mode": "",
            "readiness_status": "parked",
            "readiness_transition_id": "",
            "readiness_progress": 0.0,
            "readiness_eta_minute": 0,
            "training_level": training_level,
            "training_state": "",
            "training_progress": 0.0,
            "training_facility_id": "",
            "training_location_region_id": 0,
            "combat_posture": "hold",
            "combat_strength_modifier": 1.0,
            "war_exhaustion_modifier": 1.0,
            "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0,
            "combat_attack_risk_modifier": 1.0,
            "combat_readiness_modifier": 1.0,
            "combat_holding_modifier": 1.0,
            "combat_counterattack_modifier": 1.0,
            "cohesion": 1.0,
            "reorganization_until_minute": 0,
            "production_order_id": "",
            "foreign_order_id": "",
            "original_cost": 0.0,
            "unit_lifecycle": "available",
        }


class MilitarySystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'region_adjacency', 'treaty_effects', 'units', 'production_orders', 'unit_designs', 'unit_capability_projections', 'countries_wars', 'unit_readiness_transitions', 'unit_pending_orders', 'unit_movement_routes', 'unit_deployment_orders', 'political_effects'}),
        writes=frozenset({'countries', 'units', 'production_orders', 'unit_market_listings', 'unit_pending_orders', 'unit_movement_routes', 'unit_order_feedback', 'unit_deployment_orders'}),
        handles=frozenset(
            {
                ActionAttackUnit,
                ActionBuildUnit,
                ActionBuyMarketUnit,
                ActionDispatchUnitDeployment,
                ActionMoveUnit,
                ActionSetUnitReadiness,
            }
        ),
        phase=SystemPhase.MILITARY,
    )
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_duration_policy": SYSTEM_STATE_HELPER,
        "_unit_factory": SYSTEM_STATE_HELPER,
        "_access_policy": SYSTEM_STATE_HELPER,
        "_route_planner": SYSTEM_STATE_HELPER,
        "_naval_invasion_policy": SYSTEM_STATE_HELPER,
        "_weapons_trade_policy": SYSTEM_STATE_HELPER,
        "_readiness_system": SYSTEM_STATE_HELPER,
        "_demilitarization_policy": SYSTEM_STATE_HELPER,
        "_manpower_cache_key": SYSTEM_STATE_CACHE,
        "_manpower_by_owner": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._missing_columns = set()
        self._duration_policy = MovementDurationPolicy()
        self._unit_factory = UnitFactory()
        self._access_policy = MovementAccessPolicy()
        self._route_planner = MilitaryRoutePlanner()
        self._naval_invasion_policy = NavalInvasionPolicy()
        self._weapons_trade_policy = WeaponsTradePolicy()
        self._readiness_system = ReadinessSystem()
        self._demilitarization_policy = DemilitarizationPolicy()
        self._manpower_cache_key: tuple[int, int, int] | None = None
        self._manpower_by_owner = pl.DataFrame(
            schema={"owner": pl.Utf8, "total_core_manpower": pl.Float64}
        )

    @property
    def id(self) -> str:
        return "base.military"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.population", "base.economy", "base.diplomacy", "base.military_programs"]

    def update(self, state: GameState, delta_time: float) -> None:
        units = self._ensure_units_table(state)
        capability_speed_by_unit = self._capability_speed_by_unit(state)
        self._preflight_contact_transition_interruptions(state, units)
        self._readiness_system.update(state, delta_time)
        units = self._ensure_units_table(state)
        units = self._process_completed_production_orders(state, units)
        units = self._process_build_actions(state, units)
        units = self._process_market_buy_actions(state, units)
        units, deployment_moves = self._process_deployment_actions(state, units)
        units = self._process_move_actions(state, units, deployment_moves, capability_speed_by_unit)
        units = self._process_attack_actions(state, units)
        units = self._update_unit_movements(state, units, state.time.total_minutes, capability_speed_by_unit)
        self._refresh_deployment_state(state, units)
        if not state.get_table(UNIT_TABLE).equals(units):
            state.update_table(UNIT_TABLE, units)

        from src.shared.events import EventNewDay
        has_new_day = any(isinstance(e, EventNewDay) for e in state.events)
        if has_new_day and not state.time.is_paused and state.time.day % 7 == 1:
            self._update_manpower(state)

    def _preflight_contact_transition_interruptions(self, state: GameState, units: pl.DataFrame) -> None:
        """Cancel transitions before due processing when contact is already knowable.

        Readiness and movement share one military phase. Looking one movement
        segment ahead preserves contact-before-completion precedence without
        making the readiness system depend on the movement implementation.
        """
        war_table = state.tables.get("countries_wars")
        war_rows = [] if war_table is None else war_table.to_dicts()
        hostile_pairs = hostile_country_pairs(war_rows)
        if not hostile_pairs or units.is_empty() or "owner" not in units.columns:
            return
        hostile_countries = sorted({country for pair in hostile_pairs for country in pair})
        unit_rows = units.filter(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().is_in(hostile_countries)
        ).to_dicts()
        if not unit_rows:
            return
        by_id = {str(row.get("id") or ""): row for row in unit_rows}
        contact_ids: set[str] = set()

        for action in state.current_actions:
            if not isinstance(action, ActionAttackUnit):
                continue
            attacker = by_id.get(str(action.attacker_unit_id or ""))
            defender = by_id.get(str(action.defender_unit_id or ""))
            if not self._valid_hostile_attack(attacker, defender, hostile_pairs, state):
                continue
            if self._unit_is_transitioning(state, str(attacker.get("id") or "")):
                continue
            if str(attacker.get("readiness_status") or "").strip().lower() == "parked":
                continue
            contact_ids.update({str(attacker.get("id") or ""), str(defender.get("id") or "")})

        ordered_rows = sorted(unit_rows, key=lambda row: str(row.get("id") or ""))
        owners_by_country: dict[str, list[dict[str, Any]]] = {}
        for row in ordered_rows:
            owner = str(row.get("owner") or "").strip().upper()
            if owner:
                owners_by_country.setdefault(owner, []).append(row)
        for row in ordered_rows:
            if str(row.get("engagement_mode") or "").lower() not in {"assault", "positional"}:
                continue
            owner = str(row.get("owner") or "").strip().upper()
            hostile_units = [
                candidate
                for enemy in sorted(owners_by_country)
                if frozenset((owner, enemy)) in hostile_pairs
                for candidate in owners_by_country[enemy]
                if int(candidate.get("strength") or 0) > 0
            ]
            if hostile_units:
                contact_ids.add(str(row.get("id") or ""))
                contact_ids.update(str(candidate.get("id") or "") for candidate in hostile_units)
        for row in ordered_rows:
            if not bool(row.get("is_moving")):
                continue
            owner = str(row.get("owner") or "").strip().upper()
            hostile_candidates = [
                candidate
                for enemy in sorted(owners_by_country)
                if frozenset((owner, enemy)) in hostile_pairs
                for candidate in owners_by_country[enemy]
            ]
            if not hostile_candidates:
                continue
            departed_value = row.get("departed_at_minute")
            arrival_value = row.get("arrival_at_minute")
            departed = int(departed_value if departed_value is not None else state.time.total_minutes)
            arrival = int(arrival_value if arrival_value is not None else state.time.total_minutes)
            duration = max(1, arrival - departed)
            previous_progress = max(0.0, min(1.0, float(row.get("movement_progress") or 0.0)))
            next_progress = max(
                0.0,
                min(1.0, (int(state.time.total_minutes) - departed) / duration),
            )
            start = self._interpolate_row_geo(row, previous_progress)
            end = self._interpolate_row_geo(row, next_progress)
            contact = self._first_hostile_contact(
                row,
                hostile_candidates,
                start,
                end,
                int(state.time.total_minutes),
            )
            if contact is not None:
                contact_ids.update({str(row.get("id") or ""), str(contact[0].get("id") or "")})

        for unit_id in sorted(contact_ids):
            self._readiness_system.cancel_transition_for_unit(state, unit_id, "combat_contact")

    def _valid_hostile_attack(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
        hostile_pairs: set[frozenset[str]],
        state: GameState,
    ) -> bool:
        if attacker is None or defender is None or attacker is defender:
            return False
        if int(attacker.get("strength") or 0) <= 0 or int(defender.get("strength") or 0) <= 0:
            return False
        attacker_owner = str(attacker.get("owner") or "").strip().upper()
        defender_owner = str(defender.get("owner") or "").strip().upper()
        return frozenset((attacker_owner, defender_owner)) in hostile_pairs

    def _interpolate_row_geo(self, row: dict[str, Any], progress: float) -> GeoCoordinate:
        source = GeoCoordinate(
            latitude=self._row_float(row, "source_latitude", row.get("latitude")),
            longitude=self._row_float(row, "source_longitude", row.get("longitude")),
        )
        target = GeoCoordinate(
            latitude=self._row_float(row, "target_latitude", row.get("latitude")),
            longitude=self._row_float(row, "target_longitude", row.get("longitude")),
        )
        return interpolate_geo(source, target, progress)

    def _row_float(self, row: dict[str, Any], key: str, fallback: Any = 0.0) -> float:
        value = row.get(key)
        if value is None:
            value = fallback
        try:
            return float(value if value is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _ensure_units_table(self, state: GameState) -> pl.DataFrame:
        if UNIT_TABLE not in state.tables or state.tables[UNIT_TABLE].is_empty():
            units = self._create_initial_units(state)
            state.update_table(UNIT_TABLE, units)
            return units

        return self._normalize_units_table(state.get_table(UNIT_TABLE), state)

    def _create_initial_units(self, state: GameState) -> pl.DataFrame:
        if "regions" not in state.tables or "countries" not in state.tables:
            return self._empty_units()

        regions = state.get_table("regions")
        countries = state.get_table("countries")
        if regions.is_empty() or countries.is_empty() or "id" not in countries.columns:
            return self._empty_units()

        home_regions = self._home_regions_by_country(regions)
        region_locations = self._duration_policy.region_locations(regions)
        country_strengths = self._country_strengths(countries)
        country_units = self._country_initial_unit_types(countries, country_strengths)
        current_minute = state.time.total_minutes
        rows = []

        for country_tag in countries["id"].to_list():
            clean_tag = str(country_tag)
            if clean_tag not in home_regions:
                continue

            home_region_id = home_regions[clean_tag]
            home_geo = region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0))
            for unit_type, strength, quantity in country_units.get(clean_tag, ()):
                if strength <= 0:
                    continue
                rows.append(
                    self._unit_factory.create(
                        unit_id=f"{clean_tag}-{unit_type}-001",
                        owner=clean_tag,
                        unit_type=unit_type,
                        strength=strength,
                        region_id=home_region_id,
                        geo=home_geo,
                        current_minute=current_minute,
                        design_id=f"{clean_tag}-{unit_type}-2001",
                        equipment_quantity=quantity,
                    )
                )

        return self._units_from_rows(rows)

    def _home_regions_by_country(self, regions: pl.DataFrame) -> dict[str, int]:
        required = {"id", "owner"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        score_columns = [col for col in ("pop_15_64", "area_km2") if col in regions.columns]
        selected: dict[str, tuple[int, float]] = {}

        for row in regions.iter_rows(named=True):
            owner = row.get("owner")
            region_id = row.get("id")
            if not owner or owner == "None" or region_id is None:
                continue

            score = 0.0
            for column in score_columns:
                value = row.get(column)
                if value is not None:
                    score += float(value)

            owner_key = str(owner)
            current = selected.get(owner_key)
            if current is None or score > current[1]:
                selected[owner_key] = (int(region_id), score)

        return {owner: region_id for owner, (region_id, _) in selected.items()}

    def _country_strengths(self, countries: pl.DataFrame) -> dict[str, int]:
        if "military_count" not in countries.columns:
            return {}

        return {
            str(row["id"]): max(0, int(row["military_count"] or 0))
            for row in countries.select(["id", "military_count"]).iter_rows(named=True)
            if row["id"] is not None
        }

    def _country_initial_unit_types(
        self,
        countries: pl.DataFrame,
        country_strengths: dict[str, int],
    ) -> dict[str, tuple[tuple[str, int, int], ...]]:
        unit_columns = {unit_type.quantity_column for unit_type in MILITARY_UNIT_TYPES}
        has_unit_data = unit_columns.issubset(countries.columns)
        result: dict[str, tuple[tuple[str, int, int], ...]] = {}

        for row in countries.iter_rows(named=True):
            country_id = row.get("id")
            if country_id is None:
                continue
            tag = str(country_id)
            if has_unit_data:
                total_personnel = country_strengths.get(tag, 0)
                quantities = {
                    unit_type.role: max(0, int(row.get(unit_type.quantity_column) or 0))
                    for unit_type in MILITARY_UNIT_TYPES
                }
                if total_personnel > 0 and sum(quantities.values()) > 0:
                    equipment_roles = [
                        unit_type
                        for unit_type in MILITARY_UNIT_TYPES
                        if unit_type.role not in {"infantry", "strategic_missiles"}
                        and quantities[unit_type.role] > 0
                        and unit_type.crew_factor > 0
                    ]
                    raw_staff = {
                        unit_type.role: quantities[unit_type.role] * unit_type.crew_factor
                        for unit_type in equipment_roles
                    }
                    raw_total = sum(raw_staff.values())
                    support_limit = int(round(total_personnel * 0.40))
                    support_personnel = min(support_limit, int(round(raw_total)))
                    if equipment_roles and total_personnel >= len(equipment_roles):
                        support_personnel = max(
                            support_personnel,
                            min(support_limit, len(equipment_roles)),
                        )

                    staff_by_role = {unit_type.role: 0 for unit_type in equipment_roles}
                    if raw_total > 0 and support_personnel > 0:
                        exact_shares = {
                            role: (weight / raw_total) * support_personnel
                            for role, weight in raw_staff.items()
                        }
                        staff_by_role = {
                            role: int(value)
                            for role, value in exact_shares.items()
                        }
                        remainder = support_personnel - sum(staff_by_role.values())
                        remainder_roles = sorted(
                            exact_shares,
                            key=lambda role: (
                                exact_shares[role] - staff_by_role[role],
                                -next(index for index, item in enumerate(MILITARY_UNIT_TYPES) if item.role == role),
                            ),
                            reverse=True,
                        )
                        for role in remainder_roles[:remainder]:
                            staff_by_role[role] += 1

                    infantry_personnel = max(0, total_personnel - sum(staff_by_role.values()))
                    unit_types = []
                    for unit_type in MILITARY_UNIT_TYPES:
                        role = unit_type.role
                        if role == "strategic_missiles":
                            continue
                        quantity = quantities[role]
                        strength = infantry_personnel if role == "infantry" else staff_by_role.get(role, 0)
                        if strength > 0 and (quantity > 0 or role == "infantry"):
                            unit_types.append((role, strength, quantity))
                    if unit_types:
                        result[tag] = tuple(unit_types)
                        continue

            fallback_strength = country_strengths.get(tag, 0)
            result[tag] = (("infantry", fallback_strength, fallback_strength),) if fallback_strength > 0 else ()

        return result

    def _process_completed_production_orders(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        required_tables = {"countries", "regions", "unit_designs", "production_orders"}
        if not required_tables.issubset(state.tables):
            return units

        orders_table = state.get_table("production_orders")
        if orders_table.is_empty():
            return units
        countries = self._ensure_country_columns(state.get_table("countries"))
        regions = state.get_table("regions")
        home_regions = self._home_regions_by_country(regions)
        region_locations = self._duration_policy.region_locations(regions)
        country_rows = countries.to_dicts()
        countries_by_tag = {str(row.get("id") or "").strip().upper(): row for row in country_rows}
        designs_by_id = {
            str(row.get("id") or ""): row
            for row in state.get_table("unit_designs").to_dicts()
        }
        order_rows = orders_table.to_dicts()
        unit_rows = units.to_dicts()
        deployment_table = state.tables.get("unit_deployment_orders")
        deployment_rows = [] if deployment_table is None else deployment_table.to_dicts()
        changed = False

        for order in order_rows:
            if str(order.get("status") or "").lower() not in {
                "completed",
                "held_by_demilitarization",
            }:
                continue
            country_tag = str(order.get("country_id") or "").strip().upper()
            country = countries_by_tag.get(country_tag)
            design = designs_by_id.get(str(order.get("design_id") or ""))
            quantity = max(0, int(order.get("quantity") or 0))
            if country is None or design is None or quantity <= 0:
                continue
            if str(design.get("country_id") or "").strip().upper() != country_tag:
                continue
            if not self._demilitarization_policy.can_add(
                state,
                country_tag,
                quantity,
                unit_rows=unit_rows,
            ):
                order["status"] = "held_by_demilitarization"
                order["blocking_reason"] = (
                    "Production is complete but delivery exceeds an active demilitarization limit."
                )
                changed = True
                continue
            home_region_id = home_regions.get(str(country.get("id") or ""))
            if home_region_id is None:
                continue

            unit_type = str(design.get("class_name") or DEFAULT_UNIT_TYPE).strip().lower().replace(" ", "_")
            unit_type = unit_type or DEFAULT_UNIT_TYPE
            owner = str(country.get("id") or country_tag)
            origin_geo = region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0))
            unit_id = self._next_unit_id(unit_rows, owner, unit_type)
            unit = self._unit_factory.create(
                unit_id=unit_id,
                owner=owner,
                unit_type=unit_type,
                strength=quantity,
                region_id=0,
                geo=GeoCoordinate(0.0, 0.0),
                current_minute=state.time.total_minutes,
                design_id=str(order.get("design_id") or ""),
                training_level=str(order.get("requested_training_level") or "Recruit"),
            )
            unit.update(
                source_region_id=home_region_id,
                source_latitude=origin_geo.latitude,
                source_longitude=origin_geo.longitude,
                production_order_id=str(order.get("id") or ""),
                original_cost=max(0.0, self._row_float(order, "unit_cost")) * quantity,
                unit_lifecycle="deployment_queued",
            )
            unit_rows.append(unit)
            deployment_rows.append({
                "id": self._next_deployment_id(str(order.get("id") or ""), deployment_rows),
                "unit_id": unit_id,
                "country_id": owner,
                "production_order_id": str(order.get("id") or ""),
                "quantity": quantity,
                "source_region_id": home_region_id,
                "destination_region_id": 0,
                "route_region_ids": [],
                "route_index": 0,
                "status": "queued",
                "created_at_minute": int(state.time.total_minutes),
                "estimated_arrival_at_minute": 0,
                "blocking_reason": "Select a valid deployment region and dispatch this group.",
            })
            country["military_count"] = int(country.get("military_count") or 0) + quantity
            order["status"] = "awaiting_deployment"
            order["blocking_reason"] = "Completed; waiting for deployment and route arrival."
            order["eta_days"] = 0
            changed = True

        if not changed:
            return units
        state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        state.update_table("production_orders", pl.DataFrame(order_rows, schema=orders_table.schema))
        if deployment_table is not None:
            state.update_table(
                "unit_deployment_orders",
                pl.DataFrame(deployment_rows, schema=deployment_table.schema),
            )
        return self._units_from_rows(unit_rows)

    def _process_deployment_actions(self, state: GameState, units: pl.DataFrame):
        actions = [action for action in state.current_actions if isinstance(action, ActionDispatchUnitDeployment)]
        deployment_table = state.tables.get("unit_deployment_orders")
        if not actions or units.is_empty() or deployment_table is None:
            return units, []

        rows = units.to_dicts()
        deployments = deployment_table.to_dicts()
        units_by_id = {str(row.get("id") or ""): row for row in rows}
        deployments_by_unit = {str(row.get("unit_id") or ""): row for row in deployments}
        moves: list[ActionMoveUnit] = []
        seen: set[str] = set()
        feedback_table = state.tables.get("unit_order_feedback")
        feedback = [] if feedback_table is None else feedback_table.to_dicts()
        now = int(state.time.total_minutes)

        for action in actions:
            unit_id = str(action.unit_id or "")
            unit = units_by_id.get(unit_id)
            deployment = deployments_by_unit.get(unit_id)
            if unit is None or deployment is None:
                self._record_unit_order_feedback(feedback, unit_id, "", "deployment", "rejected", "No deployment-queued group matches this unit.", now)
                continue
            owner = str(unit.get("owner") or "").strip().upper()
            if unit_id in seen:
                self._record_unit_order_feedback(feedback, unit_id, owner, "deployment", "rejected", "A unit group can receive only one deployment order per update.", now)
                continue
            seen.add(unit_id)
            if not self._deployment_actor_authorized(state, str(action.player_id or ""), owner):
                self._record_unit_order_feedback(feedback, unit_id, owner, "deployment", "rejected", "The issuer does not control this deployment group.", now)
                continue
            if str(unit.get("unit_lifecycle") or "") not in {"deployment_queued", "deployment_blocked"}:
                self._record_unit_order_feedback(feedback, unit_id, owner, "deployment", "rejected", "The unit is not waiting for deployment or route recovery.", now)
                continue
            target_id = int(action.destination_region_id or 0)
            regions = state.tables.get("regions")
            if target_id <= 0 or regions is None or regions.filter(pl.col("id") == target_id).is_empty():
                self._record_unit_order_feedback(feedback, unit_id, owner, "deployment", "rejected", "The deployment destination is invalid.", now)
                continue
            available = max(0, int(unit.get("strength") or 0))
            requested = available if int(action.quantity or 0) <= 0 else int(action.quantity)
            if requested <= 0 or requested > available:
                self._record_unit_order_feedback(feedback, unit_id, owner, "deployment", "rejected", "The deployment quantity must be between one and the available group strength.", now)
                continue

            dispatched_id = unit_id
            if requested < available:
                available_equipment = max(0, int(unit.get("equipment_quantity") or 0))
                dispatched_equipment = min(
                    available_equipment,
                    int(round(available_equipment * requested / available)),
                )
                unit["strength"] = available - requested
                unit["equipment_quantity"] = available_equipment - dispatched_equipment
                deployment["quantity"] = available - requested
                clone = dict(unit)
                dispatched_id = self._next_unit_id(rows, owner, str(unit.get("unit_type") or DEFAULT_UNIT_TYPE))
                clone.update(
                    id=dispatched_id,
                    strength=requested,
                    equipment_quantity=dispatched_equipment,
                    unit_lifecycle="deployment_queued",
                )
                rows.append(clone)
                units_by_id[dispatched_id] = clone
                deployment = dict(deployment)
                deployment.update(
                    id=self._next_deployment_id(str(deployment.get("production_order_id") or ""), deployments),
                    unit_id=dispatched_id,
                    quantity=requested,
                    destination_region_id=0,
                    route_region_ids=[],
                    route_index=0,
                    status="queued",
                    estimated_arrival_at_minute=0,
                    blocking_reason="Select a valid deployment region and dispatch this group.",
                )
                deployments.append(deployment)
                deployments_by_unit[dispatched_id] = deployment
            deployment["destination_region_id"] = target_id
            deployment["status"] = "dispatching"
            deployment["blocking_reason"] = ""
            moves.append(ActionMoveUnit(str(action.player_id or owner), dispatched_id, target_id))

        if deployments != deployment_table.to_dicts():
            state.update_table("unit_deployment_orders", pl.DataFrame(deployments, schema=deployment_table.schema))
        self._write_unit_order_feedback(state, feedback)
        return self._units_from_rows(rows), moves

    def _refresh_deployment_state(self, state: GameState, units: pl.DataFrame) -> None:
        deployments_table = state.tables.get("unit_deployment_orders")
        if deployments_table is None or deployments_table.is_empty():
            return
        units_by_id = {str(row.get("id") or ""): row for row in units.to_dicts()}
        routes_table = state.tables.get("unit_movement_routes")
        routes = {} if routes_table is None else {
            str(row.get("unit_id") or ""): row for row in routes_table.to_dicts()
        }
        deployments = deployments_table.to_dicts()
        for deployment in deployments:
            unit_id = str(deployment.get("unit_id") or "")
            unit = units_by_id.get(unit_id)
            route = routes.get(unit_id)
            if unit is None:
                deployment.update(status="blocked", blocking_reason="The deployed group no longer exists.")
                continue
            lifecycle = str(unit.get("unit_lifecycle") or "")
            if route is not None:
                deployment["route_region_ids"] = list(route.get("route_region_ids") or [])
                deployment["route_index"] = max(0, int(route.get("route_index") or 0))
                deployment["destination_region_id"] = max(0, int(route.get("destination_region_id") or 0))
                deployment["estimated_arrival_at_minute"] = max(0, int(unit.get("arrival_at_minute") or 0))
            if lifecycle == "available":
                deployment.update(status="delivered", blocking_reason="")
            elif lifecycle in {"deployment_transit", "in_transit"}:
                deployment.update(status="in_transit", blocking_reason="")
            elif lifecycle in {"deployment_blocked", "route_blocked"}:
                deployment.update(
                    status="blocked",
                    blocking_reason=str((route or {}).get("rejection_reason") or "The deployment route needs a new order."),
                )
            elif lifecycle == "deployment_queued":
                deployment.update(status="queued", blocking_reason="Select a valid deployment region and dispatch this group.")
        frame = pl.DataFrame(deployments, schema=deployments_table.schema)
        if not frame.equals(deployments_table):
            state.update_table("unit_deployment_orders", frame)

        production_table = state.tables.get("production_orders")
        if production_table is None or production_table.is_empty():
            return
        production_rows = production_table.to_dicts()
        by_order: dict[str, list[dict[str, Any]]] = {}
        for deployment in deployments:
            by_order.setdefault(str(deployment.get("production_order_id") or ""), []).append(deployment)
        changed = False
        for order in production_rows:
            if str(order.get("status") or "") != "awaiting_deployment":
                continue
            related = by_order.get(str(order.get("id") or ""), [])
            if related and all(str(item.get("status") or "") == "delivered" for item in related):
                order["status"] = "delivered"
                order["blocking_reason"] = "All produced groups arrived at their assigned deployment regions."
                changed = True
        if changed:
            state.update_table("production_orders", pl.DataFrame(production_rows, schema=production_table.schema))

    def _deployment_actor_authorized(self, state, actor: str, owner: str) -> bool:
        return player_controls_country(state, actor, owner)

    def _next_deployment_id(self, production_order_id: str, deployments: list[dict[str, Any]]) -> str:
        existing = {str(row.get("id") or "") for row in deployments}
        index = 1
        identifier = f"deployment-{production_order_id}-{index:03d}"
        while identifier in existing:
            index += 1
            identifier = f"deployment-{production_order_id}-{index:03d}"
        return identifier

    def _process_build_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions_to_process = [a for a in state.current_actions if isinstance(a, ActionBuildUnit)]
        if not actions_to_process:
            return units

        countries = self._ensure_country_columns(state.get_table("countries"))
        regions = state.get_table("regions")
        home_regions = self._home_regions_by_country(regions)
        region_locations = self._duration_policy.region_locations(regions)
        rows = units.to_dicts()
        feedback_rows = []
        feedback_table = state.tables.get("unit_order_feedback")
        if feedback_table is not None:
            feedback_rows = feedback_table.to_dicts()
        feedback_changed = False

        for action in actions_to_process:
            country_tag = str(action.country_tag or "").strip().upper()
            if action.count <= 0:
                feedback_changed = True
                self._record_unit_order_feedback(
                    feedback_rows,
                    "",
                    country_tag,
                    "build",
                    "rejected",
                    "Recruitment quantity must be positive.",
                    state.time.total_minutes,
                )
                continue

            if not self._demilitarization_policy.can_add(
                state,
                country_tag,
                action.count,
                unit_rows=rows,
            ):
                feedback_changed = True
                self._record_unit_order_feedback(
                    feedback_rows,
                    "",
                    country_tag,
                    "build",
                    "rejected",
                    "The order would exceed an active demilitarization limit.",
                    state.time.total_minutes,
                )
                continue

            home_region_id = home_regions.get(country_tag)
            if home_region_id is None:
                feedback_changed = True
                # Reject before charging so an impossible recruit cannot mutate the treasury or force totals.
                self._record_unit_order_feedback(
                    feedback_rows,
                    "",
                    country_tag,
                    "build",
                    "rejected",
                    "No home region is available for recruitment.",
                    state.time.total_minutes,
                )
                continue

            cost = 1_000_000 * action.count
            countries = countries.with_columns(
                pl.when(pl.col("id") == country_tag)
                .then(pl.col("military_count") + action.count)
                .otherwise(pl.col("military_count"))
                .alias("military_count"),
                pl.when(pl.col("id") == country_tag)
                .then(pl.col("money_reserves") - cost)
                .otherwise(pl.col("money_reserves"))
                .alias("money_reserves"),
            )

            home_geo = region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0))

            rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(rows, country_tag, action.unit_type),
                    owner=country_tag,
                    unit_type=action.unit_type,
                    strength=action.count,
                    region_id=home_region_id,
                    geo=home_geo,
                    current_minute=state.time.total_minutes,
                )
            )

        state.update_table("countries", countries)
        if feedback_changed:
            self._write_unit_order_feedback(state, feedback_rows)
        return self._units_from_rows(rows)

    def _process_market_buy_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions = [action for action in state.current_actions if isinstance(action, ActionBuyMarketUnit)]
        required_tables = {"countries", "regions", "unit_market_listings"}
        if not actions or not required_tables.issubset(state.tables):
            return units

        listings_table = state.get_table("unit_market_listings")
        if listings_table.is_empty():
            return units
        countries = self._ensure_country_columns(state.get_table("countries"))
        regions = state.get_table("regions")
        home_regions = self._home_regions_by_country(regions)
        region_locations = self._duration_policy.region_locations(regions)
        region_rows = regions.to_dicts()
        adjacency = state.tables.get("region_adjacency")
        adjacency_rows = [] if adjacency is None else adjacency.to_dicts()
        movement_table = state.tables.get("unit_movement_routes")
        movement_rows = [] if movement_table is None else movement_table.to_dicts()
        movement_by_unit = {str(item.get("unit_id") or ""): item for item in movement_rows}
        listing_rows = listings_table.to_dicts()
        listings_by_id = {str(row.get("id") or ""): row for row in listing_rows}
        country_rows = countries.to_dicts()
        countries_by_tag = {str(row.get("id") or "").strip().upper(): row for row in country_rows}
        design_rows = state.tables.get("unit_designs")
        designs_by_id = {} if design_rows is None else {
            str(row.get("id") or ""): row
            for row in design_rows.to_dicts()
        }
        unit_rows = units.to_dicts()
        changed = False

        for action in actions:
            listing = listings_by_id.get(str(action.listing_id))
            buyer_tag = str(action.buyer_country_tag or "").strip().upper()
            seller_tag = str(listing.get("seller_country_id") or "").strip().upper() if listing else ""
            buyer, seller = countries_by_tag.get(buyer_tag), countries_by_tag.get(seller_tag)
            if not self._market_actor_authorized(state, str(action.player_id or ""), buyer_tag):
                state.journal.append_command_result({
                    "tick": int(state.globals.get("tick", 0)),
                    "player_id": str(action.player_id or ""),
                    "action_type": type(action).__name__,
                    "status": "rejected",
                    "reason": "The issuer does not control the purchasing country.",
                })
                continue
            if listing is None or buyer is None or seller is None or str(listing.get("status") or "listed").lower() != "listed":
                continue
            quantity = max(0, min(int(action.quantity), int(listing.get("quantity") or 0)))
            if not self._demilitarization_policy.can_add(
                state,
                buyer_tag,
                quantity,
                unit_rows=unit_rows,
            ):
                continue
            price = max(0.0, float(listing.get("price") or 0.0))
            if quantity <= 0 or not self._weapons_trade_policy.can_order(
                state.tables.get("treaty_effects"), buyer_tag, seller_tag, str(listing.get("eligibility") or "open"),
            ):
                continue
            total_cost = price * quantity
            if float(buyer.get("money_reserves") or 0.0) < total_cost:
                continue
            home_region_id = home_regions.get(str(buyer.get("id") or ""))
            if home_region_id is None:
                continue
            used_unit_id = str(listing.get("unit_id") or "")
            if used_unit_id:
                source_unit = next((row for row in unit_rows if str(row.get("id") or "") == used_unit_id and str(row.get("owner") or "").strip().upper() == seller_tag and not bool(row.get("is_moving"))), None)
                if source_unit is None or quantity > int(source_unit.get("strength") or 0):
                    continue
                source_region_id = int(source_unit.get("current_region_id") or 0)
                access_context = self._access_policy.for_country(state, buyer_tag)
                route_plan = self._route_planner.plan(
                    source_region_id,
                    int(home_region_id),
                    region_rows,
                    adjacency_rows,
                    lambda region, final: (
                        access_context.can_station(region)
                        if final else (
                            str(region.get("owner") or "").strip().upper() in {buyer_tag, seller_tag}
                            or access_context.can_transit(region)
                        )
                    ),
                    segment_cost=lambda left, right: self._route_segment_minutes(left, right, region_locations),
                )
                if not route_plan.is_valid:
                    continue
                first_region_id = route_plan.region_ids[1] if len(route_plan.region_ids) > 1 else 0
                first_geo = region_locations.get(first_region_id) if first_region_id else None
                if len(route_plan.region_ids) > 1 and first_geo is None:
                    continue
                total_cost = price * quantity
                if float(buyer.get("money_reserves") or 0.0) < total_cost:
                    continue
                buyer["money_reserves"] = float(buyer.get("money_reserves") or 0.0) - total_cost
                buyer["military_count"] = int(buyer.get("military_count") or 0) + quantity
                seller["money_reserves"] = float(seller.get("money_reserves") or 0.0) + total_cost
                seller["military_count"] = max(0, int(seller.get("military_count") or 0) - quantity)
                if quantity < int(source_unit.get("strength") or 0):
                    source_strength = max(1, int(source_unit.get("strength") or 0))
                    source_equipment = max(0, int(source_unit.get("equipment_quantity") or 0))
                    travel_equipment = min(
                        source_equipment,
                        int(round(source_equipment * quantity / source_strength)),
                    )
                    source_unit["strength"] = source_strength - quantity
                    source_unit["equipment_quantity"] = source_equipment - travel_equipment
                    travel_unit = dict(source_unit)
                    travel_unit["id"] = self._next_unit_id(unit_rows, buyer_tag, str(source_unit.get("unit_type") or DEFAULT_UNIT_TYPE))
                    travel_unit["strength"] = quantity
                    travel_unit["equipment_quantity"] = travel_equipment
                    unit_rows.append(travel_unit)
                else:
                    travel_unit = source_unit
                source_geo = GeoCoordinate(float(travel_unit.get("latitude") or 0.0), float(travel_unit.get("longitude") or 0.0))
                target_geo = region_locations.get(int(home_region_id), GeoCoordinate(0.0, 0.0))
                travel_unit.update(
                    owner=str(buyer.get("id") or buyer_tag),
                    foreign_order_id=f"market:{listing['id']}",
                    original_cost=self._row_float(listing, "original_cost"),
                    current_region_id=source_region_id,
                    unit_lifecycle="in_transit" if len(route_plan.region_ids) > 1 else "available",
                )
                listing["quantity"] = int(listing.get("quantity") or 0) - quantity
                if len(route_plan.region_ids) > 1:
                    travel_unit.update(
                        current_region_id=0,
                        source_region_id=source_region_id,
                        source_latitude=source_geo.latitude,
                        source_longitude=source_geo.longitude,
                        target_region_id=first_region_id,
                        target_latitude=first_geo.latitude,
                        target_longitude=first_geo.longitude,
                        departed_at_minute=int(state.time.total_minutes),
                        arrival_at_minute=int(state.time.total_minutes) + self._duration_policy.estimate_between(source_geo, first_geo),
                        movement_progress=0.0,
                        is_moving=True,
                        engagement_mode="",
                    )
                    movement_by_unit[str(travel_unit.get("id"))] = {
                        "unit_id": str(travel_unit.get("id")), "owner_country_id": buyer_tag,
                        "source_region_id": source_region_id, "destination_region_id": int(home_region_id),
                        "route_region_ids": list(route_plan.region_ids), "route_index": 1,
                        "destination_latitude": target_geo.latitude, "destination_longitude": target_geo.longitude,
                        "has_custom_destination": False, "is_naval_invasion": False,
                        "status": "in_transit", "rejection_reason": "", "updated_at_minute": int(state.time.total_minutes),
                    }
                changed = True
                continue

            buyer["money_reserves"] = float(buyer.get("money_reserves") or 0.0) - total_cost
            buyer["military_count"] = int(buyer.get("military_count") or 0) + quantity
            seller["money_reserves"] = float(seller.get("money_reserves") or 0.0) + total_cost
            listing["quantity"] = int(listing.get("quantity") or 0) - quantity
            design = designs_by_id.get(str(listing.get("design_id") or ""), {})
            unit_type = str(design.get("class_name") or DEFAULT_UNIT_TYPE).strip().lower().replace(" ", "_") or DEFAULT_UNIT_TYPE
            unit_rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(unit_rows, str(buyer.get("id") or buyer_tag), unit_type),
                    owner=str(buyer.get("id") or buyer_tag),
                    unit_type=unit_type,
                    strength=quantity,
                    region_id=home_region_id,
                    geo=region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0)),
                    current_minute=state.time.total_minutes,
                    design_id=str(listing.get("design_id") or ""),
                )
            )
            changed = True

        if not changed:
            return units
        state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        remaining_listings = [row for row in listing_rows if int(row.get("quantity") or 0) > 0]
        state.update_table("unit_market_listings", pl.DataFrame(remaining_listings, schema=listings_table.schema))
        if movement_table is not None:
            movement_frame = pl.DataFrame(list(movement_by_unit.values(),), schema=MOVEMENT_ROUTE_SCHEMA) if movement_by_unit else pl.DataFrame(schema=MOVEMENT_ROUTE_SCHEMA)
            state.update_table("unit_movement_routes", movement_frame)
        return self._units_from_rows(unit_rows)

    def _market_actor_authorized(self, state: GameState, player_id: str, buyer_country: str) -> bool:
        return player_controls_country(state, player_id, buyer_country)

    def _process_attack_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions = [action for action in state.current_actions if isinstance(action, ActionAttackUnit)]
        if not actions or units.is_empty():
            return units

        war_rows = state.tables.get("countries_wars")
        wars = [] if war_rows is None else war_rows.to_dicts()
        hostile_pairs = hostile_country_pairs(wars)
        rows = units.to_dicts()
        units_by_id = {str(row.get("id") or ""): row for row in rows}
        now = int(state.time.total_minutes)
        changed = False

        for action in actions:
            attacker = units_by_id.get(str(action.attacker_unit_id or ""))
            defender = units_by_id.get(str(action.defender_unit_id or ""))
            if attacker is None:
                continue
            if defender is None or attacker is defender:
                continue
            if int(attacker.get("strength") or 0) <= 0 or int(defender.get("strength") or 0) <= 0:
                continue
            attacker_owner = str(attacker.get("owner") or "").strip().upper()
            defender_owner = str(defender.get("owner") or "").strip().upper()
            if frozenset((attacker_owner, defender_owner)) not in hostile_pairs:
                continue

            attacker_id = str(attacker.get("id") or "")
            released_fortification = self._release_fortified_for_order(state, attacker)
            can_execute = released_fortification or self._readiness_system.prepare_order(state, attacker_id)
            if not can_execute:
                self._queue_pending_attack(state, action)
                continue
            attacker["readiness_status"] = "ready"
            attacker["readiness_progress"] = 0.0
            attacker["readiness_transition_id"] = ""
            attacker["readiness_eta_minute"] = 0

            defender_geo = self._unit_geo_at(defender, now)
            self._stop_unit_at(attacker, defender_geo, now)
            self._stop_unit_at(defender, defender_geo, now)
            attacker["current_region_id"] = int(defender.get("current_region_id") or 0)
            attacker["engagement_mode"] = "assault"
            defender["engagement_mode"] = "assault"
            changed = True

        return self._units_from_rows(rows) if changed else units

    def _process_move_actions(
        self,
        state: GameState,
        units: pl.DataFrame,
        additional_actions: Iterable[ActionMoveUnit] = (),
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> pl.DataFrame:
        move_actions = [a for a in state.current_actions if isinstance(a, ActionMoveUnit)]
        move_actions.extend(additional_actions)
        if not move_actions or units.is_empty() or "regions" not in state.tables:
            return units

        action_by_unit = {
            action.unit_id: action
            for action in move_actions
        }
        if not action_by_unit:
            return units

        rows = []
        now = int(state.time.total_minutes)
        regions = state.get_table("regions")
        region_locations = self._duration_policy.region_locations(regions)
        adjacency = state.tables.get("region_adjacency")
        prepared_graph = self._route_planner.prepare(regions, adjacency)
        region_by_id = prepared_graph.region_by_id
        route_table = state.tables.get("unit_movement_routes")
        route_rows = [] if route_table is None else route_table.to_dicts()
        route_by_unit = {str(item.get("unit_id") or ""): item for item in route_rows}
        feedback_table = state.tables.get("unit_order_feedback")
        feedback_rows = [] if feedback_table is None else feedback_table.to_dicts()
        has_domain_metadata = self._has_domain_route_metadata(region_by_id.values())

        for row in units.to_dicts():
            action = action_by_unit.get(str(row["id"]))
            if action is None:
                rows.append(row)
                continue
            unit_id = str(row.get("id") or "")
            owner = str(row.get("owner") or "").strip().upper()
            deployment_dispatch = str(row.get("unit_lifecycle") or "") in {"deployment_queued", "deployment_blocked"}
            # Deployment transit is logistics, not a combat posture change; parked units retain
            # their readiness until they arrive and receive a normal player order.
            released_fortification = False
            source_region_id = int(row.get("source_region_id") or 0) if deployment_dispatch else int(row["current_region_id"])
            target_region_id = int(action.target_region_id)
            if target_region_id not in region_by_id:
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "rejected", "The destination region is invalid.", now)
                rows.append(row)
                continue
            source_geo = GeoCoordinate(
                latitude=self._row_float(row, "source_latitude", row.get("latitude")) if deployment_dispatch else float(row["latitude"]),
                longitude=self._row_float(row, "source_longitude", row.get("longitude")) if deployment_dispatch else float(row["longitude"]),
            )
            target_geo = self._resolve_action_target_geo(action, target_region_id, region_locations)
            if target_geo is None:
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "rejected", "The destination has no valid geographic location.", now)
                rows.append(row)
                continue

            if action.is_naval_invasion:
                valid_landing, landing_reason = self._naval_invasion_policy.validate(
                    state, row, region_by_id[target_region_id], units.to_dicts(),
                    (source_geo.latitude, source_geo.longitude),
                )
                if not valid_landing:
                    self._record_unit_order_feedback(feedback_rows, unit_id, owner, "naval_invasion", "rejected", landing_reason, now)
                    rows.append(row)
                    continue

            unit_domain = self._domain_for_unit(row)
            access_context = self._access_policy.for_country(state, owner)
            segment_duration = self._route_segment_cost_for_unit(
                region_locations,
                row,
                state,
                (capability_speed_by_unit or {}).get(unit_id, 1.0),
                prepared_graph.edge_distance_km,
            )
            blocked_domains: list[int] = []

            def can_enter(region: dict[str, Any], final: bool) -> bool:
                domain_allowed, domain_reason = self._domain_route_compatible(
                    unit_domain, region, final, action.is_naval_invasion,
                    region_by_id.values(), metadata_available=has_domain_metadata,
                )
                if not domain_allowed:
                    blocked_domains.append(int(region.get("id") or 0))
                    return False
                return access_context.can_station(region) if final else access_context.can_transit(region)

            route_plan = self._route_planner.plan(
                source_region_id,
                target_region_id,
                region_by_id.values(),
                adjacency,
                can_enter,
                segment_cost=segment_duration,
                explicit_waypoints=action.via_region_ids if action.via_region_ids else None,
                prepared_graph=prepared_graph,
            )
            if not route_plan.is_valid:
                reason = route_plan.rejection_reason
                if blocked_domains:
                    reason = f"The route contains a region incompatible with the {unit_domain} domain (region {min(blocked_domains)})."
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "rejected", reason, now)
                rows.append(row)
                continue
            if len(route_plan.region_ids) < 2 and deployment_dispatch:
                row.update(
                    current_region_id=target_region_id,
                    latitude=target_geo.latitude,
                    longitude=target_geo.longitude,
                    source_region_id=target_region_id,
                    source_latitude=target_geo.latitude,
                    source_longitude=target_geo.longitude,
                    target_region_id=NO_TARGET_REGION,
                    target_latitude=target_geo.latitude,
                    target_longitude=target_geo.longitude,
                    unit_lifecycle="available",
                    is_moving=False,
                    movement_progress=0.0,
                )
                route_by_unit[unit_id] = {
                    "unit_id": unit_id,
                    "owner_country_id": owner,
                    "source_region_id": source_region_id,
                    "destination_region_id": target_region_id,
                    "route_region_ids": list(route_plan.region_ids),
                    "route_index": 0,
                    "destination_latitude": target_geo.latitude,
                    "destination_longitude": target_geo.longitude,
                    "has_custom_destination": False,
                    "is_naval_invasion": False,
                    "status": "arrived",
                    "rejection_reason": "",
                    "updated_at_minute": now,
                }
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "deployment", "arrived", "Deployment origin already matches the destination.", now)
                rows.append(row)
                continue
            if len(route_plan.region_ids) < 2 and str(row.get("engagement_mode") or "").lower() == "positional":
                released_fortification = self._release_fortified_for_order(state, row)
                can_execute = released_fortification or self._readiness_system.prepare_order(state, unit_id)
                if not can_execute:
                    self._queue_pending_move(state, action)
                    self._record_unit_order_feedback(
                        feedback_rows, unit_id, owner, "move", "queued",
                        "The move will begin when the readiness transition completes.", now,
                    )
                    rows.append(row)
                    continue
                row["readiness_status"] = "ready"
                row["readiness_progress"] = 0.0
                row["readiness_transition_id"] = ""
                row["readiness_eta_minute"] = 0
                row["engagement_mode"] = "assault"
                self._record_unit_order_feedback(
                    feedback_rows, unit_id, owner, "move", "accepted",
                    "The unit escalated its existing contact instead of leaving the battle.", now,
                )
                rows.append(row)
                continue
            if len(route_plan.region_ids) < 2 and str(row.get("engagement_mode") or "").lower() != "positional":
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "arrived", "The unit is already at the destination.", now)
                rows.append(row)
                continue

            path = list(route_plan.region_ids)
            next_region_id = path[1]
            next_geo = (
                target_geo
                if next_region_id == target_region_id
                else region_locations.get(next_region_id)
            )
            if next_geo is None:
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "rejected", "The route contains a region without valid coordinates.", now)
                rows.append(row)
                continue

            # Rejected orders must not clear a fortified posture; release it only after route validation.
            released_fortification = False if deployment_dispatch else self._release_fortified_for_order(state, row)
            can_execute = deployment_dispatch or released_fortification or self._readiness_system.prepare_order(state, str(row.get("id") or ""))
            if not can_execute:
                self._queue_pending_move(state, action)
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "queued", "The move will begin when the readiness transition completes.", now)
                rows.append(row)
                continue
            if not deployment_dispatch:
                row["readiness_status"] = "ready"
                row["readiness_progress"] = 0.0
                row["readiness_transition_id"] = ""
                row["readiness_eta_minute"] = 0
            if str(row.get("engagement_mode") or "").lower() == "positional":
                row["engagement_mode"] = "assault"
                self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "accepted", "The unit escalated its existing contact instead of leaving the battle.", now)
                rows.append(row)
                continue
            duration = segment_duration(
                region_by_id[source_region_id], region_by_id[next_region_id]
            )
            row["source_region_id"] = source_region_id
            row["source_latitude"] = source_geo.latitude
            row["source_longitude"] = source_geo.longitude
            row["target_region_id"] = next_region_id
            row["target_latitude"] = next_geo.latitude
            row["target_longitude"] = next_geo.longitude
            row["departed_at_minute"] = now
            row["arrival_at_minute"] = now + duration
            row["movement_progress"] = 0.0
            row["is_moving"] = True
            if deployment_dispatch:
                row["unit_lifecycle"] = "deployment_transit"
            route_by_unit[unit_id] = {
                "unit_id": unit_id,
                "owner_country_id": owner,
                "source_region_id": source_region_id,
                "destination_region_id": target_region_id,
                "route_region_ids": path,
                "route_index": 1,
                "destination_latitude": target_geo.latitude,
                "destination_longitude": target_geo.longitude,
                "has_custom_destination": action.target_latitude is not None and action.target_longitude is not None,
                "is_naval_invasion": bool(action.is_naval_invasion),
                "status": "in_transit",
                "rejection_reason": "",
                "updated_at_minute": now,
            }
            self._record_unit_order_feedback(feedback_rows, unit_id, owner, "move", "accepted", "Route accepted.", now)
            rows.append(row)

        routes_changed = route_table is None or route_rows != list(route_by_unit.values())
        if routes_changed:
            state.update_table(
                "unit_movement_routes",
                pl.DataFrame(list(route_by_unit.values()), schema=MOVEMENT_ROUTE_SCHEMA),
            )
        self._write_unit_order_feedback(state, feedback_rows)
        return self._units_from_rows(rows)

    def _route_segment_minutes(
        self,
        source: dict[str, Any],
        target: dict[str, Any],
        locations: dict[int, GeoCoordinate],
    ) -> float:
        source_geo = locations.get(int(source.get("id") or 0))
        target_geo = locations.get(int(target.get("id") or 0))
        if source_geo is None or target_geo is None:
            return float(DEFAULT_MOVE_MINUTES)
        return float(self._duration_policy.estimate_between(source_geo, target_geo))

    def _route_segment_minutes_for_unit(self, source, target, locations, unit, state, capability_speed_multiplier=1.0):
        source_geo = locations.get(int(source.get("id") or 0))
        target_geo = locations.get(int(target.get("id") or 0))
        if source_geo is None or target_geo is None:
            base = DEFAULT_MOVE_MINUTES
        else:
            base = self._duration_policy.estimate_between(source_geo, target_geo)
        domain = self._domain_for_unit(unit)
        domain_multipliers = state.globals.get("military_domain_duration_multipliers", {})
        domain_multiplier = 1.0
        if isinstance(domain_multipliers, dict):
            domain_multiplier = self._bounded_multiplier(domain_multipliers.get(domain), 1.0)
        size_coefficient = max(0.0, min(0.5, self._row_float_from_mapping(state.globals.get("military_force_size_duration_coefficient"), 0.0)))
        strength = max(1, int(unit.get("strength") or 1))
        size_multiplier = 1.0 + min(1.0, math.log10(strength) / 4.0) * size_coefficient
        infrastructure = max(0.0, min(1.0, self._row_float(target, "infrastructure", 0.0)))
        infrastructure_coefficient = max(0.0, min(0.5, self._row_float_from_mapping(state.globals.get("military_infrastructure_duration_coefficient", 0.25), 0.25)))
        infrastructure_multiplier = 1.0 / (1.0 + infrastructure * infrastructure_coefficient)
        telecom = max(
            0.0,
            min(
                1.0,
                self._row_float(
                    target,
                    "telecom_capacity",
                    self._row_float(target, "communications", 0.0),
                ),
            ),
        )
        telecom_coefficient = max(
            0.0,
            min(
                0.5,
                self._row_float_from_mapping(
                    state.globals.get("military_telecom_coordination_coefficient", 0.15),
                    0.15,
                ),
            ),
        )
        telecom_multiplier = 1.0 / (1.0 + telecom * telecom_coefficient)
        owner = str(unit.get("owner") or "").strip().upper()
        target_owner = str(target.get("owner") or "").strip().upper()
        territory_key = "military_domestic_duration_multiplier" if not target_owner or target_owner == owner else "military_foreign_duration_multiplier"
        territory_multiplier = self._bounded_multiplier(state.globals.get(territory_key), 1.0)
        speed_multiplier = max(0.5, min(1.5, self._row_float_from_mapping(capability_speed_multiplier, 1.0)))
        return int(max(360, min(10080, round(base * domain_multiplier * size_multiplier * infrastructure_multiplier * telecom_multiplier * territory_multiplier / speed_multiplier))))

    def _route_segment_cost_for_unit(
        self,
        locations: dict[int, GeoCoordinate],
        unit: dict[str, Any],
        state: GameState,
        capability_speed_multiplier: float = 1.0,
        edge_distance_km: dict[tuple[int, int], float] | None = None,
    ) -> Callable[[dict[str, Any], dict[str, Any]], int]:
        """Prepare unit-wide movement factors once for a route search."""
        domain = self._domain_for_unit(unit)
        domain_multipliers = state.globals.get("military_domain_duration_multipliers", {})
        domain_multiplier = (
            self._bounded_multiplier(domain_multipliers.get(domain), 1.0)
            if isinstance(domain_multipliers, dict)
            else 1.0
        )
        size_coefficient = max(
            0.0,
            min(
                0.5,
                self._row_float_from_mapping(
                    state.globals.get("military_force_size_duration_coefficient"), 0.0
                ),
            ),
        )
        strength = max(1, int(unit.get("strength") or 1))
        size_multiplier = 1.0 + min(1.0, math.log10(strength) / 4.0) * size_coefficient
        infrastructure_coefficient = max(
            0.0,
            min(
                0.5,
                self._row_float_from_mapping(
                    state.globals.get("military_infrastructure_duration_coefficient", 0.25),
                    0.25,
                ),
            ),
        )
        telecom_coefficient = max(
            0.0,
            min(
                0.5,
                self._row_float_from_mapping(
                    state.globals.get("military_telecom_coordination_coefficient", 0.15),
                    0.15,
                ),
            ),
        )
        owner = str(unit.get("owner") or "").strip().upper()
        speed_multiplier = max(
            0.5,
            min(1.5, self._row_float_from_mapping(capability_speed_multiplier, 1.0)),
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
                infrastructure = max(
                    0.0, min(1.0, self._row_float(target, "infrastructure", 0.0))
                )
                telecom = max(
                    0.0,
                    min(
                        1.0,
                        self._row_float(
                            target,
                            "telecom_capacity",
                            self._row_float(target, "communications", 0.0),
                        ),
                    ),
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
                    self._bounded_multiplier(state.globals.get(territory_key), 1.0),
                )
                target_multipliers[target_id] = target_multiplier

            infrastructure_multiplier, telecom_multiplier, territory_multiplier = target_multiplier
            duration = base * domain_multiplier
            duration *= size_multiplier
            duration *= infrastructure_multiplier
            duration *= telecom_multiplier
            duration *= territory_multiplier
            duration /= speed_multiplier
            return int(max(360, min(10080, round(duration))))

        return cost

    def _capability_speed_by_unit(self, state: GameState) -> dict[str, float]:
        table = state.tables.get("unit_capability_projections")
        if table is None or not {"unit_id", "role", "capabilities_json"}.issubset(table.columns):
            return {}
        factors: dict[str, float] = {}
        for row in table.to_dicts():
            profile = get_role_profile(row.get("role"), row.get("domain"))
            baseline = self._row_float_from_mapping(profile.capabilities.get("speed"), 0.0)
            if baseline <= 0.0:
                continue
            try:
                capabilities = json.loads(str(row.get("capabilities_json") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(capabilities, dict):
                continue
            projected = self._row_float_from_mapping(capabilities.get("speed"), baseline)
            factor = projected / baseline
            if factor > 0.0 and math.isfinite(factor):
                factors[str(row.get("unit_id") or "")] = max(0.5, min(1.5, factor))
        return factors

    def _domain_for_unit(self, unit):
        domain = str(unit.get("unit_domain") or "").strip().lower()
        return domain if domain in {"land", "air", "naval", "strategic"} else get_role_profile(unit.get("unit_type") or DEFAULT_UNIT_TYPE).domain

    def _has_domain_route_metadata(self, all_regions):
        metadata_fields = ("is_water", "region_type", "terrain", "is_port", "is_coastal")
        return any(
            any(key in row and row.get(key) is not None for key in metadata_fields)
            for row in all_regions
        )

    def _domain_route_compatible(self, domain, region, final, naval_invasion, all_regions, *, metadata_available=None):
        metadata = (
            self._has_domain_route_metadata(all_regions)
            if metadata_available is None else bool(metadata_available)
        )
        if not metadata:
            return True, ""
        is_water = self._region_is_water(region)
        is_port = bool(region.get("is_port")) or str(region.get("region_type") or region.get("terrain") or "").strip().lower() in {"port", "naval_base"}
        is_coastal = bool(region.get("is_coastal")) or is_port
        if domain == "land" and is_water:
            return False, "Ground units cannot enter a water region."
        if domain == "naval" and not is_water and not is_port and not (final and naval_invasion and is_coastal):
            return False, "Naval units require a sea zone, port, or eligible coastal landing region."
        if domain == "strategic":
            return False, "Strategic assets do not use conventional movement orders."
        return True, ""

    def _region_is_water(self, region):
        if region.get("is_water") is not None:
            return bool(region.get("is_water"))
        return str(region.get("region_type") or region.get("terrain") or "").strip().lower() in {"sea", "ocean", "water", "international_waters", "naval_zone"}

    def _bounded_multiplier(self, value, default):
        if value is None:
            return default
        return max(0.25, min(4.0, self._row_float_from_mapping(value, default)))

    def _row_float_from_mapping(self, value, default):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return number if math.isfinite(number) else default

    def _record_unit_order_feedback(
        self,
        rows: list[dict[str, Any]],
        unit_id: str,
        owner: str,
        order_type: str,
        status: str,
        reason: str,
        current_minute: int,
    ) -> None:
        rows.append({
            "id": f"{unit_id}-{current_minute}-{len(rows) + 1}",
            "unit_id": unit_id,
            "owner_country_id": owner,
            "order_type": order_type,
            "status": status,
            "reason": reason,
            "created_at_minute": current_minute,
        })
        if len(rows) > 500:
            del rows[:-500]

    def _write_unit_order_feedback(self, state: GameState, rows: list[dict[str, Any]]) -> None:
        frame = pl.DataFrame(rows, schema=UNIT_ORDER_FEEDBACK_SCHEMA) if rows else pl.DataFrame(schema=UNIT_ORDER_FEEDBACK_SCHEMA)
        current = state.tables.get("unit_order_feedback")
        if current is None or not current.equals(frame):
            state.update_table("unit_order_feedback", frame)

    def _release_fortified_for_order(self, state: GameState, unit: dict[str, Any]) -> bool:
        """Release a stable fortified posture before validating an order's route."""
        unit_id = str(unit.get("id") or "")
        if str(unit.get("readiness_status") or "").strip().lower() != "fortified":
            return False
        if self._unit_is_transitioning(state, unit_id):
            return False
        if not self._readiness_system.prepare_order(state, unit_id):
            return False
        unit["readiness_status"] = "ready"
        unit["readiness_progress"] = 0.0
        unit["readiness_transition_id"] = ""
        unit["readiness_eta_minute"] = 0
        return True

    def _unit_is_transitioning(self, state: GameState, unit_id: str) -> bool:
        transitions = state.tables.get("unit_readiness_transitions")
        return transitions is not None and not transitions.is_empty() and "unit_id" in transitions.columns and transitions.filter(pl.col("unit_id") == unit_id).height > 0

    def _queue_pending_move(self, state: GameState, action: ActionMoveUnit) -> str:
        pending = self._ensure_pending_table(state.tables.get("unit_pending_orders"))
        rows = [row for row in pending.to_dicts() if str(row.get("unit_id") or "") != str(action.unit_id)]
        order_id = f"pending-{action.unit_id}-move-{state.time.total_minutes}"
        rows.append({
            "id": order_id, "unit_id": str(action.unit_id), "player_id": str(action.player_id),
            "order_type": "move", "target_region_id": int(action.target_region_id),
            "target_latitude": float(action.target_latitude or 0.0), "target_longitude": float(action.target_longitude or 0.0),
            "target_unit_id": "", "via_region_ids": list(action.via_region_ids),
            "created_at_minute": int(state.time.total_minutes), "status": "queued",
        })
        state.update_table("unit_pending_orders", pl.DataFrame(rows, schema=self._pending_schema()))
        self._attach_pending_to_transition(state, action.unit_id, order_id)
        return order_id

    def _queue_pending_attack(self, state: GameState, action: ActionAttackUnit) -> str:
        pending = self._ensure_pending_table(state.tables.get("unit_pending_orders"))
        rows = [row for row in pending.to_dicts() if str(row.get("unit_id") or "") != str(action.attacker_unit_id)]
        order_id = f"pending-{action.attacker_unit_id}-attack-{state.time.total_minutes}"
        rows.append({
            "id": order_id, "unit_id": str(action.attacker_unit_id), "player_id": str(action.player_id),
            "order_type": "attack", "target_region_id": 0, "target_latitude": 0.0, "target_longitude": 0.0,
            "target_unit_id": str(action.defender_unit_id), "via_region_ids": [],
            "created_at_minute": int(state.time.total_minutes), "status": "queued",
        })
        state.update_table("unit_pending_orders", pl.DataFrame(rows, schema=self._pending_schema()))
        self._attach_pending_to_transition(state, action.attacker_unit_id, order_id)
        return order_id

    def _attach_pending_to_transition(self, state: GameState, unit_id: str, order_id: str) -> None:
        transitions = state.tables.get("unit_readiness_transitions")
        if transitions is None or transitions.is_empty() or "unit_id" not in transitions.columns:
            return
        rows = transitions.to_dicts()
        for row in rows:
            if str(row.get("unit_id") or "") == str(unit_id):
                row["pending_order_id"] = order_id
        state.update_table("unit_readiness_transitions", pl.DataFrame(rows, schema=transitions.schema))

    def _pending_schema(self) -> dict[str, pl.DataType]:
        return {
            "id": pl.Utf8, "unit_id": pl.Utf8, "player_id": pl.Utf8,
            "order_type": pl.Utf8, "target_region_id": pl.Int32,
            "target_latitude": pl.Float64, "target_longitude": pl.Float64,
            "target_unit_id": pl.Utf8, "via_region_ids": pl.List(pl.Int32),
            "created_at_minute": pl.Int64, "status": pl.Utf8,
        }

    def _ensure_pending_table(self, pending: pl.DataFrame | None) -> pl.DataFrame:
        schema = self._pending_schema()
        if pending is None:
            return pl.DataFrame(schema=schema)
        for column, dtype in schema.items():
            if column not in pending.columns:
                default: Any = [] if dtype == pl.List(pl.Int32) else (0 if dtype in (pl.Int32, pl.Int64, pl.Float64) else "")
                pending = pending.with_columns(pl.lit(default).cast(dtype).alias(column))
        return pending.select([pl.col(column).cast(dtype) for column, dtype in schema.items()])

    def _resolve_action_target_geo(
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

    def _try_update_uncontested_movement_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
    ) -> pl.DataFrame | None:
        required = {
            "id", "is_moving", "target_region_id", "departed_at_minute",
            "arrival_at_minute", "movement_progress",
        }
        if not required.issubset(units.columns):
            return None

        wars = state.tables.get("countries_wars")
        if wars is not None and not wars.is_empty() and hostile_country_pairs(wars.to_dicts()):
            return None
        route_table = state.tables.get("unit_movement_routes")
        if route_table is not None and not route_table.is_empty():
            routed_update = self._try_update_final_leg_movement_batch(
                state,
                units,
                current_minute,
                route_table,
            )
            if routed_update is not None:
                return routed_update
            return None

        moving = units.get_column("is_moving").fill_null(False)
        targets = units.get_column("target_region_id").fill_null(NO_TARGET_REGION)
        active_mask = moving & targets.gt(0)
        arrivals = units.get_column("arrival_at_minute").fill_null(current_minute)
        if (active_mask & arrivals.le(current_minute)).any():
            return None

        departed = pl.col("departed_at_minute").fill_null(current_minute)
        duration = (
            pl.col("arrival_at_minute").fill_null(current_minute) - departed
        ).clip(lower_bound=1)
        progress = (
            (pl.lit(current_minute) - departed).cast(pl.Float64)
            / duration.cast(pl.Float64)
        ).clip(0.0, 1.0)
        all_units_active = moving.all() and targets.gt(0).all()
        if all_units_active:
            # NumPy avoids building and evaluating a Polars expression tree for this hot numeric-only path.
            departed_values = units.get_column("departed_at_minute").fill_null(current_minute).to_numpy()
            arrival_values = arrivals.to_numpy()
            duration_values = np.maximum(arrival_values - departed_values, 1)
            progress_values = np.clip(
                (current_minute - departed_values) / duration_values,
                0.0,
                1.0,
            )
            updated_units = units.with_columns(
                pl.Series("movement_progress", progress_values, dtype=pl.Float64)
            )
        else:
            active_expression = (
                pl.col("is_moving").fill_null(False)
                & pl.col("target_region_id").fill_null(NO_TARGET_REGION).gt(0)
            )
            updated_units = units.with_columns(
                pl.when(active_expression)
                .then(progress)
                .otherwise(pl.lit(0.0))
                .alias("movement_progress"),
                active_expression.alias("is_moving"),
            )

        route_table = state.tables.get("unit_movement_routes")
        if route_table is not None and not route_table.is_empty():
            if {"unit_id", "updated_at_minute"}.issubset(route_table.columns):
                active_ids = units.filter(active_mask).get_column("id")
                if len(active_ids):
                    updated_routes = route_table.with_columns(
                        pl.when(pl.col("unit_id").is_in(active_ids.to_list()))
                        .then(pl.lit(current_minute))
                        .otherwise(pl.col("updated_at_minute"))
                        .cast(pl.Int64)
                        .alias("updated_at_minute")
                    )
                    if not route_table.equals(updated_routes):
                        state.update_table("unit_movement_routes", updated_routes)
            else:
                return None

        return updated_units

    def _try_update_final_leg_movement_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        routes: pl.DataFrame,
    ) -> pl.DataFrame | None:
        required_units = {
            "id", "owner", "unit_domain", "unit_type", "is_moving", "engagement_mode",
            "target_region_id", "target_latitude", "target_longitude", "current_region_id",
            "latitude", "longitude", "source_region_id", "source_latitude", "source_longitude",
            "departed_at_minute", "arrival_at_minute", "movement_progress",
        }
        required_routes = {
            "unit_id", "owner_country_id", "destination_region_id", "route_region_ids",
            "route_index", "has_custom_destination", "is_naval_invasion", "status",
            "rejection_reason", "updated_at_minute",
        }
        if not required_units.issubset(units.columns) or not required_routes.issubset(routes.columns):
            return None
        if units.is_empty() or routes.height != units.height:
            return None
        if not units.get_column("is_moving").fill_null(False).all():
            return None
        if units.get_column("target_region_id").fill_null(NO_TARGET_REGION).min() <= 0:
            return None
        if units.get_column("engagement_mode").fill_null("").str.strip_chars().ne("").any():
            return None
        if units.get_column("id").n_unique() != units.height or routes.get_column("unit_id").n_unique() != routes.height:
            return None
        if set(units.get_column("id").to_list()) != set(routes.get_column("unit_id").to_list()):
            return None

        route_profile_columns = [
            "owner_country_id", "destination_region_id", "route_index",
            "has_custom_destination", "is_naval_invasion", "status",
        ]
        route_profiles = routes.select(route_profile_columns).unique()
        if route_profiles.height != 1 or routes.get_column("route_region_ids").n_unique() != 1:
            return None
        route_profile = route_profiles.row(0, named=True)
        route_regions = routes.get_column("route_region_ids")[0]
        route_regions = [] if route_regions is None else [int(value) for value in route_regions]
        route_index = int(route_profile.get("route_index") or 0)
        destination_id = int(route_profile.get("destination_region_id") or 0)
        if (
            not route_regions
            or route_index != len(route_regions) - 1
            or route_regions[-1] != destination_id
            or bool(route_profile.get("has_custom_destination"))
            or bool(route_profile.get("is_naval_invasion"))
            or str(route_profile.get("status") or "") != "in_transit"
        ):
            return None

        unit_profiles = units.select(["owner", "target_region_id", "unit_domain", "unit_type"]).unique()
        if unit_profiles.height != 1:
            return None
        unit_profile = unit_profiles.row(0, named=True)
        owner = str(unit_profile.get("owner") or "").strip().upper()
        target_id = int(unit_profile.get("target_region_id") or 0)
        if (
            not owner
            or owner != str(route_profile.get("owner_country_id") or "").strip().upper()
            or target_id != destination_id
        ):
            return None

        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return None
        target_rows = regions.filter(pl.col("id") == target_id).head(1).to_dicts()
        if not target_rows:
            return None
        target_region = target_rows[0]
        access_context = self._access_policy.for_country(state, owner)
        if not access_context.can_station(target_region):
            return None
        domain = self._domain_for_unit(unit_profile)
        domain_allowed, _ = self._domain_route_compatible(
            domain,
            target_region,
            True,
            False,
            regions.to_dicts(),
        )
        if not domain_allowed:
            return None

        due = pl.col("arrival_at_minute").fill_null(current_minute).le(current_minute)
        departed = pl.col("departed_at_minute").fill_null(current_minute)
        arrival = pl.col("arrival_at_minute").fill_null(current_minute)
        duration = (arrival - departed).clip(lower_bound=1)
        progress = ((pl.lit(current_minute) - departed).cast(pl.Float64) / duration.cast(pl.Float64)).clip(0.0, 1.0)
        updates = [
            pl.when(due).then(pl.col("target_region_id")).otherwise(pl.col("current_region_id")).cast(pl.Int32).alias("current_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("latitude")).alias("latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("longitude")).alias("longitude"),
            pl.when(due).then(pl.col("target_region_id")).otherwise(pl.col("source_region_id")).cast(pl.Int32).alias("source_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("source_latitude")).alias("source_latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("source_longitude")).alias("source_longitude"),
            pl.when(due).then(pl.lit(NO_TARGET_REGION)).otherwise(pl.col("target_region_id")).cast(pl.Int32).alias("target_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("target_latitude")).alias("target_latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("target_longitude")).alias("target_longitude"),
            pl.when(due).then(pl.lit(current_minute)).otherwise(departed).cast(pl.Int64).alias("departed_at_minute"),
            pl.when(due).then(pl.lit(current_minute)).otherwise(arrival).cast(pl.Int64).alias("arrival_at_minute"),
            pl.when(due).then(pl.lit(0.0)).otherwise(progress).alias("movement_progress"),
            (~due).alias("is_moving"),
        ]
        if "unit_lifecycle" in units.columns:
            updates.append(
                pl.when(due)
                .then(pl.when(pl.col("unit_lifecycle") == "battle_retreating").then(pl.lit("battle_regrouping")).otherwise(pl.lit("available")))
                .otherwise(pl.col("unit_lifecycle"))
                .alias("unit_lifecycle")
            )
        updates.append(pl.when(due).then(pl.lit("")).otherwise(pl.col("engagement_mode")).alias("engagement_mode"))
        updated_units = units.with_columns(updates)

        due_ids = units.filter(due).get_column("id").to_list()
        arrived = pl.col("unit_id").is_in(due_ids)
        updated_routes = routes.with_columns(
            pl.when(arrived).then(pl.lit("arrived")).otherwise(pl.col("status")).alias("status"),
            pl.when(arrived).then(pl.lit("")).otherwise(pl.col("rejection_reason")).alias("rejection_reason"),
            pl.lit(current_minute).cast(pl.Int64).alias("updated_at_minute"),
        )
        if not routes.equals(updated_routes):
            state.update_table("unit_movement_routes", updated_routes)
        return updated_units

    def _update_unit_movements(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> pl.DataFrame:
        if units.is_empty():
            return units

        if {"is_moving", "movement_progress"}.issubset(units.columns):
            is_moving = units.get_column("is_moving").fill_null(False)
            has_stale_progress = (
                units.get_column("movement_progress").fill_null(0.0) != 0.0
            ).any()
            if not is_moving.any() and not has_stale_progress:
                return units

        batched = self._try_update_uncontested_movement_batch(state, units, current_minute)
        if batched is not None:
            return batched

        war_table = state.tables.get("countries_wars")
        war_rows = [] if war_table is None else war_table.to_dicts()
        hostile_owners_by_country: dict[str, set[str]] = {}
        for pair in hostile_country_pairs(war_rows):
            tags = tuple(pair)
            if len(tags) != 2:
                continue
            left, right = tags
            hostile_owners_by_country.setdefault(left, set()).add(right)
            hostile_owners_by_country.setdefault(right, set()).add(left)

        rows = units.to_dicts()
        route_table = state.tables.get("unit_movement_routes")
        route_rows = [] if route_table is None else route_table.to_dicts()
        route_by_unit = {str(route.get("unit_id") or ""): route for route in route_rows}
        regions = state.tables.get("regions")
        region_locations = {} if regions is None else self._duration_policy.region_locations(regions)
        region_rows = [] if regions is None else regions.to_dicts()
        has_domain_metadata = self._has_domain_route_metadata(region_rows)
        regions_by_id = {int(region.get("id") or 0): region for region in region_rows}
        ordered_rows = sorted(rows, key=lambda candidate: str(candidate.get("id") or ""))
        moving_owners = {
            str(row.get("owner") or "").strip().upper()
            for row in rows
            if bool(row.get("is_moving"))
        }
        contact_candidates = {
            owner: [
                candidate
                for candidate in ordered_rows
                if str(candidate.get("owner") or "").strip().upper()
                in hostile_owners_by_country.get(owner, set())
            ]
            for owner in moving_owners
        }
        access_context_by_country = {}
        for row in rows:
            unit_id = str(row.get("id") or "")
            owner = str(row.get("owner") or "").strip().upper()
            route = route_by_unit.get(unit_id)
            target_region_id = int(row.get("target_region_id") or NO_TARGET_REGION)
            if target_region_id <= 0 or not bool(row.get("is_moving")):
                row["movement_progress"] = 0.0
                row["is_moving"] = False
                continue

            departed_value = row.get("departed_at_minute")
            arrival_value = row.get("arrival_at_minute")
            departed_at = int(departed_value if departed_value is not None else current_minute)
            arrival_at = int(arrival_value if arrival_value is not None else current_minute)
            duration = max(1, arrival_at - departed_at)
            previous_progress = max(0.0, min(1.0, float(row.get("movement_progress") or 0.0)))
            progress = max(0.0, min(1.0, (current_minute - departed_at) / duration))
            source_geo = GeoCoordinate(
                latitude=self._row_float(row, "source_latitude", row.get("latitude")),
                longitude=self._row_float(row, "source_longitude", row.get("longitude")),
            )
            target_geo = GeoCoordinate(
                latitude=self._row_float(row, "target_latitude", row.get("latitude")),
                longitude=self._row_float(row, "target_longitude", row.get("longitude")),
            )
            current_target = regions_by_id.get(target_region_id)
            route_ids = [] if route is None else [int(value) for value in route.get("route_region_ids") or []]
            route_index = 0 if route is None else int(route.get("route_index") or 0)
            is_final_leg = route is None or int(route.get("destination_region_id") or target_region_id) == target_region_id
            domain_allowed = current_target is not None and self._domain_route_compatible(
                self._domain_for_unit(row),
                current_target,
                is_final_leg,
                bool(route and route.get("is_naval_invasion")),
                region_rows,
                metadata_available=has_domain_metadata,
            )[0]
            access_context = access_context_by_country.get(owner)
            if access_context is None:
                access_context = self._access_policy.for_country(state, owner)
                access_context_by_country[owner] = access_context
            access_allowed = current_target is not None and (
                access_context.can_station(current_target)
                if is_final_leg
                else access_context.can_transit(current_target)
            )
            if not domain_allowed or not access_allowed:
                # Revoked rights stop movement at the last legal waypoint instead of allowing a stale route to cross a border.
                self._stop_unit_at(row, source_geo, current_minute)
                lifecycle = str(row.get("unit_lifecycle") or "")
                if lifecycle in {"deployment_transit", "in_transit"}:
                    row["unit_lifecycle"] = "deployment_blocked"
                else:
                    row["unit_lifecycle"] = "route_blocked"
                if route is not None:
                    route["status"] = "blocked"
                    route["rejection_reason"] = (
                        "The current route segment is incompatible with the unit domain."
                        if not domain_allowed
                        else "The current route segment no longer has valid access rights."
                    )
                    route["updated_at_minute"] = current_minute
                continue
            previous_geo = interpolate_geo(source_geo, target_geo, previous_progress)
            next_geo = interpolate_geo(source_geo, target_geo, progress)
            contact = self._first_hostile_contact(
                row,
                contact_candidates.get(owner, ()),
                previous_geo,
                next_geo,
                current_minute,
            )

            if contact is not None:
                defender, fraction = contact
                contact_geo = interpolate_geo(previous_geo, next_geo, fraction)
                row["current_region_id"] = int(defender.get("current_region_id") or 0)
                self._stop_unit_at(row, contact_geo, current_minute)
                row["engagement_mode"] = "positional"
                if route is not None:
                    route["status"] = "interrupted"
                    route["rejection_reason"] = "Hostile contact interrupted the route."
                    route["updated_at_minute"] = current_minute
                defender_geo = self._unit_geo_at(defender, current_minute)
                self._stop_unit_at(defender, defender_geo, current_minute)
                defender["engagement_mode"] = "positional"
                continue

            if progress >= 1.0:
                if route is not None and bool(route.get("is_naval_invasion")) and is_final_leg:
                    destination = regions_by_id.get(target_region_id)
                    valid_landing, landing_reason = (False, "The landing region is no longer available.") if destination is None else self._naval_invasion_policy.validate(
                        state, row, destination, rows, (next_geo.latitude, next_geo.longitude),
                    )
                    if not valid_landing:
                        self._stop_unit_at(row, previous_geo, current_minute)
                        row["unit_lifecycle"] = "landing_blocked"
                        route["status"] = "blocked"
                        route["rejection_reason"] = landing_reason
                        route["updated_at_minute"] = current_minute
                        continue
                row["current_region_id"] = target_region_id
                next_index = route_index + 1
                if route is not None and next_index < len(route_ids):
                    next_region_id = route_ids[next_index]
                    next_geo = region_locations.get(next_region_id)
                    if (
                        next_geo is not None
                        and regions is not None
                        and next_region_id > 0
                    ):
                        next_region_row = regions_by_id.get(next_region_id)
                        final_leg = next_index == len(route_ids) - 1
                        domain_allowed = next_region_row is not None and self._domain_route_compatible(
                            self._domain_for_unit(row),
                            next_region_row,
                            final_leg,
                            bool(route.get("is_naval_invasion")),
                            region_rows,
                            metadata_available=has_domain_metadata,
                        )[0]
                        access_context = access_context_by_country.get(owner)
                        if access_context is None:
                            access_context = self._access_policy.for_country(state, owner)
                            access_context_by_country[owner] = access_context
                        allowed = domain_allowed and (
                            access_context.can_station(next_region_row)
                            if final_leg
                            else access_context.can_transit(next_region_row)
                        )
                        if not allowed:
                            self._stop_unit_at(row, target_geo, current_minute)
                            lifecycle = str(row.get("unit_lifecycle") or "")
                            if lifecycle in {"deployment_transit", "in_transit"}:
                                row["current_region_id"] = 0
                            row["unit_lifecycle"] = "deployment_blocked" if lifecycle == "deployment_transit" else "route_blocked"
                            route["status"] = "blocked"
                            route["rejection_reason"] = (
                                "The next route segment is incompatible with the unit domain."
                                if not domain_allowed
                                else "The next route segment no longer has valid access rights."
                            )
                            route["updated_at_minute"] = current_minute
                            continue
                        has_custom = bool(route.get("has_custom_destination")) and final_leg
                        if has_custom:
                            next_geo = GeoCoordinate(
                                float(route.get("destination_latitude") or 0.0),
                                float(route.get("destination_longitude") or 0.0),
                            )
                        row["latitude"] = target_geo.latitude
                        row["longitude"] = target_geo.longitude
                        row["source_region_id"] = target_region_id
                        row["source_latitude"] = target_geo.latitude
                        row["source_longitude"] = target_geo.longitude
                        if str(row.get("unit_lifecycle") or "") in {"deployment_transit", "in_transit"}:
                            row["current_region_id"] = 0
                        row["target_region_id"] = next_region_id
                        row["target_latitude"] = next_geo.latitude
                        row["target_longitude"] = next_geo.longitude
                        row["departed_at_minute"] = arrival_at
                        duration_locations = dict(region_locations)
                        duration_locations[target_region_id] = target_geo
                        row["arrival_at_minute"] = arrival_at + self._route_segment_minutes_for_unit(
                            regions_by_id[target_region_id],
                            next_region_row,
                            duration_locations,
                            row,
                            state,
                            (capability_speed_by_unit or {}).get(str(row.get("id") or ""), 1.0),
                        )
                        row["movement_progress"] = 0.0
                        row["is_moving"] = True
                        row["engagement_mode"] = ""
                        route["route_index"] = next_index
                        route["updated_at_minute"] = current_minute
                    else:
                        self._stop_unit_at(row, target_geo, current_minute)
                        row["engagement_mode"] = ""
                        if str(row.get("unit_lifecycle") or "") in {"deployment_transit", "in_transit"}:
                            row["current_region_id"] = 0
                            row["unit_lifecycle"] = "deployment_blocked" if str(row.get("production_order_id") or "") else "route_blocked"
                        route["status"] = "blocked"
                        route["rejection_reason"] = "The next route region no longer has a valid location."
                        route["updated_at_minute"] = current_minute
                else:
                    self._stop_unit_at(row, target_geo, current_minute)
                    row["engagement_mode"] = ""
                    if route is not None:
                        route["status"] = "arrived"
                        route["rejection_reason"] = ""
                        route["updated_at_minute"] = current_minute
                    if "unit_lifecycle" in row:
                        row["unit_lifecycle"] = (
                            "battle_regrouping"
                            if str(row.get("unit_lifecycle") or "") == "battle_retreating"
                            else "available"
                        )
            else:
                row["movement_progress"] = progress
                row["is_moving"] = True
                if route is not None:
                    route["updated_at_minute"] = current_minute

        if route_table is not None:
            route_frame = pl.DataFrame(list(route_by_unit.values()), schema=MOVEMENT_ROUTE_SCHEMA) if route_by_unit else pl.DataFrame(schema=MOVEMENT_ROUTE_SCHEMA)
            if not route_table.equals(route_frame):
                state.update_table("unit_movement_routes", route_frame)
        return self._units_from_rows(rows)

    def _first_hostile_contact(
        self,
        moving_unit: dict[str, Any],
        unit_rows: Iterable[dict[str, Any]],
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> tuple[dict[str, Any], float] | None:
        best_contact: tuple[dict[str, Any], float] | None = None
        moving_id = str(moving_unit.get("id") or "")
        for defender in unit_rows:
            if str(defender.get("id") or "") == moving_id or int(defender.get("strength") or 0) <= 0:
                continue
            fraction = first_zone_contact_fraction(
                start,
                end,
                self._unit_geo_at(defender, current_minute),
                engagement_radius_km(defender),
            )
            if fraction is None:
                continue
            # Stop at the first route contact; region and unit IDs make exact
            # fraction ties deterministic across equivalent snapshots.
            candidate_key = (
                round(float(fraction), 12),
                int(defender.get("current_region_id") or 0) if int(defender.get("current_region_id") or 0) > 0 else 2**31,
                str(defender.get("id") or ""),
            )
            best_key = None
            if best_contact is not None:
                best_defender, best_fraction = best_contact
                best_key = (
                    round(float(best_fraction), 12),
                    int(best_defender.get("current_region_id") or 0) if int(best_defender.get("current_region_id") or 0) > 0 else 2**31,
                    str(best_defender.get("id") or ""),
                )
            if best_contact is None or candidate_key < best_key:
                best_contact = (defender, fraction)
        return best_contact

    def _unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate:
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

    def _stop_unit_at(self, row: dict[str, Any], geo: GeoCoordinate, current_minute: int) -> None:
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

    def _ensure_country_columns(self, countries: pl.DataFrame) -> pl.DataFrame:
        if "military_count" not in countries.columns:
            if "military_count" not in self._missing_columns:
                print(f"[{self.id}] Column 'military_count' not found in 'countries'. Defaulting to 0.")
                self._missing_columns.add("military_count")
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        if "money_reserves" not in countries.columns:
            if "money_reserves" not in self._missing_columns:
                print(f"[{self.id}] Column 'money_reserves' not found in 'countries'. Defaulting to 0.")
                self._missing_columns.add("money_reserves")
            countries = countries.with_columns(pl.lit(0.0).alias("money_reserves"))

        return countries

    def _next_unit_id(self, unit_rows: list[dict[str, Any]], country_tag: str, unit_type: str) -> str:
        clean_unit_type = unit_type or DEFAULT_UNIT_TYPE
        prefix = f"{country_tag}-{clean_unit_type}"
        existing_ids = {str(row["id"]) for row in unit_rows}
        index = 1

        while True:
            unit_id = f"{prefix}-{index:03d}"
            if unit_id not in existing_ids:
                return unit_id
            index += 1

    def _normalize_units_table(self, units: pl.DataFrame, state: GameState | None = None) -> pl.DataFrame:
        defaults: dict[str, Any] = {
            "id": "",
            "owner": "",
            "unit_type": DEFAULT_UNIT_TYPE,
            "design_id": "",
            "unit_domain": "land",
            "strength": 1,
            "equipment_quantity": 0,
            "current_region_id": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "source_region_id": 0,
            "source_latitude": 0.0,
            "source_longitude": 0.0,
            "target_region_id": NO_TARGET_REGION,
            "target_latitude": 0.0,
            "target_longitude": 0.0,
            "departed_at_minute": 0,
            "arrival_at_minute": 0,
            "movement_progress": 0.0,
            "is_moving": False,
            "engagement_mode": "",
            "readiness_status": "ready",
            "readiness_transition_id": "",
            "readiness_progress": 0.0,
            "readiness_eta_minute": 0,
            "training_level": "Recruit",
            "training_state": "",
            "training_progress": 0.0,
            "combat_posture": "hold",
            "combat_strength_modifier": 1.0,
            "war_exhaustion_modifier": 1.0,
            "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0,
            "combat_attack_risk_modifier": 1.0,
            "combat_readiness_modifier": 1.0,
            "combat_holding_modifier": 1.0,
            "combat_counterattack_modifier": 1.0,
            "production_order_id": "",
            "foreign_order_id": "",
            "original_cost": 0.0,
            "unit_lifecycle": "available",
        }

        had_latitude = "latitude" in units.columns
        had_longitude = "longitude" in units.columns
        if "equipment_quantity" not in units.columns:
            units = units.with_columns(
                pl.col("strength").cast(pl.Int64, strict=False).fill_null(0).alias("equipment_quantity")
            )
        for column, default_value in defaults.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        if state is not None and (not had_latitude or not had_longitude) and "regions" in state.tables:
            units = self._backfill_unit_geo_from_regions(units, state.get_table("regions"))

        return units.select([pl.col(column).cast(dtype) for column, dtype in UNIT_SCHEMA.items()])

    def _backfill_unit_geo_from_regions(self, units: pl.DataFrame, regions: pl.DataFrame) -> pl.DataFrame:
        locations = self._duration_policy.region_locations(regions)
        rows = []
        for row in units.to_dicts():
            geo = locations.get(int(row["current_region_id"]), GeoCoordinate(0.0, 0.0))
            row["latitude"] = geo.latitude
            row["longitude"] = geo.longitude
            row["source_latitude"] = geo.latitude
            row["source_longitude"] = geo.longitude
            row["target_latitude"] = geo.latitude
            row["target_longitude"] = geo.longitude
            rows.append(row)

        return pl.DataFrame(rows) if rows else units

    def _units_from_rows(self, rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return self._empty_units()

        return pl.DataFrame(rows, schema=UNIT_SCHEMA)

    def _empty_units(self) -> pl.DataFrame:
        return pl.DataFrame(schema=UNIT_SCHEMA)

    def _update_manpower(self, state: GameState):
        regions = state.get_table("regions")

        if regions.is_empty() or "pop_15_64" not in regions.columns:
            return

        cache_key = (
            id(state),
            int(state.table_revisions.get("regions", 0)),
            id(regions),
        )
        if cache_key != self._manpower_cache_key:
            self._manpower_by_owner = regions.group_by("owner").agg(
                pl.col("pop_15_64").sum().alias("total_core_manpower")
            )
            self._manpower_cache_key = cache_key

        countries = state.get_table("countries")
        if countries.is_empty():
            return

        countries = (
            countries.drop("total_core_manpower")
            if "total_core_manpower" in countries.columns
            else countries
        ).join(
            self._manpower_by_owner,
            left_on="id",
            right_on="owner",
            how="left",
            maintain_order="left",
        ).with_columns(pl.col("total_core_manpower").fill_null(0))
        state.update_table("countries", countries)
