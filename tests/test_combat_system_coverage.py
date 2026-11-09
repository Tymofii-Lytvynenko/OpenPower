import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from src.shared.state import GameState


def test_resolver_delegates_expose_capability_index_and_raw_strength() -> None:
    system = CombatSystem()
    capability_index = {"usa-1": {"valid_targets": ["generic"]}}
    system._capability_index = capability_index

    units = [
        {"owner": "USA", "strength": 20, "combat_posture": "attack"},
        {"owner": "CAN", "strength": 90, "combat_posture": "hold"},
        {"owner": "USA", "strength": 40, "combat_posture": "reorganize"},
    ]

    assert system._capability_index is capability_index
    assert system._raw_strength(units, {"USA"}) == 20


def test_update_resets_battle_tables_when_required_world_tables_are_absent() -> None:
    state = GameState(tables={})

    CombatSystem().update(state, 0.0)

    assert state.get_table("battles").is_empty()
    assert state.get_table("battle_units").is_empty()


def test_engagement_anchor_and_legacy_battle_table_fallbacks() -> None:
    system = CombatSystem()

    assert system.engagement_anchor_region(
        [
            {"id": "later", "current_region_id": 7},
            {"id": "first", "current_region_id": 3},
        ]
    ) == 3
    assert system.engagement_anchor_region(
        [{"id": "unplaced", "current_region_id": 0}]
    ) == 0
    assert system._existing_active_battle_ids(
        pl.DataFrame({"id": ["battle-a", "battle-b"]})
    ) == {"battle-a", "battle-b"}
