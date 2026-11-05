from __future__ import annotations

import polars as pl

from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from src.shared.actions import ActionUpdateResourcePolicy
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["UKR", "POL"]}),
            "domestic_production": pl.DataFrame(
                {
                    "country_id": ["UKR", "POL"],
                    "game_resource_id": ["fossil_fuels", "fossil_fuels"],
                    "domestic_production": [100.0, 200.0],
                    "is_gov_controlled": [False, False],
                    "is_legal": [True, True],
                    "tax_rate": [0.05, 0.1],
                }
            ),
        },
        globals={"player_country_map": {"ukr-player": "UKR"}},
    )
    return state


def _action(**overrides) -> ActionUpdateResourcePolicy:
    values = {
        "player_id": "ukr-player",
        "country_tag": "UKR",
        "resource_id": "fossil_fuels",
        "is_gov_controlled": True,
        "is_legal": False,
        "tax_rate": 0.25,
    }
    values.update(overrides)
    return ActionUpdateResourcePolicy(**values)


def _apply(state: GameState, action: ActionUpdateResourcePolicy) -> None:
    state.current_actions = [action]
    InternalEconomySystem().update(state, 0.0)


def test_resource_policy_update_requires_control_and_reports_applied_result() -> None:
    state = _state()

    _apply(state, _action())

    row = state.tables["domestic_production"].filter(pl.col("country_id") == "UKR").row(0, named=True)
    assert row["is_gov_controlled"] is True
    assert row["is_legal"] is False
    assert row["tax_rate"] == 0.25
    result = state.journal.command_results[-1]
    assert result["status"] == "applied"
    assert result["country_id"] == "UKR"
    assert result["resource_id"] == "fossil_fuels"


def test_resource_policy_rejects_foreign_country_without_mutating_it() -> None:
    state = _state()

    _apply(state, _action(country_tag="POL"))

    row = state.tables["domestic_production"].filter(pl.col("country_id") == "POL").row(0, named=True)
    assert row["is_gov_controlled"] is False
    assert row["is_legal"] is True
    assert row["tax_rate"] == 0.1
    result = state.journal.command_results[-1]
    assert result["status"] == "rejected"
    assert "does not control" in result["reason"]


def test_resource_policy_rejects_nonfinite_tax_without_mutating_state() -> None:
    state = _state()

    _apply(state, _action(tax_rate=float("nan")))

    row = state.tables["domestic_production"].filter(pl.col("country_id") == "UKR").row(0, named=True)
    assert row["tax_rate"] == 0.05
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "finite ratio" in state.journal.command_results[-1]["reason"]
