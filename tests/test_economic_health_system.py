import math

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from src.shared.actions import (
    ActionRequestDebtContract,
    ActionResolveDebtContract,
)
from src.shared.state import GameState


def _state():
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["A", "B"],
            "money_reserves": [100.0, 1_000.0],
            "gdp": [1_000.0, 5_000.0],
        }),
    })
    build_base_schema_registry().ensure_state(state)
    return state


def _approve_contract(state, system, *, principal=300.0, rate=0.12, installment=50.0, maturity=6):
    state.current_actions = [ActionRequestDebtContract(
        player_id="A",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=principal,
        annual_interest_rate=rate,
        payment_frequency_months=1,
        principal_installment=installment,
        maturity_months=maturity,
        currency_code="USD",
        conditions="test loan",
    )]
    system.update(state, 0.0)
    contract = state.get_table("debt_contracts").row(0, named=True)
    state.current_actions = [ActionResolveDebtContract(
        player_id="B", contract_id=contract["id"], accept=True
    )]
    system.update(state, 0.0)
    return state.get_table("debt_contracts").row(0, named=True)


def test_financing_is_pending_until_creditor_approval_then_transfers_once():
    state = _state()
    system = EconomicHealthSystem()
    request = ActionRequestDebtContract(
        player_id="A",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=300.0,
        annual_interest_rate=0.12,
        payment_frequency_months=1,
        principal_installment=50.0,
        maturity_months=6,
        currency_code="USD",
        conditions="test loan",
    )
    state.current_actions = [request]
    system.update(state, 0.0)

    assert state.get_table("countries").get_column("money_reserves").to_list() == [100.0, 1_000.0]
    pending = state.get_table("debt_contracts").row(0, named=True)
    assert pending["status"] == "pending"

    state.current_actions = [ActionResolveDebtContract(
        player_id="B", contract_id=pending["id"], accept=True
    )]
    system.update(state, 0.0)

    reserves = state.get_table("countries").sort("id").get_column("money_reserves").to_list()
    assert reserves == [400.0, 700.0]
    active = state.get_table("debt_contracts").row(0, named=True)
    assert active["status"] == "current"


def test_due_service_pays_only_available_treasury_and_preserves_shortfall():
    state = _state()
    state.time.total_minutes = 1_440
    state.globals["economic_health_terms"] = {
        "max_interest_rate": 0.5,
        "max_principal_multiple_of_gdp": 10.0,
    }
    system = EconomicHealthSystem()
    state.current_actions = [ActionRequestDebtContract(
        player_id="A",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=300.0,
        annual_interest_rate=0.12,
        payment_frequency_months=1,
        principal_installment=50.0,
        maturity_months=6,
        currency_code="USD",
        conditions="test loan",
    )]
    system.update(state, 0.0)
    contract = state.get_table("debt_contracts").row(0, named=True)
    state.current_actions = [ActionResolveDebtContract(
        player_id="B", contract_id=contract["id"], accept=True
    )]
    system.update(state, 0.0)

    # The system schedules the first payment one game month after approval.
    due_at = state.get_table("debt_contracts").item(0, "next_payment_at_minute")
    state.time.total_minutes = due_at
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "A")
            .then(pl.lit(5.0))
            .otherwise(pl.col("money_reserves"))
            .alias("money_reserves")
        ),
    )
    state.current_actions = []
    system.update(state, 0.0)

    debtor = state.get_table("countries").filter(pl.col("id") == "A").row(0, named=True)
    creditor = state.get_table("countries").filter(pl.col("id") == "B").row(0, named=True)
    contract = state.get_table("debt_contracts").row(0, named=True)
    assert debtor["money_reserves"] == 0.0
    assert creditor["money_reserves"] > 700.0
    assert contract["arrears_amount"] > 0.0
    assert contract["status"] == "arrears"
    assert state.get_table("debt_distress_cases").height == 1


def test_multiple_due_contracts_share_batched_debtor_and_creditor_balances():
    state = _state()
    state.update_table(
        "countries",
        pl.concat(
            [
                state.get_table("countries"),
                pl.DataFrame({"id": ["C"], "money_reserves": [1_000.0], "gdp": [5_000.0]}),
            ],
            how="diagonal_relaxed",
        ),
    )
    system = EconomicHealthSystem()
    state.current_actions = [
        ActionRequestDebtContract("A", "A", creditor, 100.0, 0.12, 1, 20.0, 6)
        for creditor in ("B", "C")
    ]
    system.update(state, 0.0)
    pending = state.get_table("debt_contracts").sort("creditor_country_id")
    state.current_actions = [
        ActionResolveDebtContract(str(row["creditor_country_id"]), str(row["id"]), True)
        for row in pending.iter_rows(named=True)
    ]
    system.update(state, 0.0)
    contracts = state.get_table("debt_contracts")
    due_at = int(contracts.get_column("next_payment_at_minute").min())
    state.time.total_minutes = due_at
    state.current_actions = []

    system.update(state, 0.0)

    countries = {
        row["id"]: row
        for row in state.get_table("countries").select(
            "id", "money_reserves", "foreign_debt", "annual_debt_service"
        ).iter_rows(named=True)
    }
    settled = state.get_table("debt_contracts")
    assert countries["A"]["money_reserves"] == 258.0
    assert countries["A"]["foreign_debt"] == 160.0
    assert math.isclose(countries["A"]["annual_debt_service"], 499.2)
    assert countries["B"]["money_reserves"] == 921.0
    assert countries["C"]["money_reserves"] == 921.0
    assert settled.get_column("last_payment_at_minute").to_list() == [due_at, due_at]
    serviced = [event for event in state.events if getattr(event, "event_type", "") == "serviced"]
    assert len(serviced) == 2


def test_due_service_catches_up_each_overdue_calendar_payment_in_order():
    state = _state()
    system = EconomicHealthSystem()
    state.current_actions = [ActionRequestDebtContract(
        player_id="A",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=300.0,
        annual_interest_rate=0.12,
        payment_frequency_months=1,
        principal_installment=50.0,
        maturity_months=6,
        currency_code="USD",
        conditions="catch-up loan",
    )]
    system.update(state, 0.0)
    contract = state.get_table("debt_contracts").row(0, named=True)
    state.current_actions = [ActionResolveDebtContract(
        player_id="B", contract_id=contract["id"], accept=True
    )]
    system.update(state, 0.0)

    first_due = state.get_table("debt_contracts").item(0, "next_payment_at_minute")
    third_due = system._add_months(first_due, 2)
    state.time.total_minutes = third_due
    state.current_actions = []
    system.update(state, 0.0)

    debtor = state.get_table("countries").filter(pl.col("id") == "A").row(0, named=True)
    creditor = state.get_table("countries").filter(pl.col("id") == "B").row(0, named=True)
    contract = state.get_table("debt_contracts").row(0, named=True)
    payments = [event for event in state.events if getattr(event, "event_type", "") == "serviced"]
    assert debtor["money_reserves"] == 242.5
    assert creditor["money_reserves"] == 857.5
    assert contract["principal_remaining"] == 150.0
    assert contract["last_payment_at_minute"] == third_due
    assert contract["next_payment_at_minute"] > third_due
    assert len(payments) == 3
    assert [event.at_minute for event in payments] == sorted(event.at_minute for event in payments)


def test_duplicate_financing_requests_create_one_pending_contract():
    state = _state()
    system = EconomicHealthSystem()
    request = ActionRequestDebtContract(
        player_id="A",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=100.0,
        annual_interest_rate=0.05,
        payment_frequency_months=1,
        principal_installment=10.0,
        maturity_months=12,
    )
    state.current_actions = [request, request]

    system.update(state, 0.0)

    contracts = state.get_table("debt_contracts")
    assert contracts.height == 1
    assert contracts.item(0, "status") == "pending"
    assert state.get_table("countries").get_column("money_reserves").to_list() == [100.0, 1_000.0]


def test_only_authorized_creditor_can_approve_and_repeated_approval_cannot_transfer_twice():
    state = _state()
    system = EconomicHealthSystem()
    state.current_actions = [ActionRequestDebtContract(
        player_id="A", debtor_country_id="A", creditor_country_id="B", principal=100.0,
        annual_interest_rate=0.05, payment_frequency_months=1, principal_installment=10.0,
        maturity_months=12,
    )]
    system.update(state, 0.0)
    contract_id = state.get_table("debt_contracts").item(0, "id")

    state.current_actions = [ActionResolveDebtContract(player_id="A", contract_id=contract_id, accept=True)]
    system.update(state, 0.0)
    assert state.get_table("debt_contracts").item(0, "status") == "pending"
    assert state.get_table("countries").get_column("money_reserves").to_list() == [100.0, 1_000.0]

    state.current_actions = [ActionResolveDebtContract(player_id="B", contract_id=contract_id, accept=True)]
    system.update(state, 0.0)
    state.current_actions = [ActionResolveDebtContract(player_id="B", contract_id=contract_id, accept=True)]
    system.update(state, 0.0)

    assert state.get_table("debt_contracts").item(0, "status") == "current"
    assert state.get_table("countries").get_column("money_reserves").to_list() == [200.0, 900.0]


def test_creditor_capacity_shortfall_rejects_approval_without_partial_transfer():
    state = _state()
    system = EconomicHealthSystem()
    state.current_actions = [ActionRequestDebtContract(
        player_id="A", debtor_country_id="A", creditor_country_id="B", principal=900.0,
        annual_interest_rate=0.05, payment_frequency_months=1, principal_installment=75.0,
        maturity_months=12,
    )]
    system.update(state, 0.0)
    contract_id = state.get_table("debt_contracts").item(0, "id")
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "B").then(pl.lit(899.0)).otherwise(pl.col("money_reserves")).alias("money_reserves")
    ))
    state.current_actions = [ActionResolveDebtContract(player_id="B", contract_id=contract_id, accept=True)]

    system.update(state, 0.0)

    assert state.get_table("debt_contracts").item(0, "status") == "rejected"
    assert state.get_table("countries").get_column("money_reserves").to_list() == [100.0, 899.0]


def test_non_due_contracts_are_not_serviced_or_rewritten():
    state = _state()
    system = EconomicHealthSystem()
    contract = _approve_contract(state, system)
    state.time.total_minutes = int(contract["next_payment_at_minute"]) - 1
    state.current_actions = []

    system.update(state, 0.0)

    current = state.get_table("debt_contracts").row(0, named=True)
    assert current["principal_remaining"] == 300.0
    assert current["last_payment_at_minute"] == 0
    assert current["status"] == "current"
    assert state.get_table("countries").get_column("money_reserves").to_list() == [400.0, 700.0]


def test_maturity_payment_settles_remaining_principal_and_closes_service():
    state = _state()
    system = EconomicHealthSystem()
    contract = _approve_contract(state, system, principal=100.0, rate=0.0, installment=50.0, maturity=2)
    state.time.total_minutes = int(contract["maturity_at_minute"])
    state.current_actions = []

    system.update(state, 0.0)

    contract = state.get_table("debt_contracts").row(0, named=True)
    debtor = state.get_table("countries").filter(pl.col("id") == "A").row(0, named=True)
    creditor = state.get_table("countries").filter(pl.col("id") == "B").row(0, named=True)
    assert contract["status"] == "paid"
    assert contract["principal_remaining"] == 0.0
    assert contract["arrears_amount"] == 0.0
    assert debtor["foreign_debt"] == 0.0
    assert debtor["annual_debt_service"] == 0.0
    assert debtor["money_reserves"] == 100.0
    assert creditor["money_reserves"] == 1_000.0


def test_restructuring_changes_future_terms_without_forgiving_arrears_or_principal():
    from src.shared.actions import ActionRequestDebtRestructuring

    state = _state()
    system = EconomicHealthSystem()
    contract = _approve_contract(state, system)
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "A").then(pl.lit(0.0)).otherwise(pl.col("money_reserves")).alias("money_reserves")
    ))
    first_due = int(contract["next_payment_at_minute"])
    state.time.total_minutes = first_due
    state.current_actions = []
    system.update(state, 0.0)
    before = state.get_table("debt_contracts").row(0, named=True)

    request = ActionRequestDebtRestructuring(
        player_id="A",
        country_tag="A",
        contract_id=str(contract["id"]),
        annual_interest_rate=0.08,
        payment_frequency_months=2,
        principal_installment=25.0,
        maturity_months=12,
    )
    state.time.total_minutes = first_due + 1
    state.current_actions = [request]
    system.update(state, 0.0)
    restructured = state.get_table("debt_contracts").row(0, named=True)
    assert restructured["status"] == "restructured"
    assert restructured["principal_remaining"] == before["principal_remaining"]
    assert restructured["arrears_amount"] == before["arrears_amount"]
    assert restructured["annual_interest_rate"] == 0.08

    state.current_actions = [request]
    system.update(state, 0.0)
    after_duplicate = state.get_table("debt_contracts").row(0, named=True)
    assert after_duplicate["principal_remaining"] == restructured["principal_remaining"]
    assert after_duplicate["arrears_amount"] == restructured["arrears_amount"]
    assert after_duplicate["maturity_months"] == 12


def test_default_restrictions_are_removed_only_after_arrears_are_paid():
    state = _state()
    state.globals["economic_health_terms"] = {
        "default_arrears_minimum": 1.0,
        "default_arrears_gdp_ratio": 0.1,
    }
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "A").then(pl.lit(100.0)).otherwise(pl.col("gdp")).alias("gdp")
    ))
    system = EconomicHealthSystem()
    contract = _approve_contract(state, system, principal=100.0, rate=0.12, installment=50.0, maturity=6)
    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "A").then(pl.lit(0.0)).otherwise(pl.col("money_reserves")).alias("money_reserves")
    ))
    first_due = int(contract["next_payment_at_minute"])
    state.time.total_minutes = first_due
    state.current_actions = []
    system.update(state, 0.0)

    country = state.get_table("countries").filter(pl.col("id") == "A").row(0, named=True)
    case = state.get_table("debt_distress_cases").row(0, named=True)
    assert case["status"] == "default"
    assert country["economic_production_modifier"] == 0.75
    assert country["economic_health_modifier"] == 0.9
    assert country["economic_political_modifier"] == 0.75
    assert country["economic_creditworthiness_modifier"] == 0.7
    assert any(event.event_type == "default" for event in state.events if hasattr(event, "event_type"))
    defaulted_principal = state.get_table("debt_contracts").item(0, "principal_remaining")

    state.update_table("countries", state.get_table("countries").with_columns(
        pl.when(pl.col("id") == "A").then(pl.lit(500.0)).otherwise(pl.col("money_reserves")).alias("money_reserves")
    ))
    next_due = state.get_table("debt_contracts").item(0, "next_payment_at_minute")
    state.time.total_minutes = next_due
    system.update(state, 0.0)

    country = state.get_table("countries").filter(pl.col("id") == "A").row(0, named=True)
    contract = state.get_table("debt_contracts").row(0, named=True)
    case = state.get_table("debt_distress_cases").row(0, named=True)
    assert case["status"] == "closed"
    assert country["debt_distress_status"] == "current"
    assert country["economic_production_modifier"] == 1.0
    assert country["economic_trade_modifier"] == 1.0
    assert country["economic_policy_modifier"] == 1.0
    assert country["economic_health_modifier"] == 1.0
    assert country["economic_political_modifier"] == 1.0
    assert country["economic_creditworthiness_modifier"] == 1.0
    assert country["arrears"] == 0.0
    assert contract["principal_remaining"] < defaulted_principal
    assert contract["principal_remaining"] > 0.0
    assert any(event.event_type == "recovered" for event in state.events if hasattr(event, "event_type"))


def test_unauthorized_or_invalid_financing_request_changes_no_reserves():
    state = _state()
    system = EconomicHealthSystem()
    state.current_actions = [ActionRequestDebtContract(
        player_id="B",
        debtor_country_id="A",
        creditor_country_id="B",
        principal=100.0,
        annual_interest_rate=0.1,
        payment_frequency_months=1,
        principal_installment=10.0,
        maturity_months=12,
        currency_code="USD",
        conditions="unauthorized debtor",
    )]
    system.update(state, 0.0)

    assert state.get_table("debt_contracts").is_empty()
    assert state.get_table("countries").get_column("money_reserves").to_list() == [100.0, 1_000.0]
