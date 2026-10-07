from __future__ import annotations

import math

import polars as pl

from modules.base.systems.world.ai.budget_policy import BudgetPolicy, BudgetSurvivalPolicy
from modules.base.systems.world.ai.military_policies import MilitaryROIPolicy
from modules.base.systems.world.ai_system import AISystem
from src.core.ai_framework import AITableContext
from src.shared.actions import ActionBuildUnit, ActionUpdateBudget
from src.shared.events import EventNewDay
from src.shared.state import GameState


def _context(revenue: float, expense: float, reserves: float) -> AITableContext:
    return AITableContext(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "is_playable": [True],
                    "total_annual_revenue": [revenue],
                    "total_annual_expense": [expense],
                    "money_reserves": [reserves],
                    "personal_income_tax_rate": [0.20],
                    "gdp": [1_000_000.0],
                    "human_dev": [0.6],
                    "corruption": [0.2],
                    "stability": [0.7],
                }
            )
        },
        day_ordinal=0,
        total_minutes=0,
        date_text="2001-01-01 00:00",
    )


def test_budget_ai_tax_hike_matches_twelve_month_runway_formula() -> None:
    candidates = BudgetSurvivalPolicy().build_candidates(
        _context(100.0, 300.0, 50.0)
    ).collect()
    critical = candidates.filter(pl.col("reason_code") == "critical_deficit")

    assert critical.height == 1
    row = critical.row(0, named=True)
    assert math.isclose(row["utility"], 0.75, rel_tol=1e-12)
    assert math.isclose(row["tax_value"], 0.22, rel_tol=1e-12)

    action = BudgetSurvivalPolicy().resolve_action(row)
    assert isinstance(action, ActionUpdateBudget)
    assert action.allocations["personal_income_tax_rate"] == 0.22


def test_budget_ai_maps_positive_cashflow_to_no_bankruptcy_pressure() -> None:
    candidates = BudgetPolicy().build_candidates(_context(200.0, 100.0, 1_000.0)).collect()

    assert not candidates.filter(pl.col("reason_code") == "critical_deficit").height
    assert candidates.height > 0
    assert candidates.get_column("_runway_months").unique().to_list() == [999.0]


def test_budget_policy_keeps_only_the_best_discretionary_candidate_per_country() -> None:
    candidates = BudgetPolicy().build_candidates(
        _context(200.0, 100.0, 1_000.0)
    ).collect()

    assert candidates.height == 1
    assert candidates["country_id"].to_list() == ["AAA"]
    assert candidates["reason_code"].to_list() == ["sustained_surplus"]


def test_ai_system_dispatches_critical_runway_tax_update() -> None:
    state = GameState(tables={"countries": _context(100.0, 300.0, 50.0).tables["countries"]})
    state.events = [EventNewDay(1, 1, 2001)]

    AISystem().update(state, 0.0)

    action = next(item for item in state.current_actions if isinstance(item, ActionUpdateBudget))
    assert action.player_id == "ai_system"
    assert action.country_tag == "AAA"
    assert action.allocations["personal_income_tax_rate"] == 0.22


def test_military_roi_uses_specified_five_year_cost_benefit_and_threat() -> None:
    countries = pl.DataFrame(
        {
            "id": ["AAA"],
            "is_playable": [True],
            "gdp": [1_000_000_000.0],
            "human_dev": [0.5],
            "military_count": [2],
            "trait_threat_perception": [1.2],
            "money_reserves": [10_000_000.0],
            "total_annual_revenue": [200_000.0],
            "total_annual_expense": [100_000.0],
        }
    )
    context = AITableContext(
        tables={"countries": countries},
        day_ordinal=0,
        total_minutes=0,
        date_text="2001-01-01 00:00",
    )

    candidates = MilitaryROIPolicy().build_candidates(context).collect()

    assert candidates.height == 1
    row = candidates.row(0, named=True)
    expected_cost = 1_000_000.0 + (500_000.0 * 0.5 * 5.0)
    expected_benefit = 1_000_000_000.0 * 0.01 * (0.85**2) * 1.2
    expected_roi = (expected_benefit - expected_cost) / expected_cost
    assert math.isclose(row["unit_cost_5y"], expected_cost, rel_tol=1e-12)
    assert math.isclose(row["unit_benefit_5y"], expected_benefit, rel_tol=1e-12)
    assert math.isclose(row["military_roi"], expected_roi, rel_tol=1e-12)
    assert row["utility"] == 1.0
    action = MilitaryROIPolicy().resolve_action(row)
    assert action == ActionBuildUnit("ai_system", "AAA", "infantry", 1)


def test_military_roi_rejects_nonpositive_return_insufficient_reserves_or_deficit() -> None:
    countries = pl.DataFrame(
        {
            "id": ["LOW_GDP", "LOW_CASH", "DEFICIT"],
            "is_playable": [True, True, True],
            "gdp": [1_000_000.0, 1_000_000_000.0, 1_000_000_000.0],
            "human_dev": [0.5, 0.5, 0.5],
            "military_count": [0, 0, 0],
            "money_reserves": [10_000_000.0, 2_250_000.0, 10_000_000.0],
            "total_annual_revenue": [200_000.0, 200_000.0, 100.0],
            "total_annual_expense": [100_000.0, 100_000.0, 200.0],
        }
    )
    context = AITableContext(
        tables={"countries": countries},
        day_ordinal=0,
        total_minutes=0,
        date_text="2001-01-01 00:00",
    )

    assert MilitaryROIPolicy().build_candidates(context).collect().is_empty()


def test_ai_system_dispatches_profitable_military_roi_build() -> None:
    countries = pl.DataFrame(
        {
            "id": ["AAA"],
            "is_playable": [True],
            "gdp": [1_000_000_000.0],
            "human_dev": [0.5],
            "military_count": [0],
            "money_reserves": [10_000_000.0],
            "total_annual_revenue": [200_000.0],
            "total_annual_expense": [100_000.0],
        }
    )
    state = GameState(tables={"countries": countries})
    state.events = [EventNewDay(1, 1, 2001)]

    AISystem().update(state, 0.0)

    action = next(item for item in state.current_actions if isinstance(item, ActionBuildUnit))
    assert action.player_id == "ai_system"
    assert action.country_tag == "AAA"
    assert action.unit_type == "infantry"
    assert action.count == 1
