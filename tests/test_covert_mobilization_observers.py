from modules.base.systems.military.covert_operations_system import CovertOperationsSystem, SKILL_LEVELS


def test_mobilization_observers_require_active_communications_and_rank_deterministically():
    base = {
        "country_id": "AAA", "target_country_id": "BBB", "location_country_id": "BBB",
        "assignment": "espionage", "status": "active", "communications_ready": True,
    }
    cells = [
        {**base, "id": "low", "skill_level": SKILL_LEVELS[0], "readiness": 1.0},
        {**base, "id": "b", "skill_level": SKILL_LEVELS[-1], "readiness": 0.8},
        {**base, "id": "a", "skill_level": SKILL_LEVELS[-1], "readiness": 0.8},
        {**base, "id": "offline", "skill_level": SKILL_LEVELS[-1], "communications_ready": False},
        {**base, "id": "domestic", "country_id": "BBB"},
        {**base, "id": "elsewhere", "location_country_id": "CCC"},
    ]
    selected = CovertOperationsSystem()._mobilization_observers(cells, "BBB")
    assert [cell["id"] for cell in selected] == ["a", "b", "low"]
