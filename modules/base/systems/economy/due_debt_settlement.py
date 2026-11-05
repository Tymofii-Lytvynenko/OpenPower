from __future__ import annotations

import calendar
import heapq
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

import polars as pl

from modules.base.systems.economy.economic_health_policy import (
    DebtServiceSettlement,
    DebtServiceSettlementCalculator,
    DebtServiceSettlementInputs,
)
from src.shared.state import GAME_EPOCH, GameState


@dataclass
class DueDebtBatch:
    current_minute: int
    contracts: dict[str, dict[str, Any]]
    country_rows: dict[str, dict[str, Any]]
    balance_columns: tuple[str, ...]
    payment_queue: list[tuple[int, str]]
    affected_countries: set[str]
    country_balances: dict[str, float]
    changed_countries: set[str]
    cause_records: list[dict[str, Any]]


@dataclass(frozen=True)
class DueDebtInstallment:
    contract_id: str
    due_at_minute: int
    debtor_country_id: str
    creditor_country_id: str
    contract: dict[str, Any]
    settlement: DebtServiceSettlement


class DueDebtSettlementEffects(Protocol):
    def record_due_debt_settlement(
        self,
        state: GameState,
        batch: DueDebtBatch,
        installment: DueDebtInstallment,
    ) -> None: ...

    def apply_due_debt_shortfall(
        self,
        state: GameState,
        installment: DueDebtInstallment,
    ) -> None: ...

    def recover_due_debt_distress(
        self,
        state: GameState,
        country_id: str,
        now: int,
    ) -> None: ...


class DueDebtSettlementProcessor(Protocol):
    def process(
        self,
        state: GameState,
        now: int,
        effects: DueDebtSettlementEffects,
    ) -> None: ...


class DeterministicDueDebtSettlementProcessor:
    def __init__(self, calculator: DebtServiceSettlementCalculator) -> None:
        self._calculator = calculator

    def process(
        self,
        state: GameState,
        now: int,
        effects: DueDebtSettlementEffects,
    ) -> None:
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

        batch = self._prepare_batch(state, due, now)
        self._settle_queue(state, batch, effects)
        self._finalize_batch(state, batch, effects)

    def _prepare_batch(
        self,
        state: GameState,
        due: pl.DataFrame,
        now: int,
    ) -> DueDebtBatch:
        due_contracts = {
            str(row["id"]): dict(row)
            for row in due.iter_rows(named=True)
        }
        countries = state.tables.get("countries")
        balance_columns = tuple(
            column
            for column in ("money_reserves", "foreign_debt", "arrears", "annual_debt_service")
            if countries is not None and column in countries.columns
        )
        country_rows = (
            {
                str(row["id"]): dict(row)
                for row in countries.select("id", *balance_columns).iter_rows(named=True)
            }
            if countries is not None and "id" in countries.columns
            else {}
        )
        payment_queue = [
            (int(contract["next_payment_at_minute"]), contract_id)
            for contract_id, contract in due_contracts.items()
        ]
        heapq.heapify(payment_queue)
        return DueDebtBatch(
            current_minute=now,
            contracts=due_contracts,
            country_rows=country_rows,
            balance_columns=balance_columns,
            payment_queue=payment_queue,
            affected_countries=set(),
            country_balances={},
            changed_countries=set(),
            cause_records=[],
        )

    def _settle_queue(
        self,
        state: GameState,
        batch: DueDebtBatch,
        effects: DueDebtSettlementEffects,
    ) -> None:
        # Coarse time steps may cross several due dates, so installments must settle chronologically.
        while batch.payment_queue:
            due_at, contract_id = heapq.heappop(batch.payment_queue)
            contract = batch.contracts[contract_id]
            if (
                due_at > batch.current_minute
                or contract["status"] not in {"current", "arrears", "restructured"}
            ):
                continue
            self._settle_installment(state, batch, contract_id, due_at, effects)

    def _settle_installment(
        self,
        state: GameState,
        batch: DueDebtBatch,
        contract_id: str,
        due_at: int,
        effects: DueDebtSettlementEffects,
    ) -> None:
        contract = batch.contracts[contract_id]
        debtor_id = str(contract["debtor_country_id"])
        creditor_id = str(contract["creditor_country_id"])
        batch.affected_countries.add(debtor_id)
        debtor = batch.country_rows.get(debtor_id)
        available = max(0.0, finite_number((debtor or {}).get("money_reserves")))
        settlement = self._calculator.calculate(
            DebtServiceSettlementInputs(
                contract=contract,
                due_at_minute=due_at,
                available_reserves=available,
            )
        )
        installment = DueDebtInstallment(
            contract_id=contract_id,
            due_at_minute=due_at,
            debtor_country_id=debtor_id,
            creditor_country_id=creditor_id,
            contract=contract,
            settlement=settlement,
        )
        self._apply_balance_updates(batch, installment)
        self._advance_contract(batch, installment)
        batch.country_balances[debtor_id] = finite_number((debtor or {}).get("arrears"))
        effects.record_due_debt_settlement(state, batch, installment)
        if settlement.new_arrears > 1e-9:
            self._flush_country_updates(
                state,
                batch.country_rows,
                batch.changed_countries,
                batch.balance_columns,
            )
            effects.apply_due_debt_shortfall(state, installment)

    def _apply_balance_updates(
        self,
        batch: DueDebtBatch,
        installment: DueDebtInstallment,
    ) -> None:
        settlement = installment.settlement
        debtor = batch.country_rows.get(installment.debtor_country_id)
        if debtor is not None:
            for column, delta in (
                ("money_reserves", -settlement.paid),
                ("foreign_debt", -settlement.principal_paid),
                ("arrears", settlement.new_arrears - settlement.old_arrears),
                ("annual_debt_service", settlement.new_service - settlement.old_service),
            ):
                if column in batch.balance_columns:
                    debtor[column] = finite_number(debtor.get(column)) + delta
            batch.changed_countries.add(installment.debtor_country_id)

        creditor = batch.country_rows.get(installment.creditor_country_id)
        if creditor is not None and "money_reserves" in batch.balance_columns:
            creditor["money_reserves"] = finite_number(creditor.get("money_reserves")) + settlement.paid
            batch.changed_countries.add(installment.creditor_country_id)

    def _advance_contract(
        self,
        batch: DueDebtBatch,
        installment: DueDebtInstallment,
    ) -> None:
        contract = installment.contract
        settlement = installment.settlement
        due_at = installment.due_at_minute
        contract["principal_remaining"] = settlement.new_principal
        contract["arrears_amount"] = settlement.new_arrears
        contract["last_payment_at_minute"] = due_at
        contract["next_payment_at_minute"] = add_months(due_at, settlement.frequency_months)
        contract["status"] = settlement.status
        contract["reason"] = settlement.reason
        next_due = int(contract["next_payment_at_minute"])
        if contract["status"] in {"current", "arrears", "restructured"} and next_due <= batch.current_minute:
            heapq.heappush(batch.payment_queue, (next_due, installment.contract_id))

    def _finalize_batch(
        self,
        state: GameState,
        batch: DueDebtBatch,
        effects: DueDebtSettlementEffects,
    ) -> None:
        replace_rows(state, "debt_contracts", list(batch.contracts.values()))
        self._flush_country_updates(
            state,
            batch.country_rows,
            batch.changed_countries,
            batch.balance_columns,
        )
        append_rows(state, "economic_cause_records", batch.cause_records)
        distress_cases = state.tables.get("debt_distress_cases")
        if distress_cases is not None and not distress_cases.is_empty():
            for country_id in sorted(batch.affected_countries):
                if batch.country_balances.get(country_id, 0.0) <= 1e-9:
                    effects.recover_due_debt_distress(state, country_id, batch.current_minute)

        state.globals["economic_health_last_debt_scan_minute"] = batch.current_minute

    def _flush_country_updates(
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


def finite_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def add_months(minute: int, months: int) -> int:
    current = GAME_EPOCH + timedelta(minutes=max(0, int(minute)))
    month_index = (current.year * 12) + (current.month - 1) + max(1, int(months))
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(current.day, calendar.monthrange(year, month)[1])
    target = current.replace(year=year, month=month, day=day)
    return int((target - GAME_EPOCH).total_seconds() // 60)


def append_rows(state: GameState, table_name: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    frame = state.tables.get(table_name)
    if frame is None:
        return
    additions = pl.DataFrame(records, schema=frame.schema, strict=False)
    state.update_table(table_name, pl.concat([frame, additions], how="vertical_relaxed"))


def replace_rows(
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
