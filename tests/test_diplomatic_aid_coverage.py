from __future__ import annotations

import polars as pl

from modules.base.systems.economy.diplomatic_aid_system import DiplomaticAidSystem
from src.shared.events import EventRealSecond
from src.shared.state import GameState


def test_missing_treaty_effects_clear_prior_transfer_rows():
    state = GameState(tables={"countries": pl.DataFrame({"id": ["USA"]})})
    state.events = [EventRealSecond(60, False)]

    DiplomaticAidSystem().update(state, 1.0)

    assert state.get_table("diplomatic_aid_transfers").is_empty()


def test_transfer_planning_skips_invalid_recipients_and_unfundable_requests():
    system = DiplomaticAidSystem()
    countries = {
        "USA": {"total_annual_expense": 1_000.0, "trade_expense": 0.0, "gdp": 100.0},
        "CAN": {"total_annual_expense": 1_000.0, "trade_expense": 100.0, "gdp": 20.0},
    }
    aid_rows = [
        {"country_id": "MEX", "detail": '["USA"]', "value": 0.1},
        {"country_id": "CAN", "detail": "{", "value": 0.1},
        {"country_id": "CAN", "detail": "{}", "value": 0.1},
        {"country_id": "USA", "detail": '["CAN"]', "value": 0.1},
        {"country_id": "CAN", "detail": '["USA"]', "value": 0.0},
        {"country_id": "CAN", "detail": '["USA"]', "value": "invalid"},
    ]

    assert system._plan_transfers(aid_rows, countries) == []


def test_tiny_weighted_share_underflow_does_not_create_a_zero_transfer():
    system = DiplomaticAidSystem()
    countries = {
        "A_TINY": {"total_annual_expense": 1_000.0, "trade_expense": 0.0, "gdp": 1.0},
        "Z_BIG": {"total_annual_expense": 1_000.0, "trade_expense": 0.0, "gdp": 1e308},
        "CAN": {"total_annual_expense": 1_000.0, "trade_expense": 1.0, "gdp": 1.0},
    }

    transfers = system._plan_transfers(
        [
            {
                "treaty_id": "tiny-share",
                "country_id": "CAN",
                "detail": '["A_TINY", "Z_BIG"]',
                "value": 1e-320,
            }
        ],
        countries,
    )

    assert [transfer["donor_country_id"] for transfer in transfers] == ["Z_BIG"]
    assert transfers[0]["annual_amount"] > 0.0
