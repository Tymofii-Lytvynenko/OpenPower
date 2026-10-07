import os
from time import perf_counter

import polars as pl
import pytest

from modules.base.schema import build_base_schema_registry
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from src.shared.state import GameState


@pytest.mark.skipif(
    os.environ.get("RUN_ECONOMIC_HEALTH_BENCHMARKS") != "1",
    reason="Set RUN_ECONOMIC_HEALTH_BENCHMARKS=1 to run the controlled debt scale benchmark.",
)
def test_due_only_debt_service_scale_benchmark():
    country_count = 10_000
    contract_count = 100_000
    due_count = 100
    now = 1_440
    country_ids = [f"C{index:05d}" for index in range(country_count)]
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": country_ids,
            "gdp": [1_000_000.0] * country_count,
            "money_reserves": [100_000.0] * country_count,
            "economic_health_last_update_minute": [now] * country_count,
        }),
    })
    build_base_schema_registry().ensure_state(state)
    state.time.total_minutes = now
    contract_ids = [f"L{index:06d}" for index in range(contract_count)]
    debtor_ids = [country_ids[index % country_count] for index in range(contract_count)]
    creditor_ids = [country_ids[(index + 100) % country_count] for index in range(contract_count)]
    next_payment = [now if index < due_count else now + 10_000 for index in range(contract_count)]
    state.update_table("debt_contracts", pl.DataFrame({
        "id": contract_ids,
        "debtor_country_id": debtor_ids,
        "creditor_country_id": creditor_ids,
        "debt_type": ["foreign"] * contract_count,
        "principal_original": [1_000.0] * contract_count,
        "principal_remaining": [1_000.0] * contract_count,
        "annual_interest_rate": [0.05] * contract_count,
        "payment_frequency_months": [1] * contract_count,
        "principal_payment": [10.0] * contract_count,
        "currency_code": ["USD"] * contract_count,
        "conditions": [""] * contract_count,
        "created_at_minute": [0] * contract_count,
        "next_payment_at_minute": next_payment,
        "maturity_at_minute": [100_000] * contract_count,
        "maturity_months": [12] * contract_count,
        "arrears_amount": [0.0] * contract_count,
        "status": ["current"] * contract_count,
        "reason": [""] * contract_count,
        "last_payment_at_minute": [0] * contract_count,
    }))

    started = perf_counter()
    EconomicHealthSystem().update(state, 0.0)
    elapsed = perf_counter() - started

    assert state.get_table("debt_contracts").filter(pl.col("last_payment_at_minute") == now).height == due_count
    print(
        f"economic-health benchmark: {country_count:,} countries, {contract_count:,} contracts, "
        f"{due_count:,} due; {elapsed:.3f}s"
    )
    assert elapsed < 1.0
