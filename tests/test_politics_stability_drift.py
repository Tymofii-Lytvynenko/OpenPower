from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.shared.events import EventNewDay
from src.shared.state import GameState


def _weekly_state(
    *,
    approval: float | None = 50.0,
    hdi: float | None = 0.5,
    corruption: float | None = 0.1,
    stability: float | None = 50.0,
    elapsed_days: int = 7,
    engine_tick: int = 43,
) -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AAA"],
                    "gvt_approval": [approval],
                    "human_dev": [hdi],
                    "gvt_corruption": [corruption],
                    "gvt_stability": [stability],
                    "economic_political_modifier": [1.0],
                    "war_exhaustion_stability_penalty": [0.0],
                }
            )
        },
        globals={"tick": engine_tick},
    )
    ensure_base_tables(state)
    state.time.total_minutes = elapsed_days * 24 * 60
    state.time.day = elapsed_days + 1
    state.events = [EventNewDay(state.time.day, 1, 2001)]
    return state


def test_stability_drifts_by_exact_five_percent_of_specified_baseline_weekly():
    state = _weekly_state()

    PoliticsSystem().update(state, 0.0)

    # Target = (0.7 * 50 + 0.3 * 0.5 - 0.1) = 35.05; int(49.2525) = 49.
    assert state.get_table("countries").item(0, "gvt_stability") == 49


def test_null_metrics_use_specified_fallback_values():
    state = _weekly_state(approval=None, hdi=None, corruption=None, stability=None)

    PoliticsSystem().update(state, 0.0)

    assert state.get_table("countries").item(0, "gvt_stability") == 49


def test_political_drift_uses_game_week_not_engine_step_or_month_day():
    state = _weekly_state(elapsed_days=6, engine_tick=7)
    before_revision = state.table_revisions["countries"]
    before_stability = state.get_table("countries").item(0, "gvt_stability")

    PoliticsSystem().update(state, 0.0)

    assert state.table_revisions["countries"] == before_revision
    assert state.get_table("countries").item(0, "gvt_stability") == before_stability


def test_stability_fallback_is_used_when_column_is_missing():
    state = _weekly_state(stability=50.0)
    state.update_table("countries", state.get_table("countries").drop("gvt_stability"))

    PoliticsSystem().update(state, 0.0)

    assert state.get_table("countries").item(0, "gvt_stability") == 49
