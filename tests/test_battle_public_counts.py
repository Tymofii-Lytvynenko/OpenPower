from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.battle_public_counts import public_battle_counts
from modules.base.schema import ensure_base_tables
from src.client.ui.panels.military.battle_public_counts import observed_category_counts
from src.shared.state import GameState
from src.shared.snapshots import StateSnapshotDecoder, StateSnapshotEncoder


def sample():
    battle = dict(id="observed", status="active", updated_at_minute=10,
                  attacker_side="POL", defender_side="DEU")
    units = [dict(id="aa", owner="POL", unit_type="air_defense", strength=10, equipment_quantity=3),
             dict(id="aa-2", owner="POL", unit_type="air_defense", strength=11, equipment_quantity=7),
             dict(id="inf", owner="DEU", unit_type="infantry", strength=20, equipment_quantity=40)]
    members = [dict(battle_id="observed", unit_id="aa", country_id="POL", side="SIDE_A"),
               dict(battle_id="observed", unit_id="aa-2", country_id="POL", side="SIDE_A"),
               dict(battle_id="observed", unit_id="inf", country_id="DEU", side="SIDE_B")]
    return battle, units, members


def test_public_projection_contains_only_category_totals_and_valid_zeroes():
    battle, units, members = sample()
    frame = public_battle_counts([battle], members, units)
    assert set(frame.columns) == {"battle_id", "side", "category", "unit_quantity", "complete", "sampled_at_minute"}
    state = SimpleNamespace(tables={"battle_public_counts": frame})
    assert observed_category_counts(state, battle, "A") == {"I": 0, "G": 10, "A": 0, "N": 0}
    assert observed_category_counts(state, battle, "B")["I"] == 40


def test_duplicate_participants_mark_counts_incomplete_without_double_counting():
    battle, units, members = sample()
    members.append(dict(members[0]))

    frame = public_battle_counts([battle], members, units)
    attacker_counts = frame.filter(pl.col("side") == "A")

    assert not attacker_counts["complete"].any()
    assert (
        attacker_counts.filter(pl.col("category") == "G")["unit_quantity"].item()
        == 10
    )


def test_observed_counts_are_unavailable_when_the_table_is_missing():
    state = SimpleNamespace(tables={})

    assert observed_category_counts(state, {"id": "observed"}, "A") is None


def test_incomplete_unknown_and_stale_counts_are_not_exposed_as_zeroes():
    battle, units, members = sample()
    for broken in (
        [],
        [{**units[0], "unit_type": "unknown_role"}],
        [{**units[0], "owner": "OTHER"}],
        [{**units[0], "equipment_quantity": None}],
        [{**units[0], "equipment_quantity": -1}],
    ):
        frame = public_battle_counts([battle], members, broken)
        state = SimpleNamespace(tables={"battle_public_counts": frame})
        assert observed_category_counts(state, battle, "A") is None
    frame = public_battle_counts([battle], members, units)
    state = SimpleNamespace(tables={"battle_public_counts": frame})
    assert observed_category_counts(state, {**battle, "updated_at_minute": 11}, "A") is None
    assert public_battle_counts([{**battle, "status": "concluded"}], members, units).is_empty()


def test_published_counts_survive_snapshot_delivery_without_the_unit_roster():
    battle, units, members = sample()
    state = GameState(tables={"battle_public_counts": public_battle_counts([battle], members, units)})
    restored = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(state))
    assert "units" not in restored.tables
    assert observed_category_counts(restored, battle, "A")["G"] == 10


def test_legacy_group_rows_are_unavailable_until_quantity_sample_is_refreshed():
    battle, _, _ = sample()
    legacy = pl.DataFrame([
        {"battle_id": battle["id"], "side": side, "category": category,
         "group_count": 3, "complete": True, "sampled_at_minute": battle["updated_at_minute"]}
        for side in ("A", "B") for category in "IGAN"
    ])
    state = GameState(tables={"battle_public_counts": legacy})
    ensure_base_tables(state)

    assert state.tables["battle_public_counts"]["unit_quantity"].null_count() == 8
    assert observed_category_counts(state, battle, "A") is None


def test_unmapped_visible_data_does_not_hide_supported_categories():
    battle, units, members = sample()
    units.append(dict(id="strategic", owner="POL", unit_type="strategic_missiles",
                      strength=2, equipment_quantity=2))
    members.append(dict(battle_id="observed", unit_id="strategic", country_id="POL", side="SIDE_A"))
    frame = public_battle_counts([battle], members, units)
    state = SimpleNamespace(tables={"battle_public_counts": frame})

    assert observed_category_counts(state, battle, "A")["G"] == 10
