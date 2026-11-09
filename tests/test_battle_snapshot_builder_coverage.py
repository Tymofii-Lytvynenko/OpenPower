import polars as pl

from modules.base.systems.military.battle_snapshot_builder import (
    ActiveBattleSnapshotRequest,
    BattleSnapshotBuilder,
)
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.war_index import ConflictContext


def _conflict():
    return ConflictContext(
        war_id="war-1",
        side_a_members=frozenset({"AAA"}),
        side_b_members=frozenset({"BBB"}),
        side_a_tags=frozenset({"AAA"}),
        side_b_tags=frozenset({"BBB"}),
    )


def test_battle_unit_change_detection_handles_missing_snapshot_tables():
    builder = BattleSnapshotBuilder(ReadinessPolicy())

    assert builder.battle_units_changed(None, "battle-1", [{"id": "unit-1"}], _conflict())
    assert not builder.battle_units_changed(None, "battle-1", [], _conflict())


def test_current_snapshot_skips_units_outside_the_conflict():
    current = BattleSnapshotBuilder(ReadinessPolicy())._current_battle_units(
        [{"id": "unit-1", "owner": "CCC", "strength": 10}],
        _conflict(),
    )

    assert current == {}


def test_active_battle_is_changed_when_strength_differs_from_saved_snapshot():
    conflict = _conflict()
    prior_row = {
        "status": "active",
        "mode": "land",
        "attacker_side": "AAA",
        "defender_side": "BBB",
        "side_a_strength": 1,
        "side_b_strength": 2,
        "balance": 0.5,
    }
    request = ActiveBattleSnapshotRequest(
        battle_units_table=pl.DataFrame(),
        region_id=1,
        local_units=[],
        conflict=conflict,
        battle_id="battle-1",
        battle_mode="land",
        now=0,
        prior_row=prior_row,
        anchor=None,
        previous_a=1,
        previous_b=2,
        side_a_strength=3,
        side_b_strength=2,
        resolve_this_tick=False,
    )

    assert BattleSnapshotBuilder(ReadinessPolicy())._active_battle_changed(
        request, status="active", balance=0.5
    )
