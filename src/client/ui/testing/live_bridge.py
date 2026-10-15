"""File-based agent inspection and input for the existing Arcade ImGui runtime."""
from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from math import isfinite
from pathlib import Path

import arcade
from imgui_bundle import imgui

from src.client.ui.core.testability import UIRunTelemetry
from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.layout_checks import analyze_layout


class LiveUIBridge:
    """Compose telemetry and native IO events without attaching Test Engine to Arcade."""

    def __init__(
        self,
        directory: Path,
        capture=None,
        interval: float = 0.5,
        inspection_provider=None,
        dispatch_window_event: Callable[..., object] | None = None,
    ):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.telemetry = UIRunTelemetry((1, 1))
        self.capture = capture
        self.inspection_provider = inspection_provider
        self.dispatch_window_event = dispatch_window_event
        self._frame_intervals = deque(maxlen=240)
        self._previous_frame = None
        self.interval = interval
        self.results: list[dict] = []
        self._seen: set[str] = set()
        self._queue: list[dict] = []
        self._events: list = []
        self._current = None
        self._active_pointer_drag: tuple[float, float, int] | None = None
        self._frame_scope = None
        self._last_export = 0.0
        self._command_stamp = None
        self._exporter = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ui-artifacts")
        self._export_future = None
        self._closed = False
        receipts = self.directory / "receipts.json"
        report = self.directory / "report.json"
        try:
            if receipts.exists():
                self._seen.update(json.loads(receipts.read_text(encoding="utf-8"))["ids"])
            if report.exists():
                self.results = json.loads(report.read_text(encoding="utf-8")).get("commands", [])
            completed = {entry["id"] for entry in self.results}
            for command_id in self._seen - completed:
                self.results.append({"id": command_id, "passed": False, "status": "interrupted",
                                     "error": "Runtime changed before dispatch acknowledgement."})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.telemetry.record_error("live receipts", str(exc))

    def before_frame(self, viewport_size: tuple[int, int] | None = None) -> None:
        if viewport_size is not None:
            self.telemetry.viewport_size = viewport_size
        self._read_commands()
        if self._events:
            try:
                self._events.pop(0)()
            except Exception as exc:
                self._events.clear()
                error = str(exc)
                release_error = self._release_active_pointer_drag()
                if release_error:
                    error = f"{error}; pointer release failed: {release_error}"
                self.results.append({"id": self._current["id"], "passed": False, "error": error})
                self._current = None
                io = imgui.get_io()
                io.add_mouse_button_event(0, False)
                io.add_key_event(imgui.Key.mod_ctrl, False)
            return
        if self._current is not None:
            self.results.append({"id": self._current["id"], "passed": True,
                                 "status": "dispatched",
                                 "completed_frame": self.telemetry.frame_count})
            self._current = None
        if not self._queue:
            return
        command = self._queue.pop(0)
        try:
            self._events = self._input_events(command)
            self._current = command
        except Exception as exc:
            self.results.append({"id": command["id"], "passed": False, "error": str(exc)})

    def start_frame(self, size: tuple[int, int]) -> None:
        now = time.perf_counter()
        if self._previous_frame is not None:
            self._frame_intervals.append((now - self._previous_frame) * 1000)
        self._previous_frame = now
        self.abort_frame()
        self.telemetry.viewport_size = size
        self._frame_scope = self.telemetry.frame()
        self._frame_scope.__enter__()

    def abort_frame(self) -> None:
        if self._frame_scope is not None:
            self._frame_scope.__exit__(None, None, None)
            self._frame_scope = None

    def finish_frame(self, *, force: bool = False) -> None:
        self.abort_frame()
        now = time.monotonic()
        if self._closed or (not force and now - self._last_export < self.interval):
            return
        if self._export_future is not None:
            if not self._export_future.done():
                return
            try:
                self._export_future.result()
            except Exception as exc:
                self.telemetry.record_error("artifact export", str(exc))
        self._last_export = now
        snapshot = self.telemetry.to_dict()
        report = {"schema_version": 1, "runtime": "arcade", "telemetry": snapshot,
                  "commands": list(self.results),
                  "screenshot": None}
        intervals = sorted(self._frame_intervals)
        if intervals:
            report["frame_timing_ms"] = {"samples": len(intervals), "median": intervals[len(intervals) // 2],
                                        "p95": intervals[min(len(intervals) - 1, int(len(intervals) * 0.95))], "max": intervals[-1]}
        if self.inspection_provider is not None:
            try:
                report["game"] = self.inspection_provider()
            except Exception as exc:
                report["inspection_error"] = str(exc)
        frame = None
        if self.capture:
            try:
                path = self.directory / "actual.png"
                frame = self.capture(path)
                report["screenshot"] = str(path)
            except Exception as exc:
                report["screenshot_error"] = str(exc)
        self._export_future = self._exporter.submit(self._write_report, report, frame)

    def _write_report(self, report: dict, frame) -> None:
        snapshot = report["telemetry"]
        report["layout_findings"] = analyze_layout(snapshot)
        if report["screenshot"] is not None:
            import cv2
            from src.client.ui.testing.overlay import save_overlay
            path = Path(report["screenshot"])
            if frame is not None and not cv2.imwrite(str(path), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1]):
                raise OSError("Could not save the live UI screenshot.")
            report["overlay"] = save_overlay(path, self.directory / "overlay.png", snapshot, frame=frame)
        pending = self.directory / "report.pending.json"
        pending.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        # Windows readers may briefly deny replacement while inspecting the
        # current report. Retry on the artifact worker, never on the render loop.
        for attempt in range(10):
            try:
                pending.replace(self.directory / "report.json")
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)

    def flush(self) -> None:
        if self._closed:
            return
        if self._export_future is not None:
            self._export_future.result()
        self.finish_frame(force=True)
        if self._export_future is not None:
            self._export_future.result()

    def close(self) -> None:
        if not self._closed:
            try:
                self.flush()
            finally:
                self._closed = True
                self._exporter.shutdown(wait=True)

    def _read_commands(self) -> None:
        path = self.directory / "commands.json"
        if not path.exists():
            return
        stamp = path.stat().st_mtime_ns
        if stamp == self._command_stamp:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            commands = data["commands"]
            if not isinstance(commands, list):
                raise ValueError("commands must be a list")
            for command in commands:
                command_id = command.get("id")
                if not isinstance(command_id, str) or not command_id:
                    raise ValueError("Each live command needs a non-empty string id")
                if command_id not in self._seen:
                    self._seen.add(command_id)
                    self._queue.append(command)
            self._command_stamp = stamp
            # Receipt IDs survive view/context replacement, preventing a click
            # that navigated to another screen from being replayed there.
            pending = self.directory / "receipts.pending.json"
            pending.write_text(json.dumps({"ids": sorted(self._seen)}), encoding="utf-8")
            pending.replace(self.directory / "receipts.json")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # A writer may be replacing the file. Retry after the next frame;
            # malformed complete files are exposed to the agent as diagnostics.
            self.telemetry.record_error("commands.json", str(exc))

    def _input_events(self, command):
        io = imgui.get_io()
        operation = command["op"]
        if operation == "key":
            key = getattr(imgui.Key, command["key"], None)
            if key is None:
                raise ValueError("Unknown ImGui key")
            return [lambda: io.add_key_event(key, True), lambda: io.add_key_event(key, False)]
        if operation == "pointer_drag":
            return self._pointer_drag_events(command)
        target = UITestDriver(None, self.telemetry).find(command["target"])
        widget = self.telemetry.widget(target)
        if not widget["visible"] or not widget["enabled"] or not widget["interactive"]:
            raise ValueError("Live input requires a visible, enabled interactive widget")
        rect = widget["rect"]
        if operation == "input" and widget.get("components"):
            if isinstance(command["value"], list):
                if len(command["value"]) != len(widget["components"]):
                    raise ValueError("Vector input requires one value per component")
                events = []
                for index, value in enumerate(command["value"]):
                    events.extend(self._input_events({**command, "value": value, "component": index}))
                return events
            index = int(command.get("component", 0))
            rect = widget["components"][index]["rect"]
        x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2

        def press():
            io.add_mouse_pos_event(x, y)
            if operation == "input" and widget["type"].startswith(("slider_", "drag_")):
                io.add_key_event(imgui.Key.mod_ctrl, True)
            io.add_mouse_button_event(0, True)

        def release():
            io.add_mouse_button_event(0, False)
            io.add_key_event(imgui.Key.mod_ctrl, False)

        if operation == "click":
            return [press, release, lambda: None]
        if operation == "scroll":
            def wheel():
                io.add_mouse_pos_event(x, y)
                io.add_mouse_wheel_event(0, float(command.get("amount", -3)))
            return [wheel, lambda: None]
        if operation == "drag":
            fraction = float(command["fraction"])
            if not 0 <= fraction <= 1:
                raise ValueError("Drag fraction must be between 0 and 1")
            return [press, lambda: io.add_mouse_pos_event(rect["x"] + rect["width"] * fraction, y),
                    lambda: None, release]
        if operation == "input":
            def select_all():
                io.add_key_event(imgui.Key.mod_ctrl, True)
                io.add_key_event(imgui.Key.a, True)
            def insert():
                io.add_key_event(imgui.Key.a, False)
                io.add_key_event(imgui.Key.mod_ctrl, False)
                io.add_input_characters_utf8(str(command["value"]))
            return [press, release, select_all, insert,
                    lambda: io.add_key_event(imgui.Key.enter, True),
                    lambda: io.add_key_event(imgui.Key.enter, False), lambda: None]
        raise ValueError(f"Unsupported live UI operation: {operation}")

    def _pointer_drag_events(self, command: dict) -> list[Callable[[], object]]:
        dispatcher = self.dispatch_window_event
        if dispatcher is None:
            raise ValueError("Pointer drag requires a window event dispatcher.")

        width, height = self.telemetry.viewport_size
        start = self._pointer_point(command.get("start"), "start", width, height)
        end = self._pointer_point(command.get("end"), "end", width, height)

        button_name = command.get("button", "left")
        buttons = {
            "left": arcade.MOUSE_BUTTON_LEFT,
            "right": arcade.MOUSE_BUTTON_RIGHT,
            "middle": arcade.MOUSE_BUTTON_MIDDLE,
        }
        if button_name not in buttons:
            raise ValueError("Pointer drag button must be 'left', 'right', or 'middle'.")
        button = buttons[button_name]

        steps = command.get("steps", 8)
        if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 120:
            raise ValueError("Pointer drag steps must be an integer from 1 to 120.")

        events: list[Callable[[], object]] = []

        def add_event(event_type: str, *args) -> None:
            events.append(
                lambda event_type=event_type, args=args: dispatcher(event_type, *args)
            )

        start_x, start_y = start
        end_x, end_y = end
        start_arcade_y = height - start_y
        add_event("on_mouse_motion", start_x, start_arcade_y, 0.0, 0.0)

        def press() -> None:
            self._active_pointer_drag = (start_x, start_y, button)
            dispatcher("on_mouse_press", start_x, start_arcade_y, button, 0)

        events.append(press)
        previous_x, previous_y = start_x, start_arcade_y
        for step in range(1, steps + 1):
            fraction = step / steps
            x = start_x + (end_x - start_x) * fraction
            top_y = start_y + (end_y - start_y) * fraction
            y = height - top_y
            dx, dy = x - previous_x, y - previous_y

            def drag(
                x=x,
                y=y,
                top_y=top_y,
                dx=dx,
                dy=dy,
            ) -> None:
                self._active_pointer_drag = (x, top_y, button)
                dispatcher("on_mouse_drag", x, y, dx, dy, button, 0)

            events.append(drag)
            previous_x, previous_y = x, y

        def release() -> None:
            x, top_y, active_button = self._active_pointer_drag or (end_x, end_y, button)
            dispatcher("on_mouse_release", x, height - top_y, active_button, 0)
            self._active_pointer_drag = None

        events.append(release)
        return events

    @staticmethod
    def _pointer_point(value, name: str, width: int, height: int) -> tuple[float, float]:
        if not isinstance(value, dict):
            raise ValueError(f"Pointer drag {name} must be an object with x and y coordinates.")

        point = []
        for axis, limit in (("x", width), ("y", height)):
            coordinate = value.get(axis)
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise ValueError(f"Pointer drag {name}.{axis} must be a number.")
            coordinate = float(coordinate)
            if not isfinite(coordinate) or not 0 <= coordinate < limit:
                raise ValueError(f"Pointer drag {name}.{axis} must be within the {limit}-pixel viewport.")
            point.append(coordinate)
        return point[0], point[1]

    def _release_active_pointer_drag(self) -> str | None:
        active_drag = self._active_pointer_drag
        dispatcher = self.dispatch_window_event
        if active_drag is None or dispatcher is None:
            return None

        x, top_y, button = active_drag
        self._active_pointer_drag = None
        try:
            dispatcher(
                "on_mouse_release",
                x,
                self.telemetry.viewport_size[1] - top_y,
                button,
                0,
            )
        except Exception as exc:
            return str(exc)
        return None
