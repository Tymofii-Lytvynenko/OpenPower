import polars as pl
import pytest

from modules.base.schema import build_base_schema_registry
from src.client.ui.panels.economy_presenter import EconomyPresenter
from src.shared.state import GameState


def test_presenter_exposes_thresholds_obligations_causes_and_read_only_values():
    state = GameState(tables={
        "countries": pl.DataFrame({
            "id": ["A"],
            "economic_health": [0.6],
            "minimum_wage": [100.0],
            "interest_rate": [0.08],
            "inflation_rate": [0.12],
            "unemployment_rate": [0.2],
            "poverty_rate": [0.3],
            "money_reserves": [-25.0],
            "total_annual_revenue": [80.0],
            "total_annual_expense": [100.0],
            "foreign_debt": [500.0],
            "arrears": [20.0],
            "debt_distress_status": ["arrears"],
        }),
    })
    build_base_schema_registry().ensure_state(state)
    state.update_table("debt_contracts", pl.DataFrame({
        "id": ["loan-1"],
        "debtor_country_id": ["A"],
        "creditor_country_id": ["B"],
        "principal_remaining": [500.0],
        "annual_interest_rate": [0.08],
        "next_payment_at_minute": [2_000],
        "maturity_at_minute": [8_000],
        "arrears_amount": [20.0],
        "status": ["arrears"],
        "conditions": ["No new borrowing"],
    }))
    state.update_table("economic_cause_records", pl.DataFrame({
        "id": ["cause-a", "cause-b"],
        "country_id": ["A", "A"],
        "indicator": ["inflation_rate", "poverty_rate"],
        "delta": [0.02, -0.1],
        "game_minute": [1_000, 1_200],
        "reason": ["Rising costs", "Real income pressure"],
    }))
    state.globals["economic_health_terms"] = {"inflation_warning_rate": 0.1}

    view = EconomyPresenter().present(state, "A")

    assert view is not None
    assert view.fiscal_balance == -20.0
    assert view.domestic_debt == 25.0
    assert view.obligations[0].creditor_country_id == "B"
    assert view.top_causes[0].indicator == "poverty_rate"
    assert dict(view.risk_thresholds)["inflation_warning"] == 0.1
    assert view.nominal_income_index == 1.0
    assert view.employment_rate == 0.95
    assert view.migration_pressure == 0.0
    inflation_trend = next(item for item in view.indicator_trends if item.indicator == "inflation_rate")
    assert inflation_trend.direction == "rising"
    assert inflation_trend.delta == 0.02
    with pytest.raises(AttributeError):
        view.inflation_rate = 0.0
