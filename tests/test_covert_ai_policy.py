import polars as pl
from unittest.mock import patch

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.ai.covert_policy import CovertOperationsPolicy
from src.core.ai_framework import AITableContext
from src.shared.actions import ActionCreateCovertCell, ActionStartCovertMission
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["AI", "PLAYER"],
                    "gdp": [2_000.0, 1_000.0],
                    "money_reserves": [500.0, 500.0],
                    "is_playable": [True, True],
                }
            ),
            "regions": pl.DataFrame(
                {"id": [1, 2], "owner": ["AI", "PLAYER"], "latitude": [0.0, 0.0], "longitude": [0.0, 1.0]}
            ),
            "countries_relations": pl.DataFrame(
                {"source": ["AI"], "target": ["PLAYER"], "value": [-35.0]}
            ),
        }
    )
    ensure_base_tables(state)
    state.globals.update(
        {
            "player_tag": "PLAYER",
            "covert_cell_creation_cost": 10.0,
            "covert_training_points_per_level": 100.0,
            "covert_training_cost_per_point": 0.1,
            "covert_mission_cost": 2.0,
        }
    )
    return state


def _context(state: GameState, day_ordinal: int = 0) -> AITableContext:
    return AITableContext(
        tables=state.tables,
        day_ordinal=day_ordinal,
        total_minutes=day_ordinal * 1440,
        date_text="0001-01-01",
        player_tag="PLAYER",
        globals=state.globals,
    )


def test_ai_creates_and_uses_cells_through_the_authoritative_action_handler() -> None:
    state = _state()
    ai = AISystem()
    assert "covert_operations" in ai._framework.policy_ids

    evaluation = ai._framework.evaluate(_context(state))
    create_actions = [action for action in evaluation.actions if isinstance(action, ActionCreateCovertCell)]
    assert create_actions == [ActionCreateCovertCell("ai_system", "AI", "PLAYER", "Government Intelligence Cell")]

    state.current_actions = create_actions
    CovertOperationsSystem().update(state, 0.0)
    cell = state.get_table("covert_cells").row(0, named=True)
    assert cell["country_id"] == "AI"
    assert cell["target_country_id"] == "PLAYER"

    cells = state.get_table("covert_cells").with_columns(
        pl.lit("active").alias("status"),
        pl.lit("PLAYER").alias("location_country_id"),
        pl.lit("Regular").alias("skill_level"),
        pl.lit(0.43).alias("concealment"),
        pl.lit(0.5).alias("readiness"),
        pl.lit(True).alias("communications_ready"),
    )
    state.update_table("covert_cells", cells)

    next_evaluation = ai._framework.evaluate(_context(state, day_ordinal=7))
    mission_actions = [action for action in next_evaluation.actions if isinstance(action, ActionStartCovertMission)]
    assert mission_actions == [
        ActionStartCovertMission("ai_system", cell["id"], "civilian_espionage", "PLAYER")
    ]

    state.current_actions = mission_actions
    CovertOperationsSystem().update(state, 0.0)
    mission = state.get_table("covert_missions").row(0, named=True)
    assert mission["owner_country_id"] == "AI"
    assert mission["target_country_id"] == "PLAYER"
    assert mission["status"] == "preparation"


def test_relationship_index_is_shared_and_preserves_duplicate_weighting() -> None:
    state = _state()
    state.update_table("countries", pl.DataFrame({
        "id": ["A", "B", "C", "PLAYER"], "gdp": [1000.0] * 4,
        "money_reserves": [500.0] * 4, "is_playable": [True] * 4,
    }))
    state.update_table("regions", pl.DataFrame({
        "id": [1, 2, 3, 4], "owner": ["A", "B", "C", "PLAYER"],
    }))
    state.update_table("countries_relations", pl.DataFrame({
        "source": ["A", "C", "C", "A"], "target": ["C", "A", "A", "B"],
        "value": [-40.0, 10.0, 10.0, -10.0],
    }))
    policy = CovertOperationsPolicy()
    relations = state.get_table("countries_relations")
    assert policy._index_relations(relations) == policy._index_relations(relations.to_dicts())
    with patch.object(policy, "_index_relations", wraps=policy._index_relations) as index:
        candidates = policy.build_candidates(_context(state)).collect().to_dicts()
        assert index.call_count == 1
    targets = {row["country_id"]: row["target_country_id"] for row in candidates}
    assert targets == {"A": "B", "B": "A", "C": "A"}

    state.update_table("countries_relations", pl.DataFrame({
        "source": ["A"], "target": ["C"], "value": [-100.0],
    }))
    next_targets = {
        row["country_id"]: row["target_country_id"]
        for row in policy.build_candidates(_context(state)).collect().to_dicts()
    }
    assert next_targets["A"] == "C"


def test_relationship_snapshot_is_not_indexed_when_cell_creation_is_unaffordable():
    state = _state()
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(pl.lit(0.0).alias("money_reserves")),
    )
    policy = CovertOperationsPolicy()
    with patch.object(policy, "_index_relations", wraps=policy._index_relations) as index:
        candidates = policy.build_candidates(_context(state)).collect().to_dicts()

    assert candidates == []
    index.assert_not_called()
