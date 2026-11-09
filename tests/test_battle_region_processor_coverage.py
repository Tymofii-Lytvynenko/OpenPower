from types import SimpleNamespace

from modules.base.systems.military.battle_region_processor import BattleRegionProcessor
from src.shared.state import GameState


def test_process_region_stops_when_units_have_no_valid_owners():
    processor = BattleRegionProcessor.__new__(BattleRegionProcessor)
    request = SimpleNamespace()
    result = SimpleNamespace(stationary_units={7: [{"owner": ""}, {"owner": None}]})

    processor._process_region(request, result, 7, {"id": 7})


def test_mark_occupation_contested_updates_only_the_matching_region():
    state = GameState(tables={})
    state.time.total_minutes = 123
    occupations = [
        {
            "region_id": 7,
            "contested": False,
            "occupation_status": "occupied",
            "updated_at_minute": 0,
        },
        {
            "region_id": 8,
            "contested": False,
            "occupation_status": "occupied",
            "updated_at_minute": 0,
        },
    ]

    BattleRegionProcessor._mark_occupation_contested(occupations, 7, state)

    assert occupations[0] == {
        "region_id": 7,
        "contested": True,
        "occupation_status": "contested",
        "updated_at_minute": 123,
    }
    assert occupations[1]["contested"] is False
