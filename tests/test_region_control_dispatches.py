from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.service.mail_inbox_state import MailInboxState
from src.client.ui.panels.service.region_control_dispatches import region_control_dispatches


def _event(event_id, region_id, previous_owner, owner):
    return {
        "event_id": event_id,
        "event_type": "EventTerritoryOwnershipChanged",
        "payload": {
            "region_id": region_id,
            "previous_owner": previous_owner,
            "owner": owner,
        },
    }


def _state(records=()):
    return SimpleNamespace(
        journal=SimpleNamespace(domain_events=list(records)),
        tables={"regions": pl.DataFrame({"id": [1, 2, 3], "name": ["Kyiv", "Warsaw", "Lviv"]})},
    )


def test_local_territory_changes_are_grouped_into_viewable_mail_dispatches():
    state = _state([
        _event("gain-warsaw", 2, "POL", "UKR"),
        _event("gain-lviv", 3, "POL", "UKR"),
        _event("lose-kyiv", 1, "UKR", "POL"),
    ])

    dispatches = region_control_dispatches(state, "ukr")

    assert dispatches == [
        {
            "id": "region-gained:gain-lviv",
            "kind": "region_control",
            "reference": "gained",
            "subject": "Territory Gained (2)",
            "body": "TERRITORY GAINED\nWarsaw\nLviv",
            "payload": {"region_ids": [2, 3], "event_ids": ["gain-warsaw", "gain-lviv"]},
        },
        {
            "id": "region-lost:lose-kyiv",
            "kind": "region_control",
            "reference": "lost",
            "subject": "Territory Lost (1)",
            "body": "TERRITORY LOST\nKyiv",
            "payload": {"region_ids": [1], "event_ids": ["lose-kyiv"]},
        },
    ]


def test_recovered_regions_move_from_gained_to_lost_and_foreign_changes_are_ignored():
    state = _state([
        _event("gain", 2, "POL", "UKR"),
        _event("foreign", 2, "UKR", "FRA"),
        _event("recover", 2, "FRA", "UKR"),
        _event("lose", 2, "UKR", "POL"),
    ])

    dispatches = region_control_dispatches(state, "UKR")

    assert len(dispatches) == 1
    assert dispatches[0]["reference"] == "lost"
    assert dispatches[0]["body"] == "TERRITORY LOST\nWarsaw"


def test_unrelated_invalid_and_foreign_events_do_not_create_dispatches():
    state = _state([
        _event("foreign", 2, "POL", "FRA"),
        _event("bad-region", 0, "POL", "UKR"),
        _event("bad-type", "not-an-id", "POL", "UKR"),
        _event("boolean-region", True, "POL", "UKR"),
        {"event_id": "other", "event_type": "EventBattleEnded", "payload": {}},
    ])

    assert region_control_dispatches(state, "UKR") == []
    assert region_control_dispatches(state, "") == []


def test_missing_region_records_use_authoritative_region_ids_in_notice():
    state = _state()

    dispatches = region_control_dispatches(state, "UKR")
    state.journal.domain_events.append(_event("gain", 99, "POL", "UKR"))

    assert dispatches == []
    assert region_control_dispatches(state, "UKR")[0]["body"] == "TERRITORY GAINED\nRegion 99"


def test_viewed_regions_do_not_reappear_in_later_grouped_mail():
    state = _state([_event("gain-warsaw", 2, "POL", "UKR")])
    inbox_state = MailInboxState()

    first = region_control_dispatches(state, "UKR")
    inbox_state.dismiss_region_events("UKR", first[0]["payload"]["event_ids"])
    state.journal.domain_events.append(_event("gain-lviv", 3, "POL", "UKR"))

    later = region_control_dispatches(
        state,
        "UKR",
        inbox_state.dismissed_region_event_ids("UKR"),
    )

    assert len(later) == 1
    assert later[0]["subject"] == "Territory Gained (1)"
    assert later[0]["body"] == "TERRITORY GAINED\nLviv"
    assert later[0]["payload"]["event_ids"] == ["gain-lviv"]


def test_viewed_opposite_change_clears_older_pending_notice_for_the_region():
    state = _state([
        _event("gain-warsaw", 2, "POL", "UKR"),
        _event("lose-warsaw", 2, "UKR", "POL"),
    ])
    inbox_state = MailInboxState()

    pending_loss = region_control_dispatches(state, "UKR")
    assert pending_loss[0]["payload"]["event_ids"] == ["lose-warsaw"]
    inbox_state.dismiss_region_events("UKR", pending_loss[0]["payload"]["event_ids"])
    state.journal.domain_events.append(_event("regain-warsaw", 2, "POL", "UKR"))

    pending_regain = region_control_dispatches(
        state,
        "UKR",
        inbox_state.dismissed_region_event_ids("UKR"),
    )

    assert len(pending_regain) == 1
    assert pending_regain[0]["reference"] == "gained"
    assert pending_regain[0]["payload"]["event_ids"] == ["regain-warsaw"]


def test_dismissed_event_ids_are_scoped_to_the_country():
    inbox_state = MailInboxState()
    inbox_state.dismiss_region_events("ukr", ["territory-change"])

    assert inbox_state.dismissed_region_event_ids("UKR") == frozenset({"territory-change"})
    assert inbox_state.dismissed_region_event_ids("POL") == frozenset()
