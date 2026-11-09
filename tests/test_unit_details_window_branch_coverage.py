from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.ui.panels.unit_details_window import (
    UnitDetailsPresenter,
    UnitDetailsViewModel,
    UnitDetailsWindow,
    UnitRosterEntry,
)


class _FakeImgui:
    TableFlags_ = SimpleNamespace(borders=1, row_bg=2, scroll_y=4, sizing_stretch_prop=8)
    TableColumnFlags_ = SimpleNamespace(width_fixed=1, width_stretch=2)

    def __init__(self, *, combo_open=False, table_open=True):
        self.combo_open = combo_open
        self.table_open = table_open
        self.calls = []

    def text_disabled(self, value):
        self.calls.append(("text_disabled", value))

    def same_line(self):
        self.calls.append(("same_line",))

    def set_next_item_width(self, width):
        self.calls.append(("set_next_item_width", width))

    def begin_combo(self, *args):
        self.calls.append(("begin_combo", args))
        return self.combo_open

    def selectable(self, *args):
        self.calls.append(("selectable", args))

    def end_combo(self):
        self.calls.append(("end_combo",))

    def text_colored(self, color, value):
        self.calls.append(("text_colored", color, value))

    def text(self, value):
        self.calls.append(("text", value))

    def progress_bar(self, fraction, size, overlay):
        self.calls.append(("progress_bar", fraction, size, overlay))

    def separator(self):
        self.calls.append(("separator",))

    def begin_table(self, *args):
        self.calls.append(("begin_table", args))
        return self.table_open

    def table_setup_column(self, *args):
        self.calls.append(("table_setup_column", args))

    def table_headers_row(self):
        self.calls.append(("table_headers_row",))

    def table_next_row(self):
        self.calls.append(("table_next_row",))

    def table_next_column(self):
        self.calls.append(("table_next_column",))

    def end_table(self):
        self.calls.append(("end_table",))


def _unit_state(unit, **tables):
    return SimpleNamespace(
        tables={"units": pl.DataFrame([unit]), **tables},
        time=SimpleNamespace(total_minutes=0),
    )


def _install_window_ui(monkeypatch, *, imgui, window_open=True):
    module = import_module("src.client.ui.panels.unit_details_window")
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield window_open

    monkeypatch.setattr(module, "imgui", imgui)
    monkeypatch.setattr(module, "WindowManager", SimpleNamespace(window=window))
    monkeypatch.setattr(
        module,
        "GAMETHEME",
        SimpleNamespace(
            colors=SimpleNamespace(text_dim="dim", info="info", text_main="main")
        ),
    )
    return window_calls


def _view_model(*, eta=0, remaining_label="", entries=None, progress=0.0):
    return UnitDetailsViewModel(
        unit_id="unit-1",
        owner_name="United States",
        unit_label="United States Field Artillery",
        entries=tuple(entries or ()),
        readiness_status="ready",
        readiness_target="fortified",
        readiness_progress=progress,
        readiness_eta_minute=eta,
        readiness_remaining_minutes=60 if remaining_label else 0,
        readiness_remaining_label=remaining_label,
    )


def test_presenter_returns_none_for_missing_or_unmatched_units():
    presenter = UnitDetailsPresenter()

    assert presenter.build(None, "unit-1") is None
    assert presenter.build(SimpleNamespace(tables={}), "unit-1") is None
    assert presenter.build(SimpleNamespace(tables={"units": pl.DataFrame()}), "unit-1") is None
    assert presenter.build(
        SimpleNamespace(tables={"units": pl.DataFrame({"other": ["x"]})}), "unit-1",
    ) is None
    assert presenter.build(
        SimpleNamespace(tables={"units": pl.DataFrame({"id": ["unit-2"]})}), "unit-1",
    ) is None


def test_presenter_uses_fallback_names_and_moving_status():
    presenter = UnitDetailsPresenter()
    state = _unit_state(
        {
            "id": "unit-1",
            "owner": "MIA",
            "current_region_id": 7,
            "is_moving": True,
            "unit_type": "air-defense",
            "strength": -3,
        },
        countries=pl.DataFrame({"id": ["MIA"]}),
        regions=pl.DataFrame({"id": [7]}),
    )

    model = presenter.build(state, "unit-1")

    assert model is not None
    assert model.owner_name == "MIA"
    assert model.unit_label == "MIA Air Defense"
    assert model.entries[0] == UnitRosterEntry(
        "Air Defense", 0, "MIA unit · 0 personnel", "Region 7", "Moving",
    )
    assert model.readiness_remaining_minutes == 0
    assert model.readiness_remaining_label == ""


def test_name_resolvers_and_transition_lookup_cover_missing_rows_and_columns():
    presenter = UnitDetailsPresenter()
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame({"id": ["USA"], "name": [""]}),
            "regions": pl.DataFrame({"id": [2], "name": [""]}),
            "unit_readiness_transitions": pl.DataFrame(
                {"unit_id": ["unit-1"], "target_status": ["ready"]}
            ),
        }
    )

    assert presenter._resolve_country_name(state, "USA") == "USA"
    assert presenter._resolve_country_name(state, "") == "Unknown"
    assert presenter._resolve_country_name(
        SimpleNamespace(tables={"countries": pl.DataFrame({"name": ["No id"]})}), "USA",
    ) == "USA"
    assert presenter._resolve_region_name(state, 0) == "Unknown"
    assert presenter._resolve_region_name(state, 2) == "Region 2"
    assert presenter._resolve_region_name(SimpleNamespace(tables={}), 9) == "Region 9"
    assert presenter._readiness_transition(state, "unit-1", "") == {
        "unit_id": "unit-1", "target_status": "ready",
    }
    assert presenter._readiness_transition(state, "other", "") == {}
    assert presenter._readiness_transition(SimpleNamespace(tables={}), "unit-1", "") == {}
    assert presenter._readiness_transition(
        SimpleNamespace(tables={"unit_readiness_transitions": pl.DataFrame()}), "unit-1", "",
    ) == {}
    assert presenter._readiness_transition(
        SimpleNamespace(
            tables={"unit_readiness_transitions": pl.DataFrame({"id": ["t1"]})}
        ),
        "unit-1",
        "t1",
    ) == {}


def test_presenter_formats_remaining_time_and_humanizes_fallback_types():
    presenter = UnitDetailsPresenter()

    assert presenter._format_remaining(90) == "1h"
    assert presenter._format_remaining(-10) == "0h"
    assert presenter._format_remaining(1500) == "1d 1h"
    assert presenter._humanize_unit_type("") == ""
    assert presenter._humanize_unit_type("naval_fleet") == "Naval Fleet"

    state = _unit_state(
        {
            "id": "unit-1",
            "owner": "USA",
            "current_region_id": 0,
            "equipment_quantity": 1200,
            "unit_type": "mechanized_infantry",
            "readiness_status": " parked ",
            "readiness_eta_minute": 90,
        },
        countries=pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
    )
    state.time.total_minutes = 100

    model = presenter.build(state, "unit-1")

    assert model is not None
    assert model.readiness_status == "Parked"
    assert model.readiness_target == "Parked"
    assert model.readiness_remaining_minutes == 0
    assert model.entries[0].quantity == 1200
    assert model.entries[0].troop_type == "Mechanized Infantry"


def test_presenter_formats_active_readiness_transition_progress():
    state = _unit_state(
        {
            "id": "unit-1",
            "owner": "USA",
            "current_region_id": 7,
            "readiness_status": "ready",
            "readiness_transition_id": "transition-1",
            "readiness_progress": 0.375,
        },
        countries=pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
        regions=pl.DataFrame({"id": [7], "name": ["Frontier"]}),
        unit_readiness_transitions=pl.DataFrame(
            {
                "id": ["transition-1"],
                "unit_id": ["unit-1"],
                "target_status": ["fortified"],
                "completes_at_minute": [90],
            }
        ),
    )
    state.time.total_minutes = 30

    model = UnitDetailsPresenter().build(state, "unit-1")

    assert model is not None
    assert model.owner_name == "United States"
    assert model.entries[0].location == "Frontier"
    assert model.entries[0].status == "Ready 38%"
    assert model.readiness_target == "Fortified"
    assert model.readiness_progress == 0.375
    assert model.readiness_remaining_minutes == 60
    assert model.readiness_remaining_label == "1h"


def test_window_handles_closed_empty_and_open_lifecycle(monkeypatch):
    imgui = _FakeImgui()
    _install_window_ui(monkeypatch, imgui=imgui)
    presenter = Mock()
    presenter.build.return_value = None
    window = UnitDetailsWindow(presenter)

    window.render(None)
    assert presenter.build.call_count == 0

    window.open_for_unit("unit-1")
    window.render(None)
    assert presenter.build.call_args.args == (None, "unit-1")
    assert window._is_open is False
    assert window._unit_id is None


def test_window_renders_header_and_roster_rows(monkeypatch):
    imgui = _FakeImgui(combo_open=True, table_open=True)
    window_calls = _install_window_ui(monkeypatch, imgui=imgui)
    presenter = Mock()
    presenter.build.return_value = _view_model(
        eta=120,
        remaining_label="1h",
        progress=1.5,
        entries=(
            UnitRosterEntry("Infantry", 1200, "USA unit", "Texas", "Moving"),
            UnitRosterEntry("Armor", 5, "USA unit", "Oklahoma", "Ready"),
        ),
    )
    window = UnitDetailsWindow(presenter)
    window.open_for_unit("unit-1")

    window.render(SimpleNamespace())

    assert window_calls[0][0] == ("UNIT LIST##unit-1",)
    assert ("progress_bar", 1.0, (-1.0, 12.0), "") in imgui.calls
    assert ("text", "Readiness: Ready → fortified | 1h remaining") in imgui.calls
    assert ("text", "1 200") in imgui.calls
    assert ("text_colored", "info", "Moving") in imgui.calls
    assert ("text_colored", "main", "Ready") in imgui.calls
    assert ("end_combo",) in imgui.calls
    assert ("end_table",) in imgui.calls


def test_window_closes_when_imgui_window_is_closed_and_skips_closed_table(monkeypatch):
    closed_imgui = _FakeImgui()
    _install_window_ui(monkeypatch, imgui=closed_imgui, window_open=False)
    presenter = Mock()
    presenter.build.return_value = _view_model()
    closed_window = UnitDetailsWindow(presenter)
    closed_window.open_for_unit("unit-1")

    closed_window.render(SimpleNamespace())

    assert closed_window._is_open is False
    assert closed_window._unit_id is None
    assert not any(call[0] == "begin_combo" for call in closed_imgui.calls)

    table_imgui = _FakeImgui(combo_open=False, table_open=False)
    _install_window_ui(monkeypatch, imgui=table_imgui)
    table_window = UnitDetailsWindow(presenter)
    table_window.open_for_unit("unit-1")

    table_window.render(SimpleNamespace())

    assert ("begin_combo", ("##unit_type_filter", "All")) in table_imgui.calls
    assert not any(call[0] == "end_combo" for call in table_imgui.calls)
    assert not any(call[0] == "table_setup_column" for call in table_imgui.calls)
