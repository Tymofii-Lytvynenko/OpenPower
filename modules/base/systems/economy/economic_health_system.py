from __future__ import annotations

import calendar
import hashlib
import heapq
import json
import math
from datetime import timedelta
from typing import Any

import polars as pl

from modules.base.systems.economy.economic_health_policy import (
    calculate_economic_health,
    calculate_employment_rate,
    calculate_inflation_rate,
    calculate_labor_outcomes,
    calculate_real_income_index,
    calculate_scheduled_debt_service,
)
from modules.base.systems.world.authority_policy import player_controls_country
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
    ActionSetTax,
)
from src.shared.events import EventEconomicTransition, EventRealSecond
from src.shared.state import GAME_EPOCH, GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


class EconomicHealthSystem(ISystem):
    """Resolves effective-dated national economic policy and contractual debt."""

    SPENDING_POLICIES = frozenset({
        "budget_health_ratio", "budget_edu_ratio", "budget_social_ratio", "budget_gov_ratio",
        "budget_env_ratio", "budget_research_ratio", "budget_infra_ratio", "budget_telecom_ratio",
        "budget_imf_ratio", "budget_propaganda_ratio", "budget_tourism_promo_ratio",
    })

    access = SystemAccess(
        reads=frozenset({"countries", "regions", "resource_ledger", "economic_policy_transitions", "debt_contracts", "debt_distress_cases", "migration_signals", "random_event_effects"}),
        writes=frozenset({"countries", "economic_policy_transitions", "debt_contracts", "debt_distress_cases", "economic_cause_records", "migration_signals"}),
        handles=frozenset({
            ActionChangeEconomicPolicy,
            ActionSetTax,
            ActionRequestDebtContract,
            ActionResolveDebtContract,
            ActionRequestDebtRestructuring,
        }),
        phase=SystemPhase.ECONOMIC_HEALTH,
    )

    @property
    def id(self) -> str:
        return "base.economic_health"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.population", "base.trade", "base.economy", "base.migration"]

    def update(self, state: GameState, delta_time: float) -> None:
        if "countries" not in state.tables:
            return

        now = max(0, int(state.time.total_minutes))
        for action in state.current_actions:
            if isinstance(action, ActionChangeEconomicPolicy):
                self._request_policy_change(state, action, now)
            elif isinstance(action, ActionSetTax):
                self._request_policy_change(state, ActionChangeEconomicPolicy(
                    player_id=action.player_id,
                    country_tag=action.country_tag,
                    policy_name="personal_income_tax_rate",
                    target_value=action.new_tax_rate,
                ), now)
            elif isinstance(action, ActionRequestDebtContract):
                self._request_debt_contract(state, action, now)
            elif isinstance(action, ActionResolveDebtContract):
                self._resolve_debt_contract(state, action, now)
            elif isinstance(action, ActionRequestDebtRestructuring):
                self._request_restructuring(state, action, now)

        self._apply_due_policy_changes(state, now)
        self._process_due_debt(state, now)
        if any(
            isinstance(event, EventRealSecond) and not event.is_paused and event.game_seconds_passed > 0
            for event in state.events
        ):
            self._update_due_economic_profiles(state, now)

    def _terms(self, state: GameState) -> dict[str, Any]:
        configured = state.globals.get("economic_health_terms", {})
        return configured if isinstance(configured, dict) else {}

    def _number(self, value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        return number if math.isfinite(number) else default

    def _bounded(self, value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
        return min(max(self._number(value, default), minimum), maximum)

    def _country(self, state: GameState, country_id: str) -> dict[str, Any] | None:
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return None
        row = countries.filter(pl.col("id") == str(country_id))
        return row.row(0, named=True) if not row.is_empty() else None

    def _append_rows(self, state: GameState, table_name: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        frame = state.tables.get(table_name)
        if frame is None:
            return
        additions = pl.DataFrame(records, schema=frame.schema, strict=False)
        state.update_table(table_name, pl.concat([frame, additions], how="vertical_relaxed"))

    def _replace_rows(
        self,
        state: GameState,
        table_name: str,
        records: list[dict[str, Any]],
        *,
        key: str = "id",
    ) -> None:
        if not records:
            return
        frame = state.tables.get(table_name)
        if frame is None:
            return
        patch = pl.DataFrame(records, schema=frame.schema, strict=False)
        unaffected = frame.join(patch.select(key), on=key, how="anti")
        state.update_table(table_name, pl.concat([unaffected, patch], how="vertical_relaxed").sort(key))

    def _country_values(self, state: GameState, country_id: str, changes: dict[str, Any]) -> None:
        frame = state.tables.get("countries")
        if frame is None or frame.is_empty():
            return
        target = pl.col("id") == str(country_id)
        expressions = []
        for column, value in changes.items():
            if column not in frame.columns:
                continue
            if isinstance(value, tuple) and len(value) == 2 and value[0] == "add":
                expr = pl.col(column).fill_null(0.0) + float(value[1])
            else:
                expr = pl.lit(value, dtype=frame.schema[column])
            expressions.append(pl.when(target).then(expr).otherwise(pl.col(column)).alias(column))
        if expressions:
            state.update_table("countries", frame.with_columns(expressions))

    def _transition_event(
        self,
        state: GameState,
        event_type: str,
        country_id: str,
        source_id: str,
        indicator: str,
        previous: float,
        current: float,
        reason: str,
        now: int,
    ) -> None:
        state.events.append(EventEconomicTransition(
            event_type=event_type,
            country_id=country_id,
            source_id=source_id,
            indicator=indicator,
            previous_value=float(previous),
            new_value=float(current),
            reason=reason,
            at_minute=now,
        ))

    def _record_cause(
        self,
        state: GameState,
        *,
        country_id: str,
        source_type: str,
        source_id: str,
        indicator: str,
        previous: float,
        current: float,
        unit: str,
        now: int,
        reason: str,
        records: list[dict[str, Any]] | None = None,
    ) -> None:
        if abs(float(current) - float(previous)) < 1e-9:
            return
        cause_id = f"{source_id}:{country_id}:{indicator}"
        record = {
            "id": cause_id,
            "country_id": country_id,
            "source_type": source_type,
            "source_id": source_id,
            "indicator": indicator,
            "previous_value": float(previous),
            "new_value": float(current),
            "delta": float(current) - float(previous),
            "unit": unit,
            "game_minute": int(now),
            "reason": reason,
            "confidence": 1.0,
            "completeness": "complete",
        }
        if records is None:
            self._append_rows(state, "economic_cause_records", [record])
        else:
            records.append(record)

    def _reject(
        self,
        state: GameState,
        country_id: str,
        source_id: str,
        indicator: str,
        value: float,
        reason: str,
        now: int,
    ) -> None:
        self._transition_event(state, "rejected", country_id, source_id, indicator, value, value, reason, now)

    def _request_policy_change(self, state: GameState, action: ActionChangeEconomicPolicy, now: int) -> None:
        country_id = str(action.country_tag)
        country = self._country(state, country_id)
        source_id = f"policy-request:{country_id}:{action.policy_name}:{now}"
        if country is None or not player_controls_country(state, action.player_id, country_id):
            self._reject(state, country_id, source_id, action.policy_name, 0.0, "Actor is not authorized for this country.", now)
            return

        policies = {
            "minimum_wage": "minimum_wage",
            "interest_rate": "interest_rate",
            "personal_income_tax_rate": "personal_income_tax_rate",
        }
        requested_policy = str(action.policy_name).strip().lower()
        column = policies.get(requested_policy)
        if column is None and requested_policy in self.SPENDING_POLICIES:
            column = requested_policy
        if column is None:
            self._reject(state, country_id, source_id, str(action.policy_name), 0.0, "Unsupported economic policy.", now)
            return
        value = self._number(action.target_value, math.nan)
        if not math.isfinite(value):
            self._reject(state, country_id, source_id, column, 0.0, "Policy value must be finite.", now)
            return

        terms = self._terms(state)
        default_upper = 1.0 if column in self.SPENDING_POLICIES else (0.5 if column in {"interest_rate", "personal_income_tax_rate"} else 1_000_000.0)
        upper = self._bounded(terms.get(f"max_{column}"), 0.0, 1_000_000_000.0, default_upper)
        lower = self._bounded(terms.get(f"min_{column}"), 0.0, upper, 0.0)
        if value < lower or value > upper:
            self._reject(state, country_id, source_id, column, self._number(country.get(column)), "Policy value is outside scenario bounds.", now)
            return

        transitions = state.tables["economic_policy_transitions"]
        cooldowns = transitions.filter(
            (pl.col("country_id") == country_id)
            & (pl.col("policy_name") == column)
            & (pl.col("status").is_in(["scheduled", "applied"]))
            & (pl.col("cooldown_until_minute") > now)
        )
        if not cooldowns.is_empty():
            self._reject(state, country_id, source_id, column, self._number(country.get(column)), "Policy cooldown has not elapsed.", now)
            return

        previous = self._number(country.get(column))
        configured_cost = terms.get(f"{column}_transition_cost", terms.get("policy_transition_cost", 0.0))
        transition_cost = self._bounded(configured_cost, 0.0, 1_000_000_000_000.0)
        if self._number(country.get("money_reserves")) < transition_cost:
            self._reject(state, country_id, source_id, column, previous, "Treasury cannot cover the configured policy transition cost.", now)
            return
        delay = int(self._bounded(terms.get("policy_delay_minutes"), 0.0, 525_600.0, 1_440.0))
        cooldown = int(self._bounded(terms.get("policy_cooldown_minutes"), 0.0, 5_256_000.0, 43_200.0))
        transition_id = source_id
        if not transitions.filter(pl.col("id") == transition_id).is_empty():
            self._reject(state, country_id, source_id, column, previous, "A request with this deterministic identity already exists.", now)
            return
        row = {
            "id": transition_id,
            "country_id": country_id,
            "player_id": str(action.player_id),
            "policy_name": column,
            "previous_value": previous,
            "target_value": value,
            "transition_cost": transition_cost,
            "created_at_minute": now,
            "effective_at_minute": now + delay,
            "cooldown_until_minute": now + delay + cooldown,
            "status": "scheduled",
            "reason": f"Accepted at a one-time cost of {transition_cost:.2f}; the policy takes effect at its persisted effective minute.",
        }
        if transition_cost > 0.0:
            self._country_values(state, country_id, {"money_reserves": ("add", -transition_cost)})
            self._record_cause(state, country_id=country_id, source_type="policy_transition", source_id=transition_id,
                indicator="money_reserves", previous=self._number(country.get("money_reserves")),
                current=self._number(country.get("money_reserves")) - transition_cost,
                unit="currency", now=now, reason=row["reason"])
        self._append_rows(state, "economic_policy_transitions", [row])
        self._transition_event(state, "scheduled", country_id, transition_id, column, previous, value, row["reason"], now)

    def _apply_due_policy_changes(self, state: GameState, now: int) -> None:
        transitions = state.tables.get("economic_policy_transitions")
        if transitions is None or transitions.is_empty():
            return
        due = transitions.filter((pl.col("status") == "scheduled") & (pl.col("effective_at_minute") <= now)).sort(["effective_at_minute", "id"])
        if due.is_empty():
            return
        applied: list[dict[str, Any]] = []
        for transition in due.iter_rows(named=True):
            country_id = str(transition["country_id"])
            policy = str(transition["policy_name"])
            current_country = self._country(state, country_id)
            allowed_policies = {"minimum_wage", "interest_rate", "personal_income_tax_rate", *self.SPENDING_POLICIES}
            if current_country is None or policy not in allowed_policies:
                transition["status"] = "rejected"
                transition["reason"] = "Country or policy no longer exists."
                applied.append(transition)
                continue
            old = self._number(current_country.get(policy))
            target = self._number(transition.get("target_value"))
            self._country_values(state, country_id, {policy: target})
            transition["status"] = "applied"
            transition["reason"] = f"{policy.replace('_', ' ').title()} changed at its effective time."
            applied.append(transition)
            source_id = str(transition["id"])
            self._record_cause(state, country_id=country_id, source_type="policy", source_id=source_id,
                indicator=policy, previous=old, current=target, unit="policy units", now=now, reason=transition["reason"])
            self._transition_event(state, "applied", country_id, source_id, policy, old, target, transition["reason"], now)
        self._replace_rows(state, "economic_policy_transitions", applied)

    def _request_debt_contract(self, state: GameState, action: ActionRequestDebtContract, now: int) -> None:
        debtor_id = str(action.debtor_country_id)
        creditor_id = str(action.creditor_country_id)
        request_signature = "|".join((
            str(action.player_id), debtor_id, creditor_id, str(now),
            repr(self._number(action.principal)), repr(self._number(action.annual_interest_rate)),
            str(action.payment_frequency_months), repr(self._number(action.principal_installment)),
            str(action.maturity_months), str(action.currency_code or "USD"), str(action.conditions or ""),
        ))
        request_hash = hashlib.sha256(request_signature.encode("utf-8")).hexdigest()[:20]
        contract_id = f"foreign-debt:{request_hash}"
        debtor = self._country(state, debtor_id)
        creditor = self._country(state, creditor_id)
        principal = self._number(action.principal, math.nan)
        rate = self._number(action.annual_interest_rate, math.nan)
        frequency = int(self._number(action.payment_frequency_months, 0.0))
        maturity = int(self._number(action.maturity_months, 0.0))
        installment = self._number(action.principal_installment, math.nan)
        terms = self._terms(state)
        maximum_rate = self._bounded(terms.get("max_interest_rate"), 0.0, 0.5, 0.5)
        max_debt_ratio = self._bounded(terms.get("max_principal_multiple_of_gdp"), 0.0, 100.0, 3.0)
        reason = ""
        if debtor is None or creditor is None or debtor_id == creditor_id:
            reason = "Debtor and a distinct existing creditor are required."
        elif not player_controls_country(state, action.player_id, debtor_id):
            reason = "Actor is not authorized for the debtor country."
        elif not math.isfinite(principal) or principal <= 0.0 or not math.isfinite(installment) or installment < 0.0:
            reason = "Principal and installment must be finite non-negative amounts, with positive principal."
        elif not math.isfinite(rate) or rate < 0.0 or rate > maximum_rate:
            reason = "Interest rate is outside scenario bounds."
        elif frequency < 1 or frequency > 120 or maturity < frequency or maturity > 1_200:
            reason = "Payment frequency or maturity is outside supported bounds."
        elif principal > max(0.0, self._number(debtor.get("gdp"))) * max_debt_ratio:
            reason = "Requested principal exceeds the configured debt-to-GDP limit."
        if reason:
            self._reject(state, debtor_id, contract_id, "foreign_debt", max(0.0, principal if math.isfinite(principal) else 0.0), reason, now)
            return

        contracts = state.tables["debt_contracts"]
        if not contracts.filter(pl.col("id") == contract_id).is_empty():
            self._reject(state, debtor_id, contract_id, "foreign_debt", principal, "Duplicate deterministic financing request.", now)
            return
        self._append_rows(state, "debt_contracts", [{
            "id": contract_id,
            "debtor_country_id": debtor_id,
            "creditor_country_id": creditor_id,
            "debt_type": "foreign",
            "principal_original": principal,
            "principal_remaining": principal,
            "annual_interest_rate": rate,
            "payment_frequency_months": frequency,
            "principal_payment": min(principal, installment),
            "maturity_months": maturity,
            "currency_code": str(action.currency_code or "USD")[:16],
            "conditions": str(action.conditions or "")[:2_000],
            "created_at_minute": now,
            "next_payment_at_minute": 0,
            "maturity_at_minute": 0,
            "arrears_amount": 0.0,
            "status": "pending",
            "reason": "Awaiting creditor approval; no funds have moved.",
            "last_payment_at_minute": 0,
        }])
        self._transition_event(state, "requested", debtor_id, contract_id, "foreign_debt", 0.0, principal, "Financing request awaits creditor approval.", now)

    def _resolve_debt_contract(self, state: GameState, action: ActionResolveDebtContract, now: int) -> None:
        contracts = state.tables["debt_contracts"]
        match = contracts.filter((pl.col("id") == str(action.contract_id)) & (pl.col("status") == "pending"))
        if match.is_empty():
            self._reject(state, "", str(action.contract_id), "foreign_debt", 0.0, "Pending contract does not exist.", now)
            return
        contract = match.row(0, named=True)
        debtor_id = str(contract["debtor_country_id"])
        creditor_id = str(contract["creditor_country_id"])
        creditor = self._country(state, creditor_id)
        debtor = self._country(state, debtor_id)
        principal = self._number(contract.get("principal_original"))
        if not player_controls_country(state, action.player_id, creditor_id):
            self._reject(state, debtor_id, str(contract["id"]), "foreign_debt", principal, "Actor is not authorized for the creditor country.", now)
            return
        if not action.accept:
            contract["status"] = "rejected"
            contract["reason"] = "Creditor rejected the financing request; no funds moved."
            self._replace_rows(state, "debt_contracts", [contract])
            self._transition_event(state, "rejected", debtor_id, str(contract["id"]), "foreign_debt", principal, 0.0, contract["reason"], now)
            return
        if creditor is None or debtor is None or self._number(creditor.get("money_reserves")) < principal:
            contract["status"] = "rejected"
            contract["reason"] = "Creditor no longer has sufficient reserves; the pending request was closed without a transfer."
            self._replace_rows(state, "debt_contracts", [contract])
            self._transition_event(state, "rejected", debtor_id, str(contract["id"]), "foreign_debt", principal, 0.0, contract["reason"], now)
            return

        frequency = int(contract["payment_frequency_months"])
        maturity_months = max(frequency, int(contract.get("maturity_months") or frequency))
        self._country_values(state, debtor_id, {"money_reserves": ("add", principal), "foreign_debt": ("add", principal)})
        self._country_values(state, creditor_id, {"money_reserves": ("add", -principal)})
        contract["status"] = "current"
        contract["created_at_minute"] = now
        contract["next_payment_at_minute"] = self._add_months(now, frequency)
        contract["maturity_at_minute"] = self._add_months(now, maturity_months)
        contract["reason"] = "Creditor approved; principal was transferred once from creditor reserves."
        self._replace_rows(state, "debt_contracts", [contract])
        self._adjust_annual_service(state, debtor_id, 0.0, self._annualized_service(contract))
        self._record_cause(state, country_id=debtor_id, source_type="debt", source_id=str(contract["id"]), indicator="foreign_debt",
            previous=self._number(debtor.get("foreign_debt")), current=self._number(debtor.get("foreign_debt")) + principal,
            unit="currency", now=now, reason=contract["reason"])
        self._transition_event(state, "approved", debtor_id, str(contract["id"]), "foreign_debt", 0.0, principal, contract["reason"], now)

    def _request_restructuring(self, state: GameState, action: ActionRequestDebtRestructuring, now: int) -> None:
        contracts = state.tables["debt_contracts"]
        match = contracts.filter(pl.col("id") == str(action.contract_id))
        if match.is_empty():
            self._reject(state, str(action.country_tag), str(action.contract_id), "debt_restructuring", 0.0, "Debt contract does not exist.", now)
            return
        contract = match.row(0, named=True)
        debtor_id = str(contract["debtor_country_id"])
        if str(action.country_tag) != debtor_id or not player_controls_country(state, action.player_id, debtor_id):
            self._reject(state, debtor_id, str(contract["id"]), "debt_restructuring", self._number(contract.get("arrears_amount")), "Actor is not authorized for this debtor.", now)
            return
        frequency = int(self._number(action.payment_frequency_months, 0))
        maturity = int(self._number(action.maturity_months, 0))
        rate = self._number(action.annual_interest_rate, math.nan)
        installment = self._number(action.principal_installment, math.nan)
        maximum_rate = self._bounded(self._terms(state).get("max_interest_rate"), 0.0, 0.5, 0.5)
        if contract["status"] not in {"current", "arrears", "restructured"}:
            self._reject(state, debtor_id, str(contract["id"]), "debt_restructuring", 0.0, "Contract is not eligible for restructuring.", now)
            return
        if (
            contract["status"] == "restructured"
            and int(contract.get("payment_frequency_months") or 0) == frequency
            and int(contract.get("maturity_months") or 0) == maturity
            and abs(self._number(contract.get("annual_interest_rate")) - rate) < 1e-9
            and abs(self._number(contract.get("principal_payment")) - installment) < 1e-9
        ):
            self._reject(state, debtor_id, str(contract["id"]), "debt_restructuring", 0.0, "The requested restructuring terms are already active.", now)
            return
        if frequency < 1 or frequency > 120 or maturity < frequency or maturity > 1_200 or not math.isfinite(rate) or not 0.0 <= rate <= maximum_rate or not math.isfinite(installment) or installment < 0:
            self._reject(state, debtor_id, str(contract["id"]), "debt_restructuring", 0.0, "Restructured terms are outside scenario bounds.", now)
            return

        old_service = self._annualized_service(contract)
        contract["annual_interest_rate"] = rate
        contract["payment_frequency_months"] = frequency
        contract["principal_payment"] = min(self._number(contract.get("principal_remaining")), installment)
        contract["maturity_at_minute"] = self._add_months(now, maturity)
        contract["maturity_months"] = maturity
        contract["next_payment_at_minute"] = self._add_months(now, frequency)
        contract["status"] = "restructured"
        contract["reason"] = "Terms were revised by an authorized restructuring request; outstanding principal and arrears remain due."
        self._replace_rows(state, "debt_contracts", [contract])
        self._adjust_annual_service(state, debtor_id, old_service, self._annualized_service(contract))
        self._set_distress(state, debtor_id, "restructuring", "authorized_restructuring", self._number(contract.get("arrears_amount")), now, contract["reason"])
        self._transition_event(state, "restructured", debtor_id, str(contract["id"]), "foreign_debt", old_service, self._annualized_service(contract), contract["reason"], now)

    def _add_months(self, minute: int, months: int) -> int:
        current = GAME_EPOCH + timedelta(minutes=max(0, int(minute)))
        month_index = (current.year * 12) + (current.month - 1) + max(1, int(months))
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        day = min(current.day, calendar.monthrange(year, month)[1])
        target = current.replace(year=year, month=month, day=day)
        return int((target - GAME_EPOCH).total_seconds() // 60)

    def _annualized_service(self, contract: dict[str, Any]) -> float:
        principal = max(0.0, self._number(contract.get("principal_remaining")))
        rate = self._bounded(contract.get("annual_interest_rate"), 0.0, 0.5)
        frequency = max(1, int(self._number(contract.get("payment_frequency_months"), 1)))
        installment = min(principal, max(0.0, self._number(contract.get("principal_payment"))))
        return principal * rate + installment * 12.0 / frequency

    def _adjust_annual_service(self, state: GameState, debtor_id: str, old: float, new: float) -> None:
        self._country_values(state, debtor_id, {"annual_debt_service": ("add", new - old)})

    def _process_due_debt(self, state: GameState, now: int) -> None:
        contracts = state.tables.get("debt_contracts")
        if contracts is None or contracts.is_empty():
            return
        if int(state.globals.get("economic_health_last_debt_scan_minute", -1)) == now:
            return
        due = contracts.filter(
            pl.col("status").is_in(["current", "arrears", "restructured"])
            & (pl.col("next_payment_at_minute") > 0)
            & (pl.col("next_payment_at_minute") <= now)
        ).sort(["next_payment_at_minute", "id"])
        if due.is_empty():
            state.globals["economic_health_last_debt_scan_minute"] = now
            return

        due_contracts = {
            str(row["id"]): dict(row)
            for row in due.iter_rows(named=True)
        }
        countries = state.tables.get("countries")
        country_balance_columns = (
            tuple(
                column
                for column in ("money_reserves", "foreign_debt", "arrears", "annual_debt_service")
                if countries is not None and column in countries.columns
            )
        )
        country_rows = (
            {
                str(row["id"]): dict(row)
                for row in countries.select("id", *country_balance_columns).iter_rows(named=True)
            }
            if countries is not None and "id" in countries.columns
            else {}
        )
        payment_queue = [
            (int(contract["next_payment_at_minute"]), contract_id)
            for contract_id, contract in due_contracts.items()
        ]
        heapq.heapify(payment_queue)
        affected_countries: set[str] = set()
        country_balances: dict[str, float] = {}
        changed_countries: set[str] = set()
        cause_records: list[dict[str, Any]] = []

        # A save/load or coarse time step may cross multiple due dates; settle them chronologically instead of delaying each missed installment by a simulation tick.
        while payment_queue:
            due_at, contract_id = heapq.heappop(payment_queue)
            contract = due_contracts[contract_id]
            if due_at > now or contract["status"] not in {"current", "arrears", "restructured"}:
                continue
            debtor_id = str(contract["debtor_country_id"])
            creditor_id = str(contract["creditor_country_id"])
            affected_countries.add(debtor_id)
            principal = max(0.0, self._number(contract.get("principal_remaining")))
            rate = self._number(contract.get("annual_interest_rate"))
            frequency = max(1, int(contract.get("payment_frequency_months") or 1))
            installment = self._number(contract.get("principal_payment"))
            interest_due, principal_due = calculate_scheduled_debt_service(
                principal_remaining=principal,
                annual_interest_rate=rate,
                principal_installment=installment,
                payment_frequency_months=frequency,
            )
            maturity_due = due_at >= int(contract.get("maturity_at_minute") or 0)
            if maturity_due:
                principal_due = principal
            old_arrears = max(0.0, self._number(contract.get("arrears_amount")))
            total_due = old_arrears + interest_due + principal_due
            debtor = country_rows.get(debtor_id)
            available = max(0.0, self._number((debtor or {}).get("money_reserves")))
            paid = min(available, total_due)
            paid_after_arrears = max(0.0, paid - old_arrears)
            paid_after_interest = max(0.0, paid_after_arrears - interest_due)
            principal_paid = min(principal_due, paid_after_interest)
            new_principal = max(0.0, principal - principal_paid)
            new_arrears = max(0.0, total_due - paid)
            updated_service_contract = dict(contract)
            updated_service_contract["principal_remaining"] = new_principal
            new_service = 0.0 if new_principal <= 1e-9 else self._annualized_service(updated_service_contract)
            old_service = self._annualized_service(contract)
            if debtor is not None:
                for column, delta in (
                    ("money_reserves", -paid),
                    ("foreign_debt", -principal_paid),
                    ("arrears", new_arrears - old_arrears),
                    ("annual_debt_service", new_service - old_service),
                ):
                    if column in country_balance_columns:
                        debtor[column] = self._number(debtor.get(column)) + delta
                changed_countries.add(debtor_id)
            creditor = country_rows.get(creditor_id)
            if creditor is not None and "money_reserves" in country_balance_columns:
                creditor["money_reserves"] = self._number(creditor.get("money_reserves")) + paid
                changed_countries.add(creditor_id)
            contract["principal_remaining"] = new_principal
            contract["arrears_amount"] = new_arrears
            contract["last_payment_at_minute"] = due_at
            contract["next_payment_at_minute"] = self._add_months(due_at, frequency)
            if new_principal <= 1e-9 and new_arrears <= 1e-9:
                contract["status"] = "paid"
            elif new_arrears > 1e-9:
                contract["status"] = "arrears"
            elif contract["status"] != "restructured":
                contract["status"] = "current"
            contract["reason"] = (
                f"Scheduled service paid {paid:.2f} of {total_due:.2f}; "
                f"principal reduced by {principal_paid:.2f}; unpaid service remains recorded as arrears."
            )
            due_contracts[contract_id] = contract
            next_due = int(contract["next_payment_at_minute"])
            if contract["status"] in {"current", "arrears", "restructured"} and next_due <= now:
                heapq.heappush(payment_queue, (next_due, contract_id))
            country_balances[debtor_id] = self._number((debtor or {}).get("arrears"))
            self._record_cause(state, country_id=debtor_id, source_type="debt_service", source_id=f"{contract['id']}:{due_at}",
                indicator="foreign_debt", previous=principal, current=new_principal, unit="currency", now=due_at,
                reason=contract["reason"], records=cause_records)
            self._transition_event(state, "serviced", debtor_id, str(contract["id"]), "debt_service", total_due, paid, contract["reason"], due_at)
            if new_arrears > 1e-9:
                self._flush_debt_country_updates(state, country_rows, changed_countries, country_balance_columns)
                self._set_distress(state, debtor_id, "arrears", "scheduled_service_shortfall", new_arrears, due_at, contract["reason"])

        self._replace_rows(state, "debt_contracts", list(due_contracts.values()))
        self._flush_debt_country_updates(state, country_rows, changed_countries, country_balance_columns)
        self._append_rows(state, "economic_cause_records", cause_records)
        distress_cases = state.tables.get("debt_distress_cases")
        if distress_cases is not None and not distress_cases.is_empty():
            for country_id in sorted(affected_countries):
                if country_balances.get(country_id, 0.0) <= 1e-9:
                    self._recover_distress_if_eligible(state, country_id, now)

        state.globals["economic_health_last_debt_scan_minute"] = now

    def _flush_debt_country_updates(
        self,
        state: GameState,
        country_rows: dict[str, dict[str, Any]],
        changed_countries: set[str],
        balance_columns: tuple[str, ...],
    ) -> None:
        if not changed_countries or not balance_columns:
            changed_countries.clear()
            return
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            changed_countries.clear()
            return

        rows = [
            {"id": country_id, **{column: country_rows[country_id].get(column) for column in balance_columns}}
            for country_id in sorted(changed_countries)
            if country_id in country_rows
        ]
        if not rows:
            changed_countries.clear()
            return

        patch_schema = {
            "id": countries.schema["id"],
            **{column: countries.schema[column] for column in balance_columns},
        }
        patch = pl.DataFrame(rows, schema=patch_schema, strict=False)
        order_column = "__economic_debt_order"
        while order_column in countries.columns:
            order_column += "_"
        patch_suffix = "__economic_debt_patch"
        updated = (
            countries.with_row_index(order_column)
            .join(patch, on="id", how="left", suffix=patch_suffix)
            .with_columns(
                pl.coalesce([pl.col(f"{column}{patch_suffix}"), pl.col(column)]).alias(column)
                for column in balance_columns
            )
            .drop([f"{column}{patch_suffix}" for column in balance_columns])
            .sort(order_column)
            .drop(order_column)
        )
        state.update_table("countries", updated)
        changed_countries.clear()

    def _set_distress(self, state: GameState, country_id: str, status: str, trigger: str, arrears: float, now: int, reason: str) -> None:
        cases = state.tables.get("debt_distress_cases")
        if cases is None:
            return
        active = cases.filter(
            (pl.col("country_id") == country_id)
            & pl.col("status").is_in(["arrears", "restructuring", "default", "recovery_pending"])
        )
        country = self._country(state, country_id) or {}
        total_arrears = max(0.0, self._number(country.get("arrears"), arrears))
        terms = self._terms(state)
        default_floor = self._bounded(terms.get("default_arrears_minimum"), 0.0, 1_000_000_000_000.0, 100.0)
        default_share = self._bounded(terms.get("default_arrears_gdp_ratio"), 0.0, 1.0, 0.1)
        default_threshold = max(default_floor, self._number(country.get("gdp")) * default_share)
        existing_case = active.sort("entered_at_minute").row(0, named=True) if not active.is_empty() else None
        current_status = str((existing_case or {}).get("status") or "")
        resolved_status = "default" if total_arrears >= default_threshold or current_status == "default" else status
        if current_status == "restructuring" and resolved_status == "arrears":
            resolved_status = "restructuring"
        case_id = f"distress:{country_id}:{now}:{cases.height}"
        previous_status = current_status
        if active.is_empty():
            row = {
                "id": case_id,
                "country_id": country_id,
                "status": resolved_status,
                "trigger": trigger,
                "entered_at_minute": now,
                "updated_at_minute": now,
                "arrears_at_entry": total_arrears,
                "restriction_json": json.dumps(self._restrictions(resolved_status), sort_keys=True),
                "recovery_condition": "All contractual arrears are cleared and treasury is non-negative.",
                "reason": reason,
            }
            self._append_rows(state, "debt_distress_cases", [row])
        else:
            row = existing_case
            case_id = str(row["id"])
            row.update(
                status=resolved_status,
                updated_at_minute=now,
                restriction_json=json.dumps(self._restrictions(resolved_status), sort_keys=True),
                reason=reason,
            )
            self._replace_rows(state, "debt_distress_cases", [row])
        modifiers = self._restrictions(resolved_status)
        self._country_values(state, country_id, {
            "debt_distress_status": resolved_status,
            "economic_production_modifier": modifiers["production"],
            "economic_trade_modifier": modifiers["trade"],
            "economic_policy_modifier": modifiers["policy"],
            "economic_health_modifier": modifiers["health"],
            "economic_political_modifier": modifiers["politics"],
            "economic_creditworthiness_modifier": modifiers["creditworthiness"],
        })
        if previous_status != resolved_status:
            self._transition_event(state, resolved_status, country_id, case_id, "arrears", 0.0, total_arrears, reason, now)

    def _restrictions(self, status: str) -> dict[str, float]:
        configured = {
            "arrears": {
                "production": 0.95, "trade": 0.95, "policy": 0.9,
                "health": 0.98, "politics": 0.98, "creditworthiness": 0.95,
            },
            "restructuring": {
                "production": 0.9, "trade": 0.9, "policy": 0.75,
                "health": 0.95, "politics": 0.9, "creditworthiness": 0.85,
            },
            "default": {
                "production": 0.75, "trade": 0.8, "policy": 0.6,
                "health": 0.9, "politics": 0.75, "creditworthiness": 0.7,
            },
        }
        return configured.get(status, {
            "production": 1.0, "trade": 1.0, "policy": 1.0,
            "health": 1.0, "politics": 1.0, "creditworthiness": 1.0,
        })

    def _recover_distress_if_eligible(self, state: GameState, country_id: str, now: int) -> None:
        cases = state.tables.get("debt_distress_cases")
        country = self._country(state, country_id)
        if cases is None or country is None or self._number(country.get("arrears")) > 1e-9 or self._number(country.get("money_reserves")) < 0.0:
            return
        active = cases.filter(
            (pl.col("country_id") == country_id)
            & pl.col("status").is_in(["arrears", "restructuring", "default", "recovery_pending"])
        )
        if active.is_empty():
            return
        case = active.sort("entered_at_minute").row(0, named=True)
        case.update(status="closed", updated_at_minute=now, restriction_json="{}", reason="All arrears were cleared and treasury is non-negative; bounded restrictions were removed.")
        self._replace_rows(state, "debt_distress_cases", [case])
        self._country_values(state, country_id, {
            "debt_distress_status": "current",
            "economic_production_modifier": 1.0,
            "economic_trade_modifier": 1.0,
            "economic_policy_modifier": 1.0,
            "economic_health_modifier": 1.0,
            "economic_political_modifier": 1.0,
            "economic_creditworthiness_modifier": 1.0,
        })
        self._transition_event(state, "recovered", country_id, str(case["id"]), "arrears", self._number(case.get("arrears_at_entry")), 0.0, case["reason"], now)

    def _update_due_economic_profiles(self, state: GameState, now: int) -> None:
        countries = state.tables["countries"]
        boundary = now - (now % 1_440)
        due = countries.filter(pl.col("economic_health_last_update_minute") + 1_440 <= boundary)
        if due.is_empty():
            return

        migration_signals = state.tables.get("migration_signals")
        unconsumed_migration_signals: dict[str, dict[str, Any]] = {}
        if migration_signals is not None:
            for signal in migration_signals.to_dicts():
                updated_at = max(0, int(self._number(signal.get("updated_at_minute"))))
                consumed_at = max(0, int(self._number(signal.get("economy_consumed_at_minute"))))
                if updated_at > consumed_at:
                    unconsumed_migration_signals[str(signal.get("country_id", ""))] = signal

        updated_migration_signals: list[dict[str, Any]] = []
        regions = state.tables.get("regions")

        country_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            now,
            categories={"labour", "employment"},
            subject_type="country",
        )
        regional_health_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            now,
            categories={"health"},
            subject_type="region",
        )
        region_owners = {}
        if regions is not None and {"id", "owner"}.issubset(regions.columns):
            region_owners = {
                str(row.get("id")): str(row.get("owner") or "").strip().upper()
                for row in regions.select("id", "owner").iter_rows(named=True)
            }
        health_effect_by_country: dict[str, float] = {}
        for (_, region_id, _), magnitude in regional_health_effects.items():
            owner = region_owners.get(region_id, "")
            if owner:
                health_effect_by_country[owner] = health_effect_by_country.get(owner, 0.0) + magnitude

        labor_by_country: dict[str, float] = {}
        if regions is not None and {"owner", "pop_15_64"}.issubset(regions.columns):
            labor_by_country = {
                str(row["owner"]): max(0.0, self._number(row["labor_supply"]))
                for row in regions.group_by("owner").agg(pl.col("pop_15_64").fill_null(0).sum().alias("labor_supply")).iter_rows(named=True)
            }
        shortage_by_country: dict[str, float] = {}
        ledger = state.tables.get("resource_ledger")
        if ledger is not None and {"country_id", "balance_usd", "consumption_usd"}.issubset(ledger.columns):
            shortage = ledger.group_by("country_id").agg(
                pl.col("balance_usd").filter(pl.col("balance_usd") < 0).abs().sum().alias("shortage"),
                pl.col("consumption_usd").sum().alias("demand"),
            )
            shortage_by_country = {
                str(row["country_id"]): self._bounded(
                    self._number(row["shortage"]) / max(1.0, self._number(row["demand"])), 0.0, 1.0
                )
                for row in shortage.iter_rows(named=True)
            }

        updated_rows: list[dict[str, Any]] = []
        cause_records: list[dict[str, Any]] = []
        for row in due.iter_rows(named=True):
            country = dict(row)
            country_id = str(country["id"])
            previous_gdp = max(0.0, self._number(country.get("economic_previous_gdp")))
            gdp = max(0.0, self._number(country.get("gdp")))
            production_growth = self._bounded((gdp / previous_gdp) - 1.0, -0.5, 0.5) if previous_gdp > 0.0 else 0.0
            employment_before = self._bounded(country.get("employment_rate"), 0.0, 1.0, 0.95)
            raw_labor_supply = max(0.0, labor_by_country.get(country_id, self._number(country.get("labor_supply"))))
            labor_effect = country_effects.get(("country", country_id.upper(), "labour"), 0.0)
            labor_supply = raw_labor_supply * (1.0 + self._bounded(labor_effect, -0.5, 0.5))
            old_wage = max(0.0, self._number(country.get("economic_previous_minimum_wage")))
            minimum_wage = max(0.0, self._number(country.get("minimum_wage")))
            # Wage policy cannot create household income when no working-age labor pool exists to receive it.
            has_employed_population = labor_supply > 0.0 and employment_before > 0.0
            wage_growth = self._bounded((minimum_wage / old_wage) - 1.0, -1.0, 1.0) if old_wage > 0.0 and has_employed_population else 0.0
            inflation_before = self._number(country.get("inflation_rate"))
            revenue = max(0.0, self._number(country.get("total_annual_revenue")))
            expenses = max(0.0, self._number(country.get("total_annual_expense")))
            deficit_ratio = self._bounded(max(0.0, expenses - revenue) / max(1.0, gdp), 0.0, 1.0)
            inflation_after = calculate_inflation_rate(
                previous_rate=inflation_before,
                demand_growth=production_growth,
                fiscal_deficit_ratio=deficit_ratio,
                resource_cost_growth=shortage_by_country.get(country_id, 0.0),
                policy_interest_rate=self._number(country.get("interest_rate")),
            )
            real_income_before = self._bounded(country.get("real_income_index"), 0.0, 2.0, 1.0)
            nominal_index = self._bounded(
                self._number(country.get("nominal_income_index"), 1.0) * (1.0 + wage_growth), 0.0, 2.0, 1.0
            )
            real_income_after = calculate_real_income_index(real_income_before, wage_growth, inflation_after)
            employment_after = calculate_employment_rate(
                current_rate=employment_before,
                production_growth=production_growth,
                real_wage_growth=wage_growth - inflation_after,
            )
            employment_effect = country_effects.get(("country", country_id.upper(), "employment"), 0.0)
            employment_after = self._bounded(
                employment_after * (1.0 + self._bounded(employment_effect, -0.5, 0.5)),
                0.0,
                1.0,
            )
            unemployment_before = self._bounded(country.get("unemployment_rate"), 0.0, 1.0, 1.0 - employment_before)
            unemployment_after = 1.0 - employment_after
            poverty_before = self._bounded(country.get("poverty_rate"), 0.0, 1.0)
            poverty_after = self._bounded(
                poverty_before + ((unemployment_after - unemployment_before) * 0.12)
                + (max(0.0, inflation_after) * 0.02) - (max(0.0, wage_growth) * 0.04),
                0.0,
                1.0,
            )
            labor = calculate_labor_outcomes(
                labor_supply=labor_supply,
                employment_rate=employment_after,
                underemployment_rate=self._number(country.get("underemployment_rate")),
            )
            reserve_coverage = self._bounded(self._number(country.get("money_reserves")) / max(1.0, expenses), 0.0, 1.0)
            health_before = self._bounded(country.get("economic_health"), 0.0, 1.0, 1.0)
            health_after = calculate_economic_health(
                human_development=self._number(country.get("human_dev"), 0.5),
                reserve_coverage=reserve_coverage,
                inflation_rate=inflation_after,
                unemployment_rate=unemployment_after,
                poverty_rate=poverty_after,
                real_income_index=real_income_after,
            )
            migration_signal = unconsumed_migration_signals.get(country_id)
            migration_service_pressure = self._bounded(
                migration_signal.get("service_pressure") if migration_signal else 0.0,
                0.0,
                1.0,
            )
            migration_political_pressure = self._bounded(
                migration_signal.get("political_pressure") if migration_signal else 0.0,
                0.0,
                1.0,
            )
            migration_health_cost = self._bounded(
                self._terms(state).get("migration_service_health_penalty", 0.08),
                0.0,
                0.25,
            ) * migration_service_pressure
            distress_health_modifier = self._bounded(
                country.get("economic_health_modifier"), 0.5, 1.0, 1.0
            )
            health_after = self._bounded(
                (health_after * distress_health_modifier)
                - migration_health_cost
                + self._bounded(health_effect_by_country.get(country_id.upper(), 0.0), -0.5, 0.25),
                0.0,
                1.0,
            )
            migration_pressure = self._bounded(
                (0.35 * poverty_after)
                + (0.30 * unemployment_after)
                + (0.35 * max(0.0, 1.0 - real_income_after)),
                0.0,
                1.0,
            )
            migration_pressure = self._bounded(
                migration_pressure
                + (0.20 * migration_service_pressure)
                + (0.10 * migration_political_pressure),
                0.0,
                1.0,
            )
            if migration_signal is not None:
                consumed_signal = dict(migration_signal)
                consumed_signal["economy_consumed_at_minute"] = max(
                    0,
                    int(self._number(migration_signal.get("updated_at_minute"))),
                )
                updated_migration_signals.append(consumed_signal)
            domestic_debt = max(0.0, -self._number(country.get("money_reserves")))
            values = {
                "inflation_rate": inflation_after,
                "real_income_index": real_income_after,
                "nominal_income_index": nominal_index,
                "employment_rate": employment_after,
                "unemployment_rate": unemployment_after,
                "poverty_rate": poverty_after,
                "labor_supply": labor.labor_supply,
                "employed_population": labor.employed_population,
                "underemployed_population": labor.underemployed_population,
                "economic_health": health_after,
                "migration_pressure": migration_pressure,
                "domestic_debt": domestic_debt,
                "economic_previous_gdp": gdp,
                "economic_previous_minimum_wage": minimum_wage,
                "economic_health_last_update_minute": boundary,
            }
            country.update(values)
            if "gvt_approval" in country:
                approval_before = self._bounded(country.get("gvt_approval"), 0.0, 100.0, 50.0)
                approval_delta = ((health_after - health_before) * 20.0) + ((unemployment_before - unemployment_after) * 8.0)
                values["gvt_approval"] = self._bounded(approval_before + approval_delta, 0.0, 100.0)
                country["gvt_approval"] = values["gvt_approval"]
            updated_rows.append(country)
            source_id = f"daily-economic-profile:{boundary}"
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
                "inflation_rate": inflation_before,
                "nominal_income_index": self._number(row.get("nominal_income_index"), 1.0),
                "real_income_index": real_income_before,
                "employment_rate": employment_before,
                "unemployment_rate": unemployment_before,
                "labor_supply": self._number(row.get("labor_supply")),
                "employed_population": self._number(row.get("employed_population")),
                "underemployed_population": self._number(row.get("underemployed_population")),
                "poverty_rate": poverty_before,
                "economic_health": health_before,
                "migration_pressure": self._number(row.get("migration_pressure")),
                "domestic_debt": self._number(row.get("domestic_debt")),
            }
            if "gvt_approval" in row:
                old_values["gvt_approval"] = self._number(row.get("gvt_approval"), 50.0)
                reasons["gvt_approval"] = "Employment and economic-health changes influenced public approval."
                units = {"gvt_approval": "percent"}
            else:
                units = {}
            units.update({
                "inflation_rate": "rate", "nominal_income_index": "index", "real_income_index": "index",
                "employment_rate": "rate", "unemployment_rate": "rate",
                "labor_supply": "people", "employed_population": "people", "underemployed_population": "people",
                "poverty_rate": "rate", "economic_health": "index",
                "migration_pressure": "index", "domestic_debt": "currency",
            })
            for indicator, previous in old_values.items():
                current = self._number(values[indicator])
                self._record_cause(state, country_id=country_id, source_type="economic_update", source_id=source_id,
                    indicator=indicator, previous=previous, current=current, unit=units[indicator], now=boundary,
                    reason=reasons[indicator], records=cause_records)

        self._append_rows(state, "economic_cause_records", cause_records)
        update = pl.DataFrame(updated_rows, schema=countries.schema, strict=False)
        unaffected = countries.join(due.select("id"), on="id", how="anti")
        state.update_table("countries", pl.concat([unaffected, update], how="vertical_relaxed").sort("id"))
        self._replace_rows(
            state,
            "migration_signals",
            updated_migration_signals,
            key="country_id",
        )
