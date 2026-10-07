from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.military.readiness_system import ReadinessSystem
from modules.base.systems.politics.political_effect_policy import aggregate_political_effects
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.shared.actions import ActionSetUnitReadiness
from src.shared.events import EventNewDay, EventRealSecond
from src.shared.state import GameState


SECONDS_PER_GAME_YEAR = 365.25 * 24 * 60 * 60


def test_effect_aggregation_filters_domain_time_and_caps_combined_outputs() -> None:
    effects = pl.DataFrame(
        {
            "country_id": ["AAA", "AAA", "AAA", "BBB", "AAA"],
            "domain": ["tax", "tax", "rights", "tax", "tax"],
            "effect": ["rate", "rate", "rate", "rate", "rate"],
            "value": [0.8, 0.7, 0.6, -0.4, 0.9],
            "effective_at_minute": [0, 0, 0, 0, 20],
            "expires_at_minute": [0, 0, 0, 0, 0],
            "status": ["active", "active", "active", "active", "active"],
        }
    )

    result = aggregate_political_effects(effects, 10, domain="tax", effect="rate")

    assert result == {"AAA": 1.0, "BBB": -0.4}


def test_budget_uses_tax_effect_without_rewriting_the_country_policy() -> None:
    state = _budget_state(
        effects=[_effect("AAA", "tax", "personal_income_tax_rate_delta", 0.1)]
    )
    state.events = [EventRealSecond(SECONDS_PER_GAME_YEAR, False)]

    BudgetSystem().update(state, 0.0)

    country = state.get_table("countries").row(by_predicate=pl.col("id") == "AAA", named=True)
    assert abs(country["total_annual_revenue"] - 100.0) < 1e-9
    assert country["personal_income_tax_rate"] == 0.2


def test_economy_applies_only_declared_economic_and_labor_modifiers() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA", "BBB"],
                    "money_reserves": [0.0, 0.0],
                    "internal_tax_rate": [0.0, 0.0],
                    "economic_production_modifier": [1.0, 1.0],
                    "industrial_growth_rate": [0.0, 0.0],
                }
            ),
            "regions": pl.DataFrame(
                {"id": [1, 2], "owner": ["AAA", "BBB"], "pop_14": [0, 0], "pop_15_64": [0, 0], "pop_65": [0, 0]}
            ),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "game_resource_id": ["steel", "steel"],
                    "domestic_production": [100.0, 100.0],
                }
            ),
            "political_effects": pl.DataFrame(
                [
                    _effect("AAA", "economy", "production_modifier", 0.2),
                    _effect("AAA", "labor", "labor_supply_modifier", 0.1),
                    _effect("AAA", "rights", "public_rights", 0.8),
                ]
            ),
        }
    )
    ensure_base_tables(state)
    state.events = [EventRealSecond(SECONDS_PER_GAME_YEAR, False)]

    InternalEconomySystem().update(state, 0.0)

    countries = state.get_table("countries")
    assert countries.filter(pl.col("id") == "AAA")["gdp"][0] == 132.0
    assert countries.filter(pl.col("id") == "BBB")["gdp"][0] == 100.0


def test_migration_policy_view_consumes_only_effective_country_signals() -> None:
    state = GameState(
        tables={
            "migration_policies": pl.DataFrame(
                {
                    "country_id": ["AAA", "BBB"],
                    "entry_rate": [0.5, 0.5],
                    "exit_rate": [0.5, 0.5],
                    "enforcement_strength": [0.5, 0.5],
                    "effective_at_minute": [0, 0],
                }
            ),
            "political_effects": pl.DataFrame(
                [
                    _effect("AAA", "migration", "entry_rate", 0.2),
                    _effect("AAA", "migration", "enforcement_strength", 0.1),
                    _effect("AAA", "migration", "exit_rate", 0.5, effective=200),
                ]
            ),
        }
    )
    ensure_base_tables(state)
    state.time.total_minutes = 100

    policies = MigrationSystem()._effective_policy_map(state, 100)

    assert policies["AAA"]["entry_rate"] == 0.7
    assert policies["AAA"]["enforcement_strength"] == 0.6
    assert policies["AAA"]["exit_rate"] == 0.5
    assert policies["BBB"]["entry_rate"] == 0.5


def test_military_readiness_uses_effect_without_mutating_other_units() -> None:
    state = GameState(
        tables={
            "units": pl.DataFrame(
                {
                    "id": ["AAA-1", "BBB-1"],
                    "owner": ["AAA", "BBB"],
                    "readiness_status": ["parked", "parked"],
                    "readiness_progress": [0.0, 0.0],
                    "readiness_transition_id": ["", ""],
                    "readiness_eta_minute": [0, 0],
                }
            ),
            "political_effects": pl.DataFrame([_effect("AAA", "readiness", "transition_duration_modifier", 0.25)]),
        }
    )
    state.current_actions = [ActionSetUnitReadiness("AAA", "AAA-1", "ready")]

    ReadinessSystem().update(state, 0.0)

    transitions = state.get_table("unit_readiness_transitions")
    assert transitions.filter(pl.col("unit_id") == "AAA-1")["completes_at_minute"][0] == 3_600
    assert state.get_table("units").filter(pl.col("id") == "BBB-1")["readiness_eta_minute"][0] == 0


def test_rights_and_stability_signals_affect_the_existing_political_target() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [80.0],
                    "gvt_stability": [80.0],
                    "gvt_corruption": [0.0],
                    "human_dev": [0.5],
                    "economic_political_modifier": [1.0],
                }
            ),
            "political_effects": pl.DataFrame(
                [
                    _effect("AAA", "rights", "public_rights", 1.0),
                    _effect("AAA", "stability", "stability_modifier", 1.0),
                ]
            ),
        }
    )
    ensure_base_tables(state)
    state.time.total_minutes = 7 * 24 * 60
    state.time.day = 8
    state.events = [EventNewDay(8, 1, 2001)]

    PoliticsSystem().update(state, 0.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["gvt_approval"] == 80.0
    assert country["gvt_stability"] == 81


def _budget_state(*, effects: list[dict]) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gdp": [1_000.0],
                    "human_dev": [1.0],
                    "personal_income_tax_rate": [0.2],
                    "money_reserves": [0.0],
                    "corruption_index": [0.0],
                }
            ),
            "political_effects": pl.DataFrame(effects),
        }
    )
    ensure_base_tables(state)
    return state


def _effect(
    country_id: str,
    domain: str,
    effect: str,
    value: float,
    *,
    effective: int = 0,
) -> dict:
    return {
        "id": f"{country_id}:{domain}:{effect}:{effective}",
        "country_id": country_id,
        "source_type": "test",
        "source_id": "test-source",
        "domain": domain,
        "effect": effect,
        "value": value,
        "effective_at_minute": effective,
        "expires_at_minute": 0,
        "status": "active",
        "reason": "controlled integration test",
    }
