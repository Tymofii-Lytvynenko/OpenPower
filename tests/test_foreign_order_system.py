from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

import polars as pl

from modules.base.schema import build_base_schema_registry, ensure_base_tables
from modules.base.systems.military.foreign_order_system import ForeignOrderSystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, MilitarySystem, UnitFactory
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from src.core.map.geo import GeoCoordinate
from src.shared.actions import (
    ActionBuyMarketUnit,
    ActionCancelForeignUnitOrder,
    ActionCreateUnitDesign,
    ActionListUsedUnit,
    ActionQueueUnitProduction,
    ActionRequestForeignUnitOrder,
    ActionRespondForeignUnitOrder,
    ActionSetForeignOrderAcceptance,
    ActionWithdrawUsedUnitListing,
)
from src.shared.config import GameConfig
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.state import GameState


class ForeignOrderSystemTest(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN"], "money_reserves": [100.0, 100.0],
                "gdp": [1000.0, 900.0], "military_count": [10, 8],
            }),
            "regions": pl.DataFrame({
                "id": [1, 2], "owner": ["CAN", "USA"],
                "latitude": [0.0, 10.0], "longitude": [0.0, 20.0],
            }),
            "units": pl.DataFrame(schema=UNIT_SCHEMA),
        })
        ensure_base_tables(state)
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "trade", "country_id": "USA", "effect": "weapons_market_access",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        state.update_table("unit_designs", pl.DataFrame([{
            "id": "can-design", "country_id": "CAN", "branch": "ground",
            "class_name": "infantry", "display_name": "Infantry", "cost": 10.0,
        }], schema=state.get_table("unit_designs").schema))
        state.globals["foreign_order_production_minutes"] = 1
        return state

    def _set_seller_acceptance(
        self,
        state: GameState,
        *,
        accepts: bool = True,
        multiplier: float | None = 1.25,
    ) -> None:
        table = state.get_table("seller_acceptance_profiles")
        state.update_table(
            "seller_acceptance_profiles",
            pl.DataFrame(
                [
                    {
                        "country_id": "CAN",
                        "accepts_foreign_orders": accepts,
                        "price_multiplier": multiplier,
                        "cancellation_penalty": 0.01,
                    }
                ],
                schema=table.schema,
            ),
        )

    @staticmethod
    def _due_order(**changes) -> dict:
        order = {
            "id": "foreign-order-coverage",
            "buyer_country_id": "USA",
            "seller_country_id": "CAN",
            "design_id": "can-design",
            "quantity": 1,
            "price": 10.0,
            "production_cost": 5.0,
            "status": "in_production",
            "created_at_minute": 0,
            "due_at_minute": 0,
            "updated_at_minute": 0,
            "reason": "",
            "unit_ids": [],
        }
        order.update(changes)
        return order

    def test_order_requires_seller_acceptance_and_delivers_into_transit(self) -> None:
        state = self._state()
        system = ForeignOrderSystem()
        state.current_actions = [ActionSetForeignOrderAcceptance("CAN", "CAN", True)]
        system.update(state, 0.0)
        self.assertTrue(state.get_table("seller_acceptance_profiles")["accepts_foreign_orders"][0])

        state.current_actions = [ActionRequestForeignUnitOrder("USA", "USA", "CAN", "can-design", 2)]
        system.update(state, 0.0)
        order = state.get_table("foreign_unit_orders").to_dicts()[0]
        self.assertEqual(order["status"], "pending_seller_acceptance")

        state.current_actions = [ActionRespondForeignUnitOrder("CAN", order["id"], True)]
        system.update(state, 0.0)
        accepted = state.get_table("foreign_unit_orders").to_dicts()[0]
        self.assertEqual(accepted["status"], "in_production")
        self.assertEqual(accepted["price"], 25.0)

        state.time.total_minutes = accepted["due_at_minute"]
        state.current_actions = []
        system.update(state, 0.0)
        in_transit = state.get_table("foreign_unit_orders").to_dicts()[0]
        self.assertEqual(in_transit["status"], "in_transit")
        unit = state.get_table("units").to_dicts()[0]
        self.assertEqual(unit["owner"], "USA")
        self.assertEqual(unit["foreign_order_id"], order["id"])
        self.assertEqual(unit["unit_lifecycle"], "in_transit")
        self.assertEqual(unit["current_region_id"], 0)
        self.assertEqual(in_transit["unit_ids"], [unit["id"]])
        self.assertEqual(in_transit["payment_status"], "settled")
        self.assertEqual(state.get_table("unit_movement_routes").height, 1)
        countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
        self.assertEqual(countries["USA"]["money_reserves"], 75.0)
        self.assertEqual(countries["CAN"]["money_reserves"], 105.0)

        state.time.total_minutes = unit["arrival_at_minute"]
        MilitarySystem().update(state, 0.0)
        state.current_actions = []
        system.update(state, 0.0)
        delivered = state.get_table("foreign_unit_orders").to_dicts()[0]
        self.assertEqual(delivered["status"], "delivered")
        self.assertEqual(delivered["ownership_transferred_at_minute"], accepted["due_at_minute"])

    def test_scenario_permission_does_not_override_a_weapons_embargo(self) -> None:
        state = self._state()
        state.globals["foreign_order_permissions"] = [["USA", "CAN"]]
        state.update_table("treaty_effects", pl.DataFrame([
            {
                "treaty_id": "embargo", "country_id": "USA", "effect": "weapons_trade_embargo",
                "value": 1.0, "detail": json.dumps(["CAN"]),
            },
        ], schema=state.get_table("treaty_effects").schema))
        state.current_actions = [ActionSetForeignOrderAcceptance("CAN", "CAN", True)]
        system = ForeignOrderSystem()
        system.update(state, 0.0)
        state.current_actions = [ActionRequestForeignUnitOrder("USA", "USA", "CAN", "can-design", 2)]

        system.update(state, 0.0)

        self.assertTrue(state.get_table("foreign_unit_orders").is_empty())
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 100.0)

    def test_used_unit_listing_transfers_existing_force_and_routes_it(self) -> None:
        state = self._state()
        unit = {
            "id": "can-tank-1", "owner": "CAN", "unit_type": "tank", "design_id": "can-design",
            "unit_domain": "land", "strength": 3, "current_region_id": 1,
            "latitude": 0.0, "longitude": 0.0, "source_region_id": 1,
            "source_latitude": 0.0, "source_longitude": 0.0, "target_region_id": -1,
            "target_latitude": 0.0, "target_longitude": 0.0, "departed_at_minute": 0,
            "arrival_at_minute": 0, "movement_progress": 0.0, "is_moving": False,
            "engagement_mode": "", "readiness_status": "ready", "readiness_transition_id": "",
            "readiness_progress": 0.0, "readiness_eta_minute": 0, "training_level": "Regular",
            "training_state": "", "training_progress": 0.0, "combat_posture": "hold",
            "combat_strength_modifier": 1.0, "combat_casualty_modifier": 1.0,
            "production_order_id": "", "foreign_order_id": "", "original_cost": 10.0,
            "unit_lifecycle": "available",
        }
        state.update_table("units", pl.DataFrame([unit], schema=UNIT_SCHEMA))
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "trade", "country_id": "USA", "effect": "weapons_market_access",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        state.current_actions = [ActionListUsedUnit("CAN", "CAN", "can-tank-1")]
        ForeignOrderSystem().update(state, 0.0)
        listing = state.get_table("unit_market_listings").to_dicts()[0]
        self.assertEqual(listing["price"], 7.5)
        self.assertEqual(listing["quantity"], 3)

        state.current_actions = [ActionBuyMarketUnit("USA", listing["id"], "USA", 2)]
        MilitarySystem().update(state, 0.0)
        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertEqual(units["can-tank-1"]["owner"], "CAN")
        self.assertEqual(units["can-tank-1"]["strength"], 1)
        purchased = [row for row in units.values() if row["owner"] == "USA"]
        self.assertEqual(len(purchased), 1)
        self.assertEqual(purchased[0]["strength"], 2)
        self.assertTrue(purchased[0]["is_moving"])
        self.assertEqual(purchased[0]["current_region_id"], 0)
        self.assertEqual(state.get_table("unit_movement_routes").height, 1)
        self.assertEqual(state.get_table("unit_market_listings")["quantity"][0], 1)

    def test_market_purchase_requires_authority_over_the_buyer(self) -> None:
        state = self._state()
        unit = {
            "id": "can-tank-1", "owner": "CAN", "unit_type": "tank", "design_id": "can-design",
            "unit_domain": "land", "strength": 3, "current_region_id": 1,
            "latitude": 0.0, "longitude": 0.0, "source_region_id": 1,
            "source_latitude": 0.0, "source_longitude": 0.0, "target_region_id": -1,
            "target_latitude": 0.0, "target_longitude": 0.0, "departed_at_minute": 0,
            "arrival_at_minute": 0, "movement_progress": 0.0, "is_moving": False,
            "engagement_mode": "", "readiness_status": "ready", "readiness_transition_id": "",
            "readiness_progress": 0.0, "readiness_eta_minute": 0, "training_level": "Regular",
            "training_state": "", "training_progress": 0.0, "combat_posture": "hold",
            "combat_strength_modifier": 1.0, "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0, "cohesion": 1.0, "reorganization_until_minute": 0,
            "production_order_id": "", "foreign_order_id": "", "original_cost": 10.0,
            "unit_lifecycle": "available",
        }
        state.update_table("units", pl.DataFrame([unit], schema=UNIT_SCHEMA))
        state.update_table("treaty_effects", pl.DataFrame([{
            "treaty_id": "trade", "country_id": "USA", "effect": "weapons_market_access",
            "value": 1.0, "detail": json.dumps(["CAN"]),
        }], schema=state.get_table("treaty_effects").schema))
        state.current_actions = [ActionListUsedUnit("CAN", "CAN", "can-tank-1")]
        ForeignOrderSystem().update(state, 0.0)
        listing_id = state.get_table("unit_market_listings")["id"][0]

        state.current_actions = [ActionBuyMarketUnit("CAN", listing_id, "USA", 2)]
        MilitarySystem().update(state, 0.0)

        self.assertEqual(state.get_table("units")["owner"].to_list(), ["CAN"])
        self.assertEqual(state.get_table("unit_market_listings")["quantity"][0], 3)
        self.assertEqual(state.get_table("countries").filter(pl.col("id") == "USA")["money_reserves"][0], 100.0)
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_cancelling_in_production_settles_elapsed_cost_and_relation_penalty(self) -> None:
        state = self._state()
        state.globals["foreign_order_production_minutes"] = 100
        state.update_table("countries_relations", pl.DataFrame([
            {"source": "USA", "target": "CAN", "value": 0.0},
            {"source": "CAN", "target": "USA", "value": 0.0},
        ]))
        system = ForeignOrderSystem()
        state.current_actions = [ActionSetForeignOrderAcceptance("CAN", "CAN", True)]
        system.update(state, 0.0)
        state.current_actions = [ActionRequestForeignUnitOrder("USA", "USA", "CAN", "can-design", 2)]
        system.update(state, 0.0)
        order = state.get_table("foreign_unit_orders").to_dicts()[0]
        state.current_actions = [ActionRespondForeignUnitOrder("CAN", order["id"], True)]
        system.update(state, 0.0)
        state.time.total_minutes = 50

        state.current_actions = [ActionCancelForeignUnitOrder("USA", order["id"])]
        system.update(state, 0.0)

        cancelled = state.get_table("foreign_unit_orders").to_dicts()[0]
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["incurred_cost"], 10.0)
        countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
        self.assertEqual(countries["USA"]["money_reserves"], 90.0)
        self.assertEqual(countries["CAN"]["money_reserves"], 110.0)
        self.assertEqual(state.get_table("countries_relations")["value"].to_list(), [-1.0, -1.0])
        self.assertTrue(state.get_table("units").is_empty())

    def test_used_listing_can_be_withdrawn_and_duplicate_purchase_cannot_transfer_twice(self) -> None:
        state = self._state()
        unit = UnitFactory().create(
            "can-infantry-001", "CAN", "infantry", 3, 1, GeoCoordinate(0.0, 0.0), 0,
            design_id="can-design", training_level="Regular",
        )
        unit.update(original_cost=10.0, unit_lifecycle="available")
        state.update_table("units", pl.DataFrame([unit], schema=UNIT_SCHEMA))
        foreign_orders = ForeignOrderSystem()
        state.current_actions = [ActionListUsedUnit("CAN", "CAN", unit["id"])]
        foreign_orders.update(state, 0.0)
        withdrawn_id = state.get_table("unit_market_listings")["id"][0]

        state.current_actions = [ActionWithdrawUsedUnitListing("CAN", "CAN", withdrawn_id)]
        foreign_orders.update(state, 0.0)
        withdrawn = state.get_table("unit_market_listings").filter(pl.col("id") == withdrawn_id).to_dicts()[0]
        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertEqual(withdrawn["quantity"], 0)
        self.assertEqual(state.get_table("units")["owner"].to_list(), ["CAN"])

        state.current_actions = [ActionListUsedUnit("CAN", "CAN", unit["id"])]
        foreign_orders.update(state, 0.0)
        listing_id = state.get_table("unit_market_listings").filter(pl.col("status") == "listed")["id"][0]
        buy = ActionBuyMarketUnit("USA", listing_id, "USA", 3)
        state.current_actions = [buy]
        military = MilitarySystem()
        military.update(state, 0.0)
        first_transfer = state.get_table("units").sort("id").to_dicts()
        country_balances = state.get_table("countries").sort("id")["money_reserves"].to_list()
        state.current_actions = [buy]
        military.update(state, 0.0)

        final_units = state.get_table("units").to_dicts()
        self.assertEqual(sum(int(row["strength"]) for row in final_units), 3)
        self.assertEqual(sum(row["owner"] == "USA" for row in final_units), 1)
        self.assertEqual(state.get_table("countries").sort("id")["money_reserves"].to_list(), country_balances)
        self.assertEqual(state.get_table("units").sort("id").to_dicts(), first_transfer)
        self.assertTrue(state.get_table("unit_market_listings").is_empty())

    def test_production_and_foreign_transit_survive_snapshot_and_disk_continuation(self) -> None:
        state = self._state()
        research = ResearchProgramSystem()
        state.current_actions = [ActionCreateUnitDesign(
            "USA", "USA", "ground", "infantry", "Local Infantry", {"cost": 10.0},
        )]
        research.update(state, 0.0)
        local_design_id = state.get_table("unit_designs").filter(pl.col("country_id") == "USA")["id"][0]
        state.current_actions = [ActionQueueUnitProduction("USA", "USA", local_design_id, 1)]
        research.update(state, 0.0)
        order = state.get_table("production_orders").to_dicts()[0]
        state.update_table("production_orders", state.get_table("production_orders").with_columns(
            pl.when(pl.col("id") == order["id"]).then(0.25).otherwise(pl.col("progress")).alias("progress"),
            pl.when(pl.col("id") == order["id"]).then(order["work_required"] * 0.75).otherwise(pl.col("remaining_work")).alias("remaining_work"),
        ))

        foreign = ForeignOrderSystem()
        state.globals["foreign_order_production_minutes"] = 1
        state.current_actions = [ActionSetForeignOrderAcceptance("CAN", "CAN", True)]
        foreign.update(state, 0.0)
        state.current_actions = [ActionRequestForeignUnitOrder("USA", "USA", "CAN", "can-design", 1)]
        foreign.update(state, 0.0)
        contract_id = state.get_table("foreign_unit_orders")["id"][0]
        state.current_actions = [ActionRespondForeignUnitOrder("CAN", contract_id, True)]
        foreign.update(state, 0.0)
        state.time.total_minutes = 1
        state.current_actions = []
        foreign.update(state, 0.0)
        self.assertEqual(state.get_table("foreign_unit_orders")["status"][0], "in_transit")
        self.assertFalse(state.get_table("unit_movement_routes").is_empty())

        registry = build_base_schema_registry()
        snapshot = GameState.from_ipc(state.to_ipc())
        registry.ensure_state(snapshot)
        persisted_tables = (
            "production_orders", "unit_deployment_orders", "unit_movement_routes",
            "foreign_unit_orders", "seller_acceptance_profiles", "units", "countries",
        )
        for table_name in persisted_tables:
            self.assertEqual(snapshot.get_table(table_name).to_dicts(), state.get_table(table_name).to_dicts())

        with TemporaryDirectory() as temporary_directory:
            config = GameConfig(Path(temporary_directory))
            self.assertTrue(SaveWriter(config).save_game(state, "production-transit"))
            loaded = DataLoader(config, schema_registry=registry).load_save("production-transit")
            for table_name in persisted_tables:
                self.assertEqual(loaded.get_table(table_name).to_dicts(), state.get_table(table_name).to_dicts())

            continuations = (snapshot, loaded)
            for candidate in continuations:
                candidate.time.total_minutes = state.get_table("units")["arrival_at_minute"][0]
                candidate.current_actions = []
                MilitarySystem().update(candidate, 0.0)
                foreign.update(candidate, 0.0)
                ResearchProgramSystem()._advance_production(candidate, 1.0 / 365.25)
            for table_name in persisted_tables:
                self.assertEqual(continuations[0].get_table(table_name).to_dicts(), continuations[1].get_table(table_name).to_dicts())
            self.assertEqual(loaded.get_table("foreign_unit_orders")["status"][0], "delivered")

    def test_update_without_contract_tables_and_existing_acceptance_profile(self) -> None:
        system = ForeignOrderSystem()
        system.update(GameState(tables={}), 0.0)

        state = self._state()
        self._set_seller_acceptance(state)
        state.current_actions = [ActionSetForeignOrderAcceptance("CAN", "CAN", False)]
        system.update(state, 0.0)

        self.assertFalse(
            state.get_table("seller_acceptance_profiles")["accepts_foreign_orders"][0]
        )

    def test_acceptance_rejects_a_blank_seller_identity(self) -> None:
        state = self._state()
        profiles = []

        ForeignOrderSystem()._set_acceptance(
            state, profiles, ActionSetForeignOrderAcceptance("CAN", "", True)
        )

        self.assertEqual(profiles, [])

    def test_request_rejects_invalid_design_disabled_seller_and_duplicate_contract(self) -> None:
        system = ForeignOrderSystem()
        state = self._state()
        self._set_seller_acceptance(state)

        invalid_quantity = ActionRequestForeignUnitOrder(
            "USA", "USA", "CAN", "can-design", 0
        )
        missing_design = ActionRequestForeignUnitOrder(
            "USA", "USA", "CAN", "missing-design", 1
        )
        self.assertEqual(system._request(state, [], invalid_quantity), [])
        self.assertEqual(system._request(state, [], missing_design), [])

        self._set_seller_acceptance(state, accepts=False)
        disabled_seller = ActionRequestForeignUnitOrder(
            "USA", "USA", "CAN", "can-design", 1
        )
        self.assertEqual(system._request(state, [], disabled_seller), [])

        self._set_seller_acceptance(state)
        duplicate = {
            "id": "existing-order",
            "buyer_country_id": "USA",
            "seller_country_id": "CAN",
            "design_id": "can-design",
            "status": "accepted",
        }
        self.assertEqual(
            system._request(
                state,
                [duplicate],
                ActionRequestForeignUnitOrder(
                    "USA", "USA", "CAN", "can-design", 1
                ),
            ),
            [duplicate],
        )
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

    def test_respond_rejects_missing_wrong_actor_and_changed_acceptance(self) -> None:
        system = ForeignOrderSystem()
        state = self._state()
        profiles = state.get_table("seller_acceptance_profiles").to_dicts()
        system._respond(
            state,
            [],
            profiles,
            ActionRespondForeignUnitOrder("CAN", "missing", True),
        )
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

        pending = self._due_order(status="pending_seller_acceptance")
        system._respond(
            state,
            [pending],
            profiles,
            ActionRespondForeignUnitOrder("USA", pending["id"], True),
        )
        self.assertEqual(pending["status"], "pending_seller_acceptance")

        self._set_seller_acceptance(state, accepts=False)
        pending = self._due_order(status="pending_seller_acceptance")
        system._respond(
            state,
            [pending],
            state.get_table("seller_acceptance_profiles").to_dicts(),
            ActionRespondForeignUnitOrder("CAN", pending["id"], True),
        )
        self.assertEqual(pending["status"], "rejected")
        self.assertIn("acceptance changed", pending["reason"])

    def test_respond_rejection_and_default_price_multiplier(self) -> None:
        system = ForeignOrderSystem()
        state = self._state()
        self._set_seller_acceptance(state)
        pending = self._due_order(
            status="pending_seller_acceptance", production_cost=10.0
        )
        system._respond(
            state,
            [pending],
            state.get_table("seller_acceptance_profiles").to_dicts(),
            ActionRespondForeignUnitOrder("CAN", pending["id"], False),
        )
        self.assertEqual(pending["status"], "rejected")

        self._set_seller_acceptance(state, multiplier=None)
        state.globals["foreign_order_price_multiplier"] = 2.0
        pending = self._due_order(
            status="pending_seller_acceptance", production_cost=10.0
        )
        system._respond(
            state,
            [pending],
            state.get_table("seller_acceptance_profiles").to_dicts(),
            ActionRespondForeignUnitOrder("CAN", pending["id"], True),
        )
        self.assertEqual(pending["status"], "in_production")
        self.assertEqual(pending["price"], 20.0)

    def test_cancel_ignores_terminal_orders_and_rejects_unauthorized_or_unsettleable(self) -> None:
        system = ForeignOrderSystem()
        terminal = self._due_order(status="delivered")
        system._cancel(
            self._state(),
            [terminal],
            ActionCancelForeignUnitOrder("USA", terminal["id"]),
        )
        self.assertEqual(terminal["status"], "delivered")

        state = self._state()
        pending = self._due_order(status="pending_seller_acceptance")
        system._cancel(
            state,
            [pending],
            ActionCancelForeignUnitOrder("MEX", pending["id"]),
        )
        self.assertEqual(state.journal.command_results[-1]["status"], "rejected")

        state = self._state()
        countries = state.get_table("countries")
        rows = countries.to_dicts()
        next(row for row in rows if row["id"] == "USA")["money_reserves"] = 0.0
        state.update_table("countries", pl.DataFrame(rows, schema=countries.schema))
        state.time.total_minutes = 50
        producing = self._due_order(
            status="in_production",
            production_cost=20.0,
            due_at_minute=100,
            updated_at_minute=0,
        )
        system._cancel(
            state,
            [producing],
            ActionCancelForeignUnitOrder("USA", producing["id"]),
        )
        self.assertEqual(producing["status"], "in_production")
        self.assertIn("Insufficient funds", state.journal.command_results[-1]["reason"])

    def test_due_delivery_waits_for_tables_and_revalidates_contracts(self) -> None:
        system = ForeignOrderSystem()
        for missing_table in ("countries", "units"):
            with self.subTest(missing_table=missing_table):
                state = self._state()
                state.tables.pop(missing_table)
                order = self._due_order()
                system._deliver_due_orders(state, [order])
                self.assertEqual(order["status"], "in_production")

        state = self._state()
        self._set_seller_acceptance(state, accepts=False)
        order = self._due_order()
        system._deliver_due_orders(state, [order])
        self.assertEqual(order["status"], "cancelled")

        state = self._state()
        self._set_seller_acceptance(state)
        order = self._due_order(design_id="removed-design")
        system._deliver_due_orders(state, [order])
        self.assertEqual(order["status"], "cancelled")
        self.assertIn("design", order["reason"])

    def test_due_delivery_skips_other_orders_that_are_not_due(self) -> None:
        state = self._state()
        self._set_seller_acceptance(state)
        due = self._due_order(design_id="removed-design")
        future = self._due_order(id="future-order", due_at_minute=10)

        ForeignOrderSystem()._deliver_due_orders(state, [due, future])

        self.assertEqual(due["status"], "cancelled")
        self.assertEqual(future["status"], "in_production")

    def test_due_delivery_holds_for_demilitarization_funds_and_regions(self) -> None:
        system = ForeignOrderSystem()
        system._demilitarization_policy = SimpleNamespace(
            can_add=MagicMock(return_value=False)
        )
        state = self._state()
        self._set_seller_acceptance(state)
        order = self._due_order()
        system._deliver_due_orders(state, [order])
        self.assertEqual(order["status"], "in_production")
        self.assertIn("demilitarization", order["reason"])

        system = ForeignOrderSystem()
        state = self._state()
        self._set_seller_acceptance(state)
        countries = state.get_table("countries")
        rows = countries.to_dicts()
        next(row for row in rows if row["id"] == "USA")["money_reserves"] = 0.0
        state.update_table("countries", pl.DataFrame(rows, schema=countries.schema))
        order = self._due_order(price=25.0)
        system._deliver_due_orders(state, [order])
        self.assertIn("funds are insufficient", order["reason"])

        state = self._state()
        self._set_seller_acceptance(state)
        state.tables.pop("regions")
        order = self._due_order()
        system._deliver_due_orders(state, [order])
        self.assertIn("deployment region", order["reason"])

    def test_due_delivery_retains_order_when_route_or_route_table_is_unavailable(self) -> None:
        state = self._state()
        self._set_seller_acceptance(state)
        graph = SimpleNamespace(
            region_by_id={row["id"]: row for row in state.get_table("regions").to_dicts()},
            edge_distance_km={},
        )
        planner = MagicMock()
        planner.prepare.return_value = graph
        planner.plan.return_value = SimpleNamespace(
            is_valid=False,
            rejection_reason="No valid delivery route.",
            region_ids=(),
        )
        system = ForeignOrderSystem()
        system._route_planner = planner
        order = self._due_order()
        system._deliver_due_orders(state, [order])
        self.assertEqual(order["reason"], "No valid delivery route.")

        state = self._state()
        self._set_seller_acceptance(state)
        state.tables.pop("unit_movement_routes")
        order = self._due_order()
        ForeignOrderSystem()._deliver_due_orders(state, [order])
        self.assertIn("route table is unavailable", order["reason"])

    def test_refresh_delivery_status_handles_empty_missing_and_blocked_units(self) -> None:
        system = ForeignOrderSystem()
        system._refresh_delivery_status(
            GameState(tables={}),
            [{"id": "missing-table", "status": "in_transit", "unit_ids": ["u1"]}],
        )

        state = self._state()
        empty_only = [{"id": "empty", "status": "in_transit", "unit_ids": []}]
        system._refresh_delivery_status(state, empty_only)
        self.assertEqual(empty_only[0]["status"], "in_transit")

        orders = [
            {"id": "empty", "status": "in_transit", "unit_ids": []},
            {"id": "missing", "status": "in_transit", "unit_ids": ["missing-unit"]},
        ]
        system._refresh_delivery_status(state, orders)
        self.assertEqual(orders[1]["status"], "blocked")

        unit = UnitFactory().create(
            "blocked-unit", "USA", "infantry", 1, 2, GeoCoordinate(10.0, 20.0), 0
        )
        unit["unit_lifecycle"] = "route_blocked"
        state.update_table("units", pl.DataFrame([unit], schema=UNIT_SCHEMA))
        blocked = [{"id": "blocked", "status": "in_transit", "unit_ids": ["blocked-unit"]}]
        system._refresh_delivery_status(state, blocked)
        self.assertEqual(blocked[0]["status"], "blocked")

    def test_listing_guards_and_withdrawal_authority_leave_listings_unchanged(self) -> None:
        system = ForeignOrderSystem()
        listing = {"id": "listing-1", "seller_country_id": "CAN", "status": "listed"}
        listings = [listing]
        action = ActionListUsedUnit("CAN", "CAN", "missing-unit")
        system._list_used_unit(GameState(tables={}), listings, action)
        system._list_used_unit(self._state(), listings, action)
        system._withdraw_listing(
            self._state(),
            listings,
            ActionWithdrawUsedUnitListing("USA", "CAN", "listing-1"),
        )
        self.assertEqual(listings, [listing])

    def test_order_helper_fallbacks_and_naval_deployment_selection(self) -> None:
        system = ForeignOrderSystem()
        state = self._state()
        state.globals["foreign_order_permissions"] = [["USA", "CAN"]]
        self.assertTrue(system._eligible(state, "USA", "CAN"))

        missing_tables = GameState(tables={})
        self.assertFalse(system._seller_accepts(missing_tables, "CAN"))
        self.assertIsNone(system._design(missing_tables, "design", "CAN"))
        self.assertIsNone(system._home_region(missing_tables, "CAN"))
        self.assertIsNone(system._deployment_region(missing_tables, "USA", "land"))
        system._apply_relation_penalty(missing_tables, "USA", "CAN")
        system._publish(missing_tables, self._due_order())
        self.assertEqual(len(missing_tables.events), 1)
        self.assertEqual(system._unique_id("unit", {"unit", "unit-002"}), "unit-003")
        self.assertEqual(system._finite("not-a-number"), 0.0)

        access = SimpleNamespace(
            can_station=MagicMock(return_value=False),
            can_transit=MagicMock(return_value=True),
        )
        self.assertFalse(
            system._foreign_route_access(access, "USA", "CAN", {"owner": "MEX"}, True)
        )
        self.assertTrue(
            system._foreign_route_access(access, "USA", "CAN", {"owner": "MEX"}, False)
        )

        naval_state = self._state()
        naval_state.tables["regions"] = pl.DataFrame(
            [
                {"id": 1, "owner": "USA", "is_port": False, "region_type": "land"},
                {"id": 2, "owner": "USA", "is_port": True, "region_type": "port"},
            ]
        )
        naval_state.tables["country_governments"] = pl.DataFrame(
            {"country_id": ["USA"], "capital_region_id": [2]}
        )
        self.assertEqual(system._deployment_region(naval_state, "USA", "naval")["id"], 2)
        naval_state.tables["regions"] = pl.DataFrame(
            [{"id": 1, "owner": "USA", "is_port": False, "region_type": "land"}]
        )
        self.assertIsNone(system._deployment_region(naval_state, "USA", "naval"))


if __name__ == "__main__":
    unittest.main()
