from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import src.client.ui.panels.service.history_event_marker_layer as marker_module
from src.client.ui.panels.service.history_event_marker_layer import HistoryEventMarkerLayer


def test_markers_filter_events_merge_nearby_minutes_and_place_separate_groups():
    events = [
        {"game_minute": -1, "title": "Before"},
        {"game_minute": 0, "title": "Start"},
        {"game_minute": 1, "title": "Near"},
        {"game_minute": 10, "title": "Middle"},
        {"game_minute": 100, "title": "End"},
        {"game_minute": 101, "title": "After"},
    ]

    markers = HistoryEventMarkerLayer._markers(events, (0.0, 0.0, 100.0, 30.0), 0, 100)

    assert [marker.test_id for marker in markers] == [
        "history.event_marker.0",
        "history.event_marker.1",
        "history.event_marker.2",
    ]
    assert markers[0].x == pytest.approx(1.95)
    assert markers[0].y == 23.0
    assert "Start" in markers[0].text
    assert "Near" in markers[0].text


def test_markers_handle_zero_span_narrow_chart_and_empty_events():
    marker = HistoryEventMarkerLayer._markers(
        [{"game_minute": 5, "title": "At current time"}],
        (10.0, 4.0, 5.0, 12.0),
        5,
        5,
    )[0]

    assert marker.x == 11.5
    assert marker.y == 9.0
    assert HistoryEventMarkerLayer._markers([], (0.0, 0.0, 100.0, 30.0), 0, 10) == []


def test_marker_text_formats_fallback_titles_causes_and_overflow():
    events = [
        {
            "game_minute": 1000,
            "title": "",
            "event_type": " Treaty ",
            "cause_source_type": " policy ",
            "cause_source_id": " 7 ",
        },
        {"game_minute": 0, "cause_source_id": "src"},
        {"game_minute": 30, "title": " Battle "},
        {"game_minute": 40, "title": "Election", "cause_source_type": "  "},
        {"game_minute": 50, "title": "Campaign"},
    ]

    text = HistoryEventMarkerLayer._marker_text(events)

    assert text.splitlines() == [
        "Treaty · minute 1,000",
        "Cause: policy 7",
        "Recorded event · minute 0",
        "Cause:  src",
        "Battle · minute 30",
        "Election · minute 40",
        "1 more events at this time",
    ]
    assert HistoryEventMarkerLayer._marker_text([]) == ""


def test_draw_highlights_only_hovered_marker_and_updates_tooltip(monkeypatch):
    imgui = Mock()
    imgui.get_mouse_pos.side_effect = [
        SimpleNamespace(x=3.0, y=24.0),
        SimpleNamespace(x=50.0, y=50.0),
    ]
    monkeypatch.setattr(marker_module, "imgui", imgui)
    tooltip = Mock()
    monkeypatch.setattr(marker_module, "HistoryTooltipWindow", Mock(return_value=tooltip))
    layer = HistoryEventMarkerLayer()
    origin, size = (20.0, 30.0), (400.0, 220.0)

    layer.draw(
        [{"game_minute": 0, "title": "Start"}, {"game_minute": 100, "title": "End"}],
        chart_rect=(0.0, 0.0, 100.0, 30.0),
        start_minute=0,
        end_minute=100,
        parent_origin=origin,
        parent_size=size,
    )

    markers = HistoryEventMarkerLayer._markers(
        [{"game_minute": 0, "title": "Start"}, {"game_minute": 100, "title": "End"}],
        (0.0, 0.0, 100.0, 30.0), 0, 100,
    )
    draw = imgui.get_window_draw_list.return_value
    assert draw.add_rect_filled.call_count == 2
    assert draw.add_rect.call_count == 3
    assert imgui.dummy.call_count == 2
    tooltip.update_hover.assert_called_once_with(
        markers,
        "history.event_marker.0",
        parent_origin=origin,
        parent_size=size,
    )


def test_draw_empty_events_and_tooltip_methods_delegate(monkeypatch):
    imgui = Mock()
    monkeypatch.setattr(marker_module, "imgui", imgui)
    tooltip = Mock()
    tooltip.render.return_value = True
    monkeypatch.setattr(marker_module, "HistoryTooltipWindow", Mock(return_value=tooltip))
    layer = HistoryEventMarkerLayer()

    layer.draw(
        [],
        chart_rect=(0.0, 0.0, 100.0, 30.0),
        start_minute=0,
        end_minute=10,
        parent_origin=(0.0, 0.0),
        parent_size=(100.0, 30.0),
    )

    assert layer.render_tooltip() is True
    layer.hide()
    tooltip.update_hover.assert_called_once_with(
        [], None, parent_origin=(0.0, 0.0), parent_size=(100.0, 30.0),
    )
    tooltip.hide.assert_called_once_with()
