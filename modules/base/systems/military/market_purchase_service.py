"""Apply military marketplace purchases using injected domain policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import polars as pl

from modules.base.systems.military.movement_access import MovementAccessContext, MovementAccessPolicy
from modules.base.systems.military.movement_duration import DEFAULT_MOVE_MINUTES, MovementDurationPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner, RoutePlan
from modules.base.systems.military.weapons_trade_policy import WeaponsTradePolicy
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionBuyMarketUnit
from src.shared.state import GameState


class _UnitRecordFactory(Protocol):
    def create(self, **values: Any) -> dict[str, Any]: ...

    def next_id(self, unit_rows: list[dict[str, Any]], country_tag: str, unit_type: str) -> str: ...


@dataclass
class _MarketPurchaseContext:
    state: GameState
    countries: pl.DataFrame
    listings_table: pl.DataFrame
    home_regions_by_country: dict[str, int]
    region_locations: dict[int, GeoCoordinate]
    unit_rows: list[dict[str, Any]]
    country_rows: list[dict[str, Any]]
    countries_by_tag: dict[str, dict[str, Any]]
    listing_rows: list[dict[str, Any]]
    listings_by_id: dict[str, dict[str, Any]]
    region_rows: list[dict[str, Any]]
    adjacency_rows: list[dict[str, Any]]
    movement_table: pl.DataFrame | None
    movement_by_unit: dict[str, dict[str, Any]]
    designs_by_id: dict[str, dict[str, Any]]
    changed: bool = False


@dataclass(frozen=True)
class _PurchaseRequest:
    listing: dict[str, Any]
    buyer: dict[str, Any]
    seller: dict[str, Any]
    buyer_tag: str
    seller_tag: str
    quantity: int
    total_cost: float
    home_region_id: int


@dataclass(frozen=True)
class _MarketPurchaseParties:
    listing: dict[str, Any]
    buyer: dict[str, Any]
    seller: dict[str, Any]
    buyer_tag: str
    seller_tag: str


@dataclass(frozen=True)
class _UsedUnitTransfer:
    source_unit: dict[str, Any]
    source_region_id: int
    route_plan: RoutePlan
    first_region_id: int
    first_geo: GeoCoordinate | None


@dataclass(frozen=True)
class _MarketRouteAccess:
    access_context: MovementAccessContext
    buyer_tag: str
    seller_tag: str

    def can_enter(self, region: dict[str, Any], final: bool) -> bool:
        if final:
            return self.access_context.can_station(region)
        owner = str(region.get("owner") or "").strip().upper()
        return owner in {self.buyer_tag, self.seller_tag} or self.access_context.can_transit(region)


class MilitaryMarketPurchaseService:
    """Coordinate market transfers while keeping policy decisions injectable."""

    def __init__(
        self,
        unit_factory: _UnitRecordFactory,
        duration_policy: MovementDurationPolicy,
        access_policy: MovementAccessPolicy,
        route_planner: MilitaryRoutePlanner,
        demilitarization_policy: DemilitarizationPolicy,
        weapons_trade_policy: WeaponsTradePolicy,
        authorization_policy: Callable[[GameState, str, str], bool],
        route_schema: dict[str, pl.DataType],
        default_unit_type: str,
    ) -> None:
        self._unit_factory = unit_factory
        self._duration_policy = duration_policy
        self._access_policy = access_policy
        self._route_planner = route_planner
        self._demilitarization_policy = demilitarization_policy
        self._weapons_trade_policy = weapons_trade_policy
        self._authorization_policy = authorization_policy
        self._route_schema = route_schema
        self._default_unit_type = default_unit_type

    def process(
        self,
        state: GameState,
        units: pl.DataFrame,
        countries: pl.DataFrame,
        listings_table: pl.DataFrame,
        actions: list[ActionBuyMarketUnit],
        home_regions_by_country: dict[str, int],
        region_locations: dict[int, GeoCoordinate],
    ) -> list[dict[str, Any]] | None:
        context = self._build_context(
            state,
            units,
            countries,
            listings_table,
            home_regions_by_country,
            region_locations,
        )
        for action in actions:
            purchase = self._prepare_purchase(context, action)
            if purchase is None:
                continue
            if str(purchase.listing.get("unit_id") or ""):
                self._purchase_used_unit(context, purchase)
            else:
                self._purchase_new_unit(context, purchase)

        if not context.changed:
            return None
        self._publish_changes(context)
        return context.unit_rows

    def _build_context(
        self,
        state: GameState,
        units: pl.DataFrame,
        countries: pl.DataFrame,
        listings_table: pl.DataFrame,
        home_regions_by_country: dict[str, int],
        region_locations: dict[int, GeoCoordinate],
    ) -> _MarketPurchaseContext:
        regions = state.get_table("regions")
        adjacency = state.tables.get("region_adjacency")
        movement_table = state.tables.get("unit_movement_routes")
        design_rows = state.tables.get("unit_designs")
        country_rows = countries.to_dicts()
        listing_rows = listings_table.to_dicts()
        movement_rows = [] if movement_table is None else movement_table.to_dicts()
        designs = [] if design_rows is None else design_rows.to_dicts()
        return _MarketPurchaseContext(
            state=state,
            countries=countries,
            listings_table=listings_table,
            home_regions_by_country=home_regions_by_country,
            region_locations=region_locations,
            unit_rows=units.to_dicts(),
            country_rows=country_rows,
            countries_by_tag={
                str(row.get("id") or "").strip().upper(): row
                for row in country_rows
            },
            listing_rows=listing_rows,
            listings_by_id={str(row.get("id") or ""): row for row in listing_rows},
            region_rows=regions.to_dicts(),
            adjacency_rows=[] if adjacency is None else adjacency.to_dicts(),
            movement_table=movement_table,
            movement_by_unit={str(row.get("unit_id") or ""): row for row in movement_rows},
            designs_by_id={str(row.get("id") or ""): row for row in designs},
        )

    def _prepare_purchase(
        self,
        context: _MarketPurchaseContext,
        action: ActionBuyMarketUnit,
    ) -> _PurchaseRequest | None:
        parties = self._resolve_purchase_parties(context, action)
        if parties is None:
            return None

        quantity = max(0, min(int(action.quantity), int(parties.listing.get("quantity") or 0)))
        if not self._demilitarization_policy.can_add(
            context.state,
            parties.buyer_tag,
            quantity,
            unit_rows=context.unit_rows,
        ):
            return None
        total_cost = self._purchase_total_cost(context, parties, quantity)
        if total_cost is None or not self._buyer_can_cover(parties.buyer, total_cost):
            return None
        home_region_id = context.home_regions_by_country.get(str(parties.buyer.get("id") or ""))
        if home_region_id is None:
            return None
        return _PurchaseRequest(
            listing=parties.listing,
            buyer=parties.buyer,
            seller=parties.seller,
            buyer_tag=parties.buyer_tag,
            seller_tag=parties.seller_tag,
            quantity=quantity,
            total_cost=total_cost,
            home_region_id=home_region_id,
        )

    def _resolve_purchase_parties(
        self,
        context: _MarketPurchaseContext,
        action: ActionBuyMarketUnit,
    ) -> _MarketPurchaseParties | None:
        listing = context.listings_by_id.get(str(action.listing_id))
        buyer_tag = str(action.buyer_country_tag or "").strip().upper()
        if not self._authorize_market_actor(context, action, buyer_tag):
            return None

        seller_tag = str(listing.get("seller_country_id") or "").strip().upper() if listing else ""
        buyer = context.countries_by_tag.get(buyer_tag)
        seller = context.countries_by_tag.get(seller_tag)
        if not self._listing_has_valid_parties(listing, buyer, seller):
            return None
        return _MarketPurchaseParties(listing, buyer, seller, buyer_tag, seller_tag)

    def _purchase_total_cost(
        self,
        context: _MarketPurchaseContext,
        parties: _MarketPurchaseParties,
        quantity: int,
    ) -> float | None:
        if quantity <= 0:
            return None
        if not self._weapons_trade_policy.can_order(
            context.state.tables.get("treaty_effects"),
            parties.buyer_tag,
            parties.seller_tag,
            str(parties.listing.get("eligibility") or "open"),
        ):
            return None
        price = max(0.0, float(parties.listing.get("price") or 0.0))
        return price * quantity

    def _buyer_can_cover(self, buyer: dict[str, Any], total_cost: float) -> bool:
        return float(buyer.get("money_reserves") or 0.0) >= total_cost

    def _authorize_market_actor(
        self,
        context: _MarketPurchaseContext,
        action: ActionBuyMarketUnit,
        buyer_tag: str,
    ) -> bool:
        player_id = str(action.player_id or "")
        if self._authorization_policy(context.state, player_id, buyer_tag):
            return True
        context.state.journal.append_command_result({
            "tick": int(context.state.globals.get("tick", 0)),
            "player_id": player_id,
            "action_type": type(action).__name__,
            "status": "rejected",
            "reason": "The issuer does not control the purchasing country.",
        })
        return False

    def _listing_has_valid_parties(
        self,
        listing: dict[str, Any] | None,
        buyer: dict[str, Any] | None,
        seller: dict[str, Any] | None,
    ) -> bool:
        if listing is None or buyer is None or seller is None:
            return False
        return str(listing.get("status") or "listed").lower() == "listed"

    def _purchase_used_unit(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
    ) -> None:
        transfer = self._prepare_used_unit_transfer(context, purchase)
        if transfer is None:
            return

        self._settle_used_unit_accounts(purchase)
        travel_unit = self._transfer_used_unit(context, purchase, transfer)
        purchase.listing["quantity"] = int(purchase.listing.get("quantity") or 0) - purchase.quantity
        self._complete_used_unit_transfer(purchase, transfer, travel_unit)
        if len(transfer.route_plan.region_ids) > 1:
            self._start_used_unit_transit(context, purchase, transfer, travel_unit)
        context.changed = True

    def _prepare_used_unit_transfer(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
    ) -> _UsedUnitTransfer | None:
        source_unit = self._find_transfer_source(context, purchase)
        if source_unit is None:
            return None
        transfer = self._plan_used_unit_route(context, purchase, source_unit)
        if transfer is None or not self._buyer_can_cover(purchase.buyer, purchase.total_cost):
            return None
        return transfer

    def _find_transfer_source(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
    ) -> dict[str, Any] | None:
        used_unit_id = str(purchase.listing.get("unit_id") or "")
        source_unit = next(
            (
                row
                for row in context.unit_rows
                if self._is_transfer_source(row, used_unit_id, purchase.seller_tag)
            ),
            None,
        )
        if source_unit is None:
            return None
        if purchase.quantity > int(source_unit.get("strength") or 0):
            return None
        return source_unit

    def _is_transfer_source(
        self,
        unit: dict[str, Any],
        used_unit_id: str,
        seller_tag: str,
    ) -> bool:
        if str(unit.get("id") or "") != used_unit_id:
            return False
        if str(unit.get("owner") or "").strip().upper() != seller_tag:
            return False
        if bool(unit.get("is_moving")):
            return False
        return True

    def _plan_used_unit_route(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
        source_unit: dict[str, Any],
    ) -> _UsedUnitTransfer | None:
        source_region_id = int(source_unit.get("current_region_id") or 0)
        route_access = _MarketRouteAccess(
            access_context=self._access_policy.for_country(context.state, purchase.buyer_tag),
            buyer_tag=purchase.buyer_tag,
            seller_tag=purchase.seller_tag,
        )
        route_plan = self._route_planner.plan(
            source_region_id,
            purchase.home_region_id,
            context.region_rows,
            context.adjacency_rows,
            route_access.can_enter,
            segment_cost=lambda left, right: self._route_segment_minutes(
                left,
                right,
                context.region_locations,
            ),
        )
        if not route_plan.is_valid:
            return None
        first_region_id = route_plan.region_ids[1] if len(route_plan.region_ids) > 1 else 0
        first_geo = context.region_locations.get(first_region_id) if first_region_id else None
        if len(route_plan.region_ids) > 1 and first_geo is None:
            return None
        return _UsedUnitTransfer(
            source_unit=source_unit,
            source_region_id=source_region_id,
            route_plan=route_plan,
            first_region_id=first_region_id,
            first_geo=first_geo,
        )

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

    def _settle_used_unit_accounts(self, purchase: _PurchaseRequest) -> None:
        purchase.buyer["money_reserves"] = float(purchase.buyer.get("money_reserves") or 0.0) - purchase.total_cost
        purchase.buyer["military_count"] = int(purchase.buyer.get("military_count") or 0) + purchase.quantity
        purchase.seller["money_reserves"] = float(purchase.seller.get("money_reserves") or 0.0) + purchase.total_cost
        purchase.seller["military_count"] = max(
            0,
            int(purchase.seller.get("military_count") or 0) - purchase.quantity,
        )

    def _transfer_used_unit(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
        transfer: _UsedUnitTransfer,
    ) -> dict[str, Any]:
        source_unit = transfer.source_unit
        if purchase.quantity >= int(source_unit.get("strength") or 0):
            return source_unit

        source_strength = max(1, int(source_unit.get("strength") or 0))
        source_equipment = max(0, int(source_unit.get("equipment_quantity") or 0))
        travel_equipment = min(
            source_equipment,
            int(round(source_equipment * purchase.quantity / source_strength)),
        )
        source_unit["strength"] = source_strength - purchase.quantity
        source_unit["equipment_quantity"] = source_equipment - travel_equipment
        travel_unit = dict(source_unit)
        travel_unit["id"] = self._unit_factory.next_id(
            context.unit_rows,
            purchase.buyer_tag,
            str(source_unit.get("unit_type") or self._default_unit_type),
        )
        travel_unit["strength"] = purchase.quantity
        travel_unit["equipment_quantity"] = travel_equipment
        context.unit_rows.append(travel_unit)
        return travel_unit

    def _complete_used_unit_transfer(
        self,
        purchase: _PurchaseRequest,
        transfer: _UsedUnitTransfer,
        travel_unit: dict[str, Any],
    ) -> None:
        travel_unit.update(
            owner=str(purchase.buyer.get("id") or purchase.buyer_tag),
            foreign_order_id=f"market:{purchase.listing['id']}",
            original_cost=self._row_float(purchase.listing, "original_cost"),
            current_region_id=transfer.source_region_id,
            unit_lifecycle=(
                "in_transit" if len(transfer.route_plan.region_ids) > 1 else "available"
            ),
        )

    def _start_used_unit_transit(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
        transfer: _UsedUnitTransfer,
        travel_unit: dict[str, Any],
    ) -> None:
        source_geo = GeoCoordinate(
            float(travel_unit.get("latitude") or 0.0),
            float(travel_unit.get("longitude") or 0.0),
        )
        target_geo = context.region_locations.get(
            purchase.home_region_id,
            GeoCoordinate(0.0, 0.0),
        )
        first_region_id = transfer.first_region_id
        first_geo = transfer.first_geo
        if first_geo is None:
            return
        travel_unit.update(
            current_region_id=0,
            source_region_id=transfer.source_region_id,
            source_latitude=source_geo.latitude,
            source_longitude=source_geo.longitude,
            target_region_id=first_region_id,
            target_latitude=first_geo.latitude,
            target_longitude=first_geo.longitude,
            departed_at_minute=int(context.state.time.total_minutes),
            arrival_at_minute=int(context.state.time.total_minutes)
            + self._duration_policy.estimate_between(source_geo, first_geo),
            movement_progress=0.0,
            is_moving=True,
            engagement_mode="",
        )
        context.movement_by_unit[str(travel_unit.get("id"))] = {
            "unit_id": str(travel_unit.get("id")),
            "owner_country_id": purchase.buyer_tag,
            "source_region_id": transfer.source_region_id,
            "destination_region_id": int(purchase.home_region_id),
            "route_region_ids": list(transfer.route_plan.region_ids),
            "route_index": 1,
            "destination_latitude": target_geo.latitude,
            "destination_longitude": target_geo.longitude,
            "has_custom_destination": False,
            "is_naval_invasion": False,
            "status": "in_transit",
            "rejection_reason": "",
            "updated_at_minute": int(context.state.time.total_minutes),
        }

    def _purchase_new_unit(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
    ) -> None:
        self._settle_new_unit_accounts(purchase)
        purchase.listing["quantity"] = int(purchase.listing.get("quantity") or 0) - purchase.quantity
        context.unit_rows.append(self._create_market_unit(context, purchase))
        context.changed = True

    def _settle_new_unit_accounts(self, purchase: _PurchaseRequest) -> None:
        purchase.buyer["money_reserves"] = float(purchase.buyer.get("money_reserves") or 0.0) - purchase.total_cost
        purchase.buyer["military_count"] = int(purchase.buyer.get("military_count") or 0) + purchase.quantity
        purchase.seller["money_reserves"] = float(purchase.seller.get("money_reserves") or 0.0) + purchase.total_cost

    def _create_market_unit(
        self,
        context: _MarketPurchaseContext,
        purchase: _PurchaseRequest,
    ) -> dict[str, Any]:
        design = context.designs_by_id.get(str(purchase.listing.get("design_id") or ""), {})
        unit_type = (
            str(design.get("class_name") or self._default_unit_type)
            .strip()
            .lower()
            .replace(" ", "_")
            or self._default_unit_type
        )
        owner = str(purchase.buyer.get("id") or purchase.buyer_tag)
        return self._unit_factory.create(
            unit_id=self._unit_factory.next_id(
                context.unit_rows,
                owner,
                unit_type,
            ),
            owner=owner,
            unit_type=unit_type,
            strength=purchase.quantity,
            region_id=purchase.home_region_id,
            geo=context.region_locations.get(
                purchase.home_region_id,
                GeoCoordinate(0.0, 0.0),
            ),
            current_minute=context.state.time.total_minutes,
            design_id=str(purchase.listing.get("design_id") or ""),
        )

    def _publish_changes(self, context: _MarketPurchaseContext) -> None:
        context.state.update_table(
            "countries",
            pl.DataFrame(context.country_rows, schema=context.countries.schema),
        )
        remaining_listings = [
            row for row in context.listing_rows if int(row.get("quantity") or 0) > 0
        ]
        context.state.update_table(
            "unit_market_listings",
            pl.DataFrame(remaining_listings, schema=context.listings_table.schema),
        )
        if context.movement_table is None:
            return
        movement_frame = (
            pl.DataFrame(list(context.movement_by_unit.values()), schema=self._route_schema)
            if context.movement_by_unit
            else pl.DataFrame(schema=self._route_schema)
        )
        context.state.update_table("unit_movement_routes", movement_frame)

    def _row_float(self, row: dict[str, Any], key: str, fallback: float = 0.0) -> float:
        value = row.get(key)
        if value is None:
            value = fallback
        try:
            return float(value if value is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0
