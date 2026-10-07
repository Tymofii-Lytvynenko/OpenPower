from __future__ import annotations

from dataclasses import dataclass
import math


def _finite(value: object, default: float = 0.0) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return resolved if math.isfinite(resolved) else default


def _clamp(value: object, minimum: float, maximum: float, default: float = 0.0) -> float:
    return min(max(_finite(value, default), minimum), maximum)


@dataclass(frozen=True)
class LaborOutcomes:
    labor_supply: float
    employed_population: float
    unemployed_population: float
    underemployed_population: float
    employment_rate: float
    unemployment_rate: float
    underemployment_rate: float


def calculate_inflation_rate(
    *,
    previous_rate: float,
    demand_growth: float,
    fiscal_deficit_ratio: float,
    resource_cost_growth: float,
    policy_interest_rate: float,
) -> float:
    """Return a bounded inflation rate from observable demand, fiscal, and cost pressure."""

    previous = _clamp(previous_rate, -0.1, 1.0)
    demand = _clamp(demand_growth, -1.0, 1.0)
    deficit = _clamp(fiscal_deficit_ratio, -1.0, 1.0)
    resource_cost = _clamp(resource_cost_growth, -1.0, 1.0)
    interest = _clamp(policy_interest_rate, 0.0, 0.5)
    pressure = (0.35 * demand) + (0.25 * deficit) + (0.30 * resource_cost)
    pressure -= 0.10 * (interest - 0.05)
    return _clamp(previous + (pressure * 0.05), -0.1, 1.0)


def calculate_real_income_index(
    previous_index: float,
    nominal_income_growth: float,
    inflation_rate: float,
) -> float:
    previous = _clamp(previous_index, 0.0, 2.0, default=1.0)
    nominal_growth = _clamp(nominal_income_growth, -1.0, 1.0)
    inflation = _clamp(inflation_rate, -0.1, 1.0)
    denominator = max(0.1, 1.0 + inflation)
    return _clamp(previous * (1.0 + nominal_growth) / denominator, 0.0, 2.0)


def calculate_labor_outcomes(
    *,
    labor_supply: float,
    employment_rate: float,
    underemployment_rate: float = 0.0,
) -> LaborOutcomes:
    supply = max(0.0, _finite(labor_supply))
    employed_ratio = _clamp(employment_rate, 0.0, 1.0)
    underemployed_ratio = _clamp(underemployment_rate, 0.0, 1.0)
    employed = supply * employed_ratio
    return LaborOutcomes(
        labor_supply=supply,
        employed_population=employed,
        unemployed_population=max(0.0, supply - employed),
        underemployed_population=employed * underemployed_ratio,
        employment_rate=employed_ratio,
        unemployment_rate=1.0 - employed_ratio,
        underemployment_rate=underemployed_ratio,
    )


def calculate_employment_rate(
    *,
    current_rate: float,
    production_growth: float,
    real_wage_growth: float,
) -> float:
    current = _clamp(current_rate, 0.0, 1.0)
    production = _clamp(production_growth, -0.5, 0.5)
    wage_growth = _clamp(real_wage_growth, -0.5, 0.5)
    excess_wage_pressure = max(0.0, wage_growth - production)
    change = (production * 0.08) - (excess_wage_pressure * 0.04)
    return _clamp(current + change, 0.0, 1.0)


def calculate_economic_health(
    *,
    human_development: float,
    reserve_coverage: float,
    inflation_rate: float,
    unemployment_rate: float,
    poverty_rate: float,
    real_income_index: float,
) -> float:
    development = _clamp(human_development, 0.0, 1.0)
    reserves = _clamp(reserve_coverage, 0.0, 1.0)
    inflation = _clamp(inflation_rate, -0.1, 1.0)
    unemployment = _clamp(unemployment_rate, 0.0, 1.0)
    poverty = _clamp(poverty_rate, 0.0, 1.0)
    real_income = _clamp(real_income_index, 0.0, 2.0, default=1.0)
    price_stability = 1.0 - min(1.0, abs(inflation) / 0.2)
    purchasing_power = min(1.0, real_income)
    score = (
        (0.15 * development)
        + (0.20 * reserves)
        + (0.20 * (1.0 - unemployment))
        + (0.15 * (1.0 - poverty))
        + (0.15 * price_stability)
        + (0.15 * purchasing_power)
    )
    return _clamp(score, 0.0, 1.0)


def calculate_scheduled_debt_service(
    *,
    principal_remaining: float,
    annual_interest_rate: float,
    principal_installment: float,
    payment_frequency_months: int,
) -> tuple[float, float]:
    principal = max(0.0, _finite(principal_remaining))
    months = max(0, int(_finite(payment_frequency_months)))
    if principal <= 0.0 or months <= 0:
        return 0.0, 0.0
    rate = _clamp(annual_interest_rate, 0.0, 0.5)
    interest_due = principal * rate * (months / 12.0)
    principal_due = min(principal, max(0.0, _finite(principal_installment)))
    return interest_due, principal_due
