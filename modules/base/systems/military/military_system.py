from __future__ import annotations

import json
import math
from typing import Any, Callable, Iterable

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
    ActionInvadeTerritory,
    ActionSplitUnit,
    ActionMergeUnits,
    ActionDisbandUnits,
)
from src.shared.actions import ActionSetUnitReadiness
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.movement_batch_updater import MovementBatchUpdater
from modules.base.systems.military.movement_constants import NO_TARGET_REGION
from modules.base.systems.military.movement_duration import MovementDurationPolicy, DEFAULT_MOVE_MINUTES
from modules.base.systems.military.movement_progression import MovementProgression
from modules.base.systems.military.movement_order_policy import MilitaryMovementOrderPolicy
from modules.base.systems.military.movement_order_service import MilitaryMoveOrderService
from modules.base.systems.military.attack_order_service import MilitaryAttackOrderService
from modules.base.systems.military.unit_order_workflow import (
    UNIT_ORDER_FEEDBACK_SCHEMA,
    UNIT_PENDING_ORDER_SCHEMA,
    UnitOrderWorkflowService,
)
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from modules.base.systems.military.capability_catalog import get_role_profile
from modules.base.systems.military.unit_catalog import MILITARY_UNIT_TYPES
from modules.base.systems.military.naval_invasion_policy import NavalInvasionPolicy
from modules.base.systems.military.readiness_system import ReadinessSystem
from modules.base.systems.military.unit_reorganization import UnitReorganization
from modules.base.systems.military.market_purchase_service import MilitaryMarketPurchaseService
from modules.base.systems.military.territory_entry import authorized_entry_moves
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from modules.base.systems.military.war_policy import hostile_country_pairs
from modules.base.systems.military.home_region_policy import MilitaryHomeRegionPolicy
from modules.base.systems.military.production_completion_service import (
    MilitaryProductionCompletionService,
)
from modules.base.systems.military.unit_factory import DEFAULT_UNIT_TYPE, UnitFactory
from modules.base.systems.military.contact_transition_preflight import (
    MilitaryContactTransitionPreflight,
)
from modules.base.systems.military.deployment_service import (
    MilitaryDeploymentService,
)


UNIT_TABLE = "units"
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

class MilitarySystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'region_adjacency', 'treaty_effects', 'units', 'production_orders', 'unit_designs', 'unit_capability_projections', 'countries_wars', 'unit_readiness_transitions', 'unit_pending_orders', 'unit_movement_routes', 'unit_deployment_orders', 'political_effects', 'battles', 'battle_units', 'unit_training_orders', 'unit_market_listings'}),
        writes=frozenset({'countries', 'units', 'production_orders', 'unit_market_listings', 'unit_pending_orders', 'unit_movement_routes', 'unit_order_feedback', 'unit_deployment_orders'}),
        handles=frozenset(
            {
                ActionAttackUnit,
                ActionBuildUnit,
                ActionBuyMarketUnit,
                ActionDispatchUnitDeployment,
                ActionMoveUnit,
                ActionInvadeTerritory,
                ActionSplitUnit,
                ActionMergeUnits,
                ActionDisbandUnits,
                ActionSetUnitReadiness,
            }
        ),
        phase=SystemPhase.MILITARY,
    )
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_duration_policy": SYSTEM_STATE_HELPER,
        "_unit_factory": SYSTEM_STATE_HELPER,
        "_home_region_policy": SYSTEM_STATE_HELPER,
        "_access_policy": SYSTEM_STATE_HELPER,
        "_movement_batch_updater": SYSTEM_STATE_HELPER,
        "_movement_progression": SYSTEM_STATE_HELPER,
        "_movement_order_policy": SYSTEM_STATE_HELPER,
        "_movement_order_service": SYSTEM_STATE_HELPER,
        "_route_planner": SYSTEM_STATE_HELPER,
        "_naval_invasion_policy": SYSTEM_STATE_HELPER,
        "_weapons_trade_policy": SYSTEM_STATE_HELPER,
        "_readiness_system": SYSTEM_STATE_HELPER,
        "_demilitarization_policy": SYSTEM_STATE_HELPER,
        "_market_purchase_service": SYSTEM_STATE_HELPER,
        "_attack_order_service": SYSTEM_STATE_HELPER,
        "_unit_order_workflow": SYSTEM_STATE_HELPER,
        "_contact_transition_preflight": SYSTEM_STATE_HELPER,
        "_deployment_service": SYSTEM_STATE_HELPER,
        "_production_completion_service": SYSTEM_STATE_HELPER,
        "_manpower_cache_key": SYSTEM_STATE_CACHE,
        "_manpower_by_owner": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._missing_columns = set()
        self._duration_policy = MovementDurationPolicy()
        self._unit_factory = UnitFactory()
        self._home_region_policy = MilitaryHomeRegionPolicy()
        self._access_policy = MovementAccessPolicy()
        self._movement_batch_updater = MovementBatchUpdater(self._access_policy)
        self._route_planner = MilitaryRoutePlanner()
        self._naval_invasion_policy = NavalInvasionPolicy()
        self._movement_order_policy = MilitaryMovementOrderPolicy(self._duration_policy)
        self._movement_progression = MovementProgression(
            access_policy=self._access_policy,
            duration_policy=self._duration_policy,
            naval_invasion_policy=self._naval_invasion_policy,
            duration_calculator=self._movement_order_policy.route_segment_minutes_for_unit,
            route_schema=MOVEMENT_ROUTE_SCHEMA,
        )
        self._weapons_trade_policy = WeaponsTradePolicy()
        self._readiness_system = ReadinessSystem()
        self._unit_order_workflow = UnitOrderWorkflowService(self._readiness_system)
        self._deployment_service = MilitaryDeploymentService(
            unit_factory=self._unit_factory,
            unit_order_workflow=self._unit_order_workflow,
            authorization_policy=player_controls_country,
            units_from_rows=self._units_from_rows,
        )
        self._contact_transition_preflight = MilitaryContactTransitionPreflight(
            readiness_transitions=self._readiness_system,
            unit_order_workflow=self._unit_order_workflow,
            unit_movement=self._movement_progression,
            hostility_policy=hostile_country_pairs,
        )
        self._movement_order_service = MilitaryMoveOrderService(
            route_planner=self._route_planner,
            access_policy=self._access_policy,
            naval_invasion_policy=self._naval_invasion_policy,
            movement_order_policy=self._movement_order_policy,
            readiness_preparer=self._readiness_system,
            unit_order_workflow=self._unit_order_workflow,
            units_from_rows=self._units_from_rows,
            route_schema=MOVEMENT_ROUTE_SCHEMA,
        )
        self._demilitarization_policy = DemilitarizationPolicy()
        self._attack_order_service = MilitaryAttackOrderService(
            readiness_preparer=self._readiness_system,
            unit_movement=self._movement_progression,
            hostility_policy=hostile_country_pairs,
            unit_order_workflow=self._unit_order_workflow,
            units_from_rows=self._units_from_rows,
        )
        self._market_purchase_service = MilitaryMarketPurchaseService(
            unit_factory=self._unit_factory,
            duration_policy=self._duration_policy,
            access_policy=self._access_policy,
            route_planner=self._route_planner,
            demilitarization_policy=self._demilitarization_policy,
            weapons_trade_policy=self._weapons_trade_policy,
            authorization_policy=player_controls_country,
            route_schema=MOVEMENT_ROUTE_SCHEMA,
            default_unit_type=DEFAULT_UNIT_TYPE,
        )
        self._production_completion_service = MilitaryProductionCompletionService(
            unit_factory=self._unit_factory,
            demilitarization_policy=self._demilitarization_policy,
            duration_policy=self._duration_policy,
            deployment_order_creator=self._deployment_service,
            home_region_policy=self._home_region_policy,
            ensure_country_columns=self._ensure_country_columns,
            units_from_rows=self._units_from_rows,
        )
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
        units = UnitReorganization.apply(state, units)
        units, deployment_moves = self._process_deployment_actions(state, units)
        units = self._process_move_actions(state, units, [*deployment_moves, *authorized_entry_moves(state, units)], capability_speed_by_unit)
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
        self._contact_transition_preflight.process(state, units)

    def _valid_hostile_attack(
        self,
        attacker: dict[str, Any] | None,
        defender: dict[str, Any] | None,
        hostile_pairs: set[frozenset[str]],
        state: GameState,
    ) -> bool:
        return self._contact_transition_preflight.valid_hostile_attack(
            attacker,
            defender,
            hostile_pairs,
        )

    def _interpolate_row_geo(self, row: dict[str, Any], progress: float) -> GeoCoordinate:
        return self._contact_transition_preflight.interpolate_row_geo(row, progress)

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
        return self._home_region_policy.home_regions_by_country(regions)

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
        return self._production_completion_service.process_completed_orders(state, units)

    def _process_deployment_actions(self, state: GameState, units: pl.DataFrame):
        return self._deployment_service.process_actions(state, units)

    def _refresh_deployment_state(self, state: GameState, units: pl.DataFrame) -> None:
        self._deployment_service.refresh_state(state, units)

    def _deployment_actor_authorized(self, state, actor: str, owner: str) -> bool:
        return player_controls_country(state, actor, owner)

    def _next_deployment_id(self, production_order_id: str, deployments: list[dict[str, Any]]) -> str:
        return self._deployment_service.next_deployment_id(production_order_id, deployments)

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
        purchase_rows = self._market_purchase_service.process(
            state=state,
            units=units,
            countries=countries,
            listings_table=listings_table,
            actions=actions,
            home_regions_by_country=self._home_regions_by_country(regions),
            region_locations=self._duration_policy.region_locations(regions),
        )
        if purchase_rows is None:
            return units
        return self._units_from_rows(purchase_rows)

    def _process_attack_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        return self._attack_order_service.process(state, units)

    def _process_move_actions(
        self,
        state: GameState,
        units: pl.DataFrame,
        additional_actions: Iterable[ActionMoveUnit] = (),
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> pl.DataFrame:
        return self._movement_order_service.process(
            state,
            units,
            additional_actions,
            capability_speed_by_unit,
        )

    def _route_segment_minutes_for_unit(
        self,
        source,
        target,
        locations,
        unit,
        state,
        capability_speed_multiplier=1.0,
    ):
        return self._movement_order_policy.route_segment_minutes_for_unit(
            source,
            target,
            locations,
            unit,
            state,
            capability_speed_multiplier,
        )

    def _route_segment_cost_for_unit(
        self,
        locations: dict[int, GeoCoordinate],
        unit: dict[str, Any],
        state: GameState,
        capability_speed_multiplier: float = 1.0,
        edge_distance_km: dict[tuple[int, int], float] | None = None,
    ) -> Callable[[dict[str, Any], dict[str, Any]], int]:
        return self._movement_order_policy.route_segment_cost_for_unit(
            locations,
            unit,
            state,
            capability_speed_multiplier,
            edge_distance_km,
        )

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
        return self._movement_order_policy.domain_for_unit(unit)

    def _has_domain_route_metadata(self, all_regions):
        return self._movement_order_policy.has_domain_metadata(all_regions)

    def _domain_route_compatible(self, domain, region, final, naval_invasion, all_regions, *, metadata_available=None):
        return self._movement_order_policy.domain_route_compatible(
            domain,
            region,
            final,
            naval_invasion,
            all_regions,
            metadata_available=metadata_available,
        )

    def _region_is_water(self, region):
        return self._movement_order_policy.region_is_water(region)

    def _bounded_multiplier(self, value, default):
        return self._movement_order_policy.bounded_multiplier(value, default)

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
        self._unit_order_workflow.record_feedback(
            rows,
            unit_id,
            owner,
            order_type,
            status,
            reason,
            current_minute,
        )

    def _write_unit_order_feedback(self, state: GameState, rows: list[dict[str, Any]]) -> None:
        self._unit_order_workflow.write_feedback(state, rows)

    def _release_fortified_for_order(self, state: GameState, unit: dict[str, Any]) -> bool:
        return self._unit_order_workflow.release_fortified_for_order(state, unit)

    def _unit_is_transitioning(self, state: GameState, unit_id: str) -> bool:
        return self._unit_order_workflow.unit_is_transitioning(state, unit_id)

    def _queue_pending_move(self, state: GameState, action: ActionMoveUnit) -> str:
        return self._unit_order_workflow.queue_move(state, action)

    def _queue_pending_attack(self, state: GameState, action: ActionAttackUnit) -> str:
        return self._unit_order_workflow.queue_attack(state, action)

    def _attach_pending_to_transition(self, state: GameState, unit_id: str, order_id: str) -> None:
        self._unit_order_workflow.attach_pending_to_transition(state, unit_id, order_id)

    def _pending_schema(self) -> dict[str, pl.DataType]:
        return dict(UNIT_PENDING_ORDER_SCHEMA)

    def _ensure_pending_table(self, pending: pl.DataFrame | None) -> pl.DataFrame:
        return self._unit_order_workflow.ensure_pending_table(pending)

    def _resolve_action_target_geo(
        self,
        action: ActionMoveUnit,
        target_region_id: int,
        region_locations: dict[int, GeoCoordinate],
    ) -> GeoCoordinate | None:
        return self._movement_order_policy.resolve_target_geo(
            action,
            target_region_id,
            region_locations,
        )

    def _try_update_uncontested_movement_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
    ) -> pl.DataFrame | None:
        return self._movement_batch_updater.try_update_uncontested(
            state,
            units,
            current_minute,
            self._try_update_final_leg_movement_batch,
        )

    def _try_update_final_leg_movement_batch(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        routes: pl.DataFrame,
    ) -> pl.DataFrame | None:
        return self._movement_batch_updater.try_update_final_leg(
            state,
            units,
            current_minute,
            routes,
        )

    def _update_unit_movements(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        capability_speed_by_unit: dict[str, float] | None = None,
    ) -> pl.DataFrame:
        if self._unit_movement_is_idle(units):
            return units

        batched = self._try_update_uncontested_movement_batch(state, units, current_minute)
        if batched is not None:
            return batched

        updated_rows = self._movement_progression.update_rows(
            state,
            units,
            current_minute,
            capability_speed_by_unit,
        )
        return self._units_from_rows(updated_rows)

    def _unit_movement_is_idle(self, units: pl.DataFrame) -> bool:
        if units.is_empty():
            return True
        if not {"is_moving", "movement_progress"}.issubset(units.columns):
            return False
        is_moving = units.get_column("is_moving").fill_null(False)
        has_stale_progress = (units.get_column("movement_progress").fill_null(0.0) != 0.0).any()
        return not is_moving.any() and not has_stale_progress

    def _first_hostile_contact(
        self,
        moving_unit: dict[str, Any],
        unit_rows: Iterable[dict[str, Any]],
        start: GeoCoordinate,
        end: GeoCoordinate,
        current_minute: int,
    ) -> tuple[dict[str, Any], float] | None:
        return self._movement_progression.first_hostile_contact(
            moving_unit,
            unit_rows,
            start,
            end,
            current_minute,
        )

    def _unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate:
        return self._movement_progression.unit_geo_at(row, current_minute)

    def _stop_unit_at(self, row: dict[str, Any], geo: GeoCoordinate, current_minute: int) -> None:
        self._movement_progression.stop_unit_at(row, geo, current_minute)

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
        return self._unit_factory.next_id(unit_rows, country_tag, unit_type)

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
