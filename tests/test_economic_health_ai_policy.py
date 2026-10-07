import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.ai.economic_policy import EconomicPolicy
from src.core.ai_framework import AITableContext
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionResolveDebtContract,
)
from src.shared.state import GameState


def _context(countries: pl.DataFrame, *, contracts: pl.DataFrame | None = None, player_tag: str = "PLAYER"):
    state = GameState(tables={"countries": countries})
    build_base_schema_registry().ensure_state(state)
    if contracts is not None:
        state.update_table("debt_contracts", contracts)
    return AITableContext(
        tables=state.tables,
        day_ordinal=0,
        total_minutes=1_440,
        date_text="2001-01-02",
        player_tag=player_tag,
        globals={},
    )


def test_ai_policy_selects_effective_dated_interest_action_and_skips_player_country():
    countries = pl.DataFrame({
        "id": ["AI_COUNTRY", "PLAYER"],
        "gdp": [10_000.0, 10_000.0],
        "money_reserves": [5_000.0, 5_000.0],
        "total_annual_revenue": [2_000.0, 2_000.0],
        "total_annual_expense": [1_000.0, 1_000.0],
        "inflation_rate": [0.2, 0.3],
        "interest_rate": [0.1, 0.1],
        "poverty_rate": [0.1, 0.1],
        "unemployment_rate": [0.05, 0.05],
    })
    context = _context(countries)

    decisions = EconomicPolicy().build_candidates(context).collect()
    selected = decisions.filter(pl.col("action_kind") == "change_interest")

    assert selected.get_column("country_id").to_list() == ["AI_COUNTRY"]
    action = EconomicPolicy().resolve_action(selected.row(0, named=True))
    assert isinstance(action, ActionChangeEconomicPolicy)
    assert action.player_id == "ai_system"
    assert action.country_tag == "AI_COUNTRY"
    assert action.target_value > 0.1


def test_ai_requests_bounded_foreign_financing_for_liquidity_shortfall():
    countries = pl.DataFrame({
        "id": ["BORROWER", "CREDITOR", "PLAYER"],
        "gdp": [10_000.0, 100_000.0, 500_000.0],
        "money_reserves": [0.0, 50_000.0, 1_000_000.0],
        "total_annual_revenue": [200.0, 20_000.0, 100_000.0],
        "total_annual_expense": [1_000.0, 10_000.0, 50_000.0],
        "inflation_rate": [0.02, 0.02, 0.02],
        "interest_rate": [0.05, 0.05, 0.05],
        "poverty_rate": [0.1, 0.1, 0.1],
        "unemployment_rate": [0.05, 0.05, 0.05],
    })
    context = _context(countries)

    candidates = EconomicPolicy().build_candidates(context).collect().filter(
        pl.col("action_kind") == "request_debt"
    )

    assert candidates.height == 1
    action = EconomicPolicy().resolve_action(candidates.row(0, named=True))
    assert isinstance(action, ActionRequestDebtContract)
    assert action.debtor_country_id == "BORROWER"
    assert action.creditor_country_id == "CREDITOR"
    assert action.principal <= 10_000.0 * 3.0


def test_ai_approves_only_existing_pending_debt_when_creditor_can_fund_it():
    countries = pl.DataFrame({
        "id": ["BORROWER", "CREDITOR", "PLAYER"],
        "gdp": [10_000.0, 100_000.0, 500_000.0],
        "money_reserves": [0.0, 50_000.0, 1_000_000.0],
        "total_annual_revenue": [200.0, 20_000.0, 100_000.0],
        "total_annual_expense": [1_000.0, 10_000.0, 50_000.0],
        "economic_creditworthiness_modifier": [0.7, 1.0, 1.0],
        "inflation_rate": [0.02, 0.02, 0.02],
        "interest_rate": [0.05, 0.05, 0.05],
        "poverty_rate": [0.1, 0.1, 0.1],
        "unemployment_rate": [0.05, 0.05, 0.05],
    })
    contract_state = GameState()
    build_base_schema_registry().ensure_state(contract_state)
    contract = contract_state.get_table("debt_contracts").clear()
    contract = pl.DataFrame([{
        "id": "loan-1",
        "debtor_country_id": "BORROWER",
        "creditor_country_id": "CREDITOR",
        "principal_original": 5_000.0,
        "status": "pending",
    }], schema=contract.schema, strict=False)
    context = _context(countries, contracts=contract)

    candidates = EconomicPolicy().build_candidates(context).collect().filter(
        pl.col("action_kind") == "approve_debt"
    )

    assert candidates.height == 1
    assert round(candidates.item(0, "utility"), 2) == 1.05
    action = EconomicPolicy().resolve_action(candidates.row(0, named=True))
    assert isinstance(action, ActionResolveDebtContract)
    assert action.contract_id == "loan-1"
    assert action.accept is True
