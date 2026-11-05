from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import polars as pl

from modules.base.systems.economy.economic_health_policy import (
    DebtContractRequestInputs,
    DebtContractRequestPlan,
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
from modules.base.systems.economy.economic_profile_environment import (
    DeterministicEconomicProfileEnvironmentCalculator,
    EconomicProfileEnvironmentCalculator,
    EconomicProfileEnvironmentInputs,
)
from modules.base.systems.economy.economic_health_action_dispatcher import (
    DeterministicEconomicHealthActionDispatcher,
    EconomicHealthActionDispatcher,
)
from modules.base.systems.economy.economic_country_value_updater import (
    AddCountryValue,
    CountryValueChange,
    DeterministicEconomicCountryValueUpdater,
    EconomicCountryValueUpdater,
    SetCountryValue,
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
    DeterministicEconomicPolicyApplicationPlanner,
    DeterministicEconomicPolicyTransitionPlanner,
    EconomicPolicyApplicationInputs,
    EconomicPolicyApplicationPlanner,
    EconomicPolicyTransitionPlan,
    EconomicPolicyTransitionInputs,
    EconomicPolicyTransitionPlanner,
)
from modules.base.systems.economy.economic_health_records import (
    EconomicCauseRecordRequest,
    EconomicRejectionRequest,
    EconomicTransitionEventRequest,
)
from modules.base.systems.world.authority_policy import player_controls_country
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
    ActionSetTax,
)
from src.shared.events import EventRealSecond
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


@dataclass(frozen=True)
class _ValidatedEconomicPolicyChange:
    country_id: str
    source_id: str
    player_id: str
    country: Mapping[str, Any]
    terms: Mapping[str, Any]
    policy_name: str
    previous_value: float
    target_value: float

    def rejection_request(self, reason: str, at_minute: int) -> EconomicRejectionRequest:
        return EconomicRejectionRequest(
            country_id=self.country_id,
            source_id=self.source_id,
            indicator=self.policy_name,
            value=self.previous_value,
            reason=reason,
            at_minute=at_minute,
        )


@dataclass(frozen=True)
class _DebtContractResolutionContext:
    contract: dict[str, Any]
    debtor_id: str
    creditor_id: str
    creditor: dict[str, Any] | None
    debtor: dict[str, Any] | None
    principal: float


@dataclass(frozen=True)
class _PlannedDebtContractRequest:
    debtor_id: str
    plan: DebtContractRequestPlan
    at_minute: int


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
        policy_application_planner: EconomicPolicyApplicationPlanner | None = None,
        profile_environment_calculator: EconomicProfileEnvironmentCalculator | None = None,
        action_dispatcher: EconomicHealthActionDispatcher | None = None,
        country_value_updater: EconomicCountryValueUpdater | None = None,
    ) -> None:
        self._profile_calculator = _resolve_component(
            profile_calculator,
            DeterministicEconomicProfileCalculator,
        )
        self._profile_environment_calculator = _resolve_component(
            profile_environment_calculator,
            DeterministicEconomicProfileEnvironmentCalculator,
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
        self._policy_application_planner = _resolve_component(
            policy_application_planner,
            DeterministicEconomicPolicyApplicationPlanner,
        )
        self._action_dispatcher = _resolve_component(
            action_dispatcher,
            DeterministicEconomicHealthActionDispatcher,
        )
        self._country_value_updater = _resolve_component(
            country_value_updater,
            DeterministicEconomicCountryValueUpdater,
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
            self._action_dispatcher.dispatch(state, action, now, self)

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

    def _country_values(
        self,
        state: GameState,
        country_id: str,
        changes: Mapping[str, CountryValueChange],
    ) -> None:
        frame = state.tables.get("countries")
        if frame is None or frame.is_empty():
            return
        updated = self._country_value_updater.apply(frame, country_id, changes)
        if updated is not None:
            state.update_table("countries", updated)

    def _transition_event(self, state: GameState, request: EconomicTransitionEventRequest) -> None:
        state.events.append(request.to_event())

    def _record_cause(
        self,
        state: GameState,
        request: EconomicCauseRecordRequest,
        records: list[dict[str, Any]] | None = None,
    ) -> None:
        record = request.to_record()
        if record is None:
            return
        if records is None:
            self._append_rows(state, "economic_cause_records", [record])
        else:
            records.append(record)

    def _reject(self, state: GameState, request: EconomicRejectionRequest) -> None:
        self._transition_event(state, request.to_event_request())

    def _request_policy_change(self, state: GameState, action: ActionChangeEconomicPolicy, now: int) -> None:
        request = self._validate_policy_change_request(state, action, now)
        if request is None:
            return

        plan = self._plan_policy_transition_request(state, request, now)
        if plan is None:
            return

        self._persist_policy_transition_request(state, request, plan, now)

    def _validate_policy_change_request(
        self,
        state: GameState,
        action: ActionChangeEconomicPolicy,
        now: int,
    ) -> _ValidatedEconomicPolicyChange | None:
        country_id = str(action.country_tag)
        country = self._country(state, country_id)
        source_id = f"policy-request:{country_id}:{action.policy_name}:{now}"
        if country is None or not player_controls_country(state, action.player_id, country_id):
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id=country_id,
                    source_id=source_id,
                    indicator=action.policy_name,
                    value=0.0,
                    reason="Actor is not authorized for this country.",
                    at_minute=now,
                ),
            )
            return None

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
                EconomicRejectionRequest(
                    country_id=country_id,
                    source_id=source_id,
                    indicator=validation.rejection_indicator,
                    value=validation.rejection_value,
                    reason=validation.rejection_reason,
                    at_minute=now,
                ),
            )
            return None

        return _ValidatedEconomicPolicyChange(
            country_id=country_id,
            source_id=source_id,
            player_id=str(action.player_id),
            country=country,
            terms=terms,
            policy_name=validation.policy_name,
            previous_value=validation.previous_value,
            target_value=validation.target_value,
        )

    def _plan_policy_transition_request(
        self,
        state: GameState,
        request: _ValidatedEconomicPolicyChange,
        now: int,
    ) -> EconomicPolicyTransitionPlan | None:
        transitions = state.tables["economic_policy_transitions"]
        cooldown_active = not transitions.filter(
            (pl.col("country_id") == request.country_id)
            & (pl.col("policy_name") == request.policy_name)
            & (pl.col("status").is_in(["scheduled", "applied"]))
            & (pl.col("cooldown_until_minute") > now)
        ).is_empty()
        configured_cost = request.terms.get(
            f"{request.policy_name}_transition_cost",
            request.terms.get("policy_transition_cost", 0.0),
        )
        draft = self._policy_transition_planner.prepare(
            EconomicPolicyTransitionInputs(
                transition_id=request.source_id,
                country_id=request.country_id,
                player_id=request.player_id,
                policy_name=request.policy_name,
                previous_value=request.previous_value,
                target_value=request.target_value,
                current_reserves=self._number(request.country.get("money_reserves")),
                transition_cost_setting=configured_cost,
                delay_minutes_setting=request.terms.get("policy_delay_minutes"),
                cooldown_minutes_setting=request.terms.get("policy_cooldown_minutes"),
                cooldown_active=cooldown_active,
                now=now,
            )
        )
        if draft.rejection_reason is not None:
            self._reject(state, request.rejection_request(draft.rejection_reason, now))
            return None

        plan = self._policy_transition_planner.finalize(
            draft,
            transition_id_exists=not transitions.filter(
                pl.col("id") == request.source_id
            ).is_empty(),
        )
        if plan.rejection_reason is not None:
            self._reject(state, request.rejection_request(plan.rejection_reason, now))
            return None

        return plan

    def _persist_policy_transition_request(
        self,
        state: GameState,
        request: _ValidatedEconomicPolicyChange,
        plan: EconomicPolicyTransitionPlan,
        now: int,
    ) -> None:
        assert plan.row is not None
        row = plan.row
        transition_cost = plan.transition_cost
        if transition_cost > 0.0:
            self._country_values(
                state,
                request.country_id,
                {"money_reserves": AddCountryValue(-transition_cost)},
            )
            self._record_cause(
                state,
                EconomicCauseRecordRequest(
                    country_id=request.country_id,
                    source_type="policy_transition",
                    source_id=request.source_id,
                    indicator="money_reserves",
                    previous_value=self._number(request.country.get("money_reserves")),
                    new_value=self._number(request.country.get("money_reserves")) - transition_cost,
                    unit="currency",
                    game_minute=now,
                    reason=row["reason"],
                ),
            )
        self._append_rows(state, "economic_policy_transitions", [row])
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="scheduled",
                country_id=request.country_id,
                source_id=request.source_id,
                indicator=request.policy_name,
                previous_value=request.previous_value,
                new_value=request.target_value,
                reason=row["reason"],
                at_minute=now,
            ),
        )

    def _apply_due_policy_changes(self, state: GameState, now: int) -> None:
        transitions = state.tables.get("economic_policy_transitions")
        if transitions is None or transitions.is_empty():
            return
        due = transitions.filter((pl.col("status") == "scheduled") & (pl.col("effective_at_minute") <= now)).sort(["effective_at_minute", "id"])
        if due.is_empty():
            return
        supported_policies = frozenset({
            "minimum_wage",
            "interest_rate",
            "personal_income_tax_rate",
            *self.SPENDING_POLICIES,
        })
        applied = [
            self._apply_due_policy_transition(state, transition, now, supported_policies)
            for transition in due.iter_rows(named=True)
        ]
        self._replace_rows(state, "economic_policy_transitions", applied)

    def _apply_due_policy_transition(
        self,
        state: GameState,
        transition: dict[str, Any],
        now: int,
        supported_policies: frozenset[str],
    ) -> dict[str, Any]:
        country_id = str(transition["country_id"])
        policy = str(transition["policy_name"])
        current_country = self._country(state, country_id)
        application = self._policy_application_planner.plan(
            EconomicPolicyApplicationInputs(
                country_exists=current_country is not None,
                policy_name=policy,
                supported_policies=supported_policies,
            )
        )
        if not application.should_apply:
            transition["status"] = "rejected"
            transition["reason"] = application.reason
            return transition

        assert current_country is not None
        old = self._number(current_country.get(policy))
        target = self._number(transition.get("target_value"))
        self._country_values(state, country_id, {policy: SetCountryValue(target)})
        transition["status"] = "applied"
        transition["reason"] = application.reason
        source_id = str(transition["id"])
        self._record_cause(
            state,
            EconomicCauseRecordRequest(
                country_id=country_id,
                source_type="policy",
                source_id=source_id,
                indicator=policy,
                previous_value=old,
                new_value=target,
                unit="policy units",
                game_minute=now,
                reason=transition["reason"],
            ),
        )
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="applied",
                country_id=country_id,
                source_id=source_id,
                indicator=policy,
                previous_value=old,
                new_value=target,
                reason=transition["reason"],
                at_minute=now,
            ),
        )
        return transition

    def _request_debt_contract(self, state: GameState, action: ActionRequestDebtContract, now: int) -> None:
        request = self._plan_debt_contract_request(state, action, now)
        if request is None:
            return

        self._persist_debt_contract_request(state, request)

    def _plan_debt_contract_request(
        self,
        state: GameState,
        action: ActionRequestDebtContract,
        now: int,
    ) -> _PlannedDebtContractRequest | None:
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
                EconomicRejectionRequest(
                    country_id=debtor_id,
                    source_id=plan.contract_id,
                    indicator="foreign_debt",
                    value=plan.rejection_amount,
                    reason=plan.rejection_reason,
                    at_minute=now,
                ),
            )
            return None

        return _PlannedDebtContractRequest(
            debtor_id=debtor_id,
            plan=plan,
            at_minute=now,
        )

    def _persist_debt_contract_request(
        self,
        state: GameState,
        request: _PlannedDebtContractRequest,
    ) -> None:
        debtor_id = request.debtor_id
        plan = request.plan
        contracts = state.tables["debt_contracts"]
        if not contracts.filter(pl.col("id") == plan.contract_id).is_empty():
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id=debtor_id,
                    source_id=plan.contract_id,
                    indicator="foreign_debt",
                    value=plan.principal,
                    reason="Duplicate deterministic financing request.",
                    at_minute=request.at_minute,
                ),
            )
            return
        assert plan.contract_row is not None
        self._append_rows(state, "debt_contracts", [plan.contract_row])
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="requested",
                country_id=debtor_id,
                source_id=plan.contract_id,
                indicator="foreign_debt",
                previous_value=0.0,
                new_value=plan.principal,
                reason="Financing request awaits creditor approval.",
                at_minute=request.at_minute,
            ),
        )

    def _transfer_debt_principal(
        self,
        state: GameState,
        debtor_id: str,
        creditor_id: str,
        principal: float,
    ) -> None:
        self._country_values(
            state,
            debtor_id,
            {
                "money_reserves": AddCountryValue(principal),
                "foreign_debt": AddCountryValue(principal),
            },
        )
        self._country_values(
            state,
            creditor_id,
            {"money_reserves": AddCountryValue(-principal)},
        )

    def _prepare_debt_contract_resolution(
        self,
        state: GameState,
        action: ActionResolveDebtContract,
        now: int,
    ) -> _DebtContractResolutionContext | None:
        contracts = state.tables["debt_contracts"]
        match = contracts.filter((pl.col("id") == str(action.contract_id)) & (pl.col("status") == "pending"))
        if match.is_empty():
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id="",
                    source_id=str(action.contract_id),
                    indicator="foreign_debt",
                    value=0.0,
                    reason="Pending contract does not exist.",
                    at_minute=now,
                ),
            )
            return None
        contract = match.row(0, named=True)
        debtor_id = str(contract["debtor_country_id"])
        creditor_id = str(contract["creditor_country_id"])
        creditor = self._country(state, creditor_id)
        debtor = self._country(state, debtor_id)
        principal = self._number(contract.get("principal_original"))
        if not player_controls_country(state, action.player_id, creditor_id):
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id=debtor_id,
                    source_id=str(contract["id"]),
                    indicator="foreign_debt",
                    value=principal,
                    reason="Actor is not authorized for the creditor country.",
                    at_minute=now,
                ),
            )
            return None

        return _DebtContractResolutionContext(
            contract=contract,
            debtor_id=debtor_id,
            creditor_id=creditor_id,
            creditor=creditor,
            debtor=debtor,
            principal=principal,
        )

    def _resolve_debt_contract(self, state: GameState, action: ActionResolveDebtContract, now: int) -> None:
        resolution = self._prepare_debt_contract_resolution(state, action, now)
        if resolution is None:
            return

        creditor = resolution.creditor
        debtor = resolution.debtor
        principal = resolution.principal
        if not action.accept:
            self._reject_resolved_debt_contract(
                state,
                resolution,
                "Creditor rejected the financing request; no funds moved.",
                now,
            )
            return
        if (
            creditor is None
            or debtor is None
            or self._number(creditor.get("money_reserves")) < principal
        ):
            self._reject_resolved_debt_contract(
                state,
                resolution,
                "Creditor no longer has sufficient reserves; the pending request was closed without a transfer.",
                now,
            )
            return

        self._approve_resolved_debt_contract(state, resolution, now)

    def _reject_resolved_debt_contract(
        self,
        state: GameState,
        resolution: _DebtContractResolutionContext,
        reason: str,
        now: int,
    ) -> None:
        contract = resolution.contract
        contract["status"] = "rejected"
        contract["reason"] = reason
        self._replace_rows(state, "debt_contracts", [contract])
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="rejected",
                country_id=resolution.debtor_id,
                source_id=str(contract["id"]),
                indicator="foreign_debt",
                previous_value=resolution.principal,
                new_value=0.0,
                reason=reason,
                at_minute=now,
            ),
        )

    def _approve_resolved_debt_contract(
        self,
        state: GameState,
        resolution: _DebtContractResolutionContext,
        now: int,
    ) -> None:
        contract = resolution.contract
        debtor_id = resolution.debtor_id
        debtor = resolution.debtor
        assert debtor is not None
        principal = resolution.principal
        frequency = int(contract["payment_frequency_months"])
        maturity_months = max(frequency, int(contract.get("maturity_months") or frequency))
        self._transfer_debt_principal(state, debtor_id, resolution.creditor_id, principal)
        contract["status"] = "current"
        contract["created_at_minute"] = now
        contract["next_payment_at_minute"] = self._add_months(now, frequency)
        contract["maturity_at_minute"] = self._add_months(now, maturity_months)
        contract["reason"] = "Creditor approved; principal was transferred once from creditor reserves."
        self._replace_rows(state, "debt_contracts", [contract])
        self._adjust_annual_service(state, debtor_id, 0.0, self._annualized_service(contract))
        self._record_cause(
            state,
            EconomicCauseRecordRequest(
                country_id=debtor_id,
                source_type="debt",
                source_id=str(contract["id"]),
                indicator="foreign_debt",
                previous_value=self._number(debtor.get("foreign_debt")),
                new_value=self._number(debtor.get("foreign_debt")) + principal,
                unit="currency",
                game_minute=now,
                reason=contract["reason"],
            ),
        )
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="approved",
                country_id=debtor_id,
                source_id=str(contract["id"]),
                indicator="foreign_debt",
                previous_value=0.0,
                new_value=principal,
                reason=contract["reason"],
                at_minute=now,
            ),
        )

    def _request_restructuring(self, state: GameState, action: ActionRequestDebtRestructuring, now: int) -> None:
        contracts = state.tables["debt_contracts"]
        match = contracts.filter(pl.col("id") == str(action.contract_id))
        if match.is_empty():
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id=str(action.country_tag),
                    source_id=str(action.contract_id),
                    indicator="debt_restructuring",
                    value=0.0,
                    reason="Debt contract does not exist.",
                    at_minute=now,
                ),
            )
            return
        contract = match.row(0, named=True)
        debtor_id = str(contract["debtor_country_id"])
        if str(action.country_tag) != debtor_id or not player_controls_country(state, action.player_id, debtor_id):
            self._reject(
                state,
                EconomicRejectionRequest(
                    country_id=debtor_id,
                    source_id=str(contract["id"]),
                    indicator="debt_restructuring",
                    value=self._number(contract.get("arrears_amount")),
                    reason="Actor is not authorized for this debtor.",
                    at_minute=now,
                ),
            )
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
                EconomicRejectionRequest(
                    country_id=debtor_id,
                    source_id=str(contract["id"]),
                    indicator="debt_restructuring",
                    value=0.0,
                    reason=plan.rejection_reason,
                    at_minute=now,
                ),
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
            EconomicTransitionEventRequest(
                event_type="restructured",
                country_id=debtor_id,
                source_id=str(restructured_contract["id"]),
                indicator="foreign_debt",
                previous_value=plan.old_service,
                new_value=plan.new_service,
                reason=restructured_contract["reason"],
                at_minute=now,
            ),
        )

    def _add_months(self, minute: int, months: int) -> int:
        return add_months(minute, months)

    def _annualized_service(self, contract: dict[str, Any]) -> float:
        return calculate_annualized_debt_service(contract)

    def _adjust_annual_service(self, state: GameState, debtor_id: str, old: float, new: float) -> None:
        self._country_values(
            state,
            debtor_id,
            {"annual_debt_service": AddCountryValue(new - old)},
        )

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
            EconomicCauseRecordRequest(
                country_id=debtor_id,
                source_type="debt_service",
                source_id=f"{contract['id']}:{due_at}",
                indicator="foreign_debt",
                previous_value=settlement.principal,
                new_value=settlement.new_principal,
                unit="currency",
                game_minute=due_at,
                reason=contract["reason"],
            ),
            records=batch.cause_records,
        )
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="serviced",
                country_id=debtor_id,
                source_id=str(contract["id"]),
                indicator="debt_service",
                previous_value=settlement.total_due,
                new_value=settlement.paid,
                reason=contract["reason"],
                at_minute=due_at,
            ),
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
            "debt_distress_status": SetCountryValue(plan.status),
            "economic_production_modifier": SetCountryValue(plan.modifiers["production"]),
            "economic_trade_modifier": SetCountryValue(plan.modifiers["trade"]),
            "economic_policy_modifier": SetCountryValue(plan.modifiers["policy"]),
            "economic_health_modifier": SetCountryValue(plan.modifiers["health"]),
            "economic_political_modifier": SetCountryValue(plan.modifiers["politics"]),
            "economic_creditworthiness_modifier": SetCountryValue(plan.modifiers["creditworthiness"]),
        })
        if plan.previous_status != plan.status:
            self._transition_event(
                state,
                EconomicTransitionEventRequest(
                    event_type=plan.status,
                    country_id=country_id,
                    source_id=plan.case_id,
                    indicator="arrears",
                    previous_value=0.0,
                    new_value=plan.total_arrears,
                    reason=request.reason,
                    at_minute=request.now,
                ),
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
            "debt_distress_status": SetCountryValue("current"),
            "economic_production_modifier": SetCountryValue(1.0),
            "economic_trade_modifier": SetCountryValue(1.0),
            "economic_policy_modifier": SetCountryValue(1.0),
            "economic_health_modifier": SetCountryValue(1.0),
            "economic_political_modifier": SetCountryValue(1.0),
            "economic_creditworthiness_modifier": SetCountryValue(1.0),
        })
        self._transition_event(
            state,
            EconomicTransitionEventRequest(
                event_type="recovered",
                country_id=country_id,
                source_id=str(case["id"]),
                indicator="arrears",
                previous_value=self._number(case.get("arrears_at_entry")),
                new_value=0.0,
                reason=case["reason"],
                at_minute=now,
            ),
        )

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
                    EconomicCauseRecordRequest(
                        country_id=country_id,
                        source_type="economic_update",
                        source_id=source_id,
                        indicator=cause.indicator,
                        previous_value=cause.previous,
                        new_value=cause.current,
                        unit=cause.unit,
                        game_minute=boundary,
                        reason=cause.reason,
                    ),
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
        return self._profile_environment_calculator.calculate(
            EconomicProfileEnvironmentInputs(
                now=now,
                random_event_effects=state.tables.get("random_event_effects"),
                regions=regions,
                resource_ledger=state.tables.get("resource_ledger"),
            )
        )
