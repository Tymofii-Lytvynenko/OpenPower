"""Per-force battle posture commands layered over the existing two-side resolver."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import polars as pl

from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.military_system import MovementDurationPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from modules.base.systems.military.war_policy import hostile_country_pairs
from src.core.map.geo import GeoCoordinate
from src.core.map.engagement_geometry import interpolate_geo
from src.shared.actions import ActionOccupyRegion, ActionSetBattleStrategy
from src.shared.events import DomainGameEvent, EventOccupationChanged
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


POSTURE_PROJECTIONS = {
    "attack": {
        "attack_modifier": 1.10, "defense_modifier": 1.00, "casualty_modifier": 1.10,
        "attack_risk_modifier": 1.15, "readiness_modifier": 0.95,
        "holding_modifier": 0.90, "counterattack_modifier": 0.85,
    },
    "defend": {
        "attack_modifier": 0.96, "defense_modifier": 1.15, "casualty_modifier": 0.82,
        "attack_risk_modifier": 0.85, "readiness_modifier": 1.00,
        "holding_modifier": 1.15, "counterattack_modifier": 1.15,
    },
    "hold": {
        "attack_modifier": 1.00, "defense_modifier": 1.00, "casualty_modifier": 0.95,
        "attack_risk_modifier": 1.00, "readiness_modifier": 1.00,
        "holding_modifier": 1.00, "counterattack_modifier": 1.00,
    },
    "back_off": {
        "attack_modifier": 0.82, "defense_modifier": 1.00, "casualty_modifier": 0.75,
        "attack_risk_modifier": 0.85, "readiness_modifier": 0.85,
        "holding_modifier": 1.05, "counterattack_modifier": 0.75,
    },
    "retreat": {
        "attack_modifier": 0.65, "defense_modifier": 1.00, "casualty_modifier": 0.70,
        "attack_risk_modifier": 0.85, "readiness_modifier": 0.75,
        "holding_modifier": 0.95, "counterattack_modifier": 0.50,
    },
    "reorganize": {
        "attack_modifier": 0.60, "defense_modifier": 1.00, "casualty_modifier": 0.75,
        "attack_risk_modifier": 0.80, "readiness_modifier": 0.60,
        "holding_modifier": 1.00, "counterattack_modifier": 0.40,
    },
}
PRESETS = {"attack_preset": "attack", "defend_preset": "defend", "defence_preset": "defend"}


@dataclass
class EventBattleCommandApplied(DomainGameEvent):
    order_id: str
    battle_id: str
    country_id: str
    strategy: str
    unit_ids: tuple[str, ...]
    at_minute: int


class BattleStrategySystem(ISystem):
    access = SystemAccess(
        reads=frozenset({"battles", "battle_units", "units", "regions", "region_adjacency", "country_governments", "treaty_effects", "countries_wars", "countries", "occupations", "battle_force_postures", "battle_command_orders", "unit_movement_routes"}),
        writes=frozenset({"units", "regions", "countries", "occupations", "battle_units", "battle_force_postures", "battle_command_orders", "unit_movement_routes"}),
        handles=frozenset({ActionSetBattleStrategy, ActionOccupyRegion}),
        phase=SystemPhase.MILITARY + 1,
    )

    @property
    def id(self) -> str:
        return "base.battle_strategy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.military"]

    def update(self, state: GameState, delta_time: float) -> None:
        if not {"units", "battles", "battle_force_postures", "battle_command_orders"}.issubset(state.tables):
            return
        posture_frame = state.get_table("battle_force_postures")
        has_due_state = any(row.get("status") in {"disengaging", "retreating", "reorganizing", "returning"} for row in posture_frame.to_dicts())
        if not any(isinstance(action, (ActionSetBattleStrategy, ActionOccupyRegion)) for action in state.current_actions) and not has_due_state:
            return
        units_frame = state.get_table("units")
        units = units_frame.to_dicts()
        battles = state.get_table("battles").to_dicts()
        participants_frame = state.tables.get("battle_units")
        participants = [] if participants_frame is None else participants_frame.to_dicts()
        postures = posture_frame.to_dicts()
        orders = state.get_table("battle_command_orders").to_dicts()
        routes_frame = state.tables.get("unit_movement_routes")
        routes = [] if routes_frame is None else routes_frame.to_dicts()
        unit_by_id = {str(row.get("id") or ""): row for row in units}
        now = int(state.time.total_minutes)
        # A stable order gives simultaneous overlapping commands a replayable winner:
        # broad orders apply first, then force-specific orders; ties resolve by issuer
        # and strategy name, independent of packet arrival order.
        for action in sorted(
            (action for action in state.current_actions if isinstance(action, (ActionSetBattleStrategy, ActionOccupyRegion))),
            key=self._command_sort_key,
        ):
            if isinstance(action, ActionOccupyRegion):
                self._occupy_cleared_region(state, action, units, orders, routes, now)
                continue
            if not isinstance(action, ActionSetBattleStrategy):
                continue
            battle = next((row for row in battles if str(row.get("id")) == str(action.battle_id) and str(row.get("status") or "active") == "active"), None)
            if battle is None:
                self._reject(state, action, "The battle is not active.")
                continue
            requested_country = self._tag(action.country_tag or action.player_id)
            mapping = state.globals.get("player_country_map", {})
            if isinstance(mapping, dict):
                requested_country = self._tag(action.country_tag or mapping.get(str(action.player_id)) or action.player_id)
            if not self._authorized(state, action.player_id, requested_country):
                self._reject(state, action, "The player cannot command this country's forces.")
                continue
            requested_strategy = str(action.strategy or "").strip().lower().replace(" ", "_")
            preset = self._resolve_preset(state, requested_strategy)
            strategy = preset.get("default", PRESETS.get(requested_strategy, requested_strategy))
            if strategy not in POSTURE_PROJECTIONS and not preset:
                self._reject(state, action, "The requested posture is not supported.")
                continue
            unit_type = str(action.unit_type or "all").strip().lower().replace(" ", "_")
            battle_region = int(battle.get("region_id") or 0)
            eligible_ids = {
                str(row.get("unit_id") or "") for row in participants
                if str(row.get("battle_id") or "") == str(action.battle_id)
                and self._tag(row.get("country_id")) == requested_country
            }
            if not eligible_ids:
                eligible_ids = {
                    str(row.get("id") or "") for row in units
                    if int(row.get("current_region_id") or 0) == battle_region
                    and self._tag(row.get("owner")) == requested_country
                    and not bool(row.get("is_moving"))
                }
            selected = [unit_by_id[unit_id] for unit_id in sorted(eligible_ids) if unit_id in unit_by_id and (unit_type == "all" or str(unit_by_id[unit_id].get("unit_type") or "").lower().replace(" ", "_") == unit_type)]
            if preset:
                selected = [unit for unit in selected if not self._has_specific_override(orders, action.battle_id, unit)]
            if not selected:
                self._reject(state, action, "No eligible force of the requested type participates in this battle.")
                continue
            resolved_strategies = [
                (unit, self._preset_strategy(preset, unit, strategy))
                for unit in selected
            ]
            scenario_rejection = next((
                reason
                for unit, unit_strategy in resolved_strategies
                if (reason := self._scenario_constraint_rejection(
                    state, str(action.battle_id), requested_country,
                    str(unit.get("unit_type") or "unit"), unit_strategy,
                )) is not None
            ), None)
            if scenario_rejection is not None:
                self._reject(state, action, scenario_rejection)
                continue
            affected: list[str] = []
            # A valid preset default must not hide an invalid per-type override from the commander.
            rejected_presets: list[str] = []
            for unit, unit_strategy in resolved_strategies:
                unit_id = str(unit.get("id") or "")
                if unit_strategy not in POSTURE_PROJECTIONS:
                    unit_type_name = str(unit.get("unit_type") or "unit")
                    rejected_presets.append(
                        f"{unit_type_name} {unit_id}: unsupported posture '{unit_strategy}'."
                    )
                    continue
                if unit_strategy == "retreat" and not self._begin_retreat(state, unit, requested_country, battle, routes):
                    self._reject(state, action, "No valid route to a safe capital location is available.")
                    continue
                if unit_strategy == "back_off" and not self._begin_back_off(state, unit, requested_country, battle, routes):
                    self._reject(state, action, "No valid route to a safe rear position is available.")
                    continue
                if unit_strategy == "reorganize" and not self._start_reorganization(state, unit, requested_country, postures, str(action.battle_id), str(action.player_id), now):
                    self._reject(state, action, "Reorganization requires a safe location and sufficient funds.")
                    continue
                projection = self._projection(state, unit_strategy)
                unit["combat_posture"] = unit_strategy
                unit["combat_strength_modifier"] = projection["attack_modifier"]
                unit["combat_casualty_modifier"] = projection["casualty_modifier"]
                unit["combat_defense_modifier"] = projection["defense_modifier"]
                unit["combat_attack_risk_modifier"] = projection["attack_risk_modifier"]
                unit["combat_readiness_modifier"] = projection["readiness_modifier"]
                unit["combat_holding_modifier"] = projection["holding_modifier"]
                unit["combat_counterattack_modifier"] = projection["counterattack_modifier"]
                if unit_strategy == "reorganize":
                    unit["combat_strength_modifier"] = 0.0
                if unit_strategy == "attack":
                    unit["engagement_mode"] = "assault"
                else:
                    unit["engagement_mode"] = ""
                affected.append(unit_id)
                old = next((row for row in postures if str(row.get("unit_id")) == unit_id), None)
                new = {
                    "unit_id": unit_id, "battle_id": str(action.battle_id), "country_id": requested_country,
                    "strategy": unit_strategy, "issuer_player_id": str(action.player_id),
                    "effective_at_minute": now, "expires_at_minute": int(unit.get("reorganization_until_minute") or 0),
                    "reason": "Commander order",
                    **projection,
                    "status": (
                        "retreating" if unit_strategy == "retreat"
                        else "disengaging" if unit_strategy == "back_off" and unit.get("is_moving")
                        else "reorganizing" if unit_strategy == "reorganize"
                        else "active"
                    ),
                }
                if old is None:
                    postures.append(new)
                else:
                    old.update(new)
            order_id = self._next_id("battle-order", orders)
            reason = " ".join(rejected_presets)
            orders.append({
                "id": order_id, "battle_id": str(action.battle_id), "country_id": requested_country,
                "unit_type": unit_type, "strategy": strategy, "issuer_player_id": str(action.player_id),
                "created_at_minute": now, "effective_at_minute": now,
                "status": "applied" if affected else "rejected",
                "reason": reason, "affected_unit_ids": affected,
            })
            if affected:
                state.events.append(EventBattleCommandApplied(order_id, str(action.battle_id), requested_country, strategy, tuple(affected), now))
            elif rejected_presets:
                self._reject(state, action, reason)

        self._advance_posture_lifecycle(state, units, postures, routes, battles, now)

        updated_units = pl.DataFrame(units, schema=units_frame.schema) if units else pl.DataFrame(schema=units_frame.schema)
        if not units_frame.equals(updated_units):
            state.update_table("units", updated_units)
        if postures != posture_frame.to_dicts():
            self._write(state, "battle_force_postures", postures)
        if orders != state.get_table("battle_command_orders").to_dicts():
            self._write(state, "battle_command_orders", orders)
        if routes_frame is not None and routes != routes_frame.to_dicts():
            state.update_table("unit_movement_routes", pl.DataFrame(routes, schema=routes_frame.schema) if routes else pl.DataFrame(schema=routes_frame.schema))

    def _begin_retreat(self, state, unit, owner, battle, route_rows):
        region_id = int(unit.get("current_region_id") or 0)
        regions_frame = state.tables.get("regions")
        if regions_frame is None or region_id <= 0:
            return False
        regions = regions_frame.to_dicts()
        duration_policy = MovementDurationPolicy()
        locations = duration_policy.region_locations(regions_frame)
        capital_plan = self._plan_capital_route(state, owner, region_id, regions, locations, duration_policy)
        if capital_plan is None:
            return False
        return self._begin_rear_withdrawal(
            state, unit, owner, battle, route_rows, locations, duration_policy,
            lifecycle="battle_retreating", route_status="retreating",
        )

    def _begin_back_off(self, state, unit, owner, battle, route_rows):
        region_id = int(unit.get("current_region_id") or 0)
        regions_frame = state.tables.get("regions")
        if regions_frame is None or region_id <= 0:
            return False
        duration_policy = MovementDurationPolicy()
        locations = duration_policy.region_locations(regions_frame)
        return self._begin_rear_withdrawal(
            state, unit, owner, battle, route_rows, locations, duration_policy,
            lifecycle="battle_disengaging", route_status="disengaging",
        )

    def _begin_rear_withdrawal(
        self, state, unit, owner, battle, route_rows, locations, duration_policy, *, lifecycle, route_status,
    ):
        region_id = int(unit.get("current_region_id") or 0)
        rear_geo = self._battle_rear_position(state, unit, owner, battle, locations)
        source_geo = self._unit_coordinate(unit, locations.get(region_id))
        if rear_geo is None or source_geo is None:
            return False
        now = int(state.time.total_minutes)
        duration = duration_policy.estimate_between(source_geo, rear_geo)
        unit.update(
            source_region_id=region_id, source_latitude=source_geo.latitude, source_longitude=source_geo.longitude,
            target_region_id=region_id, target_latitude=rear_geo.latitude, target_longitude=rear_geo.longitude,
            departed_at_minute=now, arrival_at_minute=now + duration,
            movement_progress=0.0, is_moving=True, engagement_mode="", unit_lifecycle=lifecycle,
        )
        route = next((row for row in route_rows if str(row.get("unit_id")) == str(unit.get("id"))), None)
        route_data = {
            "unit_id": str(unit.get("id")), "owner_country_id": owner,
            "source_region_id": region_id, "destination_region_id": region_id,
            "route_region_ids": [region_id], "route_index": 0,
            "destination_latitude": rear_geo.latitude,
            "destination_longitude": rear_geo.longitude,
            "has_custom_destination": False, "is_naval_invasion": False,
            "status": route_status, "rejection_reason": "",
            "updated_at_minute": now,
        }
        if route is None:
            route_rows.append(route_data)
        else:
            route.update(route_data)
        return True

    def _plan_capital_route(self, state, owner, region_id, regions, locations, duration_policy):
        governments = state.tables.get("country_governments")
        government = next((row for row in governments.to_dicts() if self._tag(row.get("country_id")) == owner), None) if governments is not None else None
        capital_id = int(government.get("capital_region_id") or 0) if government else 0
        if capital_id <= 0:
            return None
        access = MovementAccessPolicy()
        access_context = access.for_country(state, owner)
        adjacency = state.tables.get("region_adjacency")
        plan = MilitaryRoutePlanner().plan(
            region_id, capital_id, regions,
            None if adjacency is None else adjacency.to_dicts(),
            lambda region, final: access_context.can_station(region) if final else access_context.can_transit(region),
            segment_cost=lambda left, right: duration_policy.estimate_between(
                locations[int(left.get("id") or 0)], locations[int(right.get("id") or 0)],
            ) if int(left.get("id") or 0) in locations and int(right.get("id") or 0) in locations else 1440,
        )
        return (capital_id, plan) if plan.is_valid else None

    def _battle_rear_position(self, state, unit, owner, battle, locations):
        source = self._unit_coordinate(unit, locations.get(int(unit.get("current_region_id") or 0)))
        if source is None:
            return None
        participants = state.tables.get("battle_units")
        units_frame = state.tables.get("units")
        unit_by_id = {} if units_frame is None else {str(row.get("id") or ""): row for row in units_frame.to_dicts()}
        enemies = []
        if participants is not None:
            enemies = [
                unit_by_id.get(str(row.get("unit_id") or ""))
                for row in participants.to_dicts()
                if str(row.get("battle_id") or "") == str(battle.get("id") or "")
                and self._tag(row.get("country_id")) != owner
            ]
        enemy_points = [point for point in (self._unit_coordinate(item, None) for item in enemies if item is not None) if point is not None]
        if enemy_points:
            enemy_lat = sum(point.latitude for point in enemy_points) / len(enemy_points)
            enemy_lon = sum(point.longitude for point in enemy_points) / len(enemy_points)
            north = source.latitude - enemy_lat
            east = (source.longitude - enemy_lon) * max(0.05, abs(math.cos(math.radians(source.latitude))))
        else:
            anchor = None
            try:
                latitude = float(battle.get("anchor_latitude"))
                longitude = float(battle.get("anchor_longitude"))
                if -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0:
                    anchor = GeoCoordinate(latitude, longitude)
            except (TypeError, ValueError, OverflowError):
                anchor = locations.get(int(battle.get("region_id") or 0))
            north = source.latitude - anchor.latitude if anchor is not None else 0.0
            east = (source.longitude - anchor.longitude) * max(0.05, abs(math.cos(math.radians(source.latitude)))) if anchor is not None else 0.0
        magnitude = (north * north + east * east) ** 0.5
        if magnitude < 1e-8:
            side_a = {tag.strip().upper() for tag in str(battle.get("attacker_side") or "").split(",") if tag.strip()}
            east = -1.0 if owner in side_a else 1.0
            north = 0.0
            magnitude = 1.0
        north /= magnitude
        east /= magnitude
        distance_km = max(0.1, min(50.0, self._finite(state.globals.get("battle_rear_withdrawal_distance_km", 5.0))))
        latitude = max(-89.9, min(89.9, source.latitude + north * distance_km / 111.32))
        longitude_delta = east * distance_km / (111.32 * max(0.05, abs(math.cos(math.radians(source.latitude)))))
        longitude = ((source.longitude + longitude_delta + 180.0) % 360.0) - 180.0
        return GeoCoordinate(latitude, longitude)

    def _unit_coordinate(self, row, fallback):
        if row is None:
            return fallback
        try:
            latitude, longitude = float(row.get("latitude")), float(row.get("longitude"))
        except (TypeError, ValueError, OverflowError):
            return fallback
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            return fallback
        return GeoCoordinate(latitude, longitude)

    def _resolve_preset(self, state, name):
        configured = state.globals.get("battle_strategy_presets", {})
        row = configured.get(name) if isinstance(configured, dict) else None
        if isinstance(row, dict):
            return row
        posture = PRESETS.get(name)
        return {"default": posture} if posture else {}

    def _command_sort_key(self, action):
        if isinstance(action, ActionOccupyRegion):
            return (
                0, int(action.region_id), self._tag(action.new_controller_tag),
                str(action.player_id),
            )
        country = self._tag(action.country_tag or action.player_id)
        unit_type = str(action.unit_type or "all").strip().lower().replace(" ", "_")
        return (
            1, str(action.battle_id), country,
            0 if unit_type == "all" else 1, unit_type,
            str(action.player_id),
            str(action.strategy or "").strip().lower().replace(" ", "_"),
        )

    def _scenario_constraint_rejection(self, state, battle_id, country, unit_type, strategy):
        rules = state.globals.get("battle_strategy_constraints", [])
        if not isinstance(rules, list):
            return None
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("battle_id") not in (None, "", battle_id):
                continue
            if rule.get("country_id") not in (None, "", country):
                continue
            if rule.get("unit_type") not in (None, "", "all", unit_type):
                continue
            required = str(rule.get("required_strategy") or "").strip().lower().replace(" ", "_")
            allowed = rule.get("allowed_strategies")
            if required and strategy != required:
                return f"Scenario requires {required} for {country} {unit_type}."
            if isinstance(allowed, list):
                normalized = {
                    str(value).strip().lower().replace(" ", "_")
                    for value in allowed
                }
                if strategy not in normalized:
                    return f"Scenario does not allow {strategy} for {country} {unit_type}."
        return None

    def _preset_strategy(self, preset, unit, fallback):
        if not preset:
            return fallback
        by_type = preset.get("unit_types", {})
        unit_type = str(unit.get("unit_type") or "").lower().replace(" ", "_")
        return str(by_type.get(unit_type, preset.get("default", fallback))).strip().lower().replace(" ", "_") if isinstance(by_type, dict) else str(preset.get("default", fallback))

    def _has_specific_override(self, orders, battle_id, unit):
        unit_id = str(unit.get("id") or "")
        return any(
            str(order.get("battle_id") or "") == str(battle_id)
            and str(order.get("unit_type") or "all") != "all"
            and order.get("status") == "applied"
            and unit_id in (order.get("affected_unit_ids") or [])
            for order in orders
        )

    def _projection(self, state, strategy):
        configured = state.globals.get("battle_posture_projections", {})
        row = configured.get(strategy) if isinstance(configured, dict) else None
        baseline = POSTURE_PROJECTIONS[strategy]
        bounds = {
            "attack_modifier": (0.0, 1.5),
            "defense_modifier": (0.5, 1.5),
            "casualty_modifier": (0.5, 1.5),
            "attack_risk_modifier": (0.5, 1.5),
            "readiness_modifier": (0.0, 1.5),
            "holding_modifier": (0.5, 1.5),
            "counterattack_modifier": (0.0, 1.5),
        }
        overrides = row if isinstance(row, dict) else {}
        return {
            name: max(lower, min(upper, self._finite(overrides.get(name, baseline[name]))))
            for name, (lower, upper) in bounds.items()
        }

    def _start_reorganization(self, state, unit, owner, postures, battle_id, player_id, now):
        region_frame = state.tables.get("regions")
        region_id = int(unit.get("current_region_id") or 0)
        region = None if region_frame is None else next((row for row in region_frame.to_dicts() if int(row.get("id") or 0) == region_id), None)
        if region is None or self._tag(region.get("owner")) != owner and self._tag(region.get("controller")) != owner:
            return False
        countries_frame = state.tables.get("countries")
        if countries_frame is None:
            return False
        countries = countries_frame.to_dicts()
        country = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        cost = max(0.0, self._finite(state.globals.get("battle_reorganization_cost_per_strength", 0.01))) * max(0, int(unit.get("strength") or 0))
        if country is None or self._finite(country.get("money_reserves")) < cost:
            return False
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        state.update_table("countries", pl.DataFrame(countries, schema=countries_frame.schema))
        duration = max(1, int(self._finite(state.globals.get("battle_reorganization_minutes", 720))))
        unit["cohesion"] = max(0.0, min(1.0, self._finite(unit.get("cohesion") or 1.0) * 0.6))
        unit["reorganization_until_minute"] = now + duration
        unit["unit_lifecycle"] = "reorganizing"
        return True

    def _advance_posture_lifecycle(self, state, units, postures, routes, battles, now):
        if state.time.is_paused:
            return
        unit_by_id = {str(row.get("id") or ""): row for row in units}
        route_by_id = {str(row.get("unit_id") or ""): row for row in routes}
        battle_by_id = {str(row.get("id") or ""): row for row in battles}
        for posture in postures:
            unit = unit_by_id.get(str(posture.get("unit_id") or ""))
            if unit is None or int(unit.get("strength") or 0) <= 0:
                posture.update(status="cancelled", reason="The commanded force no longer exists.")
                continue
            if posture.get("strategy") == "back_off" and posture.get("status") == "disengaging":
                route = route_by_id.get(str(unit.get("id") or ""))
                battle = battle_by_id.get(str(posture.get("battle_id") or ""), {})
                if str(battle.get("status") or "active").strip().lower() not in {"active", "stalemate", "ongoing", ""}:
                    if bool(unit.get("is_moving")) and unit.get("unit_lifecycle") == "battle_disengaging":
                        self._stop_tactical_withdrawal(unit, now)
                    if route is not None:
                        route.update(status="interrupted", rejection_reason="The battle concluded before disengagement completed.", updated_at_minute=now)
                    self._reset_combat_projection(unit)
                    posture.update(status="cancelled", reason="The battle concluded before disengagement completed.")
                elif route is None or route.get("status") in {"blocked", "interrupted"}:
                    posture.update(
                        status="blocked",
                        reason=str((route or {}).get("rejection_reason") or "The disengagement route became unavailable."),
                    )
                    unit.update(is_moving=False, engagement_mode="", unit_lifecycle="available")
                elif route.get("status") == "arrived" and not bool(unit.get("is_moving")):
                    posture.update(status="active", expires_at_minute=0, reason="Disengaged to the rear position; holding without initiating an assault.")
                    unit.update(unit_lifecycle="available", engagement_mode="")
                continue
            if posture.get("strategy") == "retreat" and posture.get("status") in {"retreating", "reorganizing", "returning"}:
                battle = battle_by_id.get(str(posture.get("battle_id") or ""), {})
                if str(battle.get("status") or "active").strip().lower() not in {"active", "stalemate", "ongoing", ""}:
                    route = route_by_id.get(str(unit.get("id") or ""))
                    if bool(unit.get("is_moving")) and str(unit.get("unit_lifecycle") or "") in {"battle_retreating", "battle_returning"}:
                        progress = max(0.0, min(1.0, float(unit.get("movement_progress") or 0.0)))
                        elapsed = now - int(unit.get("departed_at_minute") or now)
                        duration = max(1, int(unit.get("arrival_at_minute") or now) - int(unit.get("departed_at_minute") or now))
                        progress = max(progress, max(0.0, min(1.0, elapsed / duration)))
                        source = GeoCoordinate(float(unit.get("source_latitude") or 0.0), float(unit.get("source_longitude") or 0.0))
                        target = GeoCoordinate(float(unit.get("target_latitude") or 0.0), float(unit.get("target_longitude") or 0.0))
                        stopped = interpolate_geo(source, target, progress)
                        unit.update(
                            latitude=stopped.latitude, longitude=stopped.longitude,
                            source_latitude=stopped.latitude, source_longitude=stopped.longitude,
                            target_latitude=stopped.latitude, target_longitude=stopped.longitude,
                            movement_progress=0.0, is_moving=False, unit_lifecycle="available",
                        )
                    self._reset_combat_projection(unit)
                    unit["reorganization_until_minute"] = 0
                    if route is not None:
                        route.update(status="interrupted", rejection_reason="The battle concluded before the retreat completed.", updated_at_minute=now)
                    posture.update(status="cancelled", reason="The battle concluded before the retreat completed.")
                    continue
            if posture.get("strategy") == "retreat" and posture.get("status") == "retreating":
                route = route_by_id.get(str(unit.get("id") or ""))
                if route is None or route.get("status") in {"blocked", "interrupted"}:
                    reason = str((route or {}).get("rejection_reason") or "The retreat route became unavailable.")
                    posture.update(status="blocked", reason=reason)
                    projection = self._projection(state, "back_off")
                    unit.update(
                        combat_posture="back_off", unit_lifecycle="available", is_moving=False, engagement_mode="",
                        combat_strength_modifier=projection["attack_modifier"],
                        combat_defense_modifier=projection["defense_modifier"],
                        combat_casualty_modifier=projection["casualty_modifier"],
                        combat_attack_risk_modifier=projection["attack_risk_modifier"],
                        combat_readiness_modifier=projection["readiness_modifier"],
                        combat_holding_modifier=projection["holding_modifier"],
                        combat_counterattack_modifier=projection["counterattack_modifier"],
                    )
                    continue
                if route.get("status") == "arrived" and not bool(unit.get("is_moving")):
                    regroup = max(1, int(self._finite(state.globals.get("battle_regroup_minutes", 720))))
                    posture.update(status="reorganizing", effective_at_minute=now, expires_at_minute=now + regroup, reason="Withdrawn to the rear position; regrouping before returning to the capital.")
                    unit.update(combat_posture="reorganize", combat_strength_modifier=0.0, combat_casualty_modifier=1.0, combat_defense_modifier=1.0, reorganization_until_minute=now + regroup, unit_lifecycle="reorganizing")

            if posture.get("strategy") == "retreat" and posture.get("status") == "reorganizing" and now >= int(posture.get("expires_at_minute") or 0):
                if self._begin_return_to_capital(state, unit, self._tag(posture.get("country_id")), routes, now):
                    posture.update(status="returning", effective_at_minute=now, expires_at_minute=0, reason="Regrouped; returning toward the capital.")
                    self._remove_battle_participant(state, str(posture.get("battle_id") or ""), str(unit.get("id") or ""))
                else:
                    posture.update(status="blocked", reason="Regrouping completed, but no valid route to the capital remains.")
                    unit.update(combat_posture="back_off", unit_lifecycle="available", reorganization_until_minute=0)
                continue

            if posture.get("strategy") == "retreat" and posture.get("status") == "returning":
                route = route_by_id.get(str(unit.get("id") or ""))
                if route is None or route.get("status") in {"blocked", "interrupted"}:
                    reason = str((route or {}).get("rejection_reason") or "The return route became unavailable.")
                    posture.update(status="blocked", reason=reason)
                    unit.update(combat_posture="back_off", unit_lifecycle="available", reorganization_until_minute=0)
                elif route.get("status") == "arrived" and not bool(unit.get("is_moving")):
                    self._reset_combat_projection(unit)
                    unit.update(cohesion=1.0, reorganization_until_minute=0, unit_lifecycle="available")
                    posture.update(status="completed", reason="The force regrouped and returned to its capital route destination.")
                continue

            if posture.get("strategy") != "retreat" and posture.get("status") == "reorganizing" and now >= int(posture.get("expires_at_minute") or 0):
                self._reset_combat_projection(unit)
                unit.update(cohesion=1.0, reorganization_until_minute=0, unit_lifecycle="available")
                posture.update(status="completed", strategy="hold", reason="Regrouping is complete; force is available.")

    def _remove_battle_participant(self, state, battle_id, unit_id):
        participants = state.tables.get("battle_units")
        if participants is None or participants.is_empty():
            return
        remaining = participants.filter(
            ~((pl.col("battle_id") == battle_id) & (pl.col("unit_id") == unit_id))
        )
        if not participants.equals(remaining):
            state.update_table("battle_units", remaining)

    def _reset_combat_projection(self, unit):
        unit.update(
            combat_posture="hold", combat_strength_modifier=1.0,
            combat_casualty_modifier=1.0, combat_defense_modifier=1.0,
            combat_attack_risk_modifier=1.0, combat_readiness_modifier=1.0,
            combat_holding_modifier=1.0, combat_counterattack_modifier=1.0,
        )

    def _stop_tactical_withdrawal(self, unit, now):
        progress = max(0.0, min(1.0, float(unit.get("movement_progress") or 0.0)))
        departed = int(unit.get("departed_at_minute") or now)
        duration = max(1, int(unit.get("arrival_at_minute") or now) - departed)
        progress = max(progress, max(0.0, min(1.0, (now - departed) / duration)))
        source = GeoCoordinate(float(unit.get("source_latitude") or 0.0), float(unit.get("source_longitude") or 0.0))
        target = GeoCoordinate(float(unit.get("target_latitude") or 0.0), float(unit.get("target_longitude") or 0.0))
        stopped = interpolate_geo(source, target, progress)
        unit.update(
            latitude=stopped.latitude, longitude=stopped.longitude,
            source_latitude=stopped.latitude, source_longitude=stopped.longitude,
            target_latitude=stopped.latitude, target_longitude=stopped.longitude,
            movement_progress=0.0, is_moving=False, unit_lifecycle="available",
        )

    def _begin_return_to_capital(self, state, unit, owner, route_rows, now):
        regions_frame = state.tables.get("regions")
        if regions_frame is None:
            return False
        regions = regions_frame.to_dicts()
        duration_policy = MovementDurationPolicy()
        locations = duration_policy.region_locations(regions_frame)
        source_region_id = int(unit.get("current_region_id") or 0)
        capital_plan = self._plan_capital_route(state, owner, source_region_id, regions, locations, duration_policy)
        if capital_plan is None:
            return False
        capital_id, plan = capital_plan
        regions_by_id = {int(row.get("id") or 0): row for row in regions}
        capital_geo = locations.get(capital_id)
        if capital_geo is None:
            return False

        if len(plan.region_ids) > 1:
            next_region_id = plan.region_ids[1]
            next_geo = locations.get(next_region_id)
            if next_geo is None or next_region_id not in regions_by_id:
                return False
            source_geo = self._unit_coordinate(unit, locations.get(source_region_id))
            if source_geo is None:
                return False
            arrival = now + duration_policy.estimate_between(source_geo, next_geo)
            unit.update(
                source_region_id=source_region_id, source_latitude=source_geo.latitude, source_longitude=source_geo.longitude,
                target_region_id=next_region_id, target_latitude=next_geo.latitude, target_longitude=next_geo.longitude,
                departed_at_minute=now, arrival_at_minute=arrival, movement_progress=0.0,
                is_moving=True, engagement_mode="", unit_lifecycle="battle_returning",
            )
            route_index = 1
            route_status = "retreating"
        else:
            unit.update(
                source_region_id=capital_id, source_latitude=capital_geo.latitude, source_longitude=capital_geo.longitude,
                target_region_id=capital_id, target_latitude=capital_geo.latitude, target_longitude=capital_geo.longitude,
                departed_at_minute=now, arrival_at_minute=now, movement_progress=0.0,
                is_moving=False, engagement_mode="", unit_lifecycle="battle_returning",
                latitude=capital_geo.latitude, longitude=capital_geo.longitude,
            )
            route_index = 0
            route_status = "arrived"

        route = next((row for row in route_rows if str(row.get("unit_id") or "") == str(unit.get("id") or "")), None)
        route_data = {
            "unit_id": str(unit.get("id") or ""), "owner_country_id": owner,
            "source_region_id": source_region_id, "destination_region_id": capital_id,
            "route_region_ids": list(plan.region_ids), "route_index": route_index,
            "destination_latitude": capital_geo.latitude, "destination_longitude": capital_geo.longitude,
            "has_custom_destination": False, "is_naval_invasion": False,
            "status": route_status, "rejection_reason": "", "updated_at_minute": now,
        }
        if route is None:
            route_rows.append(route_data)
        else:
            route.update(route_data)
        return True

    def _occupy_cleared_region(self, state, action, units, orders, routes, now):
        owner = self._tag(action.new_controller_tag)
        if not owner or not self._authorized(state, action.player_id, owner):
            self._reject(state, action, "The player cannot command this country's forces.")
            return
        regions_frame = state.tables.get("regions")
        if regions_frame is None:
            self._reject(state, action, "The target region does not exist.")
            return
        regions = regions_frame.to_dicts()
        target = next((row for row in regions if int(row.get("id") or 0) == int(action.region_id)), None)
        if target is None or self._tag(target.get("owner")) == owner:
            self._reject(state, action, "Occupation requires a valid foreign-owned region.")
            return
        target_country = self._tag(target.get("owner"))
        wars = state.tables.get("countries_wars")
        hostile = hostile_country_pairs([] if wars is None else wars.to_dicts())
        if frozenset((owner, target_country)) not in hostile:
            self._reject(state, action, "Occupation requires an active hostile conflict.")
            return
        target_region_ids = {int(row.get("id") or 0) for row in regions if self._tag(row.get("owner")) == target_country}
        if any(
            frozenset((owner, self._tag(unit.get("owner")))) in hostile
            and int(unit.get("strength") or 0) > 0
            and not bool(unit.get("is_moving"))
            and int(unit.get("current_region_id") or 0) in target_region_ids
            for unit in units
        ):
            self._reject(state, action, "Hostile forces remain in the target country.")
            return
        controlled_ids = sorted({
            int(unit.get("current_region_id") or 0) for unit in units
            if self._tag(unit.get("owner")) == owner and int(unit.get("strength") or 0) > 0
            and not bool(unit.get("is_moving")) and int(unit.get("current_region_id") or 0) in target_region_ids
        })
        if int(target.get("id") or 0) not in controlled_ids:
            self._reject(state, action, "No eligible force is stationed in the requested region.")
            return
        self._plan_occupation_distribution(state, owner, target_country_ids=target_region_ids, occupied_region_ids=set(controlled_ids), units=units, routes=routes, now=now)
        previous_controllers = {
            int(row.get("id") or 0): self._tag(row.get("controller"))
            for row in regions if int(row.get("id") or 0) in controlled_ids
        }
        for row in regions:
            if int(row.get("id") or 0) in controlled_ids:
                row["controller"] = owner
                if previous_controllers.get(int(row.get("id") or 0)) != owner:
                    state.events.append(EventOccupationChanged(
                        region_id=int(row.get("id") or 0),
                        previous_controller=previous_controllers.get(int(row.get("id") or 0), ""),
                        controller=owner,
                        source="occupation_order",
                        at_minute=now,
                    ))
        state.update_table("regions", pl.DataFrame(regions, schema=regions_frame.schema))
        occupation_frame = state.tables.get("occupations")
        if occupation_frame is not None:
            occupation_rows = occupation_frame.to_dicts()
            for region_id in controlled_ids:
                current = next((row for row in occupation_rows if int(row.get("region_id") or 0) == region_id), None)
                garrison_strength = sum(
                    max(0, int(unit.get("strength") or 0))
                    for unit in units
                    if self._tag(unit.get("owner")) == owner
                    and int(unit.get("current_region_id") or 0) == region_id
                    and not bool(unit.get("is_moving"))
                )
                record = current or {"region_id": region_id}
                record.update(
                    controller_country_id=owner,
                    garrison_strength=garrison_strength,
                    occupation_status="active",
                    started_at_minute=int(record.get("started_at_minute") or now),
                    updated_at_minute=now,
                    contested=False,
                )
                if current is None:
                    occupation_rows.append(record)
            state.update_table("occupations", pl.DataFrame(occupation_rows, schema=occupation_frame.schema))
        affected = [str(unit.get("id")) for unit in units if self._tag(unit.get("owner")) == owner and int(unit.get("current_region_id") or 0) in controlled_ids]
        order_id = self._next_id("battle-order", orders)
        orders.append({
            "id": order_id, "battle_id": f"occupation-{action.region_id}", "country_id": owner,
            "unit_type": "all", "strategy": "occupy", "issuer_player_id": str(action.player_id),
            "created_at_minute": now, "effective_at_minute": now, "status": "applied",
            "reason": "Military control established; political ownership is unchanged.", "affected_unit_ids": affected,
        })
        state.events.append(EventBattleCommandApplied(order_id, f"occupation-{action.region_id}", owner, "occupy", tuple(affected), now))
        state.journal.append_command_result({"tick": int(state.globals.get("tick", 0)), "player_id": str(action.player_id), "action_type": type(action).__name__, "status": "applied", "reason": "Military control established; political ownership is unchanged."})

    def _plan_occupation_distribution(self, state, owner, *, target_country_ids, occupied_region_ids, units, routes, now):
        if "unit_movement_routes" not in state.tables:
            return
        regions_frame = state.tables.get("regions")
        if regions_frame is None or regions_frame.is_empty():
            return
        regions = regions_frame.to_dicts()
        duration_policy = MovementDurationPolicy()
        locations = duration_policy.region_locations(regions_frame)
        adjacency_frame = state.tables.get("region_adjacency")
        adjacency = [] if adjacency_frame is None else adjacency_frame.to_dicts()
        access = MovementAccessPolicy().for_country(state, owner)
        planner = MilitaryRoutePlanner()
        garrison_counts: dict[int, int] = {}
        surplus_units = []
        for unit in sorted(units, key=lambda row: str(row.get("id") or "")):
            region_id = int(unit.get("current_region_id") or 0)
            if (
                self._tag(unit.get("owner")) != owner
                or region_id not in target_country_ids
                or int(unit.get("strength") or 0) <= 0
                or bool(unit.get("is_moving"))
            ):
                continue
            garrison_counts[region_id] = garrison_counts.get(region_id, 0) + 1
            surplus_units.append(unit)

        surplus_units = [unit for unit in surplus_units if garrison_counts.get(int(unit.get("current_region_id") or 0), 0) > 1]
        unoccupied_targets = sorted(set(target_country_ids) - set(occupied_region_ids))
        for target_region_id in unoccupied_targets:
            legal_assignments = []
            for unit in surplus_units:
                source_region_id = int(unit.get("current_region_id") or 0)
                if garrison_counts.get(source_region_id, 0) <= 1:
                    continue
                plan = planner.plan(
                    source_region_id,
                    target_region_id,
                    regions,
                    adjacency,
                    lambda region, final: access.can_station(region) if final else access.can_transit(region),
                    segment_cost=lambda left, right: duration_policy.estimate_between(
                        locations[int(left.get("id") or 0)], locations[int(right.get("id") or 0)],
                    ) if int(left.get("id") or 0) in locations and int(right.get("id") or 0) in locations else 1440,
                )
                if plan.is_valid and len(plan.region_ids) > 1:
                    legal_assignments.append((plan.travel_cost, str(unit.get("id") or ""), unit, plan))
            if not legal_assignments:
                continue
            _, _, unit, plan = min(legal_assignments, key=lambda item: (item[0], item[1], target_region_id))
            if not self._start_occupation_route(state, owner, unit, plan, routes, locations, duration_policy, now):
                continue
            source_region_id = int(unit.get("current_region_id") or 0)
            garrison_counts[source_region_id] = garrison_counts.get(source_region_id, 0) - 1
            surplus_units.remove(unit)

    def _start_occupation_route(self, state, owner, unit, plan, routes, locations, duration_policy, now):
        source_region_id = int(unit.get("current_region_id") or 0)
        next_region_id = int(plan.region_ids[1])
        source_geo = self._unit_coordinate(unit, locations.get(source_region_id))
        target_geo = locations.get(next_region_id)
        destination_id = int(plan.region_ids[-1])
        destination_geo = locations.get(destination_id)
        if source_geo is None or target_geo is None or destination_geo is None:
            return False
        unit.update(
            source_region_id=source_region_id, source_latitude=source_geo.latitude, source_longitude=source_geo.longitude,
            target_region_id=next_region_id, target_latitude=target_geo.latitude, target_longitude=target_geo.longitude,
            departed_at_minute=now, arrival_at_minute=now + duration_policy.estimate_between(source_geo, target_geo),
            movement_progress=0.0, is_moving=True, engagement_mode="", unit_lifecycle="occupation_moving",
        )
        route = next((row for row in routes if str(row.get("unit_id") or "") == str(unit.get("id") or "")), None)
        route_data = {
            "unit_id": str(unit.get("id") or ""), "owner_country_id": owner,
            "source_region_id": source_region_id, "destination_region_id": destination_id,
            "route_region_ids": list(plan.region_ids), "route_index": 1,
            "destination_latitude": destination_geo.latitude, "destination_longitude": destination_geo.longitude,
            "has_custom_destination": False, "is_naval_invasion": False,
            "status": "moving", "rejection_reason": "", "updated_at_minute": now,
        }
        if route is None:
            routes.append(route_data)
        else:
            route.update(route_data)
        return True

    def _reject(self, state, action, reason):
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)), "player_id": str(action.player_id),
            "action_type": type(action).__name__, "status": "rejected", "reason": reason,
        })

    def _authorized(self, state, player_id, country):
        return player_controls_country(state, player_id, country)

    def _write(self, state, name, rows):
        frame = state.get_table(name)
        state.update_table(name, pl.DataFrame(rows, schema=frame.schema) if rows else pl.DataFrame(schema=frame.schema))

    def _next_id(self, prefix, rows):
        return f"{prefix}-{len(rows) + 1:08d}"

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _finite(self, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
