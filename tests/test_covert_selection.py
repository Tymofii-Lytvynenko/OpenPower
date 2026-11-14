from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.military.covert_selection import (
    CovertSelection,
    mission_index,
    selected_mission,
)
from src.client.ui.panels.service.journal_dispatches import journal_dispatches
from tests.test_support.client_presentation import client_state


def roster():
    cells = [dict(id="first", country_id="UKR", status="active", cell_name="First"),
             dict(id="selected", country_id="UKR", status="ready", cell_name="Ready")]
    missions = [dict(id="ready", cell_id="selected", owner_country_id="UKR", target_country_id="POL",
                     mission_type="civilian_espionage", status="ready", created_at_minute=10)]
    return cells, missions


def test_requested_cell_is_selected_by_id_and_missing_request_never_selects_another_cell():
    cells, missions = roster()
    selection = CovertSelection()
    selection.request("selected", "ready")
    row, warning = selection.reconcile("UKR", cells, missions)
    assert row["id"] == "selected" and not warning
    selection.request("removed", "ready")
    row, warning = selection.reconcile("UKR", cells, missions)
    assert row is None and warning
    assert selection.reconcile("UKR", cells, missions) == (None, "")
    selection.select("first")
    assert selection.reconcile("UKR", cells, missions)[0]["id"] == "first"


def test_stale_mission_request_does_not_select_another_mission_for_the_same_cell():
    cells, missions = roster()
    selection = CovertSelection()
    selection.request("selected", "old")
    assert selection.reconcile("UKR", cells, missions)[0] is None
    assert selected_mission(missions, "first") is None


def test_extended_selection_replaces_toggles_and_selects_contiguous_ranges():
    selection = CovertSelection()
    rows = ["first", "second", "third", "fourth"]
    selection.reconcile("UKR", [dict(id=value) for value in rows], [])

    selection.select_extended("first", rows)
    selection.select_extended("third", rows, ctrl=True)
    assert selection.selected_cell_ids == ("first", "third")
    assert selection.cell_id == "third"

    selection.select_extended("second", rows)
    assert selection.selected_cell_ids == ("second",)
    selection.select_extended("fourth", rows, shift=True)
    assert selection.selected_cell_ids == ("second", "third", "fourth")

    selection.select_extended("second", rows, ctrl=True)
    assert selection.selected_cell_ids == ("third", "fourth")
    selection.select_extended("third", rows, ctrl=True)
    assert selection.selected_cell_ids == ("fourth",)
    selection.select_extended("fourth", rows, ctrl=True)
    assert selection.selected_cell_ids == ()
    assert selection.reconcile("UKR", [dict(id=value) for value in rows], [])[0] is None


def test_extended_selection_can_merge_a_range_containing_an_unlisted_cell():
    selection = CovertSelection()
    rows = ["first", "second", "third"]
    selection.select_extended("first", rows)

    selection.select_extended("outside", rows, ctrl=True, shift=True)

    assert selection.selected_cell_ids == ("first", "second", "third", "outside")


def test_ready_dispatch_is_private_current_and_disappears_after_execution():
    cells, missions = roster()
    state = client_state(tables=dict(covert_cells=pl.DataFrame(cells), covert_missions=pl.DataFrame(missions)))
    notice = journal_dispatches(state, "UKR")
    assert len(notice) == 1
    assert notice[0]["kind"] == "covert_ready"
    assert notice[0]["reference"] == "selected"
    assert notice[0]["payload"]["mission_id"] == "ready"
    assert journal_dispatches(state, "POL") == []
    state.tables["covert_missions"] = pl.DataFrame([{**missions[0], "status": "executing"}])
    assert journal_dispatches(state, "UKR") == []


def test_ready_dispatch_hides_removed_or_captured_cell():
    cells, missions = roster()
    for rows in (cells[:1], [{**r, "status": "captured"} for r in cells]):
        state = client_state(tables=dict(covert_cells=pl.DataFrame(rows), covert_missions=pl.DataFrame(missions)))
        assert journal_dispatches(state, "UKR") == []


def test_mission_index_prefers_active_mission_to_newer_history():
    history = dict(id="history", cell_id="cell", status="cancelled")
    ready = dict(id="ready", cell_id="cell", status="ready")
    assert mission_index([history, ready])["cell"] == ready
    assert mission_index([ready, history])["cell"] == ready


def test_foreign_country_switch_closes_forms_before_reading_roster():
    from unittest.mock import Mock

    from src.client.ui.panels.military.covert_action_windows import CovertActionWindows
    windows = CovertActionWindows()
    windows.open("mission", "private")
    presenter = Mock()
    windows.render(None, SimpleNamespace(is_own_country=False), presenter)
    assert windows._active_window == ""
    presenter.covert_cells_for_country.assert_not_called()
