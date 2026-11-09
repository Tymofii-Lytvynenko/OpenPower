from modules.base.systems.military.training_eligibility_policy import (
    facility_domains,
    select_training_facility,
    training_cost,
    training_level_steps,
)


def test_training_level_steps_returns_zero_for_unknown_levels() -> None:
    assert training_level_steps("Recruit", "Legendary") == 0


def test_facility_domains_parses_json_lists_and_rejects_invalid_json() -> None:
    assert facility_domains({"supported_domains": '[" Land ", "", "NAVAL"]'}) == {
        "land",
        "naval",
    }
    assert facility_domains({"supported_domains": "not-json"}) == set()
    assert facility_domains({"supported_domains": "null"}) == set()


def test_select_training_facility_rejects_disabled_local_facility() -> None:
    facility = {
        "id": "site-1",
        "country_id": "AAA",
        "region_id": 5,
        "supported_domains": ["land"],
        "enabled": False,
        "instructor_count": 2,
        "capacity": 2,
    }

    selected, reason = select_training_facility(
        {"current_region_id": 5}, "AAA", "land", [facility], []
    )

    assert selected is None
    assert "facility is enabled" in reason


def test_numeric_helpers_fall_back_for_malformed_input() -> None:
    facility = {
        "id": "site-1",
        "country_id": "AAA",
        "region_id": "invalid",
        "supported_domains": ["land"],
        "enabled": True,
        "instructor_count": 1,
        "capacity": 1,
    }

    selected, reason = select_training_facility(
        {"current_region_id": "invalid"}, "AAA", "land", [facility], []
    )

    assert selected is facility
    assert reason == ""
    assert training_cost("not-a-number", 2, 4) == 0.0
