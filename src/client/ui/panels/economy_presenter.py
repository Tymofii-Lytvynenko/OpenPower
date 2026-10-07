from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import polars as pl

from src.shared.state import GAME_EPOCH


@dataclass(frozen=True, slots=True)
class EconomicCauseView:
    indicator: str
    delta: float
    game_minute: int
    reason: str


@dataclass(frozen=True, slots=True)
class EconomicIndicatorTrend:
    indicator: str
    previous_value: float
    current_value: float
    delta: float
    direction: str


@dataclass(frozen=True, slots=True)
class DebtObligationView:
    contract_id: str
    creditor_country_id: str
    principal_remaining: float
    annual_interest_rate: float
    next_payment_at_minute: int
    next_payment_date: str
    maturity_at_minute: int
    maturity_date: str
    arrears_amount: float
    status: str
    conditions: str


@dataclass(frozen=True, slots=True)
class EconomicPolicyView:
    policy_name: str
    target_value: float
    transition_cost: float
    effective_at_minute: int
    effective_date: str
    cooldown_until_minute: int
    status: str


@dataclass(frozen=True, slots=True)
class EconomicHealthView:
    country_id: str
    economic_health: float
    minimum_wage: float
    interest_rate: float
    inflation_rate: float
    employment_rate: float
    unemployment_rate: float
    underemployment_rate: float
    poverty_rate: float
    labor_supply: float
    employed_population: float
    underemployed_population: float
    nominal_income_index: float
    real_income_index: float
    migration_pressure: float
    money_reserves: float
    fiscal_balance: float
    domestic_debt: float
    foreign_debt: float
    annual_debt_service: float
    arrears: float
    distress_status: str
    risk_thresholds: tuple[tuple[str, float], ...]
    active_policies: tuple[EconomicPolicyView, ...]
    obligations: tuple[DebtObligationView, ...]
    top_causes: tuple[EconomicCauseView, ...]
    indicator_trends: tuple[EconomicIndicatorTrend, ...]
    recovery_condition: str


class EconomyPresenter:
    """Builds immutable economic read models from authoritative simulation snapshots."""

    def present(self, state: Any, country_id: str, *, cause_limit: int = 3) -> EconomicHealthView | None:
        countries = getattr(state, "tables", {}).get("countries")
        if countries is None or "id" not in countries.columns:
            return None
        selected = countries.filter(pl.col("id") == str(country_id))
        if selected.is_empty():
            return None
        country = selected.row(0, named=True)

        def number(name: str, default: float = 0.0) -> float:
            try:
                value = float(country.get(name, default) or 0.0)
            except (TypeError, ValueError, OverflowError):
                return default
            return value if value == value and abs(value) != float("inf") else default

        causes = self._causes(state, country_id, max(0, int(cause_limit)))
        obligations = self._obligations(state, country_id)
        policies = self._policies(state, country_id)
        distress = self._distress(state, country_id)
        terms = getattr(state, "globals", {}).get("economic_health_terms", {})
        terms = terms if isinstance(terms, dict) else {}
        thresholds = (
            ("inflation_warning", self._finite(terms.get("inflation_warning_rate"), 0.10)),
            ("unemployment_warning", self._finite(terms.get("unemployment_warning_rate"), 0.15)),
            ("poverty_warning", self._finite(terms.get("poverty_warning_rate"), 0.25)),
            ("economic_health_warning", self._finite(terms.get("economic_health_warning"), 0.45)),
        )
        return EconomicHealthView(
            country_id=str(country_id),
            economic_health=number("economic_health", 1.0),
            minimum_wage=number("minimum_wage"),
            interest_rate=number("interest_rate", 0.05),
            inflation_rate=number("inflation_rate"),
            employment_rate=number("employment_rate", 0.95),
            unemployment_rate=number("unemployment_rate"),
            underemployment_rate=number("underemployment_rate"),
            poverty_rate=number("poverty_rate"),
            labor_supply=number("labor_supply"),
            employed_population=number("employed_population"),
            underemployed_population=number("underemployed_population"),
            nominal_income_index=number("nominal_income_index", 1.0),
            real_income_index=number("real_income_index", 1.0),
            migration_pressure=number("migration_pressure"),
            money_reserves=number("money_reserves"),
            fiscal_balance=number("total_annual_revenue") - number("total_annual_expense"),
            domestic_debt=max(number("domestic_debt"), max(0.0, -number("money_reserves"))),
            foreign_debt=number("foreign_debt"),
            annual_debt_service=number("annual_debt_service"),
            arrears=number("arrears"),
            distress_status=str(country.get("debt_distress_status") or "current"),
            risk_thresholds=thresholds,
            active_policies=policies,
            obligations=obligations,
            top_causes=causes,
            indicator_trends=self._trends(state, country_id),
            recovery_condition=str((distress or {}).get("recovery_condition") or "No active distress case."),
        )

    def _causes(self, state: Any, country_id: str, limit: int) -> tuple[EconomicCauseView, ...]:
        frame = getattr(state, "tables", {}).get("economic_cause_records")
        if frame is None or frame.is_empty() or limit == 0:
            return ()
        ranked = frame.filter(pl.col("country_id") == str(country_id)).with_columns(
            pl.col("delta").abs().alias("_cause_strength")
        ).sort(
            ["_cause_strength", "game_minute", "indicator"],
            descending=[True, True, False],
        ).head(limit).iter_rows(named=True)
        return tuple(EconomicCauseView(
            indicator=str(row.get("indicator") or ""),
            delta=self._finite(row.get("delta")),
            game_minute=int(row.get("game_minute") or 0),
            reason=str(row.get("reason") or ""),
        ) for row in ranked)

    def _trends(self, state: Any, country_id: str) -> tuple[EconomicIndicatorTrend, ...]:
        frame = getattr(state, "tables", {}).get("economic_cause_records")
        required = {"country_id", "indicator", "previous_value", "new_value", "delta", "game_minute"}
        if frame is None or frame.is_empty() or not required.issubset(frame.columns):
            return ()
        rows = frame.filter(pl.col("country_id") == str(country_id)).sort(
            ["game_minute", "id"], descending=[True, True]
        ).iter_rows(named=True)
        latest: dict[str, EconomicIndicatorTrend] = {}
        for row in rows:
            indicator = str(row.get("indicator") or "")
            if not indicator or indicator in latest:
                continue
            delta = self._finite(row.get("delta"))
            direction = "rising" if delta > 1e-9 else "falling" if delta < -1e-9 else "stable"
            latest[indicator] = EconomicIndicatorTrend(
                indicator=indicator,
                previous_value=self._finite(row.get("previous_value")),
                current_value=self._finite(row.get("new_value")),
                delta=delta,
                direction=direction,
            )
        return tuple(latest[name] for name in sorted(latest))

    def _obligations(self, state: Any, country_id: str) -> tuple[DebtObligationView, ...]:
        frame = getattr(state, "tables", {}).get("debt_contracts")
        if frame is None or frame.is_empty():
            return ()
        active = frame.filter(
            (pl.col("debtor_country_id") == str(country_id))
            & pl.col("status").is_in(["current", "arrears", "restructured"])
        ).sort(["next_payment_at_minute", "id"])
        return tuple(DebtObligationView(
            contract_id=str(row.get("id") or ""),
            creditor_country_id=str(row.get("creditor_country_id") or ""),
            principal_remaining=self._finite(row.get("principal_remaining")),
            annual_interest_rate=self._finite(row.get("annual_interest_rate")),
            next_payment_at_minute=int(row.get("next_payment_at_minute") or 0),
            next_payment_date=self._date(int(row.get("next_payment_at_minute") or 0)),
            maturity_at_minute=int(row.get("maturity_at_minute") or 0),
            maturity_date=self._date(int(row.get("maturity_at_minute") or 0)),
            arrears_amount=self._finite(row.get("arrears_amount")),
            status=str(row.get("status") or ""),
            conditions=str(row.get("conditions") or ""),
        ) for row in active.iter_rows(named=True))

    def _policies(self, state: Any, country_id: str) -> tuple[EconomicPolicyView, ...]:
        frame = getattr(state, "tables", {}).get("economic_policy_transitions")
        if frame is None or frame.is_empty():
            return ()
        active = frame.filter(
            (pl.col("country_id") == str(country_id)) & (pl.col("status") == "scheduled")
        ).sort(["effective_at_minute", "id"])
        return tuple(EconomicPolicyView(
            policy_name=str(row.get("policy_name") or ""),
            target_value=self._finite(row.get("target_value")),
            transition_cost=self._finite(row.get("transition_cost")),
            effective_at_minute=int(row.get("effective_at_minute") or 0),
            effective_date=self._date(int(row.get("effective_at_minute") or 0)),
            cooldown_until_minute=int(row.get("cooldown_until_minute") or 0),
            status=str(row.get("status") or ""),
        ) for row in active.iter_rows(named=True))

    def _distress(self, state: Any, country_id: str) -> dict[str, Any] | None:
        frame = getattr(state, "tables", {}).get("debt_distress_cases")
        if frame is None or frame.is_empty():
            return None
        active = frame.filter(
            (pl.col("country_id") == str(country_id))
            & pl.col("status").is_in(["arrears", "restructuring", "default", "recovery_pending"])
        ).sort("entered_at_minute")
        return active.row(0, named=True) if not active.is_empty() else None

    def _finite(self, value: Any, default: float = 0.0) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return resolved if resolved == resolved and abs(resolved) != float("inf") else default

    def _date(self, minute: int) -> str:
        return (GAME_EPOCH + timedelta(minutes=max(0, int(minute)))).strftime("%Y-%m-%d %H:%M")
