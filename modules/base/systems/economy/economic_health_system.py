from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import polars as pl

from modules.base.systems.economy.economic_health_policy import (
    DebtContractRequestInputs,
    DebtContractRequestPlanner,
    DebtRestructuringInputs,
    DebtRestructuringPlan,
    DebtRestructuringPlanner,
    DebtServiceSettlementCalculator,
    DeterministicDebtContractRequestPlanner,
    DeterministicDebtRestructuringPlanner,
    DeterministicDebtServiceSettlementCalculator,
    DeterministicEconomicPolicyChangeValidator,
    DeterministicEconomicProfileCalculator,
    EconomicPolicyChangeValidationInputs,
    EconomicPolicyChangeValidator,
    EconomicProfileCalculator,
    EconomicProfileEnvironment,
    EconomicProfileInputs,
    calculate_annualized_debt_service,
)
from modules.base.systems.economy.due_debt_settlement import (
    DueDebtBatch,
    DueDebtInstallment,
    DueDebtSettlementProcessor,
    DeterministicDueDebtSettlementProcessor,
    add_months,
    append_rows,
    finite_number,
    replace_rows,
)
from modules.base.systems.economy.debt_distress_policy import (
    DebtDistressInputs,
    DebtDistressPlanner,
    DebtDistressRequest,
    DeterministicDebtDistressPlanner,
)
from modules.base.systems.economy.economic_policy_transition import (
    DeterministicEconomicPolicyTransitionPlanner,
    EconomicPolicyTransitionInputs,
    EconomicPolicyTransitionPlanner,
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
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase

TComponent = TypeVar("TComponent")


def _resolve_component(
    component: TComponent | None,
    default_factory: Callable[[], TComponent],
) -> TComponent:
    if component is not None:
        return component
    return default_factory()


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

    def __init__(
        self,
        profile_calculator: EconomicProfileCalculator | None = None,
        debt_service_calculator: DebtServiceSettlementCalculator | None = None,
        policy_change_validator: EconomicPolicyChangeValidator | None = None,
        debt_contract_request_planner: DebtContractRequestPlanner | None = None,
        debt_restructuring_planner: DebtRestructuringPlanner | None = None,
        due_debt_processor: DueDebtSettlementProcessor | None = None,
        debt_distress_planner: DebtDistressPlanner | None = None,
        policy_transition_planner: EconomicPolicyTransitionPlanner | None = None,
    ) -> None:
        self._profile_calculator = _resolve_component(
            profile_calculator,
            DeterministicEconomicProfileCalculator,
        )
        self._debt_service_calculator = _resolve_component(
            debt_service_calculator,
            DeterministicDebtServiceSettlementCalculator,
        )
        self._policy_change_validator = _resolve_component(
            policy_change_validator,
            DeterministicEconomicPolicyChangeValidator,
        )
        self._debt_contract_request_planner = _resolve_component(
            debt_contract_request_planner,
            DeterministicDebtContractRequestPlanner,
        )
        self._debt_restructuring_planner = _resolve_component(
            debt_restructuring_planner,
            DeterministicDebtRestructuringPlanner,
        )
        self._due_debt_processor = _resolve_component(
            due_debt_processor,
            lambda: DeterministicDueDebtSettlementProcessor(self._debt_service_calculator),
        )
        self._debt_distress_planner = _resolve_component(
            debt_distress_planner,
            DeterministicDebtDistressPlanner,
        )
        self._policy_transition_planner = _resolve_component(
            policy_transition_planner,
            DeterministicEconomicPolicyTransitionPlanner,
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
        return finite_number(value, default)

    def _bounded(self, value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
        return min(max(self._number(value, default), minimum), maximum)

    def _country(self, state: GameState, country_id: str) -> dict[str, Any] | None:
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return None
        row = countries.filter(pl.col("id") == str(country_id))
        return row.row(0, named=True) if not row.is_empty() else None

    def _append_rows(self, state: GameState, table_name: str, records: list[dict[str, Any]]) -> None:
        append_rows(state, table_name, records)

    def _replace_rows(
        self,
        state: GameState,
        table_name: str,
        records: list[dict[str, Any]],
        *,
        key: str = "id",
    ) -> None:
        replace_rows(state, table_name, records, key=key)

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

        terms = self._terms(state)
        validation = self._policy_change_validator.validate(
            EconomicPolicyChangeValidationInputs(
                requested_policy_name=str(action.policy_name),
                target_value=action.target_value,
                country=country,
                terms=terms,
                spending_policies=self.SPENDING_POLICIES,
            )
        )
        if validation.rejection_reason is not None:
            self._reject(
                state,
                country_id,
                source_id,
                validation.rejection_indicator,
                validation.rejection_value,
                validation.rejection_reason,
                now,
            )
            return
        column = validation.policy_name
        value = validation.target_value
        previous = validation.previous_value

        transitions = state.tables["economic_policy_transitions"]
        cooldown_active = not transitions.filter(
            (pl.col("country_id") == country_id)
            & (pl.col("policy_name") == column)
            & (pl.col("status").is_in(["scheduled", "applied"]))
            & (pl.col("cooldown_until_minute") > now)
        ).is_empty()
        configured_cost = terms.get(f"{column}_transition_cost", terms.get("policy_transition_cost", 0.0))
        draft = self._policy_transition_planner.prepare(
            EconomicPolicyTransitionInputs(
                transition_id=source_id,
                country_id=country_id,
                player_id=str(action.player_id),
                policy_name=column,
                previous_value=previous,
                target_value=value,
                current_reserves=self._number(country.get("money_reserves")),
                transition_cost_setting=configured_cost,
                delay_minutes_setting=terms.get("policy_delay_minutes"),
                cooldown_minutes_setting=terms.get("policy_cooldown_minutes"),
                cooldown_active=cooldown_active,
                now=now,
            )
        )
        if draft.rejection_reason is not None:
            self._reject(state, country_id, source_id, column, previous, draft.rejection_reason, now)
            return
        plan = self._policy_transition_planner.finalize(
            draft,
            transition_id_exists=not transitions.filter(pl.col("id") == source_id).is_empty(),
        )
        if plan.rejection_reason is not None:
            self._reject(state, country_id, source_id, column, previous, plan.rejection_reason, now)
            return
        assert plan.row is not None
        row = plan.row
        transition_cost = plan.transition_cost
        if transition_cost > 0.0:
            self._country_values(state, country_id, {"money_reserves": ("add", -transition_cost)})
            self._record_cause(state, country_id=country_id, source_type="policy_transition", source_id=source_id,
                indicator="money_reserves", previous=self._number(country.get("money_reserves")),
                current=self._number(country.get("money_reserves")) - transition_cost,
                unit="currency", now=now, reason=row["reason"])
        self._append_rows(state, "economic_policy_transitions", [row])
        self._transition_event(state, "scheduled", country_id, source_id, column, previous, value, row["reason"], now)

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
        debtor = self._country(state, debtor_id)
        creditor = self._country(state, creditor_id)
        actor_authorized = (
            debtor is not None
            and creditor is not None
            and debtor_id != creditor_id
            and player_controls_country(state, action.player_id, debtor_id)
        )
        plan = self._debt_contract_request_planner.plan(
            DebtContractRequestInputs(
                player_id=str(action.player_id),
                debtor_country_id=debtor_id,
                creditor_country_id=creditor_id,
                now=now,
                principal=action.principal,
                annual_interest_rate=action.annual_interest_rate,
                payment_frequency_months=action.payment_frequency_months,
                principal_installment=action.principal_installment,
                maturity_months=action.maturity_months,
                currency_code=action.currency_code,
                conditions=action.conditions,
                debtor_exists=debtor is not None,
                creditor_exists=creditor is not None,
                actor_authorized=actor_authorized,
                debtor_gdp=(debtor or {}).get("gdp"),
                terms=self._terms(state),
            )
        )
        if plan.rejection_reason is not None:
            self._reject(
                state,
                debtor_id,
                plan.contract_id,
                "foreign_debt",
                plan.rejection_amount,
                plan.rejection_reason,
                now,
            )
            return

        contracts = state.tables["debt_contracts"]
        if not contracts.filter(pl.col("id") == plan.contract_id).is_empty():
            self._reject(state, debtor_id, plan.contract_id, "foreign_debt", plan.principal, "Duplicate deterministic financing request.", now)
            return
        assert plan.contract_row is not None
        self._append_rows(state, "debt_contracts", [plan.contract_row])
        self._transition_event(
            state,
            "requested",
            debtor_id,
            plan.contract_id,
            "foreign_debt",
            0.0,
            plan.principal,
            "Financing request awaits creditor approval.",
            now,
        )

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
        maximum_rate = self._bounded(self._terms(state).get("max_interest_rate"), 0.0, 0.5, 0.5)
        plan = self._debt_restructuring_planner.plan(
            DebtRestructuringInputs(
                contract=contract,
                payment_frequency_months=action.payment_frequency_months,
                maturity_months=action.maturity_months,
                annual_interest_rate=action.annual_interest_rate,
                principal_installment=action.principal_installment,
                maximum_rate=maximum_rate,
            )
        )
        if plan.rejection_reason is not None:
            self._reject(
                state,
                debtor_id,
                str(contract["id"]),
                "debt_restructuring",
                0.0,
                plan.rejection_reason,
                now,
            )
            return

        self._apply_debt_restructuring_plan(state, debtor_id, plan, now)

    def _apply_debt_restructuring_plan(
        self,
        state: GameState,
        debtor_id: str,
        plan: DebtRestructuringPlan,
        now: int,
    ) -> None:
        assert plan.contract is not None
        restructured_contract = plan.contract
        restructured_contract["maturity_at_minute"] = self._add_months(
            now,
            int(restructured_contract["maturity_months"]),
        )
        restructured_contract["next_payment_at_minute"] = self._add_months(
            now,
            int(restructured_contract["payment_frequency_months"]),
        )
        self._replace_rows(state, "debt_contracts", [restructured_contract])
        self._adjust_annual_service(
            state,
            debtor_id,
            plan.old_service,
            plan.new_service,
        )
        self._set_distress(
            state,
            DebtDistressRequest(
                country_id=debtor_id,
                requested_status="restructuring",
                trigger="authorized_restructuring",
                arrears=self._number(restructured_contract.get("arrears_amount")),
                now=now,
                reason=restructured_contract["reason"],
            ),
        )
        self._transition_event(
            state,
            "restructured",
            debtor_id,
            str(restructured_contract["id"]),
            "foreign_debt",
            plan.old_service,
            plan.new_service,
            restructured_contract["reason"],
            now,
        )

    def _add_months(self, minute: int, months: int) -> int:
        return add_months(minute, months)

    def _annualized_service(self, contract: dict[str, Any]) -> float:
        return calculate_annualized_debt_service(contract)

    def _adjust_annual_service(self, state: GameState, debtor_id: str, old: float, new: float) -> None:
        self._country_values(state, debtor_id, {"annual_debt_service": ("add", new - old)})

    def _process_due_debt(self, state: GameState, now: int) -> None:
        self._due_debt_processor.process(state, now, self)

    def record_due_debt_settlement(
        self,
        state: GameState,
        batch: DueDebtBatch,
        installment: DueDebtInstallment,
    ) -> None:
        settlement = installment.settlement
        contract = installment.contract
        debtor_id = installment.debtor_country_id
        due_at = installment.due_at_minute
        self._record_cause(
            state,
            country_id=debtor_id,
            source_type="debt_service",
            source_id=f"{contract['id']}:{due_at}",
            indicator="foreign_debt",
            previous=settlement.principal,
            current=settlement.new_principal,
            unit="currency",
            now=due_at,
            reason=contract["reason"],
            records=batch.cause_records,
        )
        self._transition_event(
            state,
            "serviced",
            debtor_id,
            str(contract["id"]),
            "debt_service",
            settlement.total_due,
            settlement.paid,
            contract["reason"],
            due_at,
        )

    def apply_due_debt_shortfall(
        self,
        state: GameState,
        installment: DueDebtInstallment,
    ) -> None:
        self._set_distress(
            state,
            DebtDistressRequest(
                country_id=installment.debtor_country_id,
                requested_status="arrears",
                trigger="scheduled_service_shortfall",
                arrears=installment.settlement.new_arrears,
                now=installment.due_at_minute,
                reason=installment.contract["reason"],
            ),
        )

    def _set_distress(self, state: GameState, request: DebtDistressRequest) -> None:
        country_id = request.country_id
        cases = state.tables.get("debt_distress_cases")
        if cases is None:
            return
        active = cases.filter(
            (pl.col("country_id") == country_id)
            & pl.col("status").is_in(["arrears", "restructuring", "default", "recovery_pending"])
        )
        country = self._country(state, country_id) or {}
        terms = self._terms(state)
        existing_case = active.sort("entered_at_minute").row(0, named=True) if not active.is_empty() else None
        plan = self._debt_distress_planner.plan(
            DebtDistressInputs(
                country_id=country_id,
                requested_status=request.requested_status,
                trigger=request.trigger,
                fallback_arrears=request.arrears,
                country_arrears=country.get("arrears"),
                country_gdp=country.get("gdp"),
                default_arrears_minimum=terms.get("default_arrears_minimum"),
                default_arrears_gdp_ratio=terms.get("default_arrears_gdp_ratio"),
                now=request.now,
                reason=request.reason,
                case_count=cases.height,
                existing_case=existing_case,
            )
        )
        if plan.creates_case:
            self._append_rows(state, "debt_distress_cases", [plan.case])
        else:
            self._replace_rows(state, "debt_distress_cases", [plan.case])
        self._country_values(state, country_id, {
            "debt_distress_status": plan.status,
            "economic_production_modifier": plan.modifiers["production"],
            "economic_trade_modifier": plan.modifiers["trade"],
            "economic_policy_modifier": plan.modifiers["policy"],
            "economic_health_modifier": plan.modifiers["health"],
            "economic_political_modifier": plan.modifiers["politics"],
            "economic_creditworthiness_modifier": plan.modifiers["creditworthiness"],
        })
        if plan.previous_status != plan.status:
            self._transition_event(
                state,
                plan.status,
                country_id,
                plan.case_id,
                "arrears",
                0.0,
                plan.total_arrears,
                request.reason,
                request.now,
            )

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

    def recover_due_debt_distress(self, state: GameState, country_id: str, now: int) -> None:
        self._recover_distress_if_eligible(state, country_id, now)

    def _update_due_economic_profiles(self, state: GameState, now: int) -> None:
        countries = state.tables["countries"]
        boundary = now - (now % 1_440)
        due = countries.filter(pl.col("economic_health_last_update_minute") + 1_440 <= boundary)
        if due.is_empty():
            return

        unconsumed_migration_signals = self._unconsumed_migration_signals(state)
        regions = state.tables.get("regions")
        environment = self._economic_profile_environment(state, now, regions)
        updated_rows: list[dict[str, Any]] = []
        updated_migration_signals: list[dict[str, Any]] = []
        cause_records: list[dict[str, Any]] = []
        source_id = f"daily-economic-profile:{boundary}"

        for row in due.iter_rows(named=True):
            country = row
            country_id = str(country["id"])
            inputs = EconomicProfileInputs(
                country=country,
                boundary=boundary,
                labor_supply=max(
                    0.0,
                    environment.labor_by_country.get(
                        country_id,
                        self._number(country.get("labor_supply")),
                    ),
                ),
                labor_effect=environment.country_effects.get(
                    ("country", country_id.upper(), "labour"),
                    0.0,
                ),
                employment_effect=environment.country_effects.get(
                    ("country", country_id.upper(), "employment"),
                    0.0,
                ),
                resource_shortage=environment.shortage_by_country.get(country_id, 0.0),
                regional_health_effect=environment.health_effect_by_country.get(
                    country_id.upper(),
                    0.0,
                ),
                migration_signal=unconsumed_migration_signals.get(country_id),
                migration_health_penalty=self._bounded(
                    self._terms(state).get("migration_service_health_penalty", 0.08),
                    0.0,
                    0.25,
                ),
            )
            projection = self._profile_calculator.calculate(inputs)
            updated_rows.append(projection.country)
            if projection.consumed_migration_signal is not None:
                updated_migration_signals.append(projection.consumed_migration_signal)
            for cause in projection.cause_changes:
                self._record_cause(
                    state,
                    country_id=country_id,
                    source_type="economic_update",
                    source_id=source_id,
                    indicator=cause.indicator,
                    previous=cause.previous,
                    current=cause.current,
                    unit=cause.unit,
                    now=boundary,
                    reason=cause.reason,
                    records=cause_records,
                )

        self._append_rows(state, "economic_cause_records", cause_records)
        update = pl.DataFrame(updated_rows, schema=countries.schema, strict=False)
        unaffected = countries.join(due.select("id"), on="id", how="anti")
        state.update_table(
            "countries",
            pl.concat([unaffected, update], how="vertical_relaxed").sort("id"),
        )
        self._replace_rows(
            state,
            "migration_signals",
            updated_migration_signals,
            key="country_id",
        )

    def _unconsumed_migration_signals(
        self,
        state: GameState,
    ) -> dict[str, dict[str, Any]]:
        migration_signals = state.tables.get("migration_signals")
        unconsumed: dict[str, dict[str, Any]] = {}
        if migration_signals is not None:
            for signal in migration_signals.to_dicts():
                updated_at = max(0, int(self._number(signal.get("updated_at_minute"))))
                consumed_at = max(
                    0,
                    int(self._number(signal.get("economy_consumed_at_minute"))),
                )
                if updated_at > consumed_at:
                    unconsumed[str(signal.get("country_id", ""))] = signal
        return unconsumed

    def _economic_profile_environment(
        self,
        state: GameState,
        now: int,
        regions: pl.DataFrame | None,
    ) -> EconomicProfileEnvironment:
        return EconomicProfileEnvironment(
            country_effects=aggregate_active_effects(
                state.tables.get("random_event_effects"),
                now,
                categories={"labour", "employment"},
                subject_type="country",
            ),
            health_effect_by_country=self._health_effect_by_country(state, now, regions),
            labor_by_country=self._labor_supply_by_country(regions),
            shortage_by_country=self._resource_shortage_by_country(state),
        )

    def _health_effect_by_country(
        self,
        state: GameState,
        now: int,
        regions: pl.DataFrame | None,
    ) -> dict[str, float]:
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
                health_effect_by_country[owner] = (
                    health_effect_by_country.get(owner, 0.0) + magnitude
                )
        return health_effect_by_country

    def _labor_supply_by_country(
        self,
        regions: pl.DataFrame | None,
    ) -> dict[str, float]:
        if regions is None or not {"owner", "pop_15_64"}.issubset(regions.columns):
            return {}
        return {
            str(row["owner"]): max(0.0, self._number(row["labor_supply"]))
            for row in regions.group_by("owner").agg(
                pl.col("pop_15_64").fill_null(0).sum().alias("labor_supply")
            ).iter_rows(named=True)
        }

    def _resource_shortage_by_country(
        self,
        state: GameState,
    ) -> dict[str, float]:
        ledger = state.tables.get("resource_ledger")
        if ledger is None or not {
            "country_id",
            "balance_usd",
            "consumption_usd",
        }.issubset(ledger.columns):
            return {}
        shortage = ledger.group_by("country_id").agg(
            pl.col("balance_usd").filter(pl.col("balance_usd") < 0).abs().sum().alias("shortage"),
            pl.col("consumption_usd").sum().alias("demand"),
        )
        return {
            str(row["country_id"]): self._bounded(
                self._number(row["shortage"]) / max(1.0, self._number(row["demand"])),
                0.0,
                1.0,
            )
            for row in shortage.iter_rows(named=True)
        }
