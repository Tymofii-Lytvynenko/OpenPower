import polars as pl

from modules.base.schema import build_base_schema_registry
from modules.base.systems.demographics.migration_policy import evaluate_border_access
from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.world.ai.migration_policy import MigrationPolicy
from modules.base.systems.world.ai_system import AISystem
from src.core.ai_framework import AITableContext
from src.shared.actions import ActionUpdateMigrationPolicy
from src.shared.events import EventNewDay
from src.shared.state import GameState


def _context():
    countries = pl.DataFrame({
        "id": ["NPC", "PLAYER"],
        "is_playable": [True, True],
        "migration_pressure": [0.7, 0.7],
        "unemployment_rate": [0.15, 0.15],
    })
    policies = pl.DataFrame({
        "country_id": ["NPC", "PLAYER"],
        "migration_policy": ["open", "open"],
        "border_policy": ["open", "open"],
        "entry_rate": [1.0, 1.0],
        "exit_rate": [0.5, 0.5],
        "asylum_rate": [0.25, 0.25],
        "family_reunification_rate": [0.5, 0.5],
        "skilled_worker_preference": [0.0, 0.0],
        "enforcement_strength": [0.5, 0.5],
        "effective_at_minute": [0, 0],
        "updated_at_minute": [0, 0],
        "source": ["default", "default"],
    })
    signals = pl.DataFrame({
        "country_id": ["NPC", "PLAYER"],
        "service_pressure": [0.9, 0.9],
        "political_pressure": [0.8, 0.8],
    })
    return AITableContext(
        tables={
            "countries": countries,
            "migration_policies": policies,
            "migration_signals": signals,
        },
        day_ordinal=30,
        total_minutes=43_200,
        date_text="0001-02-01",
        player_tag="PLAYER",
        globals={},
    )


def test_policy_selects_bounded_response_only_for_ai_country():
    assert "migration" in AISystem()._framework.policy_ids
    policy = MigrationPolicy()
    candidates = policy.build_candidates(_context()).collect()

    assert candidates.get_column("country_id").to_list() == ["NPC"]
    selected = candidates.row(0, named=True)
    assert selected["migration_policy"] == "restricted"
    assert 0.0 <= selected["entry_rate"] <= 1.0
    action = policy.resolve_action(selected)
    assert isinstance(action, ActionUpdateMigrationPolicy)
    assert action.player_id == "ai_system"
    assert action.country_tag == "NPC"
    assert action.migration_policy == "restricted"


def test_ai_policy_command_uses_authoritative_migration_action_path():
    context = _context()
    state = GameState(tables={
        "countries": context.tables["countries"],
        "regions": pl.DataFrame({
            "id": pl.Series([], dtype=pl.Int32),
            "owner": pl.Series([], dtype=pl.Utf8),
        }),
        "migration_policies": context.tables["migration_policies"],
        "migration_signals": context.tables["migration_signals"],
    })
    build_base_schema_registry().ensure_state(state)
    selected = MigrationPolicy().build_candidates(context).collect().row(0, named=True)
    action = MigrationPolicy().resolve_action(selected)
    assert isinstance(action, ActionUpdateMigrationPolicy)
    state.current_actions = [action]
    state.events = [EventNewDay(day=1, month=2, year=1)]
    state.time.total_minutes = context.total_minutes
    assert {
        "countries", "regions", "migration_policies", "migration_policy_transitions",
        "migration_flows", "migration_signals",
    }.issubset(state.tables)

    MigrationSystem().update(state, 0.1)

    npc_policy = state.get_table("migration_policies").filter(pl.col("country_id") == "NPC").row(0, named=True)
    player_policy = state.get_table("migration_policies").filter(pl.col("country_id") == "PLAYER").row(0, named=True)
    assert npc_policy["migration_policy"] == "restricted"
    assert npc_policy["source"] == "ai"
    assert player_policy["migration_policy"] == "open"

    human_state = GameState(tables={
        "countries": context.tables["countries"],
        "regions": state.get_table("regions").clone(),
        "migration_policies": context.tables["migration_policies"],
        "migration_signals": context.tables["migration_signals"],
    })
    build_base_schema_registry().ensure_state(human_state)
    human_state.time.total_minutes = context.total_minutes
    human_state.current_actions = [ActionUpdateMigrationPolicy(
        "NPC",
        "NPC",
        action.migration_policy,
        action.border_policy,
        entry_rate=action.entry_rate,
        exit_rate=action.exit_rate,
        effective_at_minute=action.effective_at_minute,
    )]
    MigrationSystem().update(human_state, 0.1)

    ai_policies = MigrationSystem()._policy_map(state, context.total_minutes)
    human_policies = MigrationSystem()._policy_map(human_state, context.total_minutes)
    ai_route = evaluate_border_access(
        "NPC", "PLAYER", ai_policies["NPC"], ai_policies["PLAYER"]
    )
    human_route = evaluate_border_access(
        "NPC", "PLAYER", human_policies["NPC"], human_policies["PLAYER"]
    )
    assert ai_route == human_route
