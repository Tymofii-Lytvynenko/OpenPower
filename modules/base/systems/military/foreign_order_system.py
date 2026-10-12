"""Foreign production contracts and used-unit listings over existing unit data."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from modules.base.systems.military.military_system import MovementDurationPolicy, UNIT_SCHEMA, UnitFactory
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner
from modules.base.systems.military.capability_catalog import get_role_profile
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from modules.base.systems.military.authority_policy import TRUSTED_SYSTEM_ACTORS, player_controls_country
from src.shared.actions import (
    ActionCancelForeignUnitOrder,
    ActionListUsedUnit,
    ActionRequestForeignUnitOrder,
    ActionRespondForeignUnitOrder,
    ActionSetForeignOrderAcceptance,
    ActionWithdrawUsedUnitListing,
)
from src.shared.events import DomainGameEvent, EventMessageCreated
from src.shared.state import GameState
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


class EventForeignOrderChanged(DomainGameEvent):
    def __init__(self, order_id: str, status: str, buyer: str, seller: str, at_minute: int):
        self.order_id = order_id
        self.status = status
        self.buyer_country_id = buyer
        self.seller_country_id = seller
        self.at_minute = int(at_minute)


class ForeignOrderSystem(ISystem):
    runtime_state_contract = {
        "_trade": SYSTEM_STATE_HELPER,
        "_unit_factory": SYSTEM_STATE_HELPER,
        "_duration": SYSTEM_STATE_HELPER,
        "_route_planner": SYSTEM_STATE_HELPER,
        "_access": SYSTEM_STATE_HELPER,
        "_demilitarization_policy": SYSTEM_STATE_HELPER,
    }
    access = SystemAccess(
        reads=frozenset({"countries", "regions", "region_adjacency", "units", "unit_designs", "unit_market_listings", "foreign_unit_orders", "seller_acceptance_profiles", "treaty_effects", "countries_relations", "unit_movement_routes", "messages"}),
        writes=frozenset({"countries", "units", "unit_market_listings", "foreign_unit_orders", "seller_acceptance_profiles", "countries_relations", "unit_movement_routes", "messages"}),
        handles=frozenset({ActionSetForeignOrderAcceptance, ActionRequestForeignUnitOrder, ActionRespondForeignUnitOrder, ActionCancelForeignUnitOrder, ActionListUsedUnit, ActionWithdrawUsedUnitListing}),
        phase=SystemPhase.TRADE + 1,
    )

    def __init__(self):
        self._trade = WeaponsTradePolicy()
        self._unit_factory = UnitFactory()
        self._duration = MovementDurationPolicy()
        self._route_planner = MilitaryRoutePlanner()
        self._access = MovementAccessPolicy()
        self._demilitarization_policy = DemilitarizationPolicy()

    @property
    def id(self) -> str:
        return "base.foreign_orders"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy", "base.military_programs"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {"unit_market_listings", "foreign_unit_orders", "seller_acceptance_profiles"}
        if not required.issubset(state.tables):
            return
        listing_frame = state.get_table("unit_market_listings")
        listings = listing_frame.to_dicts()
        order_frame = state.get_table("foreign_unit_orders")
        orders = order_frame.to_dicts()
        profile_frame = state.get_table("seller_acceptance_profiles")
        profiles = profile_frame.to_dicts()
        for action in state.current_actions:
            if isinstance(action, ActionSetForeignOrderAcceptance):
                self._set_acceptance(state, profiles, action)
            elif isinstance(action, ActionRequestForeignUnitOrder):
                orders = self._request(state, orders, action)
            elif isinstance(action, ActionRespondForeignUnitOrder):
                self._respond(state, orders, profiles, action)
            elif isinstance(action, ActionCancelForeignUnitOrder):
                self._cancel(state, orders, action)
            elif isinstance(action, ActionListUsedUnit):
                listings = self._list_used_unit(state, listings, action)
            elif isinstance(action, ActionWithdrawUsedUnitListing):
                self._withdraw_listing(state, listings, action)
        self._deliver_due_orders(state, orders)
        self._refresh_delivery_status(state, orders)
        self._write(state, "unit_market_listings", listings)
        self._write(state, "foreign_unit_orders", orders)
        self._write(state, "seller_acceptance_profiles", profiles)

    def _set_acceptance(self, state, profiles, action):
        country = self._tag(action.country_tag)
        if not country or not self._authorized(state, action.player_id, country):
            return
        row = next((item for item in profiles if self._tag(item.get("country_id")) == country), None)
        if row is None:
            profiles.append({"country_id": country, "accepts_foreign_orders": bool(action.is_accepting), "price_multiplier": self._finite(state.globals.get("foreign_order_price_multiplier", 1.25)), "cancellation_penalty": self._finite(state.globals.get("foreign_order_cancellation_penalty", 0.01))})
        else:
            row["accepts_foreign_orders"] = bool(action.is_accepting)

    def _request(self, state, orders, action):
        buyer, seller = self._tag(action.buyer_country_tag), self._tag(action.seller_country_tag)
        if not self._authorized(state, action.player_id, buyer) or not self._eligible(state, buyer, seller):
            self._reject(state, action, "The buyer is not authorized or the seller is not eligible for foreign orders.")
            return orders
        quantity = int(action.quantity)
        design = self._design(state, str(action.design_id), seller)
        if quantity <= 0 or design is None:
            self._reject(state, action, "The design is not owned by the seller or the requested quantity is invalid.")
            return orders
        if not self._seller_accepts(state, seller):
            self._reject(state, action, "The seller has not enabled foreign orders.")
            return orders
        if any(row.get("status") in {"pending_seller_acceptance", "accepted", "in_production"} and row.get("buyer_country_id") == buyer and row.get("seller_country_id") == seller and row.get("design_id") == action.design_id for row in orders):
            self._reject(state, action, "An equivalent request is already active.")
            return orders
        order_id = self._next_id("foreign-order", orders)
        now = int(state.time.total_minutes)
        orders.append({
            "id": order_id, "buyer_country_id": buyer, "seller_country_id": seller,
            "design_id": str(action.design_id), "quantity": quantity, "price": 0.0,
            "incurred_cost": 0.0, "status": "pending_seller_acceptance",
            "created_at_minute": now, "due_at_minute": 0, "updated_at_minute": now,
            "production_cost": max(0.0, self._finite(design.get("cost"))) * quantity,
            "reason": "Awaiting seller acceptance.",
        })
        self._publish(state, orders[-1])
        return orders

    def _respond(self, state, orders, profiles, action):
        order = next((row for row in orders if str(row.get("id")) == str(action.order_id)), None)
        if order is None or order.get("status") != "pending_seller_acceptance":
            self._reject(state, action, "The foreign order is not awaiting a seller response.")
            return
        seller = self._tag(order.get("seller_country_id"))
        if not self._authorized(state, action.player_id, seller):
            self._reject(state, action, "Only the seller can respond to this order.")
            return
        if not action.accept:
            order.update(status="rejected", reason="The seller rejected the request.", updated_at_minute=int(state.time.total_minutes))
            self._publish(state, order)
            return
        if not self._eligible(state, self._tag(order.get("buyer_country_id")), seller) or not self._seller_accepts(state, seller):
            order.update(status="rejected", reason="Treaty eligibility or seller acceptance changed.", updated_at_minute=int(state.time.total_minutes))
            self._publish(state, order)
            return
        profile = next((row for row in profiles if self._tag(row.get("country_id")) == seller), {})
        raw_multiplier = profile.get("price_multiplier")
        if raw_multiplier is None:
            raw_multiplier = state.globals.get("foreign_order_price_multiplier", 1.25)
        multiplier = min(10.0, max(0.0, self._finite(raw_multiplier)))
        order["price"] = max(0.0, self._finite(order.get("production_cost")) * multiplier)
        duration = max(1, int(self._finite(state.globals.get("foreign_order_production_minutes", 30 * 1440))))
        order.update(status="in_production", due_at_minute=int(state.time.total_minutes) + duration, updated_at_minute=int(state.time.total_minutes), reason="Seller accepted; production and delivery are pending.")
        self._publish(state, order)

    def _cancel(self, state, orders, action):
        order = next((row for row in orders if str(row.get("id")) == str(action.order_id)), None)
        if order is None or order.get("status") not in {"pending_seller_acceptance", "in_production", "accepted"}:
            return
        actor = self._tag(action.player_id)
        buyer = self._tag(order.get("buyer_country_id"))
        seller = self._tag(order.get("seller_country_id"))
        mapping = state.globals.get("player_country_map", {})
        if isinstance(mapping, dict):
            actor = self._tag(mapping.get(str(action.player_id)) or actor)
        if actor not in {buyer, seller, *TRUSTED_SYSTEM_ACTORS}:
            self._reject(state, action, "Only the buyer or seller may cancel this contract.")
            return
        incurred = 0.0
        if order.get("status") == "in_production":
            production_start = int(order.get("updated_at_minute") or order.get("created_at_minute") or 0)
            elapsed = max(0, int(state.time.total_minutes) - production_start)
            duration = max(1, int(order.get("due_at_minute") or 0) - production_start)
            incurred = self._finite(order.get("production_cost")) * min(1.0, elapsed / duration)
        countries = state.tables.get("countries")
        if countries is not None and incurred > 0.0:
            rows = countries.to_dicts()
            payer = buyer if actor == buyer else seller
            payee = seller if actor == buyer else buyer
            payer_row = next((row for row in rows if self._tag(row.get("id")) == payer), None)
            payee_row = next((row for row in rows if self._tag(row.get("id")) == payee), None)
            if payer_row is None or payee_row is None or self._finite(payer_row.get("money_reserves")) < incurred:
                self._reject(state, action, "Insufficient funds to settle the documented cancellation cost.")
                return
            payer_row["money_reserves"] = self._finite(payer_row.get("money_reserves")) - incurred
            payee_row["money_reserves"] = self._finite(payee_row.get("money_reserves")) + incurred
            state.update_table("countries", pl.DataFrame(rows, schema=countries.schema))
        order.update(status="cancelled", incurred_cost=incurred, reason=f"Cancelled; incurred production cost settled: {incurred:.2f}.", updated_at_minute=int(state.time.total_minutes))
        self._apply_relation_penalty(state, buyer, seller)
        self._publish(state, order)

    def _deliver_due_orders(self, state, orders):
        now = int(state.time.total_minutes)
        if not any(
            order.get("status") == "in_production"
            and now >= int(order.get("due_at_minute") or 0)
            for order in orders
        ):
            return
        countries_frame = state.tables.get("countries")
        if countries_frame is None or "units" not in state.tables:
            return
        countries = countries_frame.to_dicts()
        designs = state.tables.get("unit_designs")
        regions = state.tables.get("regions")
        units_frame = state.tables.get("units")
        units = [] if units_frame is None else units_frame.to_dicts()
        existing_ids = {str(row.get("id") or "") for row in units}
        route_frame = state.tables.get("unit_movement_routes")
        routes = [] if route_frame is None else route_frame.to_dicts()
        adjacency = state.tables.get("region_adjacency")
        has_geo_coordinates = regions is not None and {
            "latitude",
            "longitude",
        }.issubset(regions.columns)
        prepared_graph = None
        for order in orders:
            if order.get("status") != "in_production" or now < int(order.get("due_at_minute") or 0):
                continue
            buyer, seller = self._tag(order.get("buyer_country_id")), self._tag(order.get("seller_country_id"))
            if not self._eligible(state, buyer, seller) or not self._seller_accepts(state, seller):
                order.update(status="cancelled", reason="The contract is no longer legally eligible.", updated_at_minute=now)
                self._publish(state, order)
                continue
            buyer_row = next((row for row in countries if self._tag(row.get("id")) == buyer), None)
            seller_row = next((row for row in countries if self._tag(row.get("id")) == seller), None)
            design = self._design(state, str(order.get("design_id")), seller)
            if buyer_row is None or seller_row is None or design is None:
                order.update(status="cancelled", reason="A party or the contracted design is no longer available.", updated_at_minute=now)
                self._publish(state, order)
                continue
            price, cost, quantity = self._finite(order.get("price")), self._finite(order.get("production_cost")), int(order.get("quantity") or 0)
            if not self._demilitarization_policy.can_add(
                state,
                buyer,
                quantity,
                unit_rows=units,
            ):
                reason = "Delivery is held by an active demilitarization limit."
                if order.get("reason") != reason:
                    order.update(reason=reason, updated_at_minute=now)
                    self._publish(state, order)
                continue
            if self._finite(buyer_row.get("money_reserves")) < price:
                order.update(reason="Buyer funds are insufficient at delivery.", updated_at_minute=now)
                continue
            design_domain = get_role_profile(design.get("class_name") or "army", design.get("domain")).domain
            origin = self._home_region(state, seller)
            destination = self._deployment_region(state, buyer, design_domain)
            if origin is None or destination is None or regions is None:
                reason = "A valid seller origin or buyer deployment region is unavailable."
                if order.get("reason") != reason:
                    order.update(reason=reason, updated_at_minute=now)
                    self._publish(state, order)
                continue
            if prepared_graph is None:
                prepared_graph = self._route_planner.prepare(regions, adjacency)
            access_context = self._access.for_country(state, buyer)

            def segment_minutes(left, right):
                left_id = int(left.get("id") or 0)
                right_id = int(right.get("id") or 0)
                edge_key = (left_id, right_id) if left_id < right_id else (right_id, left_id)
                distance = (
                    prepared_graph.edge_distance_km.get(edge_key)
                    if has_geo_coordinates
                    else None
                )
                return (
                    self._duration.estimate_from_distance(distance)
                    if distance is not None
                    else self._duration.estimate_between(self._coordinate(left), self._coordinate(right))
                )

            route = self._route_planner.plan(
                int(origin.get("id") or 0),
                int(destination.get("id") or 0),
                prepared_graph.region_by_id.values(),
                adjacency,
                lambda row, final: self._foreign_route_access(access_context, buyer, seller, row, final),
                segment_cost=segment_minutes,
                prepared_graph=prepared_graph,
            )
            if not route.is_valid:
                if order.get("reason") != route.rejection_reason:
                    order.update(reason=route.rejection_reason, updated_at_minute=now)
                    self._publish(state, order)
                continue
            if len(route.region_ids) > 1 and route_frame is None:
                reason = "The shared movement route table is unavailable; delivery remains blocked."
                if order.get("reason") != reason:
                    order.update(reason=reason, updated_at_minute=now)
                    self._publish(state, order)
                continue
            buyer_row["money_reserves"] = self._finite(buyer_row.get("money_reserves")) - price
            seller_row["money_reserves"] = self._finite(seller_row.get("money_reserves")) + price - cost
            buyer_row["military_count"] = int(buyer_row.get("military_count") or 0) + quantity
            unit_type = str(design.get("class_name") or "army").strip().lower().replace(" ", "_")
            unit_id = self._unique_id(f"foreign-{order['id']}", existing_ids)
            geo = self._coordinate(origin)
            new_unit = self._unit_factory.create(unit_id, buyer, unit_type, quantity, int(origin.get("id") or 0), geo, now, design_id=str(order.get("design_id")), training_level="Recruit")
            target_geo = self._coordinate(destination)
            first_region_id = route.region_ids[1] if len(route.region_ids) > 1 else int(destination.get("id") or 0)
            first_region = prepared_graph.region_by_id.get(first_region_id, destination)
            first_geo = self._coordinate(first_region)
            first_edge_key = (
                (int(origin.get("id") or 0), first_region_id)
                if int(origin.get("id") or 0) < first_region_id
                else (first_region_id, int(origin.get("id") or 0))
            )
            first_edge_distance = (
                prepared_graph.edge_distance_km.get(first_edge_key)
                if has_geo_coordinates
                else None
            )
            duration = (
                self._duration.estimate_from_distance(first_edge_distance)
                if first_edge_distance is not None
                else self._duration.estimate_between(geo, first_geo)
            )
            new_unit.update(
                production_order_id="", foreign_order_id=str(order["id"]), original_cost=cost,
                source_region_id=int(origin.get("id") or 0),
                source_latitude=geo.latitude, source_longitude=geo.longitude,
                target_region_id=first_region_id, target_latitude=first_geo.latitude,
                target_longitude=first_geo.longitude, departed_at_minute=now,
                arrival_at_minute=now + duration, is_moving=len(route.region_ids) > 1,
                current_region_id=0 if len(route.region_ids) > 1 else int(destination.get("id") or 0),
                unit_lifecycle="in_transit" if len(route.region_ids) > 1 else "available",
            )
            units.append(new_unit)
            existing_ids.add(unit_id)
            if new_unit["is_moving"]:
                routes.append({
                    "unit_id": unit_id, "owner_country_id": buyer,
                    "source_region_id": int(origin.get("id") or 0), "destination_region_id": int(destination.get("id") or 0),
                    "route_region_ids": list(route.region_ids), "route_index": 1,
                    "destination_latitude": target_geo.latitude, "destination_longitude": target_geo.longitude,
                    "has_custom_destination": False, "is_naval_invasion": False,
                    "status": "in_transit", "rejection_reason": "",
                    "updated_at_minute": now,
                })
            order.update(
                status="in_transit" if new_unit["is_moving"] else "delivered",
                unit_ids=[unit_id], route_region_ids=list(route.region_ids),
                destination_region_id=int(destination.get("id") or 0),
                payment_status="settled", ownership_transferred_at_minute=now,
                reason=(
                    "Paid and dispatched; ownership transferred and delivery is in transit."
                    if new_unit["is_moving"]
                    else "Paid, transferred, and delivered at the deployment destination."
                ),
                updated_at_minute=now,
            )
            self._publish(state, order)
        if countries != countries_frame.to_dicts():
            state.update_table("countries", pl.DataFrame(countries, schema=countries_frame.schema))
        if units_frame is not None and units != units_frame.to_dicts():
            state.update_table("units", pl.DataFrame(units, schema=UNIT_SCHEMA))
        if route_frame is not None and routes != route_frame.to_dicts():
            state.update_table("unit_movement_routes", pl.DataFrame(routes, schema=route_frame.schema))

    def _refresh_delivery_status(self, state, orders):
        active_orders = [
            order for order in orders
            if str(order.get("status") or "") in {"in_transit", "blocked"}
        ]
        if not active_orders:
            return
        units_table = state.tables.get("units")
        if units_table is None:
            return
        unit_ids = sorted({
            str(value)
            for order in active_orders
            for value in order.get("unit_ids") or []
            if str(value)
        })
        if not unit_ids:
            return
        relevant_units = units_table.filter(
            pl.col("id").cast(pl.Utf8, strict=False).fill_null("").is_in(unit_ids)
        )
        units = {str(row.get("id") or ""): row for row in relevant_units.to_dicts()}
        routes_table = state.tables.get("unit_movement_routes")
        routes = {}
        if routes_table is not None and "unit_id" in routes_table.columns:
            relevant_routes = routes_table.filter(
                pl.col("unit_id").cast(pl.Utf8, strict=False).fill_null("").is_in(unit_ids)
            )
            routes = {
                str(row.get("unit_id") or ""): row
                for row in relevant_routes.to_dicts()
            }
        now = int(state.time.total_minutes)
        for order in active_orders:
            unit_ids = [str(value) for value in order.get("unit_ids") or []]
            if not unit_ids:
                continue
            related_units = [units.get(unit_id) for unit_id in unit_ids]
            if any(unit is None for unit in related_units):
                status, reason = "blocked", "A transferred unit is missing from the authoritative inventory."
            elif any(
                str((routes.get(unit_id) or {}).get("status") or "") == "blocked"
                or str(units[unit_id].get("unit_lifecycle") or "") in {"route_blocked", "deployment_blocked"}
                for unit_id in unit_ids
            ):
                status = "blocked"
                reason = next((
                    str((routes.get(unit_id) or {}).get("rejection_reason") or "Delivery route requires a new order.")
                    for unit_id in unit_ids
                    if str((routes.get(unit_id) or {}).get("status") or "") == "blocked"
                    or str(units[unit_id].get("unit_lifecycle") or "") in {"route_blocked", "deployment_blocked"}
                ), "Delivery route requires a new order.")
            elif all(str(unit.get("unit_lifecycle") or "") == "available" for unit in related_units):
                status, reason = "delivered", "All transferred units arrived at their deployment destinations."
            else:
                status, reason = "in_transit", "Paid and transferred; delivery is in transit."
            if status != str(order.get("status") or "") or reason != str(order.get("reason") or ""):
                order.update(status=status, reason=reason, updated_at_minute=now)
                self._publish(state, order)

    def _list_used_unit(self, state, listings, action):
        owner = self._tag(action.country_tag)
        if not self._authorized(state, action.player_id, owner) or "units" not in state.tables:
            return listings
        participants = state.tables.get("battle_units")
        engaged_unit_ids = set() if participants is None else {
            str(row.get("unit_id") or "") for row in participants.to_dicts()
        }
        unit = next((
            row for row in state.get_table("units").to_dicts()
            if str(row.get("id")) == str(action.unit_id)
            and self._tag(row.get("owner")) == owner
            and int(row.get("strength") or 0) > 0
            and not bool(row.get("is_moving"))
            and str(row.get("unit_lifecycle") or "available") == "available"
            and str(row.get("training_state") or "") != "training"
            and str(row.get("id") or "") not in engaged_unit_ids
        ), None)
        if unit is None or any(row.get("unit_id") == action.unit_id and row.get("status", "listed") == "listed" for row in listings):
            return listings
        design = self._design(state, str(unit.get("design_id") or ""), owner)
        unit_cost = max(0.0, self._finite(unit.get("original_cost"))) or (0.0 if design is None else max(0.0, self._finite(design.get("cost"))))
        price = self._finite(action.price) if self._finite(action.price) > 0 else unit_cost * 0.75
        listings.append({
            "id": self._next_id("used-listing", listings), "seller_country_id": owner,
            "design_id": str(unit.get("design_id") or ""), "unit_id": str(action.unit_id),
            "quantity": int(unit.get("strength") or 0), "price": price,
            "original_cost": unit_cost, "eligibility": "treaty", "status": "listed",
            "created_at_minute": int(state.time.total_minutes),
        })
        return listings

    def _withdraw_listing(self, state, listings, action):
        owner = self._tag(action.country_tag)
        if not self._authorized(state, action.player_id, owner):
            return
        listing = next((row for row in listings if str(row.get("id")) == str(action.listing_id) and self._tag(row.get("seller_country_id")) == owner and row.get("status", "listed") == "listed"), None)
        if listing:
            listing.update(status="withdrawn", quantity=0)

    def _eligible(self, state, buyer, seller):
        effects = state.tables.get("treaty_effects")
        if not self._trade.can_order(effects, buyer, seller, "open"):
            return False
        permissions = state.globals.get("foreign_order_permissions", [])
        if isinstance(permissions, list) and [buyer, seller] in permissions:
            return True
        return self._trade.can_order(effects, buyer, seller, "treaty")

    def _seller_accepts(self, state, seller):
        table = state.tables.get("seller_acceptance_profiles")
        if table is None:
            return False
        row = next((item for item in table.to_dicts() if self._tag(item.get("country_id")) == seller), None)
        return bool(row and row.get("accepts_foreign_orders"))

    def _design(self, state, design_id, owner):
        table = state.tables.get("unit_designs")
        if table is None:
            return None
        return next((row for row in table.to_dicts() if str(row.get("id")) == design_id and self._tag(row.get("country_id")) == owner), None)

    def _home_region(self, state, owner):
        regions = state.tables.get("regions")
        if regions is None:
            return None
        owned = [row for row in regions.to_dicts() if self._tag(row.get("owner")) == owner]
        government_table = state.tables.get("country_governments")
        government = next((row for row in government_table.to_dicts() if self._tag(row.get("country_id")) == owner), None) if government_table is not None else None
        capital = int(government.get("capital_region_id") or 0) if government else 0
        return next((row for row in owned if int(row.get("id") or 0) == capital), None) or (min(owned, key=lambda row: int(row.get("id") or 0)) if owned else None)

    def _deployment_region(self, state, owner, domain):
        regions = state.tables.get("regions")
        if regions is None:
            return None
        owned = [row for row in regions.to_dicts() if self._tag(row.get("owner")) == owner]
        government_table = state.tables.get("country_governments")
        governments = [] if government_table is None else government_table.to_dicts()
        government = next((row for row in governments if self._tag(row.get("country_id")) == owner), None)
        capital = int(government.get("capital_region_id") or 0) if government else 0
        if domain == "naval":
            naval_regions = [row for row in owned if bool(row.get("is_port")) or str(row.get("region_type") or row.get("terrain") or "").lower() in {"port", "naval_base", "sea", "ocean"}]
            if naval_regions:
                return next((row for row in naval_regions if int(row.get("id") or 0) == capital), None) or min(naval_regions, key=lambda row: int(row.get("id") or 0))
            if owned and any(any(column in row for column in ("is_port", "region_type", "terrain")) for row in owned):
                return None
        return next((row for row in owned if int(row.get("id") or 0) == capital), None) or (min(owned, key=lambda row: int(row.get("id") or 0)) if owned else None)

    def _foreign_route_access(self, access_context, buyer, seller, region, final):
        territory = self._tag(region.get("owner"))
        if territory in {buyer, seller}:
            return True
        return access_context.can_station(region) if final else access_context.can_transit(region)

    def _coordinate(self, region):
        from src.core.map.geo import GeoCoordinate
        return GeoCoordinate(float(region.get("latitude") or 0.0), float(region.get("longitude") or 0.0))

    def _apply_relation_penalty(self, state, buyer, seller):
        table = state.tables.get("countries_relations")
        if table is None:
            return
        rows = table.to_dicts()
        for row in rows:
            if (self._tag(row.get("source")), self._tag(row.get("target"))) in {(buyer, seller), (seller, buyer)}:
                row["value"] = max(-100.0, min(100.0, self._finite(row.get("value")) - 1.0))
        state.update_table("countries_relations", pl.DataFrame(rows, schema=table.schema))

    def _publish(self, state, order):
        state.events.append(EventForeignOrderChanged(str(order.get("id")), str(order.get("status")), str(order.get("buyer_country_id")), str(order.get("seller_country_id")), int(state.time.total_minutes)))
        table = state.tables.get("messages")
        if table is None:
            return
        rows = table.to_dicts()
        for country in sorted({self._tag(order.get("buyer_country_id")), self._tag(order.get("seller_country_id"))} - {""}):
            message_id = self._next_id("foreign-order-message", rows)
            rows.append({
                "id": message_id, "country_id": country, "category": "foreign_order",
                "subject": f"Foreign unit order {order.get('status')}",
                "body": f"Order {order.get('id')}: {order.get('status')}. {order.get('reason', '')}",
                "is_read": False, "created_at": str(int(state.time.total_minutes)),
            })
            state.events.append(EventMessageCreated(message_id, country, "foreign_order"))
        state.update_table("messages", pl.DataFrame(rows, schema=table.schema))

    def _reject(self, state, action, reason):
        state.journal.append_command_result({"tick": int(state.globals.get("tick", 0)), "player_id": str(action.player_id), "action_type": type(action).__name__, "status": "rejected", "reason": reason})

    def _write(self, state, name, rows):
        table = state.get_table(name)
        frame = pl.DataFrame(rows, schema=table.schema) if rows else pl.DataFrame(schema=table.schema)
        if not frame.equals(table):
            state.update_table(name, frame)

    def _next_id(self, prefix, rows):
        return f"{prefix}-{len(rows) + 1:08d}"

    def _unique_id(self, prefix, existing):
        identifier, index = prefix, 1
        while identifier in existing:
            index += 1
            identifier = f"{prefix}-{index:03d}"
        return identifier

    def _authorized(self, state, player_id, country):
        return player_controls_country(state, player_id, country)

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _finite(self, value: Any) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
