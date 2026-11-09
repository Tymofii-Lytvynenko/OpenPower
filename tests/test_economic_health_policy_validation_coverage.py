import math

from modules.base.systems.economy.economic_health_policy import (
    DebtContractRequestInputs,
    DebtRestructuringInputs,
    DeterministicDebtContractRequestPlanner,
    DeterministicDebtRestructuringPlanner,
    DeterministicEconomicPolicyChangeValidator,
    EconomicPolicyChangeValidationInputs,
)


def _policy_inputs(policy_name, target_value):
    return EconomicPolicyChangeValidationInputs(
        requested_policy_name=policy_name,
        target_value=target_value,
        country={"minimum_wage": 10.0},
        terms={},
        spending_policies=frozenset(),
    )


def _debt_request(**overrides):
    values = {
        "player_id": "player",
        "debtor_country_id": "AAA",
        "creditor_country_id": "BBB",
        "now": 1_440,
        "principal": 100.0,
        "annual_interest_rate": 0.1,
        "payment_frequency_months": 1,
        "principal_installment": 10.0,
        "maturity_months": 12,
        "currency_code": "USD",
        "conditions": "test request",
        "debtor_exists": True,
        "creditor_exists": True,
        "actor_authorized": True,
        "debtor_gdp": 1_000.0,
        "terms": {},
    }
    values.update(overrides)
    return DebtContractRequestInputs(**values)


def _restructuring_inputs(contract, **overrides):
    values = {
        "payment_frequency_months": 1,
        "maturity_months": 12,
        "annual_interest_rate": 0.1,
        "principal_installment": 100.0,
        "maximum_rate": 0.5,
    }
    values.update(overrides)
    return DebtRestructuringInputs(contract=contract, **values)


def test_economic_policy_validator_returns_acceptance_for_supported_values():
    validator = DeterministicEconomicPolicyChangeValidator()

    unsupported = validator.validate(_policy_inputs("unknown_policy", 1.0))
    non_finite = validator.validate(_policy_inputs("minimum_wage", math.inf))
    accepted = validator.validate(_policy_inputs("minimum_wage", 12.0))

    assert not unsupported.accepted
    assert unsupported.rejection_reason == "Unsupported economic policy."
    assert not non_finite.accepted
    assert non_finite.rejection_reason == "Policy value must be finite."
    assert accepted.accepted
    assert accepted.target_value == 12.0


def test_debt_request_planner_rejects_invalid_participants_and_financial_terms():
    planner = DeterministicDebtContractRequestPlanner()
    cases = [
        (_debt_request(debtor_exists=False), "Debtor and a distinct existing creditor are required."),
        (_debt_request(principal=0.0), "Principal and installment must be finite non-negative amounts, with positive principal."),
        (_debt_request(principal_installment=-1.0), "Principal and installment must be finite non-negative amounts, with positive principal."),
        (_debt_request(annual_interest_rate=math.nan), "Interest rate is outside scenario bounds."),
        (_debt_request(annual_interest_rate=0.75), "Interest rate is outside scenario bounds."),
        (_debt_request(payment_frequency_months=0), "Payment frequency or maturity is outside supported bounds."),
        (_debt_request(maturity_months=0), "Payment frequency or maturity is outside supported bounds."),
        (
            _debt_request(principal=400.0, debtor_gdp=100.0),
            "Requested principal exceeds the configured debt-to-GDP limit.",
        ),
    ]

    for inputs, expected_reason in cases:
        assert planner.plan(inputs).rejection_reason == expected_reason


def test_restructuring_planner_rejects_ineligible_terms_and_allows_changed_terms():
    planner = DeterministicDebtRestructuringPlanner()
    contract = {
        "status": "restructured",
        "principal_remaining": 1_000.0,
        "principal_payment": 100.0,
        "payment_frequency_months": 1,
        "maturity_months": 12,
        "annual_interest_rate": 0.1,
    }

    ineligible = planner.plan(_restructuring_inputs({**contract, "status": "pending"}))
    outside_bounds = planner.plan(_restructuring_inputs(
        {**contract, "status": "current"}, payment_frequency_months=0, maturity_months=0
    ))
    assert ineligible.rejection_reason == "Contract is not eligible for restructuring."
    assert outside_bounds.rejection_reason == "Restructured terms are outside scenario bounds."

    changed_terms = [
        _restructuring_inputs(contract, payment_frequency_months=2),
        _restructuring_inputs(contract, maturity_months=24),
        _restructuring_inputs(contract, annual_interest_rate=0.12),
    ]
    assert all(planner.plan(inputs).rejection_reason is None for inputs in changed_terms)
