from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from src.shared.events import EventNewDay, EventRealSecond
from src.shared.state import GameState
import tests.test_migration_system as migration_test


def _add_effect(
    state: GameState,
    *,
    effect_id: str,
    category: str,
    subject_type: str,
    subject_id: str,
    magnitude: float,
    starts_at_minute: int = 0,
    expires_at_minute: int = 100_000,
    status: str = "active",
) -> None:
    effects = state.get_table("random_event_effects")
    state.update_table(
        "random_event_effects",
        pl.concat(
            [
                effects,
                pl.DataFrame(
                    [
                        {
                            "id": effect_id,
                            "event_id": effect_id.split(":", 1)[0],
                            "category": category,
                            "subject_type": subject_type,
                            "subject_id": subject_id,
                            "magnitude": magnitude,
                            "unit": "index",
                            "application_mode": "recurring",
                            "starts_at_minute": starts_at_minute,
                            "expires_at_minute": expires_at_minute,
                            "last_applied_at_minute": 0,
                            "status": status,
                            "mitigation_pending": False,
                            "recovery_state_json": "{}",
                        }
                    ],
                    schema=effects.schema,
                    strict=False,
                ),
            ],
            how="vertical_relaxed",
        ),
    )


def _world(country_fields: dict | None = None) -> GameState:
    country = {"id": "AAA", **(country_fields or {})}
    state = GameState(
        tables={
            "countries": pl.DataFrame([country], strict=False),
            "regions": pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["AAA"],
                    "pop_14": [10_000],
                    "pop_15_64": [100_000],
                    "pop_65": [10_000],
                    "health_capacity": [1.0],
                }
            ),
            "domestic_production": pl.DataFrame(
                schema={
                    "country_id": pl.Utf8,
                    "game_resource_id": pl.Utf8,
                    "domestic_production": pl.Float64,
                }
            ),
            "resource_ledger": pl.DataFrame(
                schema={
                    "country_id": pl.Utf8,
                    "game_resource_id": pl.Utf8,
                    "consumption_usd": pl.Float64,
                }
            ),
        }
    )
    ensure_base_tables(state)
    return state


def test_effect_aggregation_filters_lifecycle_and_uses_bounded_scope_keys() -> None:
    state = _world()
    _add_effect(
        state,
        effect_id="active:one",
        category="health",
        subject_type="region",
        subject_id="1",
        magnitude=-0.03,
    )
    _add_effect(
        state,
        effect_id="future:one",
        category="health",
        subject_type="region",
        subject_id="1",
        magnitude=-0.5,
        starts_at_minute=20,
    )
    _add_effect(
        state,
        effect_id="expired:one",
        category="health",
        subject_type="region",
        subject_id="1",
        magnitude=-0.5,
        expires_at_minute=10,
    )

    totals = aggregate_active_effects(
        state.get_table("random_event_effects"),
        15,
        categories={"health"},
        subject_type="region",
    )

    assert totals == {("region", "1", "health"): -0.03}


def test_health_event_increases_regional_mortality_without_mutating_region_schema() -> None:
    state = _world({"life_expectancy": 67.0, "fertility_rate": 2.7, "economic_health": 1.0})
    base = _world({"life_expectancy": 67.0, "fertility_rate": 2.7, "economic_health": 1.0})
    state.time.total_minutes = 1_440
    base.time.total_minutes = 1_440
    _add_effect(
        state,
        effect_id="health:one",
        category="health",
        subject_type="region",
        subject_id="1",
        magnitude=-0.5,
    )

    PopulationSystem()._apply_tfr_growth(state, 365.25)
    PopulationSystem()._apply_tfr_growth(base, 365.25)

    assert state.get_table("regions").item(0, "pop_65") < base.get_table("regions").item(0, "pop_65")
    assert "_event_health_modifier" not in state.get_table("regions").columns


def test_health_and_strike_effects_flow_into_labor_outcomes() -> None:
    def run(with_effects: bool) -> GameState:
        state = _world(
            {
                "gdp": 1_000_000.0,
                "economic_previous_gdp": 1_000_000.0,
                "minimum_wage": 0.0,
                "economic_previous_minimum_wage": 0.0,
                "employment_rate": 0.95,
                "unemployment_rate": 0.05,
                "economic_health_last_update_minute": 0,
            }
        )
        state.time.total_minutes = 1_440
        state.events = [EventRealSecond(game_seconds_passed=86_400.0, is_paused=False)]
        if with_effects:
            _add_effect(
                state,
                effect_id="strike:employment",
                category="employment",
                subject_type="country",
                subject_id="AAA",
                magnitude=-0.4,
            )
            _add_effect(
                state,
                effect_id="epidemic:labour",
                category="labour",
                subject_type="country",
                subject_id="AAA",
                magnitude=-0.3,
            )
            _add_effect(
                state,
                effect_id="epidemic:health",
                category="health",
                subject_type="region",
                subject_id="1",
                magnitude=-0.2,
            )
        EconomicHealthSystem().update(state, 0.0)
        return state

    baseline = run(False).get_table("countries").row(0, named=True)
    affected = run(True).get_table("countries").row(0, named=True)

    assert affected["employment_rate"] < baseline["employment_rate"]
    assert affected["labor_supply"] < baseline["labor_supply"]
    assert affected["economic_health"] < baseline["economic_health"]


def test_migration_event_increases_authorized_origin_flow_only_within_capacity() -> None:
    baseline = migration_test.TestMigrationSystem._state()
    affected = migration_test.TestMigrationSystem._state()
    for state in (baseline, affected):
        state.time.total_minutes = 1_440
        state.events = [EventNewDay(day=1, month=2, year=2001)]
        state.update_table("migration_flows", pl.DataFrame(schema=state.get_table("migration_flows").schema))
        state.update_table(
            "countries",
            state.get_table("countries").with_columns(pl.lit(1.0).alias("migration_pressure")),
        )
        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("transport_access"),
                pl.when(pl.col("id") == 1).then(0.1).otherwise(0.9).alias("health_capacity"),
            ),
        )
        state.update_table(
            "migration_policies",
            state.get_table("migration_policies").with_columns(
                pl.lit(1.0).alias("entry_rate"),
                pl.lit(1.0).alias("exit_rate"),
                pl.lit(1.0).alias("family_reunification_rate"),
            ),
        )
    _add_effect(
        affected,
        effect_id="displacement:migration",
        category="migration",
        subject_type="region",
        subject_id="1",
        magnitude=0.5,
    )

    MigrationSystem().update(baseline, 0.0)
    MigrationSystem().update(affected, 0.0)

    baseline_flow = baseline.get_table("migration_flows").filter(pl.col("status") == "pending").row(0, named=True)
    affected_flow = affected.get_table("migration_flows").filter(pl.col("status") == "pending").row(0, named=True)
    assert affected_flow["population_count"] > baseline_flow["population_count"]
    assert affected_flow["population_count"] <= 80


def test_production_event_modifies_gdp_without_compounding_source_production() -> None:
    def run(with_effect: bool) -> GameState:
        state = _world({"money_reserves": 0.0, "internal_tax_rate": 0.0, "industrial_growth_rate": 0.0})
        production_schema = state.get_table("domestic_production").schema
        state.update_table(
            "domestic_production",
            pl.DataFrame(
                [{"country_id": "AAA", "game_resource_id": "machinery_and_instruments", "domestic_production": 1_000.0}],
                schema=production_schema,
                strict=False,
            ),
        )
        if with_effect:
            _add_effect(
                state,
                effect_id="boom:production",
                category="production",
                subject_type="country",
                subject_id="AAA",
                magnitude=0.25,
            )
        InternalEconomySystem()._process_economy(state, 0.0)
        return state

    baseline = run(False)
    affected = run(True)

    assert affected.get_table("countries").item(0, "gdp") > baseline.get_table("countries").item(0, "gdp")
    assert affected.get_table("domestic_production").item(0, "domestic_production") == baseline.get_table("domestic_production").item(0, "domestic_production")


def test_boom_and_strike_demand_effect_changes_formulaic_consumption_pool() -> None:
    baseline = _world({"poverty_rate": 0.2, "human_dev": 0.8, "gdp_per_capita": 20_000.0})
    affected = _world({"poverty_rate": 0.2, "human_dev": 0.8, "gdp_per_capita": 20_000.0})
    _add_effect(
        affected,
        effect_id="boom:demand",
        category="demand",
        subject_type="country",
        subject_id="AAA",
        magnitude=0.2,
    )

    baseline_total = InternalEconomySystem()._calculate_formulaic_consumption(baseline)["consumption_usd"].sum()
    affected_total = InternalEconomySystem()._calculate_formulaic_consumption(affected)["consumption_usd"].sum()

    assert affected_total > baseline_total


def test_approval_and_budget_effects_reach_politics_and_treasury_calculations() -> None:
    politics_state = _world({"gvt_approval": 50.0, "gvt_stability": 50.0})
    politics_state.time.total_minutes = 7 * 24 * 60
    politics_state.time.day = 8
    politics_state.events = [EventNewDay(day=8, month=1, year=2001)]
    _add_effect(
        politics_state,
        effect_id="strike:approval",
        category="approval",
        subject_type="country",
        subject_id="AAA",
        magnitude=-0.03,
    )
    approval_before = politics_state.get_table("countries").item(0, "gvt_approval")
    PoliticsSystem().update(politics_state, 0.0)

    budget_base = _world({"gdp": 1_000_000.0, "money_reserves": 1_000_000.0})
    budget_affected = _world({"gdp": 1_000_000.0, "money_reserves": 1_000_000.0})
    ledger_schema = budget_base.get_table("resource_ledger").schema
    ledger_row = {
        "country_id": "AAA",
        "game_resource_id": "cereals",
        "consumption_usd": 1_000_000.0,
    }
    for state in (budget_base, budget_affected):
        state.update_table("resource_ledger", pl.DataFrame([ledger_row], schema=ledger_schema, strict=False))
    _add_effect(
        budget_affected,
        effect_id="response:budget-pressure",
        category="budget_pressure",
        subject_type="country",
        subject_id="AAA",
        magnitude=0.5,
    )
    BudgetSystem()._process_budget(budget_base, 0.0)
    BudgetSystem()._process_budget(budget_affected, 0.0)

    assert politics_state.get_table("countries").item(0, "gvt_approval") < approval_before
    assert budget_affected.get_table("countries").item(0, "total_annual_expense") > budget_base.get_table("countries").item(0, "total_annual_expense")


def test_health_and_political_effects_raise_migration_service_and_political_signals() -> None:
    baseline = migration_test.TestMigrationSystem._state()
    affected = migration_test.TestMigrationSystem._state()
    for state in (baseline, affected):
        state.time.total_minutes = 1_440
        state.update_table(
            "migration_flows",
            pl.DataFrame(schema=state.get_table("migration_flows").schema),
        )
    _add_effect(
        affected,
        effect_id="epidemic:signal-health",
        category="health",
        subject_type="region",
        subject_id="1",
        magnitude=-0.25,
    )
    _add_effect(
        affected,
        effect_id="strike:signal-politics",
        category="political_pressure",
        subject_type="country",
        subject_id="AAA",
        magnitude=0.25,
    )

    MigrationSystem()._update_signals(baseline, 1_440, [])
    MigrationSystem()._update_signals(affected, 1_440, [])
    base_signal = baseline.get_table("migration_signals").row(0, named=True)
    affected_signal = affected.get_table("migration_signals").row(0, named=True)

    assert affected_signal["service_pressure"] > base_signal["service_pressure"]
    assert affected_signal["political_pressure"] > base_signal["political_pressure"]
