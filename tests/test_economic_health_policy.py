import math
from dataclasses import asdict

import pytest

from modules.base.systems.economy.economic_health_policy import (
    calculate_economic_health,
    calculate_employment_rate,
    calculate_inflation_rate,
    calculate_labor_outcomes,
    calculate_real_income_index,
    calculate_scheduled_debt_service,
)
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
)
from src.shared.events import DomainGameEvent, EventEconomicTransition


def test_economic_indicators_remain_bounded_and_explain_feedback_inputs():
    inflation = calculate_inflation_rate(
        previous_rate=0.02,
        demand_growth=0.12,
        fiscal_deficit_ratio=0.08,
        resource_cost_growth=0.04,
        policy_interest_rate=0.05,
    )
    real_income = calculate_real_income_index(
        previous_index=1.0,
        nominal_income_growth=0.10,
        inflation_rate=inflation,
    )
    health = calculate_economic_health(
        human_development=0.7,
        reserve_coverage=0.6,
        inflation_rate=inflation,
        unemployment_rate=0.1,
        poverty_rate=0.2,
        real_income_index=real_income,
    )

    assert 0.0 <= inflation <= 1.0
    assert 0.0 <= real_income <= 2.0
    assert 0.0 <= health <= 1.0
    assert inflation > 0.02


def test_extreme_or_non_finite_inputs_cannot_escape_indicator_bounds():
    inflation = calculate_inflation_rate(
        previous_rate=math.inf,
        demand_growth=math.nan,
        fiscal_deficit_ratio=100.0,
        resource_cost_growth=-100.0,
        policy_interest_rate=-100.0,
    )
    real_income = calculate_real_income_index(1.0, math.inf, 0.0)
    health = calculate_economic_health(
        human_development=math.nan,
        reserve_coverage=math.inf,
        inflation_rate=-100.0,
        unemployment_rate=math.nan,
        poverty_rate=math.inf,
        real_income_index=math.nan,
    )
    assert -0.1 <= inflation <= 1.0
    assert 0.0 <= real_income <= 2.0
    assert 0.0 <= health <= 1.0


def test_labor_profile_and_employment_update_preserve_population_conservation():
    labor = calculate_labor_outcomes(
        labor_supply=1_000.0,
        employment_rate=0.75,
        underemployment_rate=0.1,
    )
    next_rate = calculate_employment_rate(
        current_rate=0.75,
        production_growth=0.2,
        real_wage_growth=0.0,
    )

    assert labor.labor_supply == 1_000.0
    assert labor.employed_population == 750.0
    assert labor.unemployed_population == 250.0
    assert labor.underemployed_population == 75.0
    assert 0.75 < next_rate <= 1.0


@pytest.mark.parametrize(
    ("principal", "rate", "installment", "months", "expected_interest", "expected_principal"),
    [
        (1_000.0, 0.12, 100.0, 1, 10.0, 100.0),
        (50.0, 0.12, 100.0, 12, 6.0, 50.0),
        (1_000.0, -1.0, -1.0, 0, 0.0, 0.0),
    ],
)
def test_scheduled_debt_service_is_finite_and_capped_by_principal(
    principal, rate, installment, months, expected_interest, expected_principal
):
    interest, principal_due = calculate_scheduled_debt_service(
        principal_remaining=principal,
        annual_interest_rate=rate,
        principal_installment=installment,
        payment_frequency_months=months,
    )

    assert interest == pytest.approx(expected_interest)
    assert principal_due == pytest.approx(expected_principal)
    assert math.isfinite(interest + principal_due)


def test_economic_commands_and_domain_events_keep_serializable_payload_contracts():
    actions = (
        ActionChangeEconomicPolicy("A", "A", "interest_rate", 0.08),
        ActionRequestDebtContract("A", "A", "B", 100.0, 0.05, 1, 10.0, 12),
        ActionResolveDebtContract("B", "loan-1", True),
        ActionRequestDebtRestructuring("A", "A", "loan-1", 0.04, 2, 5.0, 24),
    )

    payloads = tuple(asdict(action) for action in actions)
    event = EventEconomicTransition(
        "scheduled", "A", "policy-1", "interest_rate", 0.05, 0.08, "Policy accepted.", 120
    )

    assert payloads[0] == {
        "player_id": "A", "country_tag": "A", "policy_name": "interest_rate", "target_value": 0.08
    }
    assert payloads[1]["principal"] == 100.0
    assert payloads[1]["currency_code"] == "USD"
    assert payloads[2]["accept"] is True
    assert payloads[3]["maturity_months"] == 24
    assert isinstance(event, DomainGameEvent)
    assert asdict(event)["at_minute"] == 120
