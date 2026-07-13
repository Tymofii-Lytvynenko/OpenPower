from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE, SYSTEM_STATE_HELPER
from src.shared.state import GameState
from src.shared.actions import ActionAttackUnit, ActionBuildUnit, ActionBuyMarketUnit, ActionMoveUnit
from src.core.map.geo import EquirectangularProjection, GeoCoordinate, MapPixelCoordinate
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from src.shared.engagement import countries_are_hostile, engagement_radius_km, first_zone_contact_fraction, interpolate_geo


UNIT_TABLE = "units"
NO_TARGET_REGION = -1
DEFAULT_UNIT_TYPE = "army"
DEFAULT_MOVE_MINUTES = 1440

UNIT_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "owner": pl.Utf8,
    "unit_type": pl.Utf8,
    "strength": pl.Int64,
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
    ) -> dict[str, Any]:
        safe_strength = max(1, int(strength))
        return {
            "id": unit_id,
            "owner": owner,
            "unit_type": unit_type or DEFAULT_UNIT_TYPE,
            "strength": safe_strength,
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
        }


class MilitarySystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'production_orders', 'unit_designs', 'countries_wars'}),
        writes=frozenset({'countries', 'units', 'production_orders', 'unit_market_listings'}),
        handles=frozenset(
            {
                ActionAttackUnit,
                ActionBuildUnit,
                ActionBuyMarketUnit,
                ActionMoveUnit,
            }
        ),
        phase=SystemPhase.MILITARY,
    )
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_duration_policy": SYSTEM_STATE_HELPER,
        "_unit_factory": SYSTEM_STATE_HELPER,
        "_access_policy": SYSTEM_STATE_HELPER,
        "_weapons_trade_policy": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._missing_columns = set()
        self._duration_policy = MovementDurationPolicy()
        self._unit_factory = UnitFactory()
        self._access_policy = MovementAccessPolicy()
        self._weapons_trade_policy = WeaponsTradePolicy()

    @property
    def id(self) -> str:
        return "base.military"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.population", "base.economy", "base.diplomacy", "base.military_programs"]

    def update(self, state: GameState, delta_time: float) -> None:
        units = self._ensure_units_table(state)
        units = self._process_completed_production_orders(state, units)
        units = self._process_build_actions(state, units)
        units = self._process_market_buy_actions(state, units)
        units = self._process_move_actions(state, units)
        units = self._process_attack_actions(state, units)
        units = self._update_unit_movements(state, units, state.time.total_minutes)
        state.update_table(UNIT_TABLE, units)

        from src.shared.events import EventNewDay
        has_new_day = any(isinstance(e, EventNewDay) for e in state.events)
        if has_new_day and not state.time.is_paused and state.time.day % 7 == 1:
            self._update_manpower(state)

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
        country_strength = self._country_strengths(countries)
        current_minute = state.time.total_minutes
        rows = []

        for country_tag in countries["id"].to_list():
            clean_tag = str(country_tag)
            if clean_tag not in home_regions:
                continue

            home_region_id = home_regions[clean_tag]
            home_geo = region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0))
            rows.append(
                self._unit_factory.create(
                    unit_id=f"{clean_tag}-{DEFAULT_UNIT_TYPE}-001",
                    owner=clean_tag,
                    unit_type=DEFAULT_UNIT_TYPE,
                    strength=country_strength.get(clean_tag, 1),
                    region_id=home_region_id,
                    geo=home_geo,
                    current_minute=current_minute,
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
            str(row["id"]): max(1, int(row["military_count"] or 0))
            for row in countries.select(["id", "military_count"]).iter_rows(named=True)
            if row["id"] is not None
        }

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
        changed = False

        for order in order_rows:
            if str(order.get("status") or "").lower() != "completed":
                continue
            country_tag = str(order.get("country_id") or "").strip().upper()
            country = countries_by_tag.get(country_tag)
            design = designs_by_id.get(str(order.get("design_id") or ""))
            quantity = max(0, int(order.get("quantity") or 0))
            if country is None or design is None or quantity <= 0:
                continue
            if str(design.get("country_id") or "").strip().upper() != country_tag:
                continue
            home_region_id = home_regions.get(str(country.get("id") or ""))
            if home_region_id is None:
                continue

            unit_type = str(design.get("class_name") or DEFAULT_UNIT_TYPE).strip().lower().replace(" ", "_")
            unit_type = unit_type or DEFAULT_UNIT_TYPE
            owner = str(country.get("id") or country_tag)
            unit_rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(unit_rows, owner, unit_type),
                    owner=owner,
                    unit_type=unit_type,
                    strength=quantity,
                    region_id=home_region_id,
                    geo=region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0)),
                    current_minute=state.time.total_minutes,
                )
            )
            country["military_count"] = int(country.get("military_count") or 0) + quantity
            order["status"] = "delivered"
            order["eta_days"] = 0
            changed = True

        if not changed:
            return units
        state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        state.update_table("production_orders", pl.DataFrame(order_rows, schema=orders_table.schema))
        return self._units_from_rows(unit_rows)

    def _process_build_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions_to_process = [a for a in state.current_actions if isinstance(a, ActionBuildUnit)]
        if not actions_to_process:
            return units

        countries = self._ensure_country_columns(state.get_table("countries"))
        regions = state.get_table("regions")
        home_regions = self._home_regions_by_country(regions)
        region_locations = self._duration_policy.region_locations(regions)
        rows = units.to_dicts()

        for action in actions_to_process:
            cost = 1_000_000 * action.count
            countries = countries.with_columns(
                pl.when(pl.col("id") == action.country_tag)
                .then(pl.col("military_count") + action.count)
                .otherwise(pl.col("military_count"))
                .alias("military_count"),
                pl.when(pl.col("id") == action.country_tag)
                .then(pl.col("money_reserves") - cost)
                .otherwise(pl.col("money_reserves"))
                .alias("money_reserves"),
            )

            home_region_id = home_regions.get(action.country_tag)
            if home_region_id is None:
                continue
            home_geo = region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0))

            rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(rows, action.country_tag, action.unit_type),
                    owner=action.country_tag,
                    unit_type=action.unit_type,
                    strength=action.count,
                    region_id=home_region_id,
                    geo=home_geo,
                    current_minute=state.time.total_minutes,
                )
            )

        state.update_table("countries", countries)
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
        listing_rows = listings_table.to_dicts()
        listings_by_id = {str(row.get("id") or ""): row for row in listing_rows}
        country_rows = countries.to_dicts()
        countries_by_tag = {str(row.get("id") or "").strip().upper(): row for row in country_rows}
        design_rows = state.tables.get("unit_designs")
        designs_by_id = {} if design_rows is None else {
            str(row.get("id") or ""): str(row.get("class_name") or DEFAULT_UNIT_TYPE)
            for row in design_rows.to_dicts()
        }
        unit_rows = units.to_dicts()
        changed = False

        for action in actions:
            listing = listings_by_id.get(str(action.listing_id))
            buyer_tag = str(action.buyer_country_tag or "").strip().upper()
            seller_tag = str(listing.get("seller_country_id") or "").strip().upper() if listing else ""
            buyer, seller = countries_by_tag.get(buyer_tag), countries_by_tag.get(seller_tag)
            if listing is None or buyer is None or seller is None:
                continue
            quantity = max(0, min(int(action.quantity), int(listing.get("quantity") or 0)))
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
            buyer["money_reserves"] = float(buyer.get("money_reserves") or 0.0) - total_cost
            buyer["military_count"] = int(buyer.get("military_count") or 0) + quantity
            seller["money_reserves"] = float(seller.get("money_reserves") or 0.0) + total_cost
            listing["quantity"] = int(listing.get("quantity") or 0) - quantity
            unit_type = designs_by_id.get(str(listing.get("design_id") or ""), DEFAULT_UNIT_TYPE)
            unit_type = unit_type.strip().lower().replace(" ", "_") or DEFAULT_UNIT_TYPE
            unit_rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(unit_rows, str(buyer.get("id") or buyer_tag), unit_type),
                    owner=str(buyer.get("id") or buyer_tag),
                    unit_type=unit_type,
                    strength=quantity,
                    region_id=home_region_id,
                    geo=region_locations.get(home_region_id, GeoCoordinate(0.0, 0.0)),
                    current_minute=state.time.total_minutes,
                )
            )
            changed = True

        if not changed:
            return units
        state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        remaining_listings = [row for row in listing_rows if int(row.get("quantity") or 0) > 0]
        state.update_table("unit_market_listings", pl.DataFrame(remaining_listings, schema=listings_table.schema))
        return self._units_from_rows(unit_rows)

    def _process_attack_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions = [action for action in state.current_actions if isinstance(action, ActionAttackUnit)]
        if not actions or units.is_empty():
            return units

        war_rows = state.tables.get("countries_wars")
        wars = [] if war_rows is None else war_rows.to_dicts()
        rows = units.to_dicts()
        units_by_id = {str(row.get("id") or ""): row for row in rows}
        now = int(state.time.total_minutes)
        changed = False

        for action in actions:
            attacker = units_by_id.get(str(action.attacker_unit_id or ""))
            defender = units_by_id.get(str(action.defender_unit_id or ""))
            if attacker is None or defender is None or attacker is defender:
                continue
            if int(attacker.get("strength") or 0) <= 0 or int(defender.get("strength") or 0) <= 0:
                continue
            if not countries_are_hostile(wars, str(attacker.get("owner") or ""), str(defender.get("owner") or "")):
                continue

            defender_geo = self._unit_geo_at(defender, now)
            self._stop_unit_at(attacker, defender_geo, now)
            self._stop_unit_at(defender, defender_geo, now)
            attacker["current_region_id"] = int(defender.get("current_region_id") or 0)
            attacker["engagement_mode"] = "assault"
            defender["engagement_mode"] = "assault"
            changed = True

        return self._units_from_rows(rows) if changed else units

    def _process_move_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        move_actions = [a for a in state.current_actions if isinstance(a, ActionMoveUnit)]
        if not move_actions or units.is_empty() or "regions" not in state.tables:
            return units

        valid_regions = set(state.get_table("regions")["id"].to_list())
        action_by_unit = {
            action.unit_id: action
            for action in move_actions
            if action.target_region_id in valid_regions
        }
        if not action_by_unit:
            return units

        rows = []
        now = int(state.time.total_minutes)
        regions = state.get_table("regions")
        region_locations = self._duration_policy.region_locations(regions)
        region_by_id = {int(region["id"]): region for region in regions.to_dicts()}

        for row in units.to_dicts():
            action = action_by_unit.get(str(row["id"]))
            if action is None:
                rows.append(row)
                continue
            if str(row.get("engagement_mode") or "").lower() == "positional":
                row["engagement_mode"] = "assault"
                rows.append(row)
                continue


            source_region_id = int(row["current_region_id"])
            target_region_id = int(action.target_region_id)
            via_regions = [
                region_by_id.get(int(region_id))
                for region_id in action.via_region_ids
            ]
            if (
                not self._access_policy.can_station(state, str(row["owner"]), region_by_id[target_region_id])
                or any(region is None or not self._access_policy.can_transit(state, str(row["owner"]), region) for region in via_regions)
            ):
                rows.append(row)
                continue
            source_geo = GeoCoordinate(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            target_geo = self._resolve_action_target_geo(action, target_region_id, region_locations)
            if target_geo is None:
                rows.append(row)
                continue

            duration = self._duration_policy.estimate_between(source_geo, target_geo)
            row["source_region_id"] = source_region_id
            row["source_latitude"] = source_geo.latitude
            row["source_longitude"] = source_geo.longitude
            row["target_region_id"] = target_region_id
            row["target_latitude"] = target_geo.latitude
            row["target_longitude"] = target_geo.longitude
            row["departed_at_minute"] = now
            row["arrival_at_minute"] = now + duration
            row["movement_progress"] = 0.0
            row["is_moving"] = True
            rows.append(row)

        return self._units_from_rows(rows)

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

    def _update_unit_movements(self, state: GameState, units: pl.DataFrame, current_minute: int) -> pl.DataFrame:
        if units.is_empty():
            return units

        war_table = state.tables.get("countries_wars")
        war_rows = [] if war_table is None else war_table.to_dicts()
        rows = units.to_dicts()
        for row in rows:
            target_region_id = int(row.get("target_region_id") or NO_TARGET_REGION)
            if target_region_id <= 0 or not bool(row.get("is_moving")):
                row["movement_progress"] = 0.0
                row["is_moving"] = False
                continue

            departed_at = int(row.get("departed_at_minute") or current_minute)
            arrival_at = int(row.get("arrival_at_minute") or current_minute)
            duration = max(1, arrival_at - departed_at)
            previous_progress = max(0.0, min(1.0, float(row.get("movement_progress") or 0.0)))
            progress = max(0.0, min(1.0, (current_minute - departed_at) / duration))
            source_geo = GeoCoordinate(
                latitude=float(row.get("source_latitude") or row.get("latitude") or 0.0),
                longitude=float(row.get("source_longitude") or row.get("longitude") or 0.0),
            )
            target_geo = GeoCoordinate(
                latitude=float(row.get("target_latitude") or row.get("latitude") or 0.0),
                longitude=float(row.get("target_longitude") or row.get("longitude") or 0.0),
            )
            previous_geo = interpolate_geo(source_geo, target_geo, previous_progress)
            next_geo = interpolate_geo(source_geo, target_geo, progress)
            contact = self._first_hostile_contact(row, rows, previous_geo, next_geo, war_rows, current_minute)

            if contact is not None:
                defender, fraction = contact
                contact_geo = interpolate_geo(previous_geo, next_geo, fraction)
                row["current_region_id"] = int(defender.get("current_region_id") or 0)
                self._stop_unit_at(row, contact_geo, current_minute)
                row["engagement_mode"] = "positional"
                defender_geo = self._unit_geo_at(defender, current_minute)
                self._stop_unit_at(defender, defender_geo, current_minute)
                defender["engagement_mode"] = "positional"
                continue

            if progress >= 1.0:
                row["current_region_id"] = target_region_id
                self._stop_unit_at(row, target_geo, current_minute)
                row["engagement_mode"] = ""
            else:
                row["movement_progress"] = progress
                row["is_moving"] = True

        return self._units_from_rows(rows)

    def _first_hostile_contact(
        self,
        moving_unit: dict[str, Any],
        unit_rows: list[dict[str, Any]],
        start: GeoCoordinate,
        end: GeoCoordinate,
        war_rows: list[dict[str, Any]],
        current_minute: int,
    ) -> tuple[dict[str, Any], float] | None:
        best_contact: tuple[dict[str, Any], float] | None = None
        moving_owner = str(moving_unit.get("owner") or "")
        moving_id = str(moving_unit.get("id") or "")
        for defender in sorted(unit_rows, key=lambda row: str(row.get("id") or "")):
            if str(defender.get("id") or "") == moving_id or int(defender.get("strength") or 0) <= 0:
                continue
            if not countries_are_hostile(war_rows, moving_owner, str(defender.get("owner") or "")):
                continue
            fraction = first_zone_contact_fraction(
                start,
                end,
                self._unit_geo_at(defender, current_minute),
                engagement_radius_km(defender),
            )
            if fraction is None:
                continue
            if best_contact is None or fraction < best_contact[1]:
                best_contact = (defender, fraction)
        return best_contact

    def _unit_geo_at(self, row: dict[str, Any], current_minute: int) -> GeoCoordinate:
        current_geo = GeoCoordinate(
            latitude=float(row.get("latitude") or 0.0),
            longitude=float(row.get("longitude") or 0.0),
        )
        if not bool(row.get("is_moving")) or int(row.get("target_region_id") or NO_TARGET_REGION) <= 0:
            return current_geo
        source_geo = GeoCoordinate(
            latitude=float(row.get("source_latitude") or current_geo.latitude),
            longitude=float(row.get("source_longitude") or current_geo.longitude),
        )
        target_geo = GeoCoordinate(
            latitude=float(row.get("target_latitude") or current_geo.latitude),
            longitude=float(row.get("target_longitude") or current_geo.longitude),
        )
        departed_at = int(row.get("departed_at_minute") or current_minute)
        arrival_at = int(row.get("arrival_at_minute") or current_minute)
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
            "strength": 1,
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
        }

        had_latitude = "latitude" in units.columns
        had_longitude = "longitude" in units.columns
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

        manpower_df = (
            regions.group_by("owner", maintain_order=True)
            .agg(pl.col("pop_15_64").sum().alias("total_core_manpower"))
            .rename({"owner": "id"})
        )

        countries = state.get_table("countries")
        if countries.is_empty():
            return

        if "total_core_manpower" in countries.columns:
            countries = countries.drop("total_core_manpower")

        countries = countries.join(manpower_df, on="id", how="left").with_columns(
            pl.col("total_core_manpower").fill_null(0)
        )
        state.update_table("countries", countries)
