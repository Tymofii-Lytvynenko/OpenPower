from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Protocol


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


def calculate_annualized_debt_service(contract: Mapping[str, Any]) -> float:
    principal = max(0.0, _finite(contract.get("principal_remaining")))
    rate = _clamp(contract.get("annual_interest_rate"), 0.0, 0.5)
    frequency = max(1, int(_finite(contract.get("payment_frequency_months"), 1.0)))
    installment = min(
        principal,
        max(0.0, _finite(contract.get("principal_payment"))),
    )
    return principal * rate + installment * 12.0 / frequency


@dataclass(frozen=True)
class DebtServiceSettlementInputs:
    contract: Mapping[str, Any]
    due_at_minute: int
    available_reserves: float


@dataclass(frozen=True)
class DebtServiceSettlement:
    principal: float
    old_arrears: float
    total_due: float
    paid: float
    principal_paid: float
    new_principal: float
    new_arrears: float
    old_service: float
    new_service: float
    frequency_months: int
    status: str
    reason: str


class DebtServiceSettlementCalculator(Protocol):
    def calculate(self, inputs: DebtServiceSettlementInputs) -> DebtServiceSettlement: ...


@dataclass(frozen=True)
class _DebtServiceAllocation:
    principal: float
    old_arrears: float
    total_due: float
    paid: float
    principal_paid: float
    new_principal: float
    new_arrears: float
    frequency_months: int


class DeterministicDebtServiceSettlementCalculator:
    """Calculate debt-service allocation without mutating world state."""

    def calculate(self, inputs: DebtServiceSettlementInputs) -> DebtServiceSettlement:
        contract = inputs.contract
        allocation = self._calculate_allocation(inputs)
        updated_contract = dict(contract)
        updated_contract["principal_remaining"] = allocation.new_principal
        status = self._updated_status(
            str(contract["status"]),
            allocation.new_principal,
            allocation.new_arrears,
        )
        reason = (
            f"Scheduled service paid {allocation.paid:.2f} of {allocation.total_due:.2f}; "
            f"principal reduced by {allocation.principal_paid:.2f}; "
            "unpaid service remains recorded as arrears."
        )
        return DebtServiceSettlement(
            principal=allocation.principal,
            old_arrears=allocation.old_arrears,
            total_due=allocation.total_due,
            paid=allocation.paid,
            principal_paid=allocation.principal_paid,
            new_principal=allocation.new_principal,
            new_arrears=allocation.new_arrears,
            old_service=calculate_annualized_debt_service(contract),
            new_service=self._remaining_service(updated_contract, allocation.new_principal),
            frequency_months=allocation.frequency_months,
            status=status,
            reason=reason,
        )

    def _calculate_allocation(
        self,
        inputs: DebtServiceSettlementInputs,
    ) -> _DebtServiceAllocation:
        contract = inputs.contract
        principal = max(0.0, _finite(contract.get("principal_remaining")))
        frequency = max(1, int(contract.get("payment_frequency_months") or 1))
        interest_due, principal_due = calculate_scheduled_debt_service(
            principal_remaining=principal,
            annual_interest_rate=_finite(contract.get("annual_interest_rate")),
            principal_installment=_finite(contract.get("principal_payment")),
            payment_frequency_months=frequency,
        )
        maturity_at_minute = int(contract.get("maturity_at_minute") or 0)
        old_arrears = max(0.0, _finite(contract.get("arrears_amount")))
        principal_due = self._matured_principal_due(
            principal_due,
            principal,
            inputs.due_at_minute,
            maturity_at_minute,
        )
        total_due = old_arrears + interest_due + principal_due
        available = max(0.0, _finite(inputs.available_reserves))
        paid = min(available, total_due)
        paid_after_arrears = max(0.0, paid - old_arrears)
        paid_after_interest = max(0.0, paid_after_arrears - interest_due)
        principal_paid = min(principal_due, paid_after_interest)
        new_principal = max(0.0, principal - principal_paid)
        new_arrears = max(0.0, total_due - paid)
        return _DebtServiceAllocation(
            principal=principal,
            old_arrears=old_arrears,
            total_due=total_due,
            paid=paid,
            principal_paid=principal_paid,
            new_principal=new_principal,
            new_arrears=new_arrears,
            frequency_months=frequency,
        )

    @staticmethod
    def _matured_principal_due(
        scheduled_principal_due: float,
        principal: float,
        due_at_minute: int,
        maturity_at_minute: int,
    ) -> float:
        return (
            principal
            if due_at_minute >= maturity_at_minute
            else scheduled_principal_due
        )

    @staticmethod
    def _remaining_service(contract: Mapping[str, Any], new_principal: float) -> float:
        if new_principal <= 1e-9:
            return 0.0
        return calculate_annualized_debt_service(contract)

    @staticmethod
    def _updated_status(status: str, new_principal: float, new_arrears: float) -> str:
        if new_principal <= 1e-9 and new_arrears <= 1e-9:
            return "paid"
        elif new_arrears > 1e-9:
            return "arrears"
        return "current" if status != "restructured" else status


@dataclass(frozen=True)
class EconomicProfileEnvironment:
    country_effects: Mapping[tuple[str, str, str], Any]
    health_effect_by_country: Mapping[str, float]
    labor_by_country: Mapping[str, float]
    shortage_by_country: Mapping[str, float]


@dataclass(frozen=True)
class EconomicProfileInputs:
    country: Mapping[str, Any]
    boundary: int
    labor_supply: float
    labor_effect: Any
    employment_effect: Any
    resource_shortage: float
    regional_health_effect: float
    migration_signal: Mapping[str, Any] | None
    migration_health_penalty: float


@dataclass(frozen=True)
class EconomicCauseChange:
    indicator: str
    previous: float
    current: float
    unit: str
    reason: str


@dataclass(frozen=True)
class EconomicProfileProjection:
    country: dict[str, Any]
    consumed_migration_signal: dict[str, Any] | None
    cause_changes: tuple[EconomicCauseChange, ...]


class EconomicProfileCalculator(Protocol):
    def calculate(self, inputs: EconomicProfileInputs) -> EconomicProfileProjection: ...


@dataclass(frozen=True)
class _MarketOutcomes:
    wage_growth: float
    inflation_before: float
    inflation_after: float
    nominal_income_after: float
    real_income_before: float
    real_income_after: float
    employment_before: float
    employment_after: float
    unemployment_before: float
    unemployment_after: float
    poverty_before: float
    poverty_after: float
    labor: LaborOutcomes


@dataclass(frozen=True)
class _WageOutcomes:
    employment_before: float
    labor_supply: float
    wage_growth: float


@dataclass(frozen=True)
class _PriceOutcomes:
    inflation_before: float
    inflation_after: float
    nominal_income_after: float
    real_income_before: float
    real_income_after: float


@dataclass(frozen=True)
class _EmploymentOutcomes:
    employment_after: float
    unemployment_before: float
    unemployment_after: float
    poverty_before: float
    poverty_after: float
    labor: LaborOutcomes


@dataclass(frozen=True)
class _SocialOutcomes:
    health_before: float
    health_after: float
    migration_pressure: float
    domestic_debt: float


@dataclass(frozen=True)
class _MigrationPressures:
    service: float
    political: float


class DeterministicEconomicProfileCalculator:
    """Calculate one country's daily profile without mutating simulation state."""

    def calculate(self, inputs: EconomicProfileInputs) -> EconomicProfileProjection:
        original_country = inputs.country
        country = dict(original_country)
        market = self._calculate_market_outcomes(country, inputs)
        social = self._calculate_social_outcomes(country, inputs, market)
        values = self._profile_values(country, inputs.boundary, market, social)
        country.update(values)
        return EconomicProfileProjection(
            country=country,
            consumed_migration_signal=self._consume_migration_signal(inputs.migration_signal),
            cause_changes=self._cause_changes(original_country, values, market, social),
        )

    def _calculate_market_outcomes(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
    ) -> _MarketOutcomes:
        previous_gdp = max(0.0, _finite(country.get("economic_previous_gdp")))
        gdp = max(0.0, _finite(country.get("gdp")))
        production_growth = (
            _clamp((gdp / previous_gdp) - 1.0, -0.5, 0.5)
            if previous_gdp > 0.0
            else 0.0
        )
        wage = self._calculate_wage_outcomes(country, inputs)
        prices = self._calculate_price_outcomes(country, inputs, production_growth, wage)
        employment = self._calculate_employment_outcomes(
            country,
            inputs,
            production_growth,
            wage,
            prices,
        )
        return _MarketOutcomes(
            wage_growth=wage.wage_growth,
            inflation_before=prices.inflation_before,
            inflation_after=prices.inflation_after,
            nominal_income_after=prices.nominal_income_after,
            real_income_before=prices.real_income_before,
            real_income_after=prices.real_income_after,
            employment_before=wage.employment_before,
            employment_after=employment.employment_after,
            unemployment_before=employment.unemployment_before,
            unemployment_after=employment.unemployment_after,
            poverty_before=employment.poverty_before,
            poverty_after=employment.poverty_after,
            labor=employment.labor,
        )

    def _calculate_wage_outcomes(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
    ) -> _WageOutcomes:
        employment_before = _clamp(country.get("employment_rate"), 0.0, 1.0, 0.95)
        labor_supply = inputs.labor_supply * (1.0 + _clamp(inputs.labor_effect, -0.5, 0.5))
        old_wage = max(0.0, _finite(country.get("economic_previous_minimum_wage")))
        minimum_wage = max(0.0, _finite(country.get("minimum_wage")))
        # Wage policy cannot create household income when no working-age labor pool exists to receive it.
        has_employed_population = labor_supply > 0.0 and employment_before > 0.0
        wage_growth = (
            _clamp((minimum_wage / old_wage) - 1.0, -1.0, 1.0)
            if old_wage > 0.0 and has_employed_population
            else 0.0
        )
        return _WageOutcomes(employment_before, labor_supply, wage_growth)

    def _calculate_price_outcomes(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
        production_growth: float,
        wage: _WageOutcomes,
    ) -> _PriceOutcomes:
        inflation_before = _finite(country.get("inflation_rate"))
        revenue = max(0.0, _finite(country.get("total_annual_revenue")))
        expenses = max(0.0, _finite(country.get("total_annual_expense")))
        gdp = max(0.0, _finite(country.get("gdp")))
        deficit_ratio = _clamp(max(0.0, expenses - revenue) / max(1.0, gdp), 0.0, 1.0)
        inflation_after = calculate_inflation_rate(
            previous_rate=inflation_before,
            demand_growth=production_growth,
            fiscal_deficit_ratio=deficit_ratio,
            resource_cost_growth=inputs.resource_shortage,
            policy_interest_rate=_finite(country.get("interest_rate")),
        )
        real_income_before = _clamp(country.get("real_income_index"), 0.0, 2.0, 1.0)
        nominal_income_after = _clamp(
            _finite(country.get("nominal_income_index"), 1.0) * (1.0 + wage.wage_growth),
            0.0,
            2.0,
            1.0,
        )
        real_income_after = calculate_real_income_index(
            real_income_before,
            wage.wage_growth,
            inflation_after,
        )
        return _PriceOutcomes(
            inflation_before,
            inflation_after,
            nominal_income_after,
            real_income_before,
            real_income_after,
        )

    def _calculate_employment_outcomes(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
        production_growth: float,
        wage: _WageOutcomes,
        prices: _PriceOutcomes,
    ) -> _EmploymentOutcomes:
        employment_after = calculate_employment_rate(
            current_rate=wage.employment_before,
            production_growth=production_growth,
            real_wage_growth=wage.wage_growth - prices.inflation_after,
        )
        employment_after = _clamp(
            employment_after * (1.0 + _clamp(inputs.employment_effect, -0.5, 0.5)),
            0.0,
            1.0,
        )
        unemployment_before = _clamp(
            country.get("unemployment_rate"),
            0.0,
            1.0,
            1.0 - wage.employment_before,
        )
        unemployment_after = 1.0 - employment_after
        poverty_before = _clamp(country.get("poverty_rate"), 0.0, 1.0)
        poverty_after = _clamp(
            poverty_before
            + ((unemployment_after - unemployment_before) * 0.12)
            + (max(0.0, prices.inflation_after) * 0.02)
            - (max(0.0, wage.wage_growth) * 0.04),
            0.0,
            1.0,
        )
        labor = calculate_labor_outcomes(
            labor_supply=wage.labor_supply,
            employment_rate=employment_after,
            underemployment_rate=_finite(country.get("underemployment_rate")),
        )
        return _EmploymentOutcomes(
            employment_after=employment_after,
            unemployment_before=unemployment_before,
            unemployment_after=unemployment_after,
            poverty_before=poverty_before,
            poverty_after=poverty_after,
            labor=labor,
        )

    def _calculate_social_outcomes(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
        market: _MarketOutcomes,
    ) -> _SocialOutcomes:
        health_before, health_after = self._base_economic_health(country, market)
        migration_pressures = self._migration_pressures(inputs.migration_signal)
        health_after = self._migration_adjusted_health(
            country,
            inputs,
            health_after,
            migration_pressures.service,
        )
        migration_pressure = self._migration_pressure(market, migration_pressures)
        domestic_debt = max(0.0, -_finite(country.get("money_reserves")))
        return _SocialOutcomes(
            health_before,
            health_after,
            migration_pressure,
            domestic_debt,
        )

    def _base_economic_health(
        self,
        country: Mapping[str, Any],
        market: _MarketOutcomes,
    ) -> tuple[float, float]:
        expenses = max(0.0, _finite(country.get("total_annual_expense")))
        reserve_coverage = _clamp(
            _finite(country.get("money_reserves")) / max(1.0, expenses),
            0.0,
            1.0,
        )
        health_before = _clamp(country.get("economic_health"), 0.0, 1.0, 1.0)
        health_after = calculate_economic_health(
            human_development=_finite(country.get("human_dev"), 0.5),
            reserve_coverage=reserve_coverage,
            inflation_rate=market.inflation_after,
            unemployment_rate=market.unemployment_after,
            poverty_rate=market.poverty_after,
            real_income_index=market.real_income_after,
        )
        return health_before, health_after

    def _migration_pressures(
        self,
        migration_signal: Mapping[str, Any] | None,
    ) -> _MigrationPressures:
        return _MigrationPressures(
            service=_clamp(
                migration_signal.get("service_pressure") if migration_signal else 0.0,
                0.0,
                1.0,
            ),
            political=_clamp(
                migration_signal.get("political_pressure") if migration_signal else 0.0,
                0.0,
                1.0,
            ),
        )

    def _migration_adjusted_health(
        self,
        country: Mapping[str, Any],
        inputs: EconomicProfileInputs,
        health_after: float,
        service_pressure: float,
    ) -> float:
        migration_health_cost = inputs.migration_health_penalty * service_pressure
        distress_health_modifier = _clamp(
            country.get("economic_health_modifier"),
            0.5,
            1.0,
            1.0,
        )
        return _clamp(
            (health_after * distress_health_modifier)
            - migration_health_cost
            + _clamp(inputs.regional_health_effect, -0.5, 0.25),
            0.0,
            1.0,
        )

    def _migration_pressure(
        self,
        market: _MarketOutcomes,
        pressures: _MigrationPressures,
    ) -> float:
        base_pressure = _clamp(
            (0.35 * market.poverty_after)
            + (0.30 * market.unemployment_after)
            + (0.35 * max(0.0, 1.0 - market.real_income_after)),
            0.0,
            1.0,
        )
        return _clamp(
            base_pressure
            + (0.20 * pressures.service)
            + (0.10 * pressures.political),
            0.0,
            1.0,
        )

    def _profile_values(
        self,
        country: Mapping[str, Any],
        boundary: int,
        market: _MarketOutcomes,
        social: _SocialOutcomes,
    ) -> dict[str, Any]:
        gdp = max(0.0, _finite(country.get("gdp")))
        minimum_wage = max(0.0, _finite(country.get("minimum_wage")))
        values = {
            "inflation_rate": market.inflation_after,
            "real_income_index": market.real_income_after,
            "nominal_income_index": market.nominal_income_after,
            "employment_rate": market.employment_after,
            "unemployment_rate": market.unemployment_after,
            "poverty_rate": market.poverty_after,
            "labor_supply": market.labor.labor_supply,
            "employed_population": market.labor.employed_population,
            "underemployed_population": market.labor.underemployed_population,
            "economic_health": social.health_after,
            "migration_pressure": social.migration_pressure,
            "domestic_debt": social.domestic_debt,
            "economic_previous_gdp": gdp,
            "economic_previous_minimum_wage": minimum_wage,
            "economic_health_last_update_minute": boundary,
        }
        if "gvt_approval" in country:
            approval_before = _clamp(country.get("gvt_approval"), 0.0, 100.0, 50.0)
            approval_delta = (
                ((social.health_after - social.health_before) * 20.0)
                + ((market.unemployment_before - market.unemployment_after) * 8.0)
            )
            values["gvt_approval"] = _clamp(approval_before + approval_delta, 0.0, 100.0)
        return values

    def _cause_changes(
        self,
        country: Mapping[str, Any],
        values: Mapping[str, Any],
        market: _MarketOutcomes,
        social: _SocialOutcomes,
    ) -> tuple[EconomicCauseChange, ...]:
        reasons = {
            "inflation_rate": "Demand growth, fiscal deficit, resource shortage, and policy interest rate changed price pressure.",
            "real_income_index": "Nominal income growth was adjusted for the observed inflation rate.",
            "nominal_income_index": "Minimum-wage policy changed the nominal income index only where working-age labor is available.",
            "employment_rate": "Production growth and real wage pressure changed labor demand.",
            "unemployment_rate": "Unemployment is the unfilled share of the available labor supply.",
            "labor_supply": "Regional working-age population cohorts changed the country's available labor supply.",
            "employed_population": "Employment rate was applied to the available working-age labor supply.",
            "underemployed_population": "Configured underemployment was applied to the employed working-age population.",
            "poverty_rate": "Labor outcomes, purchasing-power loss, and wage growth changed poverty pressure.",
            "economic_health": "Economic health aggregates development, reserve coverage, prices, labor, poverty, real income, migration service pressure, and bounded debt-distress effects.",
            "migration_pressure": "Poverty, unemployment, lost purchasing power, and newly observed migration service or political pressure influence mobility.",
            "domestic_debt": "Negative treasury reserves are reported as domestic overdraft exposure without inventing a creditor.",
        }
        old_values = {
            "inflation_rate": market.inflation_before,
            "nominal_income_index": _finite(country.get("nominal_income_index"), 1.0),
            "real_income_index": market.real_income_before,
            "employment_rate": market.employment_before,
            "unemployment_rate": market.unemployment_before,
            "labor_supply": _finite(country.get("labor_supply")),
            "employed_population": _finite(country.get("employed_population")),
            "underemployed_population": _finite(country.get("underemployed_population")),
            "poverty_rate": market.poverty_before,
            "economic_health": social.health_before,
            "migration_pressure": _finite(country.get("migration_pressure")),
            "domestic_debt": _finite(country.get("domestic_debt")),
        }
        units = {
            "inflation_rate": "rate",
            "nominal_income_index": "index",
            "real_income_index": "index",
            "employment_rate": "rate",
            "unemployment_rate": "rate",
            "labor_supply": "people",
            "employed_population": "people",
            "underemployed_population": "people",
            "poverty_rate": "rate",
            "economic_health": "index",
            "migration_pressure": "index",
            "domestic_debt": "currency",
        }
        if "gvt_approval" in country:
            old_values["gvt_approval"] = _finite(country.get("gvt_approval"), 50.0)
            reasons["gvt_approval"] = "Employment and economic-health changes influenced public approval."
            units["gvt_approval"] = "percent"
        return tuple(
            EconomicCauseChange(
                indicator=indicator,
                previous=previous,
                current=_finite(values[indicator]),
                unit=units[indicator],
                reason=reasons[indicator],
            )
            for indicator, previous in old_values.items()
        )

    @staticmethod
    def _consume_migration_signal(
        migration_signal: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if migration_signal is None:
            return None
        consumed_signal = dict(migration_signal)
        consumed_signal["economy_consumed_at_minute"] = max(
            0,
            int(_finite(migration_signal.get("updated_at_minute"))),
        )
        return consumed_signal
