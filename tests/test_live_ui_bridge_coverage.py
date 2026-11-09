import json
import sys
import types
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from src.client.ui.testing import live_bridge as bridge_module
from src.client.ui.testing.live_bridge import LiveUIBridge


class FakeTelemetry:
    def __init__(self):
        self.viewport_size = (1, 1)
        self.frame_count = 0
        self.errors = []
        self.widgets = {}

    def record_error(self, source, message):
        self.errors.append((source, message))

    def to_dict(self):
        return {"viewport_size": self.viewport_size, "frame_count": self.frame_count}

    def widget(self, target):
        return self.widgets[target]

    @contextmanager
    def frame(self):
        self.frame_count += 1
        yield


class FakeFuture:
    def __init__(self, result=None, error=None, done=True):
        self.value = result
        self.error = error
        self.is_done = done

    def done(self):
        return self.is_done

    def result(self):
        if self.error:
            raise self.error
        return self.value


class InlineExecutor:
    def __init__(self, **_kwargs):
        self.shutdown_called = False
        self.submissions = 0

    def submit(self, function, *args):
        self.submissions += 1
        try:
            return FakeFuture(function(*args))
        except Exception as exc:
            return FakeFuture(error=exc)

    def shutdown(self, *, wait):
        self.shutdown_called = wait


class FakeDriver:
    def __init__(self, _context, telemetry):
        self.telemetry = telemetry

    def find(self, target):
        return target


def harness(monkeypatch, directory, *, interval=0.5, capture=None, inspection_provider=None):
    telemetry = FakeTelemetry()
    io = SimpleNamespace(
        add_key_event=Mock(),
        add_mouse_button_event=Mock(),
        add_mouse_pos_event=Mock(),
        add_mouse_wheel_event=Mock(),
        add_input_characters_utf8=Mock(),
    )
    imgui = SimpleNamespace(
        Key=SimpleNamespace(mod_ctrl="ctrl", a="a", enter="enter"),
        get_io=lambda: io,
    )
    arcade = SimpleNamespace(MOUSE_BUTTON_LEFT=1, MOUSE_BUTTON_RIGHT=2, MOUSE_BUTTON_MIDDLE=3)
    monkeypatch.setattr(bridge_module, "UIRunTelemetry", lambda *_args, **_kwargs: telemetry)
    monkeypatch.setattr(bridge_module, "UITestDriver", FakeDriver)
    monkeypatch.setattr(bridge_module, "imgui", imgui)
    monkeypatch.setattr(bridge_module, "arcade", arcade)
    monkeypatch.setattr(bridge_module, "ThreadPoolExecutor", InlineExecutor)
    monkeypatch.setattr(bridge_module, "analyze_layout", lambda snapshot: [{"frame": snapshot["frame_count"]}])
    bridge = LiveUIBridge(
        Path(directory), capture=capture, interval=interval,
        inspection_provider=inspection_provider,
    )
    return bridge, telemetry, io


def widget(*, visible=True, enabled=True, interactive=True, widget_type="button", components=None):
    return {
        "visible": visible,
        "enabled": enabled,
        "interactive": interactive,
        "type": widget_type,
        "rect": {"x": 10.0, "y": 20.0, "width": 40.0, "height": 10.0},
        "components": components or [],
    }


def test_constructor_restores_receipts_and_marks_unacknowledged_commands_interrupted(monkeypatch, tmp_path):
    (tmp_path / "receipts.json").write_text(json.dumps({"ids": ["done", "pending"]}), encoding="utf-8")
    (tmp_path / "report.json").write_text(
        json.dumps({"commands": [{"id": "done", "passed": True}]}), encoding="utf-8"
    )
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)

    assert bridge._seen == {"done", "pending"}
    assert bridge.results[0]["id"] == "done"
    assert bridge.results[1] == {
        "id": "pending",
        "passed": False,
        "status": "interrupted",
        "error": "Runtime changed before dispatch acknowledgement.",
    }
    bridge.close()


def test_constructor_records_invalid_persisted_files_without_failing(monkeypatch, tmp_path):
    (tmp_path / "receipts.json").write_text("{broken", encoding="utf-8")
    bridge, telemetry, _io = harness(monkeypatch, tmp_path)
    assert telemetry.errors and telemetry.errors[0][0] == "live receipts"
    bridge.close()


def test_commands_are_acknowledged_after_key_events_and_receipts_prevent_replay(monkeypatch, tmp_path):
    bridge, _telemetry, io = harness(monkeypatch, tmp_path)
    commands = tmp_path / "commands.json"
    commands.write_text(json.dumps({"commands": [{"id": "open", "op": "key", "key": "a"}]}), encoding="utf-8")

    bridge.before_frame((800, 600))
    assert bridge._current["id"] == "open"
    assert io.add_key_event.call_count == 0
    bridge.before_frame()
    bridge.before_frame()
    assert io.add_key_event.call_args_list == [
        (("a", True),), (("a", False),)
    ]
    bridge.before_frame()
    assert bridge.results == [{"id": "open", "passed": True, "status": "dispatched", "completed_frame": 0}]
    assert json.loads((tmp_path / "receipts.json").read_text(encoding="utf-8")) == {"ids": ["open"]}

    bridge._read_commands()
    assert bridge._queue == []
    bridge.close()


def test_read_commands_reports_invalid_json_and_command_shapes(monkeypatch, tmp_path):
    bridge, telemetry, _io = harness(monkeypatch, tmp_path)
    commands = tmp_path / "commands.json"
    commands.write_text("{broken", encoding="utf-8")
    bridge._read_commands()
    assert telemetry.errors[-1][0] == "commands.json"

    commands.write_text(json.dumps({"commands": {"id": "bad"}}), encoding="utf-8")
    bridge._read_commands()
    assert "commands must be a list" in telemetry.errors[-1][1]

    commands.write_text(json.dumps({"commands": [{"id": ""}]}), encoding="utf-8")
    bridge._read_commands()
    assert "non-empty string id" in telemetry.errors[-1][1]
    bridge.close()


def test_before_frame_records_input_failure_and_releases_stuck_pointer(monkeypatch, tmp_path):
    bridge, _telemetry, io = harness(monkeypatch, tmp_path)
    bridge.telemetry.viewport_size = (800, 600)
    bridge._current = {"id": "drag"}
    bridge._events = [Mock(side_effect=RuntimeError("dispatch failed"))]
    bridge._active_pointer_drag = (20.0, 30.0, 1)
    bridge.dispatch_window_event = Mock()

    bridge.before_frame()

    assert bridge.results == [{"id": "drag", "passed": False, "error": "dispatch failed"}]
    bridge.dispatch_window_event.assert_called_once_with("on_mouse_release", 20.0, 570.0, 1, 0)
    io.add_mouse_button_event.assert_called_once_with(0, False)
    io.add_key_event.assert_called_once_with("ctrl", False)
    assert bridge._current is None and bridge._events == []
    bridge.close()


def test_before_frame_keeps_release_failure_in_failure_receipt(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge._current = {"id": "drag"}
    bridge._events = [Mock(side_effect=ValueError("event failed"))]
    bridge._active_pointer_drag = (10.0, 5.0, 2)
    bridge.dispatch_window_event = Mock(side_effect=RuntimeError("release failed"))

    bridge.before_frame()

    assert bridge.results[0]["error"] == "event failed; pointer release failed: release failed"
    bridge.close()


def test_before_frame_records_invalid_queued_command_without_starting_it(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge._queue = [{"id": "bad-key", "op": "key", "key": "missing"}]

    bridge.before_frame()

    assert bridge.results == [{"id": "bad-key", "passed": False, "error": "Unknown ImGui key"}]
    assert bridge._current is None
    assert bridge._events == []
    bridge.close()


def test_input_events_validate_targets_and_create_click_scroll_drag_and_text_sequences(monkeypatch, tmp_path):
    bridge, telemetry, io = harness(monkeypatch, tmp_path)
    telemetry.widgets["save"] = widget(widget_type="slider_float")

    click = bridge._input_events({"op": "click", "target": "save"})
    click[0]()
    click[1]()
    assert io.add_mouse_pos_event.call_args == ((30.0, 25.0),)
    assert io.add_mouse_button_event.call_args_list[-2:] == [((0, True),), ((0, False),)]
    assert io.add_key_event.call_count == 1
    assert io.add_key_event.call_args.args == ("ctrl", False)

    slider_input = bridge._input_events({"op": "input", "target": "save", "value": "5"})
    slider_input[0]()
    slider_input[1]()
    assert io.add_key_event.call_args_list[-2:] == [call("ctrl", True), call("ctrl", False)]

    scroll = bridge._input_events({"op": "scroll", "target": "save", "amount": 2})
    scroll[0]()
    assert io.add_mouse_wheel_event.call_args == ((0, 2.0),)

    drag = bridge._input_events({"op": "drag", "target": "save", "fraction": 0.75})
    drag[1]()
    assert io.add_mouse_pos_event.call_args == ((40.0, 25.0),)

    with pytest.raises(ValueError, match="Drag fraction"):
        bridge._input_events({"op": "drag", "target": "save", "fraction": 2})
    with pytest.raises(ValueError, match="Unsupported"):
        bridge._input_events({"op": "unknown", "target": "save"})
    with pytest.raises(ValueError, match="visible, enabled interactive"):
        telemetry.widgets["hidden"] = widget(visible=False)
        bridge._input_events({"op": "click", "target": "hidden"})
    with pytest.raises(ValueError, match="Unknown ImGui key"):
        bridge._input_events({"op": "key", "key": "missing"})
    bridge.close()


def test_input_text_replaces_value_and_vector_inputs_map_to_component_rectangles(monkeypatch, tmp_path):
    bridge, telemetry, io = harness(monkeypatch, tmp_path)
    telemetry.widgets["name"] = widget(widget_type="input_text")
    text_events = bridge._input_events({"op": "input", "target": "name", "value": "World"})
    for event in text_events:
        event()
    assert io.add_input_characters_utf8.call_args == (("World",),)

    telemetry.widgets["vector"] = widget(
        widget_type="input_float",
        components=[
            {"rect": {"x": 0, "y": 2, "width": 10, "height": 4}},
            {"rect": {"x": 20, "y": 2, "width": 10, "height": 4}},
        ],
    )
    events = bridge._input_events({"op": "input", "target": "vector", "value": [1, 2]})
    assert len(events) == 14
    with pytest.raises(ValueError, match="one value per component"):
        bridge._input_events({"op": "input", "target": "vector", "value": [1]})
    bridge.close()


def test_pointer_drag_builds_arcade_events_and_releases_at_final_location(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge.telemetry.viewport_size = (100, 80)
    dispatch = Mock()
    bridge.dispatch_window_event = dispatch
    events = bridge._pointer_drag_events({
        "op": "pointer_drag",
        "start": {"x": 10, "y": 20},
        "end": {"x": 50, "y": 40},
        "button": "right",
        "steps": 2,
    })
    assert len(events) == 5
    for event in events:
        event()
    assert dispatch.call_args_list == [
        (("on_mouse_motion", 10.0, 60.0, 0.0, 0.0),),
        (("on_mouse_press", 10.0, 60.0, 2, 0),),
        (("on_mouse_drag", 30.0, 50.0, 20.0, -10.0, 2, 0),),
        (("on_mouse_drag", 50.0, 40.0, 20.0, -10.0, 2, 0),),
        (("on_mouse_release", 50.0, 40.0, 2, 0),),
    ]
    assert bridge._active_pointer_drag is None
    bridge.close()


def test_input_events_dispatch_pointer_drag_operation(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge.telemetry.viewport_size = (100, 80)
    bridge.dispatch_window_event = Mock()
    events = bridge._input_events({
        "op": "pointer_drag",
        "start": {"x": 5, "y": 6},
        "end": {"x": 7, "y": 8},
        "steps": 1,
    })

    for event in events:
        event()

    assert bridge.dispatch_window_event.call_count == 4
    bridge.dispatch_window_event.assert_called_with("on_mouse_release", 7.0, 72.0, 1, 0)
    bridge.close()


@pytest.mark.parametrize("invalid", [None, [], {"x": True, "y": 1}, {"x": float("nan"), "y": 1}, {"x": 100, "y": 0}])
def test_pointer_drag_rejects_invalid_coordinates(monkeypatch, tmp_path, invalid):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge.telemetry.viewport_size = (100, 80)
    bridge.dispatch_window_event = Mock()
    with pytest.raises(ValueError, match="Pointer drag start"):
        bridge._pointer_drag_events({
            "start": invalid,
            "end": {"x": 50, "y": 40},
            "steps": 1,
        })
    bridge.close()


def test_pointer_drag_validates_dispatch_button_and_step_count(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge.telemetry.viewport_size = (100, 80)
    with pytest.raises(ValueError, match="dispatcher"):
        bridge._pointer_drag_events({"start": {}, "end": {}})
    bridge.dispatch_window_event = Mock()
    base = {"start": {"x": 1, "y": 1}, "end": {"x": 2, "y": 2}}
    with pytest.raises(ValueError, match="button"):
        bridge._pointer_drag_events({**base, "button": "side"})
    for steps in (True, 0, 121, 2.5):
        with pytest.raises(ValueError, match="steps"):
            bridge._pointer_drag_events({**base, "steps": steps})
    bridge.close()


def test_pointer_release_is_idempotent_and_reports_dispatch_errors(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    assert bridge._release_active_pointer_drag() is None
    bridge._active_pointer_drag = (5.0, 6.0, 3)
    bridge.dispatch_window_event = Mock()
    assert bridge._release_active_pointer_drag() is None
    bridge.dispatch_window_event.assert_called_once_with("on_mouse_release", 5.0, -5.0, 3, 0)

    bridge._active_pointer_drag = (5.0, 6.0, 3)
    bridge.dispatch_window_event.side_effect = RuntimeError("release refused")
    assert bridge._release_active_pointer_drag() == "release refused"
    assert bridge._active_pointer_drag is None
    bridge.close()


def test_start_abort_and_finish_export_timing_telemetry_and_provider_errors(monkeypatch, tmp_path):
    bridge, telemetry, _io = harness(
        monkeypatch,
        tmp_path,
        inspection_provider=Mock(side_effect=RuntimeError("inspect failed")),
    )
    times = iter([10.0, 10.016])
    monkeypatch.setattr(bridge_module.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: 20.0)
    bridge.start_frame((640, 480))
    assert telemetry.viewport_size == (640, 480)
    bridge.start_frame((800, 600))
    assert list(bridge._frame_intervals) == pytest.approx([16.0])
    assert telemetry.viewport_size == (800, 600)
    bridge.finish_frame(force=True)

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["runtime"] == "arcade"
    assert report["inspection_error"] == "inspect failed"
    assert report["frame_timing_ms"]["samples"] == 1
    assert report["layout_findings"] == [{"frame": telemetry.frame_count}]
    bridge.close()


def test_finish_frame_throttles_pending_exports_and_records_export_failure(monkeypatch, tmp_path):
    bridge, telemetry, _io = harness(monkeypatch, tmp_path, interval=100)
    bridge._last_export = 20.0
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: 20.1)
    bridge.finish_frame()
    assert bridge._exporter.submissions == 0

    bridge._export_future = FakeFuture(done=False)
    bridge.finish_frame(force=True)
    assert bridge._exporter.submissions == 0

    bridge._export_future = FakeFuture(error=OSError("export failed"))
    bridge.finish_frame(force=True)
    assert ("artifact export", "export failed") in telemetry.errors
    assert bridge._exporter.submissions == 1
    bridge.close()


def test_capture_failure_is_reported_and_close_is_idempotent(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(
        monkeypatch, tmp_path, capture=Mock(side_effect=RuntimeError("capture failed"))
    )
    bridge.finish_frame(force=True)
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["screenshot_error"] == "capture failed"
    assert report["screenshot"] is None
    bridge.close()
    bridge.close()
    assert bridge._closed is True
    assert bridge._exporter.shutdown_called is True


def test_screenshot_export_writes_frame_and_overlay(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path, capture=Mock(return_value=b"pixels"))
    cv2 = SimpleNamespace(IMWRITE_PNG_COMPRESSION=1, imwrite=Mock(return_value=True))
    overlay = types.ModuleType("src.client.ui.testing.overlay")
    overlay.save_overlay = Mock(return_value="overlay.png")
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "src.client.ui.testing.overlay", overlay)

    bridge.finish_frame(force=True)

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["screenshot"] == str(tmp_path / "actual.png")
    assert report["overlay"] == "overlay.png"
    cv2.imwrite.assert_called_once_with(
        str(tmp_path / "actual.png"), b"pixels", [cv2.IMWRITE_PNG_COMPRESSION, 1]
    )
    overlay.save_overlay.assert_called_once()
    bridge.close()


def test_screenshot_export_fails_when_image_writer_cannot_save(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    cv2 = SimpleNamespace(IMWRITE_PNG_COMPRESSION=1, imwrite=Mock(return_value=False))
    overlay = types.ModuleType("src.client.ui.testing.overlay")
    overlay.save_overlay = Mock()
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "src.client.ui.testing.overlay", overlay)
    report = {
        "telemetry": {"frame_count": 0},
        "screenshot": str(tmp_path / "actual.png"),
    }

    with pytest.raises(OSError, match="Could not save the live UI screenshot"):
        bridge._write_report(report, b"pixels")

    overlay.save_overlay.assert_not_called()


@pytest.mark.parametrize("failures,raises", [(2, False), (10, True)])
def test_report_replace_retries_transient_permission_errors(monkeypatch, tmp_path, failures, raises):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    original_replace = Path.replace
    attempts = []
    sleep = Mock()

    def replace(source, target):
        if source.name == "report.pending.json":
            attempts.append(source)
            if len(attempts) <= failures:
                raise PermissionError("file is being read")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(bridge_module, "time", SimpleNamespace(sleep=sleep))
    report = {"telemetry": {"frame_count": 0}, "screenshot": None}

    if raises:
        with pytest.raises(PermissionError, match="file is being read"):
            bridge._write_report(report, None)
        assert len(attempts) == 10
        assert sleep.call_count == 9
    else:
        bridge._write_report(report, None)
        assert len(attempts) == 3
        assert sleep.call_count == 2
        assert (tmp_path / "report.json").exists()


def test_flush_waits_for_existing_export_before_scheduling_latest_snapshot(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge._export_future = FakeFuture()
    bridge.flush()
    assert bridge._exporter.submissions == 1
    assert (tmp_path / "report.json").exists()
    bridge.close()


def test_flush_returns_after_bridge_is_closed(monkeypatch, tmp_path):
    bridge, _telemetry, _io = harness(monkeypatch, tmp_path)
    bridge._closed = True
    bridge.flush()
    assert bridge._exporter.submissions == 0
