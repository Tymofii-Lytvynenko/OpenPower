import pytest

from modules.base.systems.military.battle_change_detection import battle_snapshot_changed


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "retreating"),
        ("mode", "assault"),
        ("attacker_side", "USA"),
        ("defender_side", "FRA"),
        ("side_a_strength", 99),
        ("side_b_strength", 51),
        ("balance", 0.7),
    ],
)
def test_battle_snapshot_detects_changed_public_fields(field, value):
    previous = {
        "status": "active",
        "mode": "positional",
        "attacker_side": "CAN,USA",
        "defender_side": "FRA,GBR",
        "side_a_strength": 100,
        "side_b_strength": 50,
        "balance": 2 / 3,
    }
    current = dict(
        status="active",
        mode="positional",
        side_a_tags={"USA", "CAN"},
        side_b_tags={"GBR", "FRA"},
        side_a_strength=100,
        side_b_strength=50,
        balance=2 / 3,
    )
    assert not battle_snapshot_changed(previous, **current)
    previous[field] = value
    assert battle_snapshot_changed(previous, **current)
