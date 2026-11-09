from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polars as pl

from modules.base.systems.military.market_purchase_service import (
    DEFAULT_MOVE_MINUTES,
    MilitaryMarketPurchaseService,
    _MarketPurchaseContext,
    _MarketPurchaseParties,
    _MarketRouteAccess,
    _PurchaseRequest,
    _UsedUnitTransfer,
)
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionBuyMarketUnit


class MarketPurchaseServiceCoverageTest(unittest.TestCase):
    def _service(self):
        dependencies = {
            "factory": Mock(),
            "duration": Mock(),
            "access": Mock(),
            "routes": Mock(),
            "demilitarization": Mock(),
            "weapons_trade": Mock(),
        }
        service = MilitaryMarketPurchaseService(
            unit_factory=dependencies["factory"],
            duration_policy=dependencies["duration"],
            access_policy=dependencies["access"],
            route_planner=dependencies["routes"],
            demilitarization_policy=dependencies["demilitarization"],
            weapons_trade_policy=dependencies["weapons_trade"],
            authorization_policy=lambda state, player_id, buyer_tag: True,
            route_schema={},
            default_unit_type="infantry",
        )
        dependencies["weapons_trade"].can_order.return_value = True
        return service, dependencies

    def _context(self, *, listing=None, buyer=None, seller=None, **changes):
        listing = listing or {
            "id": "listing-1",
            "seller_country_id": "CAN",
            "status": "listed",
            "quantity": 3,
            "price": 5.0,
            "unit_id": "used-1",
        }
        buyer = buyer or {"id": "USA", "money_reserves": 100.0, "military_count": 0}
        seller = seller or {"id": "CAN", "money_reserves": 100.0, "military_count": 3}
        state = SimpleNamespace(
            tables={"treaty_effects": None},
            globals={"tick": 0},
            journal=SimpleNamespace(append_command_result=Mock()),
            time=SimpleNamespace(total_minutes=10),
            update_table=Mock(),
        )
        values = {
            "state": state,
            "countries": pl.DataFrame([buyer, seller]),
            "listings_table": pl.DataFrame([listing]),
            "home_regions_by_country": {"USA": 2},
            "region_locations": {1: GeoCoordinate(0.0, 0.0), 2: GeoCoordinate(1.0, 1.0)},
            "unit_rows": [],
            "country_rows": [buyer, seller],
            "countries_by_tag": {"USA": buyer, "CAN": seller},
            "listing_rows": [listing],
            "listings_by_id": {"listing-1": listing},
            "region_rows": [{"id": 1, "owner": "CAN"}, {"id": 2, "owner": "USA"}],
            "adjacency_rows": [],
            "movement_table": None,
            "movement_by_unit": {},
            "designs_by_id": {},
        }
        values.update(changes)
        return _MarketPurchaseContext(**values)

    def _purchase(self, *, listing=None, buyer=None, quantity=2, total_cost=10.0):
        listing = listing or {"id": "listing-1", "unit_id": "used-1"}
        buyer = buyer or {"id": "USA", "money_reserves": 100.0, "military_count": 0}
        seller = {"id": "CAN", "money_reserves": 100.0, "military_count": 3}
        return _PurchaseRequest(
            listing=listing,
            buyer=buyer,
            seller=seller,
            buyer_tag="USA",
            seller_tag="CAN",
            quantity=quantity,
            total_cost=total_cost,
            home_region_id=2,
        )

    def test_route_access_uses_station_and_transit_policies(self) -> None:
        access_context = SimpleNamespace(
            can_station=Mock(return_value=False),
            can_transit=Mock(return_value=True),
        )
        access = _MarketRouteAccess(access_context, "USA", "CAN")

        self.assertFalse(access.can_enter({"owner": "USA"}, final=True))
        self.assertTrue(access.can_enter({"owner": "CAN"}, final=False))
        self.assertTrue(access.can_enter({"owner": "MEX"}, final=False))
        access_context.can_transit.return_value = False
        self.assertFalse(access.can_enter({"owner": "MEX"}, final=False))

    def test_preparation_rejects_demilitarization_and_missing_home_region(self) -> None:
        service, dependencies = self._service()
        context = self._context()
        action = ActionBuyMarketUnit("player", "listing-1", "USA", 2)
        dependencies["demilitarization"].can_add.return_value = False

        self.assertIsNone(service._prepare_purchase(context, action))

        dependencies["demilitarization"].can_add.return_value = True
        context.home_regions_by_country = {}
        self.assertIsNone(service._prepare_purchase(context, action))

    def test_party_and_cost_validation_reject_invalid_market_data(self) -> None:
        service, dependencies = self._service()
        withdrawn_listing = {
            "id": "listing-1",
            "seller_country_id": "CAN",
            "status": "withdrawn",
            "quantity": 3,
            "price": 5.0,
        }
        context = self._context(listing=withdrawn_listing)
        action = ActionBuyMarketUnit("player", "listing-1", "USA", 2)

        self.assertIsNone(service._resolve_purchase_parties(context, action))
        self.assertFalse(service._listing_has_valid_parties(None, {}, {}))
        parties = _MarketPurchaseParties(withdrawn_listing, {}, {}, "USA", "CAN")
        self.assertIsNone(service._purchase_total_cost(context, parties, 0))
        dependencies["weapons_trade"].can_order.return_value = False
        self.assertIsNone(service._purchase_total_cost(context, parties, 2))

        dependencies["weapons_trade"].can_order.return_value = True
        dependencies["demilitarization"].can_add.return_value = True
        context.listings_by_id["listing-1"]["status"] = "listed"
        context.home_regions_by_country = {"USA": 2}
        dependencies["weapons_trade"].can_order.return_value = False
        self.assertIsNone(service._prepare_purchase(context, action))

    def test_used_purchase_stops_when_transfer_or_funds_are_unavailable(self) -> None:
        service, _ = self._service()
        context = self._context()
        purchase = self._purchase()

        with patch.object(service, "_prepare_used_unit_transfer", return_value=None):
            service._purchase_used_unit(context, purchase)
        self.assertFalse(context.changed)

        with patch.object(service, "_find_transfer_source", return_value=None):
            self.assertIsNone(service._prepare_used_unit_transfer(context, purchase))

        purchase.buyer["money_reserves"] = 0.0
        with (
            patch.object(service, "_find_transfer_source", return_value={"id": "used-1"}),
            patch.object(service, "_plan_used_unit_route", return_value=object()),
        ):
            self.assertIsNone(service._prepare_used_unit_transfer(context, purchase))

    def test_transfer_source_requires_matching_owner_and_stationary_unit(self) -> None:
        service, _ = self._service()
        context = self._context(unit_rows=[])
        purchase = self._purchase()

        self.assertIsNone(service._find_transfer_source(context, purchase))

        context.unit_rows = [{"id": "used-1", "owner": "CAN", "strength": 1}]
        self.assertIsNone(service._find_transfer_source(context, purchase))

        self.assertFalse(service._is_transfer_source({"id": "other", "owner": "CAN"}, "used-1", "CAN"))
        self.assertFalse(service._is_transfer_source({"id": "used-1", "owner": "USA"}, "used-1", "CAN"))
        self.assertFalse(service._is_transfer_source(
            {"id": "used-1", "owner": "CAN", "is_moving": True}, "used-1", "CAN",
        ))
        self.assertTrue(service._is_transfer_source(
            {"id": "used-1", "owner": "can", "is_moving": False}, "used-1", "CAN",
        ))

    def test_route_planning_rejects_invalid_routes_and_missing_first_stop(self) -> None:
        service, dependencies = self._service()
        context = self._context()
        purchase = self._purchase()
        dependencies["access"].for_country.return_value = SimpleNamespace(
            can_station=Mock(return_value=True),
            can_transit=Mock(return_value=True),
        )
        source = {"current_region_id": 1}

        dependencies["routes"].plan.return_value = SimpleNamespace(is_valid=False, region_ids=[])
        self.assertIsNone(service._plan_used_unit_route(context, purchase, source))

        dependencies["routes"].plan.return_value = SimpleNamespace(is_valid=True, region_ids=[1, 3, 2])
        self.assertIsNone(service._plan_used_unit_route(context, purchase, source))

    def test_route_segment_uses_default_duration_without_both_locations(self) -> None:
        service, _ = self._service()

        self.assertEqual(service._route_segment_minutes({"id": 1}, {"id": 2}, {}), float(DEFAULT_MOVE_MINUTES))

    def test_transit_and_publish_helpers_return_when_optional_data_is_absent(self) -> None:
        service, _ = self._service()
        context = self._context(movement_table=None)
        purchase = self._purchase()
        transfer = _UsedUnitTransfer(
            source_unit={},
            source_region_id=1,
            route_plan=SimpleNamespace(region_ids=[1, 2]),
            first_region_id=2,
            first_geo=None,
        )

        service._start_used_unit_transit(context, purchase, transfer, {})
        service._publish_changes(context)

        self.assertEqual(context.state.update_table.call_count, 2)

    def test_row_float_uses_fallback_and_rejects_invalid_values(self) -> None:
        service, _ = self._service()

        self.assertEqual(service._row_float({"amount": None}, "amount", 2.5), 2.5)
        self.assertEqual(service._row_float({"amount": "invalid"}, "amount"), 0.0)

    def test_new_unit_purchase_settles_accounts_and_creates_design_unit(self) -> None:
        service, dependencies = self._service()
        context = self._context(
            listing={
                "id": "new-listing",
                "seller_country_id": "CAN",
                "status": "listed",
                "quantity": 4,
                "price": 5.0,
                "unit_id": "",
                "design_id": "design-1",
            },
        )
        context.designs_by_id = {"design-1": {"class_name": "Heavy Tank"}}
        purchase = _PurchaseRequest(
            listing=context.listing_rows[0],
            buyer=context.countries_by_tag["USA"],
            seller=context.countries_by_tag["CAN"],
            buyer_tag="USA",
            seller_tag="CAN",
            quantity=2,
            total_cost=10.0,
            home_region_id=2,
        )
        dependencies["factory"].next_id.return_value = "USA-heavy_tank-1"
        dependencies["factory"].create.return_value = {"id": "USA-heavy_tank-1"}

        service._purchase_new_unit(context, purchase)

        self.assertEqual(purchase.buyer["money_reserves"], 90.0)
        self.assertEqual(purchase.buyer["military_count"], 2)
        self.assertEqual(purchase.seller["money_reserves"], 110.0)
        self.assertEqual(context.listing_rows[0]["quantity"], 2)
        self.assertEqual(context.unit_rows, [{"id": "USA-heavy_tank-1"}])
        self.assertTrue(context.changed)
        dependencies["factory"].create.assert_called_once()
        self.assertEqual(dependencies["factory"].create.call_args.kwargs["unit_type"], "heavy_tank")

    def test_process_dispatches_new_unit_purchase(self) -> None:
        service, _ = self._service()
        context = self._context()
        purchase = self._purchase(listing={"id": "new-listing", "unit_id": ""})
        action = ActionBuyMarketUnit("player", "new-listing", "USA", 1)

        with (
            patch.object(service, "_build_context", return_value=context),
            patch.object(service, "_prepare_purchase", return_value=purchase),
            patch.object(service, "_purchase_new_unit") as purchase_new_unit,
        ):
            result = service.process(context.state, None, None, None, [action], {}, {})

        purchase_new_unit.assert_called_once_with(context, purchase)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
