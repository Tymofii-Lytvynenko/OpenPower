from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.service import history_panel as history_module
from src.client.ui.panels.service.history_panel import HistoryPanel


class FakeWidgets:
    def __init__(self, *, button=False, rect=None):
        self.button_result = button
        self.rect_result = rect
        self.calls = []

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return self.button_result

    def path(self, slot):
        return slot

    def rect(self, slot):
        self.calls.append(("rect", slot))
        return self.rect_result

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))


class FakeImGui:
    StyleVar_ = SimpleNamespace(frame_padding="frame_padding")

    def __init__(self, **overrides):
        self.messages = []
        self.clipboard = None
        self.combo_result = (False, 0)
        self.popup_open = False
        self.combo_open = False
        self.begin_disabled_calls = 0
        self.end_disabled_calls = 0
        self.end_popup_calls = 0
        self.end_combo_calls = 0
        self.selectable_labels = set()
        self.overrides = overrides

    def __getattr__(self, name):
        if name in self.overrides:
            return self.overrides[name]
        raise AttributeError(name)

    def push_style_var(self, *args):
        self.messages.append(("push_style_var", args))

    def pop_style_var(self):
        self.messages.append(("pop_style_var",))

    def begin_disabled(self):
        self.begin_disabled_calls += 1

    def end_disabled(self):
        self.end_disabled_calls += 1

    def combo(self, *args, **kwargs):
        self.messages.append(("combo", args, kwargs))
        return self.combo_result

    def begin_combo(self, *args, **kwargs):
        return self.combo_open

    def end_combo(self):
        self.end_combo_calls += 1

    def begin_popup(self, *args, **kwargs):
        return self.popup_open

    def end_popup(self):
        self.end_popup_calls += 1

    def input_text(self, label, value, size):
        return True, self.overrides.get("search", value)

    def selectable(self, label, selected):
        return label in self.selectable_labels, selected

    def checkbox(self, label, selected):
        return self.overrides.get("checkbox", {}).get(label, (False, selected))

    def text(self, message):
        self.messages.append(("text", message))

    def text_disabled(self, message):
        self.messages.append(("text_disabled", message))

    def text_colored(self, *args, **kwargs):
        self.messages.append(("text_colored", args, kwargs))

    def button(self, label):
        return label in self.overrides.get("buttons", set())

    def set_clipboard_text(self, value):
        self.clipboard = value

    def separator(self):
        pass

    def same_line(self):
        pass


def test_render_closes_panel_hides_markers_and_clamps_window_position(monkeypatch):
    fake = FakeImGui(get_main_viewport=Mock(return_value=SimpleNamespace(size=SimpleNamespace(x=1200, y=800))))
    monkeypatch.setattr(history_module, "imgui", fake)
    layout = SimpleNamespace(width=1000, height=700)
    monkeypatch.setattr(history_module, "get_gml_layout", lambda _name: layout)
    window_args = []

    @contextmanager
    def window(*args, **kwargs):
        window_args.append(kwargs)
        yield False

    monkeypatch.setattr(history_module.WindowManager, "window", window)
    panel = HistoryPanel()
    panel._history_event_markers = Mock()

    assert panel.render(object(), PanelRenderContext(target_tag="USA", is_own_country=True)) is False

    assert window_args[0]["x"] == 200
    assert window_args[0]["y"] == 90
    panel._history_event_markers.hide.assert_called_once()


def test_render_draws_content_and_event_tooltip_when_open(monkeypatch):
    fake = FakeImGui(get_main_viewport=Mock(return_value=SimpleNamespace(size=SimpleNamespace(x=600, y=400))))
    monkeypatch.setattr(history_module, "imgui", fake)
    monkeypatch.setattr(history_module, "get_gml_layout", lambda _name: SimpleNamespace(width=800, height=500))

    @contextmanager
    def window(*args, **kwargs):
        yield True

    monkeypatch.setattr(history_module.WindowManager, "window", window)
    panel = HistoryPanel()
    panel._render_content = Mock()
    panel._history_event_markers = Mock()
    state = object()
    context = PanelRenderContext(target_tag="USA", is_own_country=True)

    assert panel.render(state, context) is True

    panel._render_content.assert_called_once_with(state, context)
    panel._history_event_markers.render_tooltip.assert_called_once()


def test_content_shows_initial_empty_state_and_opens_analysis_popup(monkeypatch):
    title_ui = FakeWidgets(button=True)
    monkeypatch.setattr(history_module, "GMLWidgets", lambda prefix: title_ui if prefix.endswith("frmTitle") else FakeWidgets())
    fake = FakeImGui(open_popup=Mock())
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._render_indicator_selector = Mock(return_value=None)
    panel._render_chart_message = Mock()
    panel._render_analysis_popup = Mock()
    panel._history_event_markers = Mock()
    state = SimpleNamespace(tables={}, time=SimpleNamespace(total_minutes=100))

    panel._render_content(state, PanelRenderContext(target_tag="USA", is_own_country=True))

    fake.open_popup.assert_called_once_with("HistoryAnalytics")
    panel._history_event_markers.hide.assert_called_once()
    panel._render_chart_message.assert_called_once_with("Historical data will appear after the first simulation update.")
    panel._render_analysis_popup.assert_called_once_with(state, [], 0, 100, [])


def test_content_handles_subjectless_indicator_and_renders_selected_series(monkeypatch):
    widgets = []

    def make_widgets(prefix):
        ui = FakeWidgets()
        widgets.append((prefix, ui))
        return ui

    monkeypatch.setattr(history_module, "GMLWidgets", make_widgets)
    monkeypatch.setattr(history_module, "imgui", FakeImGui())
    panel = HistoryPanel()
    panel._render_indicator_selector = Mock(return_value={
        "id": "country.population", "subject_type": "country", "unit": "people",
    })
    panel._render_chart_message = Mock()
    panel._render_time_ticks = Mock()
    panel._draw_trend = Mock()
    panel._render_analysis_popup = Mock()
    panel._history_events = Mock(return_value=[])
    state = SimpleNamespace(tables={}, time=SimpleNamespace(total_minutes=500))
    context = PanelRenderContext(target_tag="USA", is_own_country=True)

    panel._subjects = Mock(return_value=[])
    panel._history_event_markers = Mock()
    panel._render_content(state, context)
    panel._render_chart_message.assert_called_once_with("No subjects currently provide this indicator.")
    panel._history_event_markers.hide.assert_called_once()

    panel._render_chart_message.reset_mock()
    panel._subjects.return_value = ["CAN", "USA"]
    panel._queries = Mock()
    panel._queries.series.return_value = [{"value": None}, {"value": 4}, {"value": 12}]
    panel._history_events.return_value = [{"title": "event"}]
    panel._render_content(state, context)

    assert panel._subject_id == "USA"
    panel._queries.series.assert_called_once()
    panel._render_time_ticks.assert_called_once()
    panel._draw_trend.assert_called_once_with(
        [{"value": None}, {"value": 4}, {"value": 12}], "people",
        events=[{"title": "event"}], start_minute=0, end_minute=500, step=False,
    )
    panel._render_analysis_popup.assert_called_with(state, ["CAN", "USA"], 0, 500, panel._queries.series.return_value)
    graph = next(ui for prefix, ui in widgets if prefix.endswith("frmGraph"))
    assert [call[1][1] for call in graph.calls if call[0] == "text"] == ["4", "12"]


def test_content_uses_selected_region_as_default_subject(monkeypatch):
    monkeypatch.setattr(history_module, "GMLWidgets", lambda _prefix: FakeWidgets())
    monkeypatch.setattr(history_module, "imgui", FakeImGui())
    panel = HistoryPanel()
    panel._render_indicator_selector = Mock(return_value={
        "id": "region.population", "subject_type": "region", "unit": "people",
    })
    panel._subjects = Mock(return_value=["2", "3"])
    panel._queries = Mock()
    panel._queries.series.return_value = []
    panel._history_events = Mock(return_value=[])
    panel._render_time_ticks = Mock()
    panel._draw_trend = Mock()
    panel._render_analysis_popup = Mock()
    state = SimpleNamespace(tables={}, time=SimpleNamespace(total_minutes=500))

    panel._render_content(
        state,
        PanelRenderContext(target_tag="USA", is_own_country=False, selected_region_id=2),
    )

    assert panel._subject_id == "2"


def test_indicator_selector_disables_empty_state_and_restores_imgui_style(monkeypatch):
    fake = FakeImGui()
    monkeypatch.setattr(history_module, "imgui", fake)

    result = HistoryPanel()._render_indicator_selector([], FakeWidgets())

    assert result is None
    assert fake.begin_disabled_calls == 1
    assert fake.end_disabled_calls == 1
    assert ("pop_style_var",) in fake.messages


def test_indicator_selector_sorts_options_and_applies_selected_indicator(monkeypatch):
    fake = FakeImGui()
    fake.combo_result = (True, 1)
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "unsupported"
    definitions = [
        {"id": "region.population", "subject_type": "region"},
        {"id": "country.gdp", "subject_type": "country"},
        {"id": "country.population", "subject_type": "country"},
    ]

    selected = panel._render_indicator_selector(definitions, FakeWidgets())

    assert panel._subject_type == "country"
    assert panel._indicator_id == "country.gdp"
    assert selected["id"] == "country.gdp"
    combo = next(call for call in fake.messages if call[0] == "combo")
    assert combo[1][2] == ["Population (country)", "Country / Gdp (country)", "Region / Population (region)"]


def test_indicator_selector_uses_saved_indicator_when_combo_unchanged(monkeypatch):
    fake = FakeImGui()
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._indicator_id = "country.population"
    definitions = [
        {"id": "country.population", "subject_type": "country"},
        {"id": "country.gdp", "subject_type": "country"},
    ]

    selected = panel._render_indicator_selector(definitions, FakeWidgets())

    assert selected["id"] == "country.population"
    assert panel._indicator_id == "country.population"


def test_subject_selector_filters_and_selects_subject(monkeypatch):
    fake = FakeImGui(search=" mex ")
    fake.combo_open = True
    fake.selectable_labels = {"MEX"}
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_id = "USA"

    panel._render_subject_selector(["USA", "MEX", "CAN"])

    assert panel._subject_search == " mex "
    assert panel._subject_id == "MEX"


def test_subject_selector_reports_no_matches_and_caps_visible_subjects(monkeypatch):
    fake = FakeImGui(search="absent")
    fake.combo_open = True
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()

    panel._render_subject_selector([f"C{i}" for i in range(250)])

    assert ("text_disabled", "No matching subjects.") in fake.messages
    fake = FakeImGui(search="")
    fake.combo_open = True
    monkeypatch.setattr(history_module, "imgui", fake)
    panel._render_subject_selector([f"C{i}" for i in range(250)])
    assert fake.end_combo_calls == 1


def test_time_range_granularity_and_ticks_update_selected_values(monkeypatch):
    fake = FakeImGui()
    fake.combo_result = (True, 0)
    fake.combo_open = True
    fake.selectable_labels = {"1 week"}

    def selectable(label, selected):
        return label == "1 week", selected

    fake.selectable = selectable
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    ui = FakeWidgets()

    panel._render_time_range_selector()
    panel._render_granularity_selector()
    panel._render_time_ticks(ui, 900)

    assert panel._range_minutes == 30 * 1440
    assert panel._granularity_minutes == 10080
    assert fake.end_combo_calls == 1
    assert len([call for call in ui.calls if call[0] == "text"]) == 6
    assert ui.calls[0][1][1] == "-30d"
    assert ui.calls[-1][1][1] == "now"


def test_chart_message_uses_empty_state_when_layout_is_unavailable(monkeypatch):
    monkeypatch.setattr(history_module, "GMLWidgets", lambda _prefix: FakeWidgets())
    monkeypatch.setattr(history_module, "active_gml_layout", lambda: None)
    empty = Mock()
    monkeypatch.setattr(history_module, "draw_empty_state", empty)

    HistoryPanel()._render_chart_message("Nothing yet")

    empty.assert_called_once_with("Nothing yet")


def test_chart_message_draws_wrapped_text_inside_active_layout(monkeypatch):
    rect = SimpleNamespace(x=10, y=20, width=200, height=80)
    session = SimpleNamespace(window_position=(50, 70))
    monkeypatch.setattr(history_module, "GMLWidgets", lambda _prefix: FakeWidgets(rect=rect))
    monkeypatch.setattr(history_module, "active_gml_layout", lambda: session)
    suspended = object()
    suspend = Mock(return_value=suspended)
    resume = Mock()
    monkeypatch.setattr(history_module, "suspend_gml_layout", suspend)
    monkeypatch.setattr(history_module, "resume_gml_layout", resume)
    draw = Mock()
    fake = FakeImGui(
        set_cursor_screen_pos=Mock(),
        get_window_draw_list=Mock(return_value=draw),
        get_color_u32=Mock(side_effect=lambda color: color),
        get_cursor_pos_x=Mock(return_value=4.0),
        push_text_wrap_pos=Mock(),
        pop_text_wrap_pos=Mock(),
        invisible_button=Mock(),
    )
    monkeypatch.setattr(history_module, "imgui", fake)

    HistoryPanel()._render_chart_message("A long empty-state explanation")

    assert draw.add_rect_filled.called
    assert draw.add_rect.called
    assert fake.invisible_button.call_args.args == ("##history_chart_empty", (200, 80))
    fake.push_text_wrap_pos.assert_called_once_with(188.0)
    fake.pop_text_wrap_pos.assert_called_once()
    suspend.assert_called_once()
    resume.assert_called_once_with(suspended)


def test_analysis_popup_returns_cleanly_for_closed_and_empty_states(monkeypatch):
    fake = FakeImGui()
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._render_analysis_popup(object(), [], 0, 10, [])
    assert fake.end_popup_calls == 0

    fake.popup_open = True
    panel._render_analysis_popup(object(), [], 0, 10, [])
    assert fake.end_popup_calls == 1
    assert ("text_disabled", "Additional analysis is available after history indicators are recorded.") in fake.messages


def test_analysis_popup_composes_all_analysis_sections(monkeypatch):
    fake = FakeImGui(checkbox={"Step trend": (True, True)})
    fake.popup_open = True
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._render_subject_selector = Mock()
    panel._render_time_range_selector = Mock()
    panel._render_granularity_selector = Mock()
    panel._render_comparison = Mock(return_value={"comparison": True})
    panel._render_ranking = Mock()
    panel._render_timelines = Mock(return_value=[{"event": True}])
    panel._render_export = Mock()
    state = object()
    series = [{"value": 1}]

    panel._render_analysis_popup(state, ["USA", "CAN"], 0, 50, series)

    assert panel._step_trend is True
    panel._render_subject_selector.assert_called_once_with(["USA", "CAN"])
    panel._render_comparison.assert_called_once_with(state, ["USA", "CAN"], 0, 50)
    panel._render_export.assert_called_once_with(series, {"comparison": True}, [{"event": True}])
    assert fake.end_popup_calls == 1


def test_comparison_handles_incompatible_units_missing_values_and_csv(monkeypatch):
    fake = FakeImGui(buttons={"Copy comparison CSV"})
    fake.checkbox = lambda _label, selected: (False, False)
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._indicator_id = "country.gdp"
    panel._queries = Mock()
    panel._queries.compare.return_value = {
        "common_values": {"USA": {"value": 10, "unit": "USD"}},
        "unit_compatible": False,
        "evaluation_minute": None,
    }
    panel._queries.export_csv.return_value = "csv-data"

    result = panel._render_comparison(object(), ["USA", "CAN"], None, 10)

    assert result["unit_compatible"] is False
    assert panel._comparison_initialized is True
    assert panel._comparison_ids == {"CAN"}
    assert ("text", "  USA: 10.000 USD") in fake.messages
    assert ("text", "  CAN: unavailable") in fake.messages
    assert any(call[0] == "text_colored" for call in fake.messages)
    assert panel._queries.export_csv.called
    assert fake.clipboard == "csv-data"


def test_comparison_skips_unsupported_subjects_and_small_subject_sets(monkeypatch):
    monkeypatch.setattr(history_module, "imgui", FakeImGui())
    panel = HistoryPanel()
    panel._subject_type = "relationship"
    assert panel._render_comparison(None, ["USA", "CAN"], 0, 10) is None
    panel._subject_type = "country"
    assert panel._render_comparison(None, ["USA"], 0, 10) is None


def test_comparison_removes_deselected_subject_from_open_combo(monkeypatch):
    fake = FakeImGui(checkbox={"CAN": (True, False)})
    fake.combo_open = True
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._comparison_initialized = True
    panel._comparison_ids = {"CAN"}
    panel._queries = Mock()
    panel._queries.compare.return_value = {
        "common_values": {}, "unit_compatible": True, "evaluation_minute": None,
    }

    panel._render_comparison(object(), ["USA", "CAN"], 0, 10)

    assert panel._comparison_ids == set()
    assert fake.end_combo_calls == 1


def test_comparison_reports_subjects_without_normalization_baseline(monkeypatch):
    fake = FakeImGui()
    fake.checkbox = lambda _label, selected: (False, selected)
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._indicator_id = "country.gdp"
    panel._queries = Mock()
    panel._queries.compare.return_value = {
        "common_values": {},
        "normalized_common_values": {},
        "normalization_basis": "First positive value is 100.",
        "normalization_unavailable_subjects": ["CAN"],
        "unit_compatible": False,
        "evaluation_minute": 10,
    }

    panel._render_comparison(object(), ["USA", "CAN"], 0, 10)

    assert any(
        message[0] == "text_disabled" and message[1] == "No compatible positive baseline for: CAN"
        for message in fake.messages
    )


def test_ranking_skips_non_country_and_reports_boundary_exclusions(monkeypatch):
    fake = FakeImGui(checkbox={"Highest first": (False, True)})
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "region"
    panel._render_ranking(object(), 0, 20)
    assert fake.messages == []

    panel._subject_type = "country"
    panel._indicator_id = "country.gdp"
    panel._queries = Mock()
    panel._queries.rank.return_value = {
        "evaluation_minute": None,
        "rows": [{"subject_id": "USA", "value": 2, "unit": "index"}, {"subject_id": "CAN", "value": 3}],
        "freshness_by_subject": {},
        "incompatible_unit_subjects": ["MEX"],
        "excluded": ["MEX", "USA"],
        "ties": [{"value": 2, "unit": "index", "subjects": ["USA", "CAN"]}],
    }
    panel._render_ranking(object(), None, 20)
    assert any("all recorded history · highest first · common boundary unavailable" in message[1] for message in fake.messages if message[0] == "text")
    assert any("unknown age" in message[1] for message in fake.messages if message[0] == "text")
    assert any("Excluded for incompatible units: MEX" in message[1] for message in fake.messages if message[0] == "text_colored")
    assert any("Unavailable at boundary: USA" in message[1] for message in fake.messages if message[0] == "text_disabled")


def test_timelines_cover_relationship_event_and_empty_branches(monkeypatch):
    fake = FakeImGui(buttons={"Copy event timeline CSV"})
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._subject_type = "relationship"
    panel._subject_id = "CAN|USA"
    panel._queries = Mock()
    panel._queries.relationship_timeline.return_value = [
        {"game_minute": 4, "title": "Created", "cause_source_type": "diplomacy", "cause_source_id": "treaty"},
        {"game_minute": 5, "event_type": "Changed"},
    ]

    state = object()
    events = panel._render_timelines(state, 100)
    assert events[0]["title"] == "Created"
    assert panel._queries.export_csv.called
    panel._queries.relationship_timeline.assert_called_once_with(state, "CAN", "USA")

    panel._subject_type = "country"
    panel._subject_id = "USA"
    panel._queries.event_timeline.return_value = []
    empty = panel._render_timelines(state, 100)
    assert empty == []
    assert ("text_disabled", "No attributable events are recorded in this period.") in fake.messages


def test_history_events_filters_relationship_rows_and_delegates_other_subjects():
    panel = HistoryPanel()
    panel._subject_type = "relationship"
    panel._subject_id = "CAN|USA"
    panel._queries = Mock()
    panel._queries.relationship_timeline.return_value = [
        {"timeline_kind": "event", "game_minute": 5},
        {"timeline_kind": "status", "game_minute": 5},
        {"timeline_kind": "event", "game_minute": 12},
    ]
    assert panel._history_events(object(), 5, 10) == [{"timeline_kind": "event", "game_minute": 5}]

    panel._subject_type = "region"
    panel._subject_id = "8"
    panel._queries.event_timeline.return_value = [{"title": "found"}]
    assert panel._history_events(object(), 2, 20) == [{"title": "found"}]
    args, kwargs = panel._queries.event_timeline.call_args
    assert kwargs["subject_type"] == "region"
    assert kwargs["subject_id"] == "8"
    assert kwargs["country_ids"] == ()


def test_subjects_returns_copies_from_cache_when_tables_are_missing():
    panel = HistoryPanel()
    state = SimpleNamespace(tables={}, table_revisions={})

    first = panel._subjects(state, "country")
    first.append("MUTATED")

    assert panel._subjects(state, "country") == []


def test_draw_trend_fallback_marks_gaps_and_formats_empty_data(monkeypatch):
    monkeypatch.setattr(history_module, "active_gml_layout", lambda: None)
    draw = Mock()
    fake = FakeImGui(
        get_content_region_avail=Mock(return_value=SimpleNamespace(x=320)),
        get_cursor_screen_pos=Mock(return_value=SimpleNamespace(x=2, y=3)),
        get_window_draw_list=Mock(return_value=draw),
        get_color_u32=Mock(side_effect=lambda color: color),
        dummy=Mock(),
        text_disabled=Mock(),
    )
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()

    panel._draw_trend([{"value": 1}, {"value": 3}, {"value": None}, {"value": 5}], "", events=[], start_minute=0, end_minute=10, step=True)

    assert draw.add_rect_filled.called
    assert draw.add_line.call_count == 3
    assert any(
        message[0] == "text_disabled" and message[1].startswith("Min 1.000")
        and "unit unspecified" in message[1] and "step trend" in message[1]
        for message in fake.messages
    )

    empty_state = Mock()
    monkeypatch.setattr(history_module, "draw_empty_state", empty_state)
    panel._draw_trend([{"value": None}], "people", events=[], start_minute=0, end_minute=10)
    empty_state.assert_called_once_with("No historical samples in this range; no zero line is implied.")


def test_draw_trend_layout_plots_records_and_event_markers(monkeypatch):
    component = object()
    rect = SimpleNamespace(x=10, y=20, width=200, height=100)
    layout = SimpleNamespace(width=800, height=600, component=Mock(return_value=component))
    session = SimpleNamespace(
        layout=layout,
        window_position=(50, 70),
        rect_for=Mock(return_value=rect),
    )
    monkeypatch.setattr(history_module, "active_gml_layout", lambda: session)
    draw = Mock()
    fake = FakeImGui(
        get_window_draw_list=Mock(return_value=draw),
        get_color_u32=Mock(side_effect=lambda color: color),
        set_cursor_screen_pos=Mock(),
        invisible_button=Mock(),
    )
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()
    panel._history_event_markers = Mock()
    events = [{"title": "Test"}]

    panel._draw_trend([
        {"game_minute": "bad", "value": 1},
        {"game_minute": 3, "value": 2},
        {"game_minute": 5, "value": None},
        {"game_minute": 10, "value": 3},
    ], "index", events=events, start_minute=0, end_minute=10, step=True)

    assert draw.add_rect_filled.call_count >= 2
    assert draw.add_line.call_count >= 9
    panel._history_event_markers.draw.assert_called_once()
    marker_kwargs = panel._history_event_markers.draw.call_args.kwargs
    assert marker_kwargs["chart_rect"] == (60, 90, 200, 100)
    assert marker_kwargs["start_minute"] == 0
    fake.invisible_button.assert_called_once()

    panel._draw_trend([{"value": None}], "index", events=[], start_minute=0, end_minute=10)
    assert draw.add_text.called


def test_export_reports_empty_selection_without_copying(monkeypatch):
    fake = FakeImGui(buttons={"Copy selected series as CSV"})
    monkeypatch.setattr(history_module, "imgui", fake)
    panel = HistoryPanel()

    panel._render_export([], comparison=None, timeline=[])

    assert panel._export_status == "There are no samples to export."
    assert fake.clipboard is None
    assert ("text_disabled", "There are no samples to export.") in fake.messages


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        (10, "10"),
        (-12345, "-12k"),
        (1_250_000, "1.2m"),
        (1_250_000_000, "1.2b"),
    ],
)
def test_axis_and_value_formatting_handles_ranges_and_missing(value, expected):
    assert HistoryPanel._axis_value(value) == expected
    if value is None:
        assert HistoryPanel._format_value(value, "index") == "unavailable"
    else:
        assert HistoryPanel._format_value(value, " index ").endswith("index")
