import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import MilitarySystem, UNIT_SCHEMA
from modules.base.systems.military.research_program_system import ResearchProgramSystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.engine.simulator import Engine
from src.shared.actions import (
    ActionAttackUnit,
    ActionCreateTreaty,
    ActionQueueUnitProduction,
    ActionUpdateBudget,
)
from src.shared.events import EventBattleStarted, EventNewDay
from src.shared.state import GameState
from src.shared.system_interfaces import SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER


class _TimeSignalSystem:
    access = SystemAccess(phase=SystemPhase.CLOCK)
    runtime_state_contract = {}

    @property
    def id(self) -> str:
        return "base.time"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        state.events.append(EventNewDay(day=2, month=1, year=2001))


class _DependencyStub:
    access = SystemAccess(phase=SystemPhase.POPULATION)
    runtime_state_contract = {"_id": SYSTEM_STATE_HELPER}

    def __init__(self, system_id: str) -> None:
        self._id = system_id

    @property
    def id(self) -> str:
        return self._id

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return


class TestAISameTickIntegration(unittest.TestCase):
    def test_generated_actions_reach_existing_handlers_in_the_same_engine_step(self):
        state = self._state()
        initial_units = state.get_table("units")
        engine = Engine(dev_mode=True)
        engine.register_systems(
            [
                _TimeSignalSystem(),
                BootstrapSystem(),
                _DependencyStub("base.population"),
                _DependencyStub("base.economy"),
                _DependencyStub("base.trade"),
                AISystem(),
                DiplomacySystem(),
                ResearchProgramSystem(),
                MilitarySystem(),
                BudgetSystem(),
                CombatSystem(),
            ]
        )

        result = engine.step(state, [], 0.1)

        self.assertTrue(result.success)
        action_types = {type(action) for action in state.current_actions}
        self.assertTrue(
            {
                ActionUpdateBudget,
                ActionCreateTreaty,
                ActionQueueUnitProduction,
                ActionAttackUnit,
            }.issubset(action_types)
        )
        ai_index = [system.id for system in engine.execution_order].index("base.ai")
        for handler_id in (
            "base.diplomacy",
            "base.military_programs",
            "base.military",
            "base.budget",
            "base.combat",
        ):
            self.assertLess(
                ai_index,
                [system.id for system in engine.execution_order].index(handler_id),
            )

        countries = state.get_table("countries")
        ai_country = countries.filter(pl.col("id") == "AAA").row(0, named=True)
        player_country = countries.filter(pl.col("id") == "PLAYER").row(0, named=True)
        self.assertAlmostEqual(ai_country["personal_income_tax_rate"], 0.25)
        self.assertAlmostEqual(player_country["personal_income_tax_rate"], 0.20)

        queued = state.get_table("production_orders").filter(
            (pl.col("country_id") == "AAA") & (pl.col("status") == "queued")
        )
        self.assertEqual(queued.height, 1)

        pending = state.get_table("pending_treaties").filter(
            (pl.col("source_country_id") == "AAA")
            & (pl.col("target_country_id") == "DDD")
        )
        self.assertEqual(pending.height, 1)

        self.assertFalse(state.get_table("units").equals(initial_units))
        self.assertTrue(any(isinstance(event, EventBattleStarted) for event in state.events))
        self.assertFalse(any(self._acts_for_player(action) for action in state.current_actions))

    def test_region_release_preserves_sparse_runtime_schema(self):
        regions = pl.DataFrame(
            {
                "id": list(range(1, 102)),
                "owner": ["BBB"] * 101,
                "controller": ["AAA"] * 101,
                "region_name": [None] * 100 + ["Absheron Economic Region"],
            },
            schema_overrides={"region_name": pl.Utf8},
        )
        original_schema = regions.schema
        state = GameState(tables={"regions": regions})

        DiplomacySystem()._release_regions(state, {"AAA"}, {"BBB"})

        updated = state.get_table("regions")
        self.assertEqual(updated.schema, original_schema)
        self.assertEqual(updated["controller"].tail(1).item(), "BBB")

    def _state(self) -> GameState:
        countries = pl.DataFrame(
            [
                self._country("AAA", 100, 1_000_000_000.0, 100.0, 2_000_000_000.0),
                self._country("BBB", 500, 1_000_000_000.0, 100.0, 100.0),
                self._country("CCC", 50, 100_000_000.0, 100.0, 100.0),
                self._country("DDD", 100, 100_000_000.0, 100.0, 100.0),
                self._country("PLAYER", 100, 100_000_000.0, 100.0, 100.0),
            ]
        )
        regions = pl.DataFrame(
            {
                "id": [1, 2, 3, 4, 5],
                "owner": ["AAA", "BBB", "CCC", "DDD", "PLAYER"],
                "controller": ["AAA", "BBB", "CCC", "DDD", "PLAYER"],
                "latitude": [1.0, 2.0, 3.0, 4.0, 5.0],
                "longitude": [1.0, 2.0, 3.0, 4.0, 5.0],
                "area_km2": [100.0] * 5,
                "pop_14": [100.0] * 5,
                "pop_15_64": [500.0] * 5,
                "pop_65": [50.0] * 5,
            }
        )
        units = pl.DataFrame(
            [
                self._unit("a1", "AAA", 200, 1),
                self._unit("b1", "BBB", 500, 2),
                self._unit("c1", "CCC", 50, 1),
            ],
            schema=UNIT_SCHEMA,
        )
        state = GameState(
            tables={
                "countries": countries,
                "regions": regions,
                "units": units,
                "countries_relations": pl.DataFrame(
                    {"source": ["AAA"], "target": ["DDD"], "value": [85.0]}
                ),
                "countries_treaties": pl.DataFrame(
                    schema={
                        "id": pl.Utf8,
                        "type": pl.Utf8,
                        "members": pl.List(pl.Utf8),
                        "side_a": pl.List(pl.Utf8),
                        "side_b": pl.List(pl.Utf8),
                        "status": pl.Utf8,
                    }
                ),
                "countries_wars": pl.DataFrame(
                    {
                        "id": ["war-1", "war-2"],
                        "side_a": [["AAA"], ["AAA"]],
                        "side_b": [["BBB"], ["CCC"]],
                        "status": ["active", "active"],
                        "created_at": ["2001-01-01", "2001-01-01"],
                    }
                ),
            }
        )
        state.globals["player_tag"] = "PLAYER"
        ensure_base_tables(state)
        return state

    def _country(
        self,
        tag: str,
        military_count: int,
        reserves: float,
        revenue: float,
        expense: float,
    ) -> dict:
        return {
            "id": tag,
            "gdp": 1_000_000_000.0,
            "human_dev": 0.7,
            "personal_income_tax_rate": 0.2,
            "money_reserves": reserves,
            "total_annual_revenue": revenue,
            "total_annual_expense": expense,
            "trait_threat_perception": 1.0,
            "military_count": military_count,
            "is_playable": True,
            "stability": 0.6,
        }

    def _unit(
        self,
        unit_id: str,
        owner: str,
        strength: int,
        region_id: int,
    ) -> dict:
        defaults = {
            pl.Utf8: "",
            pl.Int64: 0,
            pl.Int32: 0,
            pl.Float64: 0.0,
            pl.Boolean: False,
        }
        row = {
            column: defaults[dtype]
            for column, dtype in UNIT_SCHEMA.items()
        }
        row.update(
            {
                "id": unit_id,
                "owner": owner,
                "unit_type": "army",
                "strength": strength,
                "current_region_id": region_id,
                "latitude": float(region_id),
                "longitude": float(region_id),
                "source_region_id": region_id,
                "source_latitude": float(region_id),
                "source_longitude": float(region_id),
                "target_region_id": -1,
                "engagement_mode": "idle",
            }
        )
        return row

    def _acts_for_player(self, action) -> bool:
        source_fields = (
            "country_tag",
            "buyer_country_tag",
            "source_country_tag",
            "responder_country_tag",
        )
        return any(
            str(getattr(action, field, "")).upper() == "PLAYER"
            for field in source_fields
        )


if __name__ == "__main__":
    unittest.main()
