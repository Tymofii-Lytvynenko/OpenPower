from modules.base.systems.military.research_eligibility_policy import (
    _nonnegative_int,
    research_requirements_met,
)


def test_malformed_persisted_requirements_fall_back_to_an_empty_mapping():
    assert research_requirements_met("{not-json", {})


def test_non_mapping_requirements_are_rejected():
    assert not research_requirements_met('["ground", 2]', {})


def test_invalid_research_levels_normalize_to_zero():
    assert _nonnegative_int("not-a-level") == 0
    assert _nonnegative_int(float("inf")) == 0
    assert not research_requirements_met({"air": 1}, {"air": "not-a-level"})
