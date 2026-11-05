from __future__ import annotations

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.actions import ActionSetCountryCapital
from src.shared.events import EventGovernmentCapitalChanged
from src.shared.state import GameState


def _world() -> tuple[GameState, PoliticalLifecycleSystem]:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                [
                    {"id": "AAA", "money_reserves": 100.0},
                    {"id": "BBB", "money_reserves": 100.0},
                ]
            ),
            "country_governments": pl.DataFrame(
                [
                    {
                        "country_id": "AAA",
                        "government_type": "Transitional republic",
                        "government_form_id": "transitional republic",
                        "capital_region_id": 1,
                        "initialized": True,
                        "election_eligible": False,
                        "crisis_status": "none",
                    }
                ]
            ),
            "regions": pl.DataFrame(
                [
                    {"id": 1, "owner": "AAA", "controller": "AAA"},
                    {"id": 2, "owner": "AAA", "controller": "AAA"},
                    {"id": 3, "owner": "BBB", "controller": "BBB"},
                ]
            ),
        },
        globals={"player_country_map": {"player": "AAA"}},
    )
    ensure_base_tables(state)
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    state.events.clear()
    return state, system


def test_capital_change_updates_government_and_emits_domain_event() -> None:
    state, system = _world()
    state.current_actions = [ActionSetCountryCapital("player", "AAA", 1, 2)]

    system.update(state, 0.0)

    government = state.tables["country_governments"].row(0, named=True)
    assert government["capital_region_id"] == 2
    assert government["updated_at_minute"] == 0
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.journal.command_results[-1]["from_region_id"] == 1
    assert state.journal.command_results[-1]["to_region_id"] == 2
    event = next(event for event in state.events if isinstance(event, EventGovernmentCapitalChanged))
    assert (event.country_id, event.previous_region_id, event.new_region_id) == ("AAA", 1, 2)


@pytest.mark.parametrize(
    ("actor", "expected", "target", "reason"),
    [
        ("foreign-player", 1, 2, "does not control"),
        ("player", 0, 2, "changed after"),
        ("player", 1, 3, "currently controlled"),
        ("player", 1, 99, "unavailable"),
    ],
)
def test_invalid_or_unauthorized_capital_change_is_rejected(
    actor: str,
    expected: int,
    target: int,
    reason: str,
) -> None:
    state, system = _world()
    state.current_actions = [ActionSetCountryCapital(actor, "AAA", expected, target)]

    system.update(state, 0.0)

    assert state.tables["country_governments"]["capital_region_id"][0] == 1
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert reason in state.journal.command_results[-1]["reason"]
    assert not any(isinstance(event, EventGovernmentCapitalChanged) for event in state.events)


def test_capital_can_move_into_region_under_active_military_control() -> None:
    state, system = _world()
    state.update_table(
        "regions",
        state.tables["regions"].with_columns(
            pl.when(pl.col("id") == 3)
            .then(pl.lit(""))
            .otherwise(pl.col("controller"))
            .alias("controller")
        ),
    )
    state.update_table(
        "occupations",
        pl.DataFrame(
            [
                {
                    "region_id": 3,
                    "controller_country_id": "AAA",
                    "occupation_status": "active",
                }
            ],
            schema=state.tables["occupations"].schema,
            strict=False,
        ),
    )
    state.current_actions = [ActionSetCountryCapital("player", "AAA", 1, 3)]

    system.update(state, 0.0)

    assert state.tables["country_governments"]["capital_region_id"][0] == 3
    assert state.journal.command_results[-1]["status"] == "applied"


def test_capital_changes_remain_limited_to_the_players_country() -> None:
    state, system = _world()
    state.current_actions = [ActionSetCountryCapital("player", "BBB", 3, 3)]

    system.update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "does not control" in state.journal.command_results[-1]["reason"]
