import polars as pl
from unittest.mock import patch
from types import SimpleNamespace

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.world.ai_system import AISystem
import modules.base.systems.world.ai.covert_policy as covert_policy_module
from modules.base.systems.world.ai.covert_policy import CovertOperationsPolicy
from src.core.ai_framework import AITableContext
from src.shared.actions import (
    ActionCreateCovertCell,
    ActionStartCovertMission,
    ActionTrainCovertCell,
)
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


def _ai_context(tables, globals_=None) -> AITableContext:
    return AITableContext(
        tables=tables,
        day_ordinal=0,
        total_minutes=0,
        date_text="0001-01-01",
        player_tag="PLAYER",
        globals=globals_ or {},
    )


def test_candidate_builder_returns_empty_for_unscheduled_or_incomplete_snapshots(monkeypatch):
    policy = CovertOperationsPolicy()
    monkeypatch.setattr(
        covert_policy_module,
        "country_frame",
        lambda *_args: pl.DataFrame(schema={"country_id": pl.Utf8}).lazy(),
    )
    assert policy.build_candidates(_ai_context({})).collect().is_empty()

    monkeypatch.setattr(
        covert_policy_module,
        "country_frame",
        lambda *_args: pl.DataFrame({"country_id": ["AI"]}).lazy(),
    )
    base = _state()
    incomplete = dict(base.tables)
    incomplete.pop("regions")
    assert policy.build_candidates(_ai_context(incomplete)).collect().is_empty()

    missing_country_id = {
        "countries": pl.DataFrame({"name": ["AI"]}),
        "regions": base.get_table("regions"),
        "covert_cells": base.get_table("covert_cells"),
        "covert_missions": base.get_table("covert_missions"),
    }
    assert policy.build_candidates(_ai_context(missing_country_id)).collect().is_empty()


def test_active_cell_and_mission_indexes_ignore_unknown_schemas():
    cells = CovertOperationsPolicy._active_cell_frame(
        pl.DataFrame({"unexpected": [1]}), ["AI"]
    )
    missions = CovertOperationsPolicy._active_mission_frame(
        pl.DataFrame({"unexpected": [1]})
    )

    assert cells.columns == ["cell_id", "country_id"]
    assert missions.columns == ["active_cell_id"]


def test_creation_targets_excludes_allies_and_resolves_treaty_frames():
    policy = CovertOperationsPolicy()
    owners = pl.DataFrame({"country_id": ["AI"]})
    countries = pl.DataFrame({"id": ["AI", "PLAYER", "OTHER"]})
    owned_regions = pl.DataFrame({"country_id": ["AI", "PLAYER", "OTHER"]})

    targets = policy._creation_targets(
        owners,
        countries,
        owned_regions,
        {("AI", "PLAYER"), ("PLAYER", "AI")},
        {("AI", "OTHER"): [-10.0]},
    )
    assert targets.to_dicts() == [{"country_id": "AI", "target_country_id": "OTHER"}]
    assert policy._allied_pairs_from_frame(pl.DataFrame({"status": ["active"]})) == set()
    assert policy._allied_pairs_from_frame(
        pl.DataFrame(
            {
                "status": ["ACTIVE", "expired"],
                "treaty_type": ["ALLIANCE", "alliance"],
                "members": ['["AI", "PLAYER"]', '["AI", "OTHER"]'],
            }
        )
    ) == {("AI", "PLAYER"), ("PLAYER", "AI")}


def test_action_resolution_covers_training_and_unknown_actions():
    policy = CovertOperationsPolicy()

    action = policy.resolve_action(
        {"country_id": "AI", "action_kind": "train_cell", "cell_id": "cell-1", "training_points": 0}
    )

    assert action == ActionTrainCovertCell("ai_system", "cell-1", 1.0)
    assert policy.resolve_action({"country_id": "AI", "action_kind": "other"}) is None


def test_cell_actions_skip_blocked_cells_before_training_or_starting_missions(monkeypatch):
    policy = CovertOperationsPolicy()
    monkeypatch.setattr(
        covert_policy_module,
        "skill_profile",
        lambda skill: SimpleNamespace(max_mission_risk=0.0 if skill == "Low" else 1.0),
    )

    assert policy._cell_action(
        "AI", 0.0, [{"id": "recruit", "status": "active", "skill_level": "Recruit"}],
        set(), 100.0, 10.0, 2.0, 0.2,
    ) is None

    rows = [
        {"id": "", "status": "active"},
        {"id": "retired", "status": "retired"},
        {"id": "busy", "status": "active", "skill_level": "Regular"},
        {"id": "low-risk", "status": "active", "skill_level": "Low"},
        {"id": "no-target", "status": "active", "skill_level": "Regular"},
        {
            "id": "wrong-location", "status": "active", "skill_level": "Regular",
            "target_country_id": "PLAYER", "location_country_id": "OTHER",
        },
        {
            "id": "no-comms", "status": "active", "skill_level": "Regular",
            "target_country_id": "PLAYER", "location_country_id": "PLAYER",
            "communications_ready": False,
        },
        {
            "id": "assigned", "status": "active", "skill_level": "Regular",
            "target_country_id": "PLAYER", "location_country_id": "PLAYER",
            "communications_ready": True, "assignment": "security",
        },
        {
            "id": "mission", "status": "active", "skill_level": "Regular",
            "target_country_id": "PLAYER", "location_country_id": "PLAYER",
            "communications_ready": True, "assignment": "espionage",
        },
    ]
    mission = policy._cell_action("AI", 10.0, rows, {"busy"}, 100.0, 10.0, 2.0, 0.2)
    assert mission["action_kind"] == "start_mission"
    assert mission["cell_id"] == "mission"

    training = policy._cell_action(
        "AI", 10.0, [{"id": "recruit", "status": "idle", "skill_level": "Recruit"}],
        set(), 100.0, 10.0, 2.0, 0.2,
    )
    assert training["action_kind"] == "train_cell"
    assert training["training_points"] == 100.0


def test_target_selection_and_alliance_members_are_normalized_safely():
    policy = CovertOperationsPolicy()
    countries = [
        {"id": ""},
        {"id": "AI"},
        {"id": "ALLY"},
        {"id": "UNOWNED"},
        {"id": "OTHER"},
    ]
    relations = {("AI", "OTHER"): [10.0], ("OTHER", "AI"): [20.0]}

    assert policy._choose_target(
        "AI", countries, relations, {("AI", "ALLY")}, {"AI", "ALLY", "OTHER"}
    ) == "OTHER"
    assert policy._choose_target("AI", countries, {}, set(), {"AI"}) == ""

    pairs = policy._allied_pairs(
        [
            {"status": "expired", "treaty_type": "alliance", "members": ["A", "B"]},
            {"status": "active", "treaty_type": "trade", "members": ["A", "C"]},
            {"treaty_type": "alliance", "members": '["b", "A", "", "A"]'},
            {"status": "active", "treaty_type": "alliance", "members": "{bad"},
            {"status": "active", "treaty_type": "alliance", "members": {"A": "B"}},
            {"status": "active", "treaty_type": "alliance", "members": ["solo", ""]},
        ]
    )
    assert pairs == {("A", "B"), ("B", "A")}


def test_policy_numeric_fallbacks_reject_nonfinite_inputs():
    assert CovertOperationsPolicy._finite("invalid", 7.0) == 7.0
    assert CovertOperationsPolicy._finite("inf", 7.0) == 7.0
