import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from src.client.ui.testing import journey as journey_module
from src.client.ui.testing.journey import (
    JourneyRuntime,
    _assert_action,
    _assert_minimum_dimensions,
    _assert_navigation_request,
    _assert_rect,
    _assert_region,
    _assert_relative_rect,
    _assert_viewport_request,
    _assert_widget,
    action_record,
    run_steps,
)
from src.shared.actions import ActionOfferPeace


RECT = {"x": 10.0, "y": 20.0, "width": 30.0, "height": 15.0}


class FakeTelemetry:
    viewport_size = (200, 120)

    def __init__(self):
        self.widgets = {
            "save": {
                "present": True, "visible": True, "enabled": True,
                "interactive": True, "value": True, "type": "button", "label": "Save",
                "rect": dict(RECT), "components": [],
            },
            "other": {
                "present": True, "visible": True, "enabled": True,
                "interactive": True, "value": None, "type": "button", "label": "Other",
                "rect": {"x": 70.0, "y": 20.0, "width": 20.0, "height": 15.0},
                "components": [],
            },
        }
        self.regions = {
            "panel": {"present": True, "visible": True, "kind": "window", "label": "Panel", "rect": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 80.0}},
            "window": {"present": True, "visible": True, "kind": "window", "label": "Main", "rect": dict(RECT)},
        }

    def widget(self, target):
        return self.widgets.get(target)

    def region(self, selector):
        return self.regions.get(selector)

    def to_dict(self):
        return {"viewport_size": list(self.viewport_size), "widgets": self.widgets}


class FakeDriver:
    def __init__(self, *, present=True):
        self.calls = []
        self.present = present

    def find(self, selector):
        self.calls.append(("find", selector))
        return selector

    def matches(self, selector):
        self.calls.append(("matches", selector))
        return self.present

    def __getattr__(self, name):
        def invoke(*args):
            self.calls.append((name, *args))
        return invoke


def test_action_record_and_action_assertions_cover_count_index_nested_fields_and_tolerance():
    @dataclass
    class Record:
        score: float

    action = ActionOfferPeace(player_id="p", war_id="w-1", source_country_tag="UKR", terms="peace")
    assert action_record(action)["terms"] == "peace"
    assert action_record(Record(1.5)) == {"type": "Record", "score": 1.5}
    assert action_record("finished") == {"type": "str", "value": "finished"}
    _assert_action({"type": "ActionOfferPeace", "fields": {
        "war_id": "w-1", "source_country_tag": "UKR", "terms": "peace"
    }}, [action])
    _assert_action({"type": "Missing", "count": 0}, [action])
    _assert_action({"type": "ActionOfferPeace", "fields": {"player_id": "p"}, "tolerance": 0.1}, [action])

    with pytest.raises(AssertionError, match="Unexpected count"):
        _assert_action({"type": "Missing"}, [action])
    with pytest.raises(ValueError, match="cannot inspect"):
        _assert_action({"type": "Missing", "count": 0, "fields": {"war_id": "w-1"}}, [action])
    with pytest.raises(AssertionError, match="outside"):
        _assert_action({"type": "ActionOfferPeace", "index": 2}, [action])
    with pytest.raises(AssertionError, match="terms"):
        _assert_action({"type": "ActionOfferPeace", "fields": {"terms": "war"}}, [action])
    with pytest.raises(AssertionError, match="score"):
        _assert_action({"type": "Record", "fields": {"score": 2}}, [Record(1.5)])


def test_rectangle_minimum_overlap_and_relative_geometry_assertions():
    _assert_rect(RECT, {"x": 10, "height": 15})
    with pytest.raises(ValueError, match="Unsupported rectangle"):
        _assert_rect(RECT, {"depth": 2})
    with pytest.raises(AssertionError, match="Rectangle x"):
        _assert_rect(RECT, {"x": 20}, tolerance=1)

    _assert_minimum_dimensions({"width": 200, "height": 10}, {"min_width": 300, "min_height": 8}, (200, 120), "Widget")
    with pytest.raises(AssertionError, match="min_height"):
        _assert_minimum_dimensions({"width": 12, "height": 6}, {"min_height": 8}, (200, 120), "Widget")
    assert journey_module._overlap_check_applies({"no_overlap_min_viewport_width": 200}, (200, 100))
    assert not journey_module._overlap_check_applies({"no_overlap_min_viewport_width": 300}, (200, 100))
    assert journey_module._relative_rect_check_applies({"relative_rect_min_viewport_width": 100}, (200, 100))
    assert not journey_module._relative_rect_check_applies({"relative_rect_min_viewport_height": 200}, (200, 100))

    telemetry = FakeTelemetry()
    _assert_relative_rect({"x": 15, "y": 25, "width": 30, "height": 15}, {
        "relative_to": "panel", "relative_rect": {"x": 15, "y": 25, "width": 30},
    }, telemetry)
    with pytest.raises(KeyError, match="No UI region"):
        _assert_relative_rect(RECT, {"relative_to": "missing", "relative_rect": {"x": 0}}, telemetry)
    with pytest.raises(AssertionError, match="Relative x"):
        _assert_relative_rect(RECT, {"relative_to": "panel", "relative_rect": {"x": 0}}, telemetry)


def test_widget_assertions_cover_attributes_parent_overlap_and_viewport_thresholds():
    telemetry = FakeTelemetry()
    driver = FakeDriver()
    _assert_widget({
        "visible": True, "enabled": True, "value": True, "type": "button", "label": "Save",
        "inside": "panel", "no_overlap": "other", "relative_to": "panel",
        "relative_rect": {"x": 10, "y": 20}, "min_width": 20,
    }, "save", telemetry, driver)

    with pytest.raises(AssertionError, match="enabled"):
        _assert_widget({"enabled": False}, "save", telemetry, driver)
    with pytest.raises(AssertionError, match="outside"):
        telemetry.regions["window"]["rect"] = {"x": 50, "y": 50, "width": 5, "height": 5}
        _assert_widget({"inside": "window"}, "save", telemetry, driver)
    telemetry.widgets["other"]["rect"] = dict(RECT)
    with pytest.raises(AssertionError, match="overlap"):
        _assert_widget({"no_overlap": "other"}, "save", telemetry, driver)
    telemetry.viewport_size = (50, 30)
    _assert_widget({"no_overlap": "other", "no_overlap_min_viewport_width": 80}, "save", telemetry, driver)


def test_region_assertions_validate_presence_geometry_viewport_and_overlap():
    telemetry = FakeTelemetry()
    _assert_region({
        "present": True, "visible": True, "kind": "window", "label": "Main",
        "rect": {"x": 10, "y": 20}, "inside_viewport": True,
    }, "window", telemetry)
    with pytest.raises(ValueError, match="exact semantic"):
        _assert_region({}, 12, telemetry)
    with pytest.raises(KeyError, match="No UI region"):
        _assert_region({}, "missing", telemetry)
    with pytest.raises(AssertionError, match="kind"):
        _assert_region({"kind": "popup"}, "window", telemetry)
    with pytest.raises(AssertionError, match="outside the viewport"):
        telemetry.regions["window"]["rect"]["x"] = 190
        _assert_region({"inside_viewport": True}, "window", telemetry)

    telemetry = FakeTelemetry()
    telemetry.regions["window"]["rect"] = {"x": 5, "y": 5, "width": 20, "height": 10}
    with pytest.raises(KeyError, match="not present"):
        telemetry.regions["window"].update(present=False, visible=False)
        _assert_region({}, "window", telemetry)
    _assert_region({"visible": False}, "window", telemetry)
    telemetry.regions["window"]["present"] = True
    telemetry.regions["other"] = {"present": True, "visible": True, "kind": "window", "label": "Other", "rect": {"x": 6, "y": 6, "width": 5, "height": 5}}
    with pytest.raises(AssertionError, match="overlaps"):
        _assert_region({"no_overlap": "other"}, "window", telemetry)
    with pytest.raises(KeyError, match="No UI region"):
        _assert_region({"no_overlap": "missing"}, "window", telemetry)
    telemetry.viewport_size = (50, 30)
    _assert_region({"no_overlap": "other", "no_overlap_min_viewport_width": 80}, "window", telemetry)


def test_request_assertions_support_zero_count_fallback_types_and_field_errors():
    requests = [{"country": "UKR", "country_tag": "UKR", "zoom": 2.0}, {"type": "region", "id": 5}]
    _assert_viewport_request({"type": "country", "fields": {"zoom": 2.001}}, requests)
    _assert_viewport_request({"type": "missing", "count": 0}, requests)
    with pytest.raises(AssertionError, match="Unexpected count"):
        _assert_viewport_request({"type": "map_mode"}, requests)
    with pytest.raises(AssertionError, match="outside"):
        _assert_viewport_request({"type": "country", "index": 1}, requests)
    with pytest.raises(AssertionError, match="country_tag"):
        _assert_viewport_request({"type": "country", "fields": {"country_tag": "POL"}}, requests)

    _assert_navigation_request({"type": "open", "fields": {"type": "open"}}, [{"type": "open"}])
    _assert_navigation_request({"type": "close"}, ["close"])
    _assert_navigation_request({"type": "missing", "count": 0}, [])
    with pytest.raises(ValueError, match="cannot inspect"):
        _assert_navigation_request({"type": "close", "fields": {"x": 1}}, ["close"])
    with pytest.raises(AssertionError, match="Unexpected count"):
        _assert_navigation_request({"type": "open"}, [])
    with pytest.raises(AssertionError, match="outside"):
        _assert_navigation_request({"type": "open", "index": 1}, ["open"])
    with pytest.raises(AssertionError, match="type"):
        _assert_navigation_request({"type": "open", "fields": {"type": "close"}}, [{"type": "open"}])


def test_journey_runtime_dispatches_driver_context_and_fixture_operations(monkeypatch, tmp_path):
    driver = FakeDriver(present=False)
    context = MagicMock()
    telemetry = FakeTelemetry()
    event_sink = Mock()
    snapshot_sink = Mock()
    runtime = JourneyRuntime(
        context, telemetry, driver, [], event_sink, snapshot_sink,
        [{"type": "country", "country": "UKR"}], ["open"],
    )
    monkeypatch.setattr(journey_module, "imgui", SimpleNamespace(Key=SimpleNamespace(a="key-a")))

    for step in (
        {"op": "click", "target": "save"}, {"op": "hold", "target": "save", "frames": 2},
        {"op": "hold", "target": "save", "duration_ms": 25}, {"op": "hover", "target": "save"},
        {"op": "input", "target": "save", "value": "text"}, {"op": "replace", "target": "save", "value": "x"},
        {"op": "replace_text", "target": "save", "value": "y"}, {"op": "drag", "target": "save", "fraction": 0.5},
        {"op": "open", "target": "save"}, {"op": "check", "target": "save", "value": True},
        {"op": "select", "target": "save", "value": "x"}, {"op": "scroll", "target": "save"},
    ):
        runtime.execute(step)
    runtime.execute({"op": "drag_window", "target": "window", "dx": 2, "dy": 3})
    runtime.execute({"op": "close_window", "target": "window"})
    runtime.execute({"op": "key", "key": "a"})
    runtime.execute({"op": "key_down", "key": "a"})
    runtime.execute({"op": "key_up", "key": "a"})
    runtime.execute({"op": "wait", "frames": 3})
    runtime.execute({"op": "assert", "target": "save", "visible": True})
    runtime.execute({"op": "assert_absent", "target": "missing"})
    runtime.execute({"op": "assert_region", "target": "window", "visible": True})
    runtime.execute({"op": "assert_viewport_request", "type": "country", "fields": {"country": "UKR"}})
    runtime.execute({"op": "assert_navigation_request", "type": "open"})
    runtime.execute({"op": "assert_action", "type": "none", "count": 0})
    runtime.execute({"op": "server_event", "target": "connected", "payload": {"value": 1}, "event_id": "e-1"})
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"revision": 4}', encoding="utf-8")
    runtime.execute({"op": "server_snapshot", "fixture": str(snapshot)})

    assert event_sink.call_args.args == ("connected", {"value": 1}, "e-1")
    assert snapshot_sink.call_args.args == ({"revision": 4},)
    with pytest.raises(ValueError, match="Hold must"):
        runtime.execute({"op": "hold", "target": "save", "frames": 0})
    with pytest.raises(ValueError, match="Window drag"):
        runtime.execute({"op": "drag_window", "target": ["bad"], "dx": 1, "dy": 1})
    with pytest.raises(ValueError, match="Window-close"):
        runtime.execute({"op": "close_window", "target": None})
    with pytest.raises(ValueError, match="Unknown ImGui key"):
        runtime.execute({"op": "key", "key": "missing"})
    with pytest.raises(ValueError, match="Wait must"):
        runtime.execute({"op": "wait", "frames": 601})
    with pytest.raises(AssertionError, match="still present"):
        driver.present = True
        runtime.execute({"op": "assert_absent", "target": "save"})
    with pytest.raises(ValueError, match="authoritative event"):
        JourneyRuntime(context, telemetry, driver, []).execute({"op": "server_event", "target": "x", "payload": {}, "event_id": "id"})
    with pytest.raises(ValueError, match="snapshot-delivery"):
        JourneyRuntime(context, telemetry, driver, []).execute({"op": "server_snapshot", "fixture": str(snapshot)})
    with pytest.raises(ValueError, match="Unsupported journey"):
        runtime.execute({"op": "unknown"})


def test_runtime_rejects_invalid_assertion_targets_and_regions():
    runtime = JourneyRuntime(MagicMock(), FakeTelemetry(), FakeDriver(), [])
    with pytest.raises(ValueError, match="exact semantic"):
        runtime.execute({"op": "assert_region", "target": ["window"]})
    with pytest.raises(AssertionError, match="Widget is still present"):
        runtime.driver.present = True
        runtime.execute({"op": "assert_absent", "target": "save"})


def test_checkpoint_capture_saves_snapshot_and_only_error_severity_findings(monkeypatch, tmp_path):
    context = MagicMock()
    context.capture_screenshot.return_value = True
    telemetry = FakeTelemetry()
    monkeypatch.setattr(journey_module, "analyze_layout", lambda _snapshot: [
        {"severity": "warning"}, {"severity": "error", "kind": "overlap"}
    ])

    result = journey_module._capture_checkpoint(context, telemetry, tmp_path, 3, "window")

    image = tmp_path / "003.png"
    assert result["screenshot"] == str(image.resolve())
    assert result["region"] == "window"
    assert result["geometry_errors"] == [{"severity": "error", "kind": "overlap"}]
    assert image.with_suffix(".json").exists()
    context.capture_set_filename.assert_called_once_with(str(image.resolve()))

    context.capture_screenshot.return_value = False
    with pytest.raises(RuntimeError, match="Could not capture destination"):
        journey_module._capture_checkpoint(context, telemetry, tmp_path, 4, "missing")


def test_run_steps_records_success_capture_error_and_stops_after_first_failure(monkeypatch, tmp_path):
    driver = FakeDriver()
    monkeypatch.setattr(journey_module, "UITestDriver", lambda context, telemetry: driver)
    monkeypatch.setattr(journey_module, "imgui", SimpleNamespace(
        test_engine=SimpleNamespace(check=Mock(), TestCheckFlags_=SimpleNamespace(none="none"))
    ))
    telemetry = FakeTelemetry()
    context = MagicMock()
    context.is_error.return_value = False
    results = []
    run_steps(context, telemetry, [{"op": "click", "target": "save"}], [], results)
    assert results == [{"step": 0, "op": "click", "passed": True}]
    assert context.yield_.call_args_list[0].args == (6,)

    context = MagicMock()
    context.is_error.return_value = True
    results = []
    run_steps(context, telemetry, [{"op": "wait", "frames": 0}], [], results)
    assert results[0]["passed"] is False
    assert "rejected" in results[0]["error"]
    journey_module.imgui.test_engine.check.assert_called_once()

    context = MagicMock()
    context.is_error.return_value = False
    context.capture_screenshot.return_value = True
    results = []
    monkeypatch.setattr(journey_module, "analyze_layout", lambda _snapshot: [])
    run_steps(context, telemetry, [{"op": "assert_region", "target": "window"}], [], results, tmp_path)
    assert results[0]["passed"] is True
    assert results[0]["region"] == "window"

    context = MagicMock()
    results = []
    run_steps(context, telemetry, [{"op": "unknown"}, {"op": "click", "target": "save"}], [], results)
    assert len(results) == 1 and results[0]["passed"] is False
