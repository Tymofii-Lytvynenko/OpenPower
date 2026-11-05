from types import SimpleNamespace

from modules.base.systems.military.covert_incidents import mission_incident


def test_undiscovered_incident_is_only_visible_to_the_owner():
    mission = {"id": "m1", "owner_country_id": " aaa ", "target_country_id": "bbb"}
    outcome = SimpleNamespace(discovered=False, attributed_country_id="CCC", result="failure")
    record = mission_incident(mission, outcome, "incident-1", 42)
    assert record["audience_country_ids"] == ["AAA"]
    assert record["incident_type"] == "operation_result"
    assert record["summary"] == "failure"


def test_discovered_framed_incident_includes_target_and_attributed_country():
    mission = {"id": "m1", "owner_country_id": "AAA", "target_country_id": "BBB"}
    outcome = SimpleNamespace(discovered=True, attributed_country_id="CCC", result="success")
    record = mission_incident(mission, outcome, "incident-1", 42)
    assert record["audience_country_ids"] == ["AAA", "BBB", "CCC"]
    assert record["incident_type"] == "discovery"
    assert record["created_at_minute"] == 42
