from modules.base.systems.economy.debt_distress_policy import (
    DebtDistressInputs,
    DeterministicDebtDistressPlanner,
)


def test_existing_restructuring_case_stays_restructuring_when_arrears_requested():
    inputs = DebtDistressInputs(
        country_id="country-1",
        requested_status="arrears",
        trigger="contractual_arrears",
        fallback_arrears=0.0,
        country_arrears=50.0,
        country_gdp=10_000.0,
        default_arrears_minimum=100.0,
        default_arrears_gdp_ratio=0.1,
        now=120,
        reason="Payments remain overdue.",
        case_count=1,
        existing_case={"id": "distress:country-1:90:0", "status": "restructuring"},
    )

    plan = DeterministicDebtDistressPlanner().plan(inputs)

    assert plan.status == "restructuring"
    assert plan.previous_status == "restructuring"
    assert plan.case["status"] == "restructuring"
    assert plan.case["id"] == "distress:country-1:90:0"
