import unittest

import polars as pl

from modules.base.systems.world.ai import (
    BudgetPolicy,
    DiplomacyPolicy,
    MilitaryOperationsPolicy,
    ProcurementPolicy,
    WarPolicy,
)
from modules.base.systems.world.ai.diplomacy_policy import TREATY_PROFILES
from modules.base.systems.world.ai_system import AISystem
from src.core.ai_framework import AITableContext, DeclarativeAIFramework
from src.shared.actions import (
    ActionAttackUnit,
    ActionBuyMarketUnit,
    ActionDeclareWar,
    ActionMoveUnit,
    ActionOfferPeace,
    ActionQueueUnitProduction,
    ActionRespondTreaty,
    ActionUpdateBudget,
)
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.shared.treaties import TREATY_DEFINITIONS


class TestTabularAIPolicies(unittest.TestCase):
    def test_policy_contracts_are_lazy_and_cover_current_treaty_vocabulary(self):
        context = self._context(
            {
                "countries": self._countries(["AAA"]),
                "regions": self._regions(),
                "units": self._units([]),
                "countries_wars": self._wars([]),
                "unit_designs": self._designs([]),
                "production_orders": self._orders([]),
            }
        )

        for policy in (
            BudgetPolicy(),
            ProcurementPolicy(),
            MilitaryOperationsPolicy(),
            WarPolicy(),
            DiplomacyPolicy(),
        ):
            with self.subTest(policy=policy.id):
                self.assertIsInstance(policy.build_candidates(context), pl.LazyFrame)

        self.assertEqual(
            {row[0] for row in TREATY_PROFILES},
            set(TREATY_DEFINITIONS),
        )

    def test_budget_handles_critical_managed_and_surplus_cases(self):
        countries = self._countries(
            ["CRITICAL", "MANAGED", "SURPLUS"],
            {
                "CRITICAL": {
                    "money_reserves": 0.0,
                    "total_annual_revenue": 100.0,
                    "total_annual_expense": 1000.0,
                },
                "MANAGED": {
                    "money_reserves": 5000.0,
                    "total_annual_revenue": 100.0,
                    "total_annual_expense": 200.0,
                },
                "SURPLUS": {
                    "money_reserves": 1000.0,
                    "total_annual_revenue": 200.0,
                    "total_annual_expense": 100.0,
                },
            },
        )
        result = self._evaluate(BudgetPolicy(), {"countries": countries})
        actions = {
            action.country_tag: action
            for action in result.actions
            if isinstance(action, ActionUpdateBudget)
        }

        self.assertEqual(set(actions), {"CRITICAL", "MANAGED", "SURPLUS"})
        self.assertAlmostEqual(
            actions["CRITICAL"].allocations["personal_income_tax_rate"],
            0.25,
        )
        self.assertGreater(len(actions["CRITICAL"].allocations), 2)
        self.assertEqual(len(actions["MANAGED"].allocations), 1)
        self.assertAlmostEqual(next(iter(actions["MANAGED"].allocations.values())), 0.45)
        self.assertEqual(len(actions["SURPLUS"].allocations), 1)
        self.assertAlmostEqual(next(iter(actions["SURPLUS"].allocations.values())), 0.55)

    def test_procurement_prefers_cheaper_market_then_falls_back_to_owned_design(self):
        tables = self._procurement_tables()
        market_result = self._evaluate(ProcurementPolicy(), tables)
        market_actions = [
            action for action in market_result.actions if isinstance(action, ActionBuyMarketUnit)
        ]

        self.assertEqual(len(market_actions), 1)
        self.assertEqual(market_actions[0].buyer_country_tag, "AAA")

        without_market = dict(tables)
        without_market.pop("unit_market_listings")
        production_result = self._evaluate(ProcurementPolicy(), without_market)
        production_actions = [
            action
            for action in production_result.actions
            if isinstance(action, ActionQueueUnitProduction)
        ]

        self.assertEqual(len(production_actions), 1)
        self.assertEqual(production_actions[0].country_tag, "AAA")

    def test_procurement_does_not_duplicate_active_orders(self):
        tables = self._procurement_tables()
        tables["production_orders"] = self._orders(
            [
                {
                    "id": "order-1",
                    "country_id": "AAA",
                    "design_id": "aaa-ground",
                    "quantity": 10,
                    "status": "queued",
                }
            ]
        )

        result = self._evaluate(ProcurementPolicy(), tables)

        self.assertFalse(
            any(
                isinstance(action, (ActionQueueUnitProduction, ActionBuyMarketUnit))
                and getattr(action, "country_tag", getattr(action, "buyer_country_tag", "")) == "AAA"
                for action in result.actions
            )
        )

    def test_local_superiority_attacks_and_moving_units_are_never_reordered(self):
        tables = {
            "countries": self._countries(
                ["AAA", "BBB"],
                {"AAA": {"military_count": 200.0}, "BBB": {"military_count": 100.0}},
            ),
            "regions": self._regions(),
            "units": self._units(
                [
                    self._unit("a1", "AAA", 200, 1),
                    self._unit("b1", "BBB", 100, 1),
                ]
            ),
            "countries_wars": self._wars(
                [self._war("war-1", ["AAA"], ["BBB"], "2000-01-01")]
            ),
        }
        result = self._evaluate(MilitaryOperationsPolicy(), tables)

        attacks = [action for action in result.actions if isinstance(action, ActionAttackUnit)]
        self.assertEqual([(action.attacker_unit_id, action.defender_unit_id) for action in attacks], [("a1", "b1")])

        moving_tables = dict(tables)
        moving_tables["units"] = self._units(
            [
                self._unit("a1", "AAA", 200, 1, is_moving=True),
                self._unit("b1", "BBB", 100, 1),
            ]
        )
        moving_result = self._evaluate(MilitaryOperationsPolicy(), moving_tables)
        self.assertFalse(
            any(
                isinstance(action, (ActionAttackUnit, ActionMoveUnit))
                and getattr(action, "attacker_unit_id", getattr(action, "unit_id", "")) == "a1"
                for action in moving_result.actions
            )
        )

    def test_military_orders_prioritize_liberation_and_apply_daily_quota(self):
        regions = self._regions(
            [
                self._region(1, "AAA", "AAA", 0.0, 0.0),
                self._region(2, "AAA", "BBB", 1.0, 1.0),
                self._region(3, "BBB", "BBB", 2.0, 2.0),
            ]
        )
        units = [
            self._unit(f"a{index}", "AAA", 20, 1, latitude=0.0, longitude=0.0)
            for index in range(6)
        ]
        units.append(self._unit("b1", "BBB", 200, 3, latitude=2.0, longitude=2.0))
        tables = {
            "countries": self._countries(["AAA", "BBB"]),
            "regions": regions,
            "units": self._units(units),
            "countries_wars": self._wars(
                [self._war("war-1", ["AAA"], ["BBB"], "2000-01-01")]
            ),
        }

        result = self._evaluate(MilitaryOperationsPolicy(), tables)
        moves = [
            action
            for action in result.actions
            if isinstance(action, ActionMoveUnit) and action.unit_id.startswith("a")
        ]

        self.assertEqual(len(moves), 4)
        self.assertTrue(all(action.target_region_id == 2 for action in moves))
        self.assertTrue(
            all(
                reason == "liberate_home_region"
                for reason in result.decisions.filter(pl.col("country_id") == "AAA")["reason_code"].to_list()
            )
        )

    def test_peacetime_forces_return_home_when_home_share_is_below_half(self):
        tables = {
            "countries": self._countries(["AAA", "BBB"]),
            "regions": self._regions(
                [
                    self._region(1, "AAA", "AAA", 0.0, 0.0),
                    self._region(2, "BBB", "BBB", 2.0, 2.0),
                ]
            ),
            "units": self._units(
                [self._unit("a1", "AAA", 100, 2, latitude=2.0, longitude=2.0)]
            ),
            "countries_wars": self._wars([]),
        }

        result = self._evaluate(MilitaryOperationsPolicy(), tables)
        moves = [
            action
            for action in result.actions
            if isinstance(action, ActionMoveUnit) and action.unit_id.startswith("a")
        ]

        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].target_region_id, 1)

    def test_war_declaration_thresholds_and_active_pair_deduplication(self):
        tables = self._war_candidate_tables()
        result = self._evaluate(WarPolicy(), tables)
        declarations = [
            action for action in result.actions if isinstance(action, ActionDeclareWar)
        ]

        self.assertEqual(len(declarations), 1)
        self.assertEqual(
            (declarations[0].source_country_tag, declarations[0].target_country_tag),
            ("AAA", "BBB"),
        )

        tables["countries_wars"] = self._wars(
            [self._war("war-1", ["BBB"], ["AAA"], "2000-01-01")]
        )
        duplicate_result = self._evaluate(WarPolicy(), tables)
        self.assertFalse(
            any(isinstance(action, ActionDeclareWar) for action in duplicate_result.actions)
        )

    def test_peace_timing_distinguishes_offensive_and_defensive_sides(self):
        countries = self._countries(
            ["AAA", "BBB"],
            {
                "AAA": {
                    "money_reserves": -10.0,
                    "total_annual_revenue": 10.0,
                    "total_annual_expense": 100.0,
                    "military_count": 20.0,
                    "stability": 0.2,
                },
                "BBB": {
                    "money_reserves": 1000.0,
                    "total_annual_revenue": 100.0,
                    "total_annual_expense": 50.0,
                    "military_count": 300.0,
                },
            },
        )
        offensive = {
            "countries": countries,
            "countries_wars": self._wars(
                [self._war("war-1", ["AAA"], ["BBB"], "2001-01-01")]
            ),
        }

        first_day = self._evaluate(WarPolicy(), offensive, date_text="2001-01-01 00:00")
        self.assertFalse(
            any(
                isinstance(action, ActionOfferPeace)
                and action.source_country_tag == "AAA"
                for action in first_day.actions
            )
        )

        after_month = self._evaluate(WarPolicy(), offensive, date_text="2001-02-02 00:00")
        self.assertTrue(
            any(
                isinstance(action, ActionOfferPeace)
                and action.source_country_tag == "AAA"
                for action in after_month.actions
            )
        )

        defensive = dict(offensive)
        defensive["countries_wars"] = self._wars(
            [self._war("war-2", ["BBB"], ["AAA"], "2001-01-01")]
        )
        defensive_result = self._evaluate(
            WarPolicy(),
            defensive,
            date_text="2001-01-01 00:00",
        )
        self.assertTrue(
            any(
                isinstance(action, ActionOfferPeace)
                and action.source_country_tag == "AAA"
                for action in defensive_result.actions
            )
        )

    def test_pending_treaties_receive_one_ai_response_each_without_player_impersonation(self):
        countries = self._countries(["SOURCE", "FRIEND", "HOSTILE", "PLAYER"])
        pending = pl.DataFrame(
            {
                "id": ["proposal-1", "proposal-2"],
                "source_country_id": ["SOURCE", "SOURCE"],
                "target_country_id": ["FRIEND", "HOSTILE"],
                "treaty_type": ["alliance", "alliance"],
                "required_responses": [["FRIEND", "PLAYER"], ["HOSTILE"]],
                "status": ["pending", "pending"],
            }
        )
        relations = pl.DataFrame(
            {
                "source": ["FRIEND", "HOSTILE"],
                "target": ["SOURCE", "SOURCE"],
                "value": [80.0, -80.0],
            }
        )
        result = self._evaluate(
            DiplomacyPolicy(),
            {
                "countries": countries,
                "pending_treaties": pending,
                "countries_relations": relations,
            },
            player_tag="PLAYER",
        )
        responses = [
            action for action in result.actions if isinstance(action, ActionRespondTreaty)
        ]

        self.assertEqual(
            {(action.responder_country_tag, action.accept) for action in responses},
            {("FRIEND", True), ("HOSTILE", False)},
        )

    def test_treaty_groups_use_real_state_signals_and_existing_pairs_are_deduplicated(self):
        countries = self._countries(
            ["AAA", "BBB"],
            {
                "AAA": {
                    "gdp": 1_000_000.0,
                    "money_reserves": 1_000_000.0,
                    "total_annual_revenue": 200.0,
                    "total_annual_expense": 50.0,
                    "human_dev": 0.9,
                    "budget_research_ratio": 0.8,
                    "military_count": 500.0,
                },
                "BBB": {
                    "gdp": 100_000.0,
                    "money_reserves": 100.0,
                    "total_annual_revenue": 50.0,
                    "total_annual_expense": 200.0,
                    "human_dev": 0.4,
                    "budget_research_ratio": 0.1,
                    "foreign_debt": 1000.0,
                    "military_count": 100.0,
                },
            },
        )
        friendly = {
            "countries": countries,
            "countries_relations": pl.DataFrame(
                {"source": ["AAA"], "target": ["BBB"], "value": [85.0]}
            ),
        }
        friendly_candidates = DiplomacyPolicy().build_candidates(
            self._context(friendly)
        ).collect()
        proposed_friendly = set(
            friendly_candidates.filter(pl.col("action_kind") == "create_treaty")[
                "treaty_type"
            ].to_list()
        )
        self.assertTrue(
            {
                "alliance",
                "military_trespassing_right",
                "cultural_exchanges",
                "noble_cause",
                "research_partnership",
                "human_development_collaboration",
                "economic_partnership",
                "common_market",
                "economic_aid",
                "assume_foreign_debt",
                "weapons_trade",
            }.issubset(proposed_friendly)
        )

        friendly["countries_treaties"] = self._treaties(
            [
                {
                    "id": "alliance-1",
                    "type": "alliance",
                    "members": ["BBB", "AAA"],
                    "side_a": ["BBB", "AAA"],
                    "side_b": [],
                    "status": "active",
                    "open_to_new_members": True,
                    "source_country_id": "BBB",
                }
            ]
        )
        deduplicated = DiplomacyPolicy().build_candidates(
            self._context(friendly)
        ).collect()
        duplicate_alliance = deduplicated.filter(
            (pl.col("action_kind") == "create_treaty")
            & (pl.col("treaty_type") == "alliance")
        )
        self.assertTrue(duplicate_alliance.is_empty())

        hostile = {
            "countries": countries,
            "countries_relations": pl.DataFrame(
                {"source": ["AAA"], "target": ["BBB"], "value": [-90.0]}
            ),
            "regions": self._regions(
                [
                    self._region(1, "AAA", "BBB", 0.0, 0.0),
                    self._region(2, "BBB", "AAA", 1.0, 1.0),
                ]
            ),
            "units": self._units(
                [
                    self._unit("a1", "AAA", 500, 2),
                    self._unit("b1", "BBB", 100, 1),
                ]
            ),
        }
        hostile_candidates = DiplomacyPolicy().build_candidates(
            self._context(hostile)
        ).collect()
        proposed_hostile = set(
            hostile_candidates.filter(pl.col("action_kind") == "create_treaty")[
                "treaty_type"
            ].to_list()
        )
        self.assertTrue(
            {
                "request_war_declaration",
                "request_military_presence_removal",
                "annexation",
                "free_region",
                "economic_embargo",
                "weapons_trade_embargo",
            }.issubset(proposed_hostile)
        )

    def test_system_protects_player_and_non_playable_countries(self):
        countries = self._countries(
            ["PLAYER", "AI", "DISABLED"],
            {
                tag: {
                    "money_reserves": 0.0,
                    "total_annual_revenue": 10.0,
                    "total_annual_expense": 1000.0,
                }
                for tag in ("PLAYER", "AI", "DISABLED")
            },
        ).with_columns(
            pl.Series("is_playable", [True, True, False])
        )
        state = GameState(tables={"countries": countries})
        state.globals["player_tag"] = "PLAYER"
        state.events.append(EventNewDay(day=2, month=1, year=2001))

        AISystem().update(state, 0.1)

        country_sources = {
            getattr(action, "country_tag", "")
            for action in state.current_actions
            if isinstance(action, ActionUpdateBudget)
        }
        self.assertEqual(country_sources, {"AI"})

    def _evaluate(
        self,
        policy,
        tables: dict[str, pl.DataFrame],
        *,
        date_text: str = "2001-01-01 00:00",
        player_tag: str = "",
    ):
        return DeclarativeAIFramework(policy).evaluate(
            self._context(tables, date_text=date_text, player_tag=player_tag)
        )

    def _context(
        self,
        tables: dict[str, pl.DataFrame],
        *,
        date_text: str = "2001-01-01 00:00",
        player_tag: str = "",
    ) -> AITableContext:
        return AITableContext(
            tables=tables,
            day_ordinal=0,
            total_minutes=0,
            date_text=date_text,
            player_tag=player_tag,
        )

    def _countries(
        self,
        tags: list[str],
        overrides: dict[str, dict] | None = None,
    ) -> pl.DataFrame:
        overrides = overrides or {}
        defaults = {
            "is_playable": True,
            "gdp": 1_000_000.0,
            "money_reserves": 100_000.0,
            "total_annual_revenue": 100.0,
            "total_annual_expense": 100.0,
            "human_dev": 0.6,
            "stability": 0.6,
            "corruption_index": 0.2,
            "military_count": 100.0,
            "personal_income_tax_rate": 0.2,
            "budget_research_ratio": 0.5,
            "foreign_debt": 0.0,
        }
        for column in (
            "budget_health_ratio",
            "budget_edu_ratio",
            "budget_social_ratio",
            "budget_gov_ratio",
            "budget_env_ratio",
            "budget_infra_ratio",
            "budget_telecom_ratio",
            "budget_propaganda_ratio",
            "budget_tourism_promo_ratio",
        ):
            defaults[column] = 0.5
        defaults["budget_imf_ratio"] = 0.0
        return pl.DataFrame(
            {
                "id": tags,
                **{
                    column: [
                        overrides.get(tag, {}).get(column, value)
                        for tag in tags
                    ]
                    for column, value in defaults.items()
                },
            }
        )

    def _procurement_tables(self) -> dict[str, pl.DataFrame]:
        return {
            "countries": self._countries(
                ["AAA", "BBB"],
                {
                    "AAA": {"military_count": 100.0, "money_reserves": 1_000_000.0},
                    "BBB": {"military_count": 500.0},
                },
            ),
            "units": self._units(
                [
                    self._unit("a1", "AAA", 100, 1),
                    self._unit("b1", "BBB", 500, 2),
                ]
            ),
            "countries_wars": self._wars(
                [self._war("war-1", ["AAA"], ["BBB"], "2000-01-01")]
            ),
            "unit_designs": self._designs(
                [
                    self._design("aaa-ground", "AAA", 100.0),
                    self._design("bbb-ground", "BBB", 80.0),
                ]
            ),
            "production_orders": self._orders([]),
            "unit_market_listings": pl.DataFrame(
                {
                    "id": ["listing-1"],
                    "seller_country_id": ["BBB"],
                    "design_id": ["bbb-ground"],
                    "quantity": [20],
                    "price": [50.0],
                    "eligibility": ["open"],
                }
            ),
        }

    def _war_candidate_tables(self) -> dict[str, pl.DataFrame]:
        return {
            "countries": self._countries(
                ["AAA", "BBB"],
                {
                    "AAA": {
                        "money_reserves": 1_000_000.0,
                        "total_annual_revenue": 200.0,
                        "total_annual_expense": 100.0,
                        "military_count": 500.0,
                    },
                    "BBB": {"military_count": 100.0},
                },
            ),
            "countries_relations": pl.DataFrame(
                {"source": ["AAA"], "target": ["BBB"], "value": [-80.0]}
            ),
        }

    def _regions(self, rows: list[dict] | None = None) -> pl.DataFrame:
        rows = rows or [self._region(1, "AAA", "AAA", 0.0, 0.0)]
        return pl.DataFrame(rows)

    def _region(
        self,
        region_id: int,
        owner: str,
        controller: str,
        latitude: float,
        longitude: float,
    ) -> dict:
        return {
            "id": region_id,
            "owner": owner,
            "controller": controller,
            "latitude": latitude,
            "longitude": longitude,
            "area_km2": 100.0,
            "pop_14": 100.0,
            "pop_15_64": 500.0,
            "pop_65": 50.0,
        }

    def _units(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8,
            "owner": pl.Utf8,
            "strength": pl.Int64,
            "current_region_id": pl.Int32,
            "latitude": pl.Float64,
            "longitude": pl.Float64,
            "is_moving": pl.Boolean,
            "engagement_mode": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)

    def _unit(
        self,
        unit_id: str,
        owner: str,
        strength: int,
        region_id: int,
        *,
        latitude: float = 0.0,
        longitude: float = 0.0,
        is_moving: bool = False,
    ) -> dict:
        return {
            "id": unit_id,
            "owner": owner,
            "strength": strength,
            "current_region_id": region_id,
            "latitude": latitude,
            "longitude": longitude,
            "is_moving": is_moving,
            "engagement_mode": "idle",
        }

    def _wars(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8,
            "side_a": pl.List(pl.Utf8),
            "side_b": pl.List(pl.Utf8),
            "status": pl.Utf8,
            "created_at": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)

    def _war(
        self,
        war_id: str,
        side_a: list[str],
        side_b: list[str],
        created_at: str,
    ) -> dict:
        return {
            "id": war_id,
            "side_a": side_a,
            "side_b": side_b,
            "status": "active",
            "created_at": created_at,
        }

    def _designs(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8,
            "country_id": pl.Utf8,
            "cost": pl.Float64,
            "quality": pl.Float64,
            "speed": pl.Float64,
            "firepower": pl.Float64,
        }
        return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)

    def _design(self, design_id: str, country: str, cost: float) -> dict:
        return {
            "id": design_id,
            "country_id": country,
            "cost": cost,
            "quality": 0.6,
            "speed": 0.5,
            "firepower": 0.7,
        }

    def _orders(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8,
            "country_id": pl.Utf8,
            "design_id": pl.Utf8,
            "quantity": pl.Int32,
            "status": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)

    def _treaties(self, rows: list[dict]) -> pl.DataFrame:
        schema = {
            "id": pl.Utf8,
            "type": pl.Utf8,
            "members": pl.List(pl.Utf8),
            "side_a": pl.List(pl.Utf8),
            "side_b": pl.List(pl.Utf8),
            "status": pl.Utf8,
            "open_to_new_members": pl.Boolean,
            "source_country_id": pl.Utf8,
        }
        return pl.DataFrame(rows, schema=schema)


if __name__ == "__main__":
    unittest.main()
