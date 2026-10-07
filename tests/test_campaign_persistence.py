from __future__ import annotations

import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.world.campaign_system import CampaignSetupSystem, CampaignSystem
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionSetSphereDelegation, ActionStartCampaign
from src.shared.config import GameConfig
from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder
from src.shared.state import GameState
from tests.test_campaign_system import _add_scenario, _state


_CAMPAIGN_TABLES = (
    "campaign_scenarios",
    "campaigns",
    "objectives",
    "sphere_delegations",
    "advisor_recommendations",
)


def _start_persistable_campaign() -> GameState:
    state = _state()
    _add_scenario(state, [{
        "id": "raise-oil-output",
        "objective_type": "resource_quantity",
        "target_resource_id": "oil",
        "target_value": 100,
        "deadline_minutes": 500,
        "failure_conditions": [{
            "objective_type": "gdp_per_capita", "target_value": 5, "comparison": "at_most",
        }],
    }])
    state.time.total_minutes = 10
    state.current_actions = [ActionStartCampaign("local_admin", "test", "USA")]
    setup = CampaignSetupSystem()
    evaluator = CampaignSystem()
    setup.update(state, 0.0)
    evaluator.update(state, 0.0)
    state.current_actions = [ActionSetSphereDelegation(
        "local_admin", "USA", "country", "USA", "ai", ["economy"], ["campaign_objectives"],
    )]
    setup.update(state, 0.0)
    evaluator.update(state, 0.0)
    state.current_actions = []
    return state


def _advance_campaign(state: GameState, minute: int) -> None:
    state.time.total_minutes = minute
    state.current_actions = []
    state.update_table("domestic_production", state.tables["domestic_production"].with_columns(
        pl.when(pl.col("country_id") == "USA")
        .then(pl.lit(100.0))
        .otherwise(pl.col("domestic_production"))
        .alias("domestic_production")
    ))
    CampaignSystem().update(state, 0.0)


def test_campaign_setup_progress_delegation_and_outcome_continue_after_all_persistence_paths(tmp_path) -> None:
    state = _start_persistable_campaign()
    registry = build_base_schema_registry()
    snapshot = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(state, force_full=True))
    ipc = GameState.from_ipc(state.to_ipc())
    registry.ensure_state(snapshot)
    registry.ensure_state(ipc)

    config = GameConfig(tmp_path)
    assert SaveWriter(config).save_game(state, "campaign-continue")
    loaded = DataLoader(config, schema_registry=registry).load_save("campaign-continue")
    continuations = (state, snapshot, ipc, loaded)
    for candidate in continuations[1:]:
        for table_name in _CAMPAIGN_TABLES:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()

    for candidate in continuations:
        _advance_campaign(candidate, 20)
    for candidate in continuations[1:]:
        for table_name in _CAMPAIGN_TABLES:
            assert candidate.get_table(table_name).to_dicts() == state.get_table(table_name).to_dicts()

    assert state.get_table("objectives").filter(pl.col("campaign_id") != "")["status"][0] == "completed"
    assert state.get_table("campaigns")[0, "outcome"] == "victory"
    assert state.get_table("sphere_delegations")[0, "active"] is True


def test_campaign_ordered_action_replay_produces_identical_progress_and_advisor_rows() -> None:
    original = _start_persistable_campaign()
    replayed = _start_persistable_campaign()

    assert all(
        original.get_table(name).to_dicts() == replayed.get_table(name).to_dicts()
        for name in _CAMPAIGN_TABLES
    )
    for candidate in (original, replayed):
        candidate.update_table("news_items", pl.DataFrame([{
            "id": "replay-news", "category": "opportunity", "severity": "info",
            "headline": "Production opportunity", "body": "Expand production.",
            "related_country_id": "USA",
        }], schema=candidate.get_table("news_items").schema, strict=False))
        _advance_campaign(candidate, 20)

    for table_name in _CAMPAIGN_TABLES:
        assert original.get_table(table_name).to_dicts() == replayed.get_table(table_name).to_dicts()
