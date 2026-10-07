import polars as pl
from dataclasses import asdict

from src.engine.journal import DomainEventJournal
from modules.base.schema import build_base_schema_registry
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionResolveDebtContract,
    ActionSetTax,
)
from src.shared.events import EventEconomicTransition, EventNewDay, EventRealSecond
from src.shared.config import GameConfig
from src.shared.state import GameState


def _seed_state():
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["A"],
            "gdp": [1_000.0],
            "economic_previous_gdp": [500.0],
            "money_reserves": [2_000.0],
            "total_annual_revenue": [500.0],
            "total_annual_expense": [400.0],
            "human_dev": [0.7],
            "poverty_rate": [0.2],
            "employment_rate": [0.5],
            "unemployment_rate": [0.5],
            "minimum_wage": [100.0],
            "economic_previous_minimum_wage": [100.0],
            "gvt_approval": [50.0],
        }),
        "regions": pl.DataFrame({
            "owner": ["A"],
            "pop_15_64": [1_000],
        }),
    })
    build_base_schema_registry().ensure_state(state)
    return state


def test_policy_transition_is_effective_dated_and_records_its_cause():
    state = _seed_state()
    state.globals["economic_health_terms"] = {"policy_delay_minutes": 10, "policy_cooldown_minutes": 20}
    system = EconomicHealthSystem()
    state.current_actions = [ActionChangeEconomicPolicy(
        player_id="A", country_tag="A", policy_name="minimum_wage", target_value=120.0
    )]
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "minimum_wage") == 100.0

    transition = state.get_table("economic_policy_transitions").row(0, named=True)
    assert transition["effective_at_minute"] == 10
    assert transition["transition_cost"] == 0.0
    state.current_actions = []
    state.time.total_minutes = 9
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "minimum_wage") == 100.0

    state.time.total_minutes = 10
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "minimum_wage") == 120.0
    assert state.get_table("economic_policy_transitions").item(0, "status") == "applied"
    assert state.get_table("economic_cause_records").filter(pl.col("indicator") == "minimum_wage").height == 1
    assert any(isinstance(event, EventEconomicTransition) and event.event_type == "applied" for event in state.events)


def test_daily_profile_uses_labor_and_fiscal_inputs_and_records_causes():
    state = _seed_state()
    state.time.total_minutes = 1_440
    state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))
    EconomicHealthSystem().update(state, 1.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["labor_supply"] == 1_000.0
    assert country["employed_population"] > 500.0
    assert country["unemployment_rate"] < 0.5
    assert country["inflation_rate"] > 0.0
    assert country["real_income_index"] < 1.0
    assert 0.0 <= country["economic_health"] <= 1.0
    assert country["economic_health_last_update_minute"] == 1_440
    assert country["gvt_approval"] != 50.0
    causes = state.get_table("economic_cause_records")
    assert {"inflation_rate", "real_income_index", "employment_rate", "economic_health"}.issubset(
        set(causes.get_column("indicator").to_list())
    )


def test_debt_distress_modifiers_reach_economic_health_and_political_stability():
    baseline = _seed_state()
    distressed = _seed_state()
    distressed.update_table(
        "countries",
        distressed.get_table("countries").with_columns(
            pl.lit(0.9).alias("economic_health_modifier"),
            pl.lit(0.75).alias("economic_political_modifier"),
        ),
    )
    for state in (baseline, distressed):
        state.time.total_minutes = 1_440
        state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))
        EconomicHealthSystem().update(state, 1.0)

    assert (
        distressed.get_table("countries").item(0, "economic_health")
        < baseline.get_table("countries").item(0, "economic_health")
    )

    stability_results = []
    for political_modifier in (1.0, 0.75):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["A"],
                "gvt_approval": [50.0],
                "human_dev": [0.5],
                "gvt_corruption": [0.1],
                "gvt_stability": [50.0],
                "economic_political_modifier": [political_modifier],
            }),
        })
        build_base_schema_registry().ensure_state(state)
        state.time.total_minutes = 7 * 24 * 60
        state.time.day = 8
        state.events = [EventNewDay(day=8, month=1, year=2001)]
        PoliticsSystem().update(state, 0.0)
        stability_results.append(state.get_table("countries").item(0, "gvt_stability"))

    assert stability_results[1] < stability_results[0]


def test_daily_profile_consumes_migration_service_pressure_once():
    baseline = _seed_state()
    pressured = _seed_state()
    signal_schema = pressured.get_table("migration_signals").schema
    pressured.update_table("migration_signals", pl.DataFrame({
        "country_id": ["A"],
        "gross_inflow": [80],
        "gross_outflow": [10],
        "net_flow": [70],
        "working_age_delta": [45],
        "service_pressure": [0.8],
        "political_pressure": [0.6],
        "law_pressure": [0.3],
        "window_start_minute": [0],
        "updated_at_minute": [1_200],
        "politics_consumed_at_minute": [0],
        "economy_consumed_at_minute": [0],
    }, schema=signal_schema))
    for state in (baseline, pressured):
        state.time.total_minutes = 1_440
        state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))

    system = EconomicHealthSystem()
    system.update(baseline, 1.0)
    system.update(pressured, 1.0)

    baseline_country = baseline.get_table("countries").row(0, named=True)
    pressured_country = pressured.get_table("countries").row(0, named=True)
    signal = pressured.get_table("migration_signals").row(0, named=True)
    assert pressured_country["economic_health"] < baseline_country["economic_health"]
    assert pressured_country["migration_pressure"] > baseline_country["migration_pressure"]
    assert signal["economy_consumed_at_minute"] == 1_200

    pressured.time.total_minutes = 2_880
    pressured.events = [EventRealSecond(game_seconds_passed=1.0, is_paused=False)]
    system.update(pressured, 1.0)

    next_signal = pressured.get_table("migration_signals").row(0, named=True)
    assert next_signal["economy_consumed_at_minute"] == 1_200


def test_identical_policy_and_debt_inputs_produce_identical_economic_traces():
    def run_trace():
        state = _seed_state()
        state.update_table("countries", pl.concat([
            state.get_table("countries"),
            pl.DataFrame({"id": ["B"], "gdp": [5_000.0], "money_reserves": [1_000.0]}),
        ], how="diagonal_relaxed"))
        state.globals["economic_health_terms"] = {"policy_delay_minutes": 5, "policy_cooldown_minutes": 10}
        system = EconomicHealthSystem()
        state.current_actions = [
            ActionChangeEconomicPolicy("A", "A", "interest_rate", 0.08),
            ActionRequestDebtContract("A", "A", "B", 100.0, 0.05, 1, 10.0, 12),
        ]
        system.update(state, 0.0)
        contract_id = state.get_table("debt_contracts").item(0, "id")
        state.current_actions = [ActionResolveDebtContract("B", contract_id, True)]
        system.update(state, 0.0)
        state.current_actions = []
        state.time.total_minutes = 5
        system.update(state, 0.0)
        state.time.total_minutes = 1_440
        state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))
        system.update(state, 1.0)
        due_at = state.get_table("debt_contracts").item(0, "next_payment_at_minute")
        state.time.total_minutes = due_at
        system.update(state, 0.0)
        transitions = tuple(asdict(event) for event in state.events if isinstance(event, EventEconomicTransition))
        return (
            state.get_table("countries"),
            state.get_table("economic_policy_transitions"),
            state.get_table("debt_contracts"),
            state.get_table("debt_distress_cases"),
            state.get_table("economic_cause_records"),
            transitions,
        )

    first = run_trace()
    second = run_trace()

    for first_table, second_table in zip(first[:5], second[:5]):
        assert first_table.equals(second_table)
    assert first[5] == second[5]


def test_wage_change_does_not_invent_nominal_income_without_available_workers():
    state = _seed_state()
    countries = state.get_table("countries").with_columns(
        pl.lit(0.0).alias("employment_rate"),
        pl.lit(1.0).alias("unemployment_rate"),
        pl.lit(0.0).alias("employed_population"),
        pl.lit(200.0).alias("minimum_wage"),
        pl.lit(100.0).alias("economic_previous_minimum_wage"),
        pl.lit(1.0).alias("nominal_income_index"),
        pl.lit(500.0).alias("gdp"),
        pl.lit(500.0).alias("economic_previous_gdp"),
    )
    state.update_table("countries", countries)
    state.update_table("regions", pl.DataFrame({
        "owner": pl.Series([], dtype=pl.Utf8),
        "pop_15_64": pl.Series([], dtype=pl.Int64),
    }))
    state.time.total_minutes = 1_440
    state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))

    EconomicHealthSystem().update(state, 1.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["labor_supply"] == 0.0
    assert country["employed_population"] == 0.0
    assert country["nominal_income_index"] == 1.0


def test_economic_policy_and_debt_rows_survive_snapshot_and_save_roundtrips(tmp_path):
    state = _seed_state()
    countries = pl.concat([
        state.get_table("countries"),
        pl.DataFrame({"id": ["B"], "gdp": [5_000.0], "money_reserves": [1_000.0]}),
    ], how="diagonal_relaxed")
    state.update_table("countries", countries)
    state.globals["economic_health_terms"] = {"policy_transition_cost": 10.0, "policy_delay_minutes": 5}
    system = EconomicHealthSystem()
    state.current_actions = [
        ActionChangeEconomicPolicy(
            player_id="A", country_tag="A", policy_name="interest_rate", target_value=0.08
        ),
        ActionRequestDebtContract(
            player_id="A", debtor_country_id="A", creditor_country_id="B", principal=100.0,
            annual_interest_rate=0.05, payment_frequency_months=1, principal_installment=10.0,
            maturity_months=12, currency_code="USD", conditions="snapshot test",
        ),
    ]
    system.update(state, 0.0)
    pending = state.get_table("debt_contracts").row(0, named=True)
    state.current_actions = [ActionResolveDebtContract(
        player_id="B", contract_id=pending["id"], accept=True
    )]
    system.update(state, 0.0)
    contract = state.get_table("debt_contracts").row(0, named=True)
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "A").then(pl.lit(0.0)).otherwise(pl.col("money_reserves")).alias("money_reserves")
    ))
    state.time.total_minutes = int(contract["next_payment_at_minute"])
    state.current_actions = []
    system.update(state, 0.0)
    journaled = DomainEventJournal().capture(state)
    assert journaled
    assert any(record["event_type"] == "EventEconomicTransition" for record in journaled)
    assert all(record["payload"]["reason"] for record in journaled)

    restored = GameState.from_ipc(state.to_ipc())

    assert restored.get_table("economic_policy_transitions").equals(state.get_table("economic_policy_transitions"))
    assert restored.get_table("debt_contracts").equals(state.get_table("debt_contracts"))
    assert restored.get_table("debt_distress_cases").equals(state.get_table("debt_distress_cases"))
    assert restored.get_table("economic_cause_records").equals(state.get_table("economic_cause_records"))
    assert restored.get_table("debt_contracts").item(0, "status") == "arrears"
    assert restored.get_table("debt_distress_cases").height == 1
    assert restored.get_table("economic_cause_records").height > 0

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "economic-health")
    loaded = DataLoader(config, schema_registry=build_base_schema_registry()).load_save("economic-health")
    assert loaded.journal.domain_events == state.journal.domain_events
    for table_name in (
        "countries", "economic_policy_transitions", "debt_contracts",
        "debt_distress_cases", "economic_cause_records",
    ):
        assert loaded.get_table(table_name).equals(state.get_table(table_name))


def test_tax_action_uses_the_same_effective_date_and_configured_cost_contract():
    state = _seed_state()
    state.globals["economic_health_terms"] = {
        "policy_delay_minutes": 5,
        "policy_cooldown_minutes": 20,
        "personal_income_tax_rate_transition_cost": 25.0,
    }
    system = EconomicHealthSystem()
    state.current_actions = [ActionSetTax(
        player_id="A", country_tag="A", new_tax_rate=0.3
    )]
    system.update(state, 0.0)

    country = state.get_table("countries").row(0, named=True)
    transition = state.get_table("economic_policy_transitions").row(0, named=True)
    assert country["personal_income_tax_rate"] == 0.2
    assert country["money_reserves"] == 1_975.0
    assert transition["transition_cost"] == 25.0
    assert transition["effective_at_minute"] == 5

    state.current_actions = []
    state.time.total_minutes = 5
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "personal_income_tax_rate") == 0.3


def test_policy_cost_and_cooldown_rejections_leave_the_country_unchanged():
    state = _seed_state()
    state.globals["economic_health_terms"] = {
        "policy_delay_minutes": 5,
        "policy_cooldown_minutes": 10,
        "minimum_wage_transition_cost": 3_000.0,
    }
    system = EconomicHealthSystem()
    unaffordable = ActionChangeEconomicPolicy(
        player_id="A", country_tag="A", policy_name="minimum_wage", target_value=120.0
    )
    state.current_actions = [unaffordable]
    system.update(state, 0.0)
    assert state.get_table("economic_policy_transitions").is_empty()
    assert state.get_table("countries").item(0, "money_reserves") == 2_000.0
    assert any(isinstance(event, EventEconomicTransition) and event.event_type == "rejected" for event in state.events)

    state.globals["economic_health_terms"]["minimum_wage_transition_cost"] = 0.0
    state.current_actions = [unaffordable]
    system.update(state, 0.0)
    scheduled = state.get_table("economic_policy_transitions").row(0, named=True)
    assert scheduled["status"] == "scheduled"

    state.time.total_minutes = 4
    state.current_actions = [ActionChangeEconomicPolicy(
        player_id="A", country_tag="A", policy_name="minimum_wage", target_value=130.0
    )]
    system.update(state, 0.0)
    assert state.get_table("economic_policy_transitions").height == 1
    assert state.get_table("countries").item(0, "minimum_wage") == 100.0
    assert sum(event.event_type == "rejected" for event in state.events if isinstance(event, EventEconomicTransition)) == 2

    state.time.total_minutes = 5
    state.current_actions = []
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "minimum_wage") == 120.0

    state.time.total_minutes = 15
    state.current_actions = [ActionChangeEconomicPolicy(
        player_id="A", country_tag="A", policy_name="minimum_wage", target_value=130.0
    )]
    system.update(state, 0.0)
    assert state.get_table("economic_policy_transitions").height == 2


def test_unauthorized_and_out_of_range_policy_actions_do_not_change_state():
    state = _seed_state()
    state.globals["economic_health_terms"] = {"max_minimum_wage": 500.0}
    system = EconomicHealthSystem()
    state.current_actions = [
        ActionChangeEconomicPolicy("unauthorized", "A", "minimum_wage", 150.0),
        ActionChangeEconomicPolicy("A", "A", "minimum_wage", 501.0),
    ]

    system.update(state, 0.0)

    assert state.get_table("economic_policy_transitions").is_empty()
    country = state.get_table("countries").row(0, named=True)
    assert country["minimum_wage"] == 100.0
    assert country["money_reserves"] == 2_000.0
    rejected = [event for event in state.events if isinstance(event, EventEconomicTransition) and event.event_type == "rejected"]
    assert len(rejected) == 2


def test_wage_growth_changes_nominal_income_when_workers_are_available():
    state = _seed_state()
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.lit(1.0).alias("nominal_income_index"),
        pl.lit(110.0).alias("minimum_wage"),
    ))
    state.time.total_minutes = 1_440
    state.events.append(EventRealSecond(game_seconds_passed=1.0, is_paused=False))

    EconomicHealthSystem().update(state, 1.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["labor_supply"] == 1_000.0
    assert country["employed_population"] > 0.0
    assert country["nominal_income_index"] > 1.0


def test_public_spending_policy_uses_validated_effective_transition():
    state = _seed_state()
    state.globals["economic_health_terms"] = {"policy_delay_minutes": 5}
    system = EconomicHealthSystem()
    state.current_actions = [ActionChangeEconomicPolicy(
        player_id="A", country_tag="A", policy_name="budget_health_ratio", target_value=0.75
    )]
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "budget_health_ratio") == 0.5

    state.current_actions = []
    state.time.total_minutes = 5
    system.update(state, 0.0)
    assert state.get_table("countries").item(0, "budget_health_ratio") == 0.75


def test_inflation_adjusted_real_income_scales_existing_household_demand():
    state = _seed_state()
    state.update_table("regions", pl.DataFrame({
        "owner": ["A"], "pop_14": [0], "pop_15_64": [1_000], "pop_65": [0],
    }))
    countries = state.get_table("countries").with_columns(
        pl.lit(1_000.0).alias("gdp_per_capita"),
        pl.lit(1.0).alias("real_income_index"),
    )
    state.update_table("countries", countries)
    economy = InternalEconomySystem()
    full_purchasing_power = economy._calculate_formulaic_consumption(state)["consumption_usd"].sum()

    state.update_table("countries", state.get_table("countries").with_columns(pl.lit(0.5).alias("real_income_index")))
    reduced_purchasing_power = economy._calculate_formulaic_consumption(state)["consumption_usd"].sum()

    assert reduced_purchasing_power == full_purchasing_power * 0.5


def test_economic_health_changes_existing_population_health_outcomes():
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["HEALTHY", "DISTRESSED"],
            "fertility_rate": [0.0, 0.0],
            "life_expectancy": [100.0, 100.0],
            "economic_health": [1.0, 0.0],
        }),
        "regions": pl.DataFrame({
            "owner": ["HEALTHY", "DISTRESSED"],
            "pop_14": [0, 0],
            "pop_15_64": [0, 0],
            "pop_65": [10_000_000, 10_000_000],
            "health_capacity": [1.0, 1.0],
        }),
    })
    state.events.append(EventRealSecond(game_seconds_passed=86_400.0, is_paused=False))

    PopulationSystem().update(state, 86_400.0)

    regions = state.get_table("regions").sort("owner")
    assert regions.item(0, "pop_65") < regions.item(1, "pop_65")


def test_budget_includes_contractual_service_in_forecast_without_double_debiting_reserves():
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["A"],
            "gdp": [0.0],
            "money_reserves": [-1_000.0],
            "interest_rate": [0.1],
            "annual_debt_service": [100.0],
            "human_dev": [0.5],
            "personal_income_tax_rate": [0.0],
        }),
        "resource_ledger": pl.DataFrame({
            "country_id": [], "consumption_usd": [],
        }, schema={"country_id": pl.Utf8, "consumption_usd": pl.Float64}),
    })
    build_base_schema_registry().ensure_state(state)

    BudgetSystem()._process_budget(state, 1.0)

    country = state.get_table("countries").row(0, named=True)
    assert country["total_annual_expense"] == 200.0
    assert country["money_reserves"] == -1_100.0
