import polars as pl

from modules.base.systems.military.war_index import WarIndex


def test_war_index_selects_first_active_war_in_stable_id_order():
    wars = pl.DataFrame(
        [
            {"id": "war-z", "side_a": "usa, can", "side_b": "fra", "status": "active"},
            {"id": "war-a", "side_a": "usa, can", "side_b": "fra", "status": "ongoing"},
            {"id": "war-0", "side_a": "usa", "side_b": "fra", "status": "ended"},
        ]
    )

    index = WarIndex.from_table(wars)
    conflict = index.active_battle_for_region({"USA", "FRA"})

    assert conflict is not None
    assert conflict.war_id == "war-a"
    assert conflict.side_a_members == frozenset({"USA", "CAN"})
    assert conflict.side_a_tags == frozenset({"USA"})
    assert index.is_hostile("CAN", "FRA")
    assert not index.is_hostile("USA", "CAN")


def test_war_index_ignores_missing_or_one_sided_wars():
    assert WarIndex.from_table(None).active_battle_for_region({"USA", "FRA"}) is None
    wars = pl.DataFrame([{"id": "war-a", "side_a": "USA", "side_b": "", "status": "active"}])
    assert not WarIndex.from_table(wars).is_hostile("USA", "FRA")
