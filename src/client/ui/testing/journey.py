"""A data-only interaction language for AI agents and reusable UI scenarios."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import json
from pathlib import Path
from typing import Any, Callable

from imgui_bundle import imgui

from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.layout_checks import analyze_layout, contains, overlaps


def action_record(action) -> dict:
    return {"type": type(action).__name__,
            **(asdict(action) if is_dataclass(action) else {"value": str(action)})}


def _assert_action(step: dict, actions: list) -> None:
    records = [action_record(action) for action in actions]
    expected = step["type"]
    matching = [action for action in records if action["type"] == expected]
    expected_count = int(step.get("count", 1))
    if len(matching) != expected_count:
        raise AssertionError(f"Unexpected count for {expected}: {len(matching)}")
    if expected_count == 0:
        # A successful absence assertion has no action payload to inspect.
        if step.get("fields") or "index" in step:
            raise ValueError("A zero-count action assertion cannot inspect an action payload.")
        return

    action_index = int(step.get("index", -1))
    try:
        selected_action = matching[action_index]
    except IndexError as exc:
        raise AssertionError(
            f"Action index {action_index} is outside {expected} results."
        ) from exc
    for key, expected_value in step.get("fields", {}).items():
        actual = selected_action
        for part in key.split("."):
            actual = actual[part]
        if isinstance(actual, float) and isinstance(expected_value, (int, float)):
            if abs(actual - expected_value) > float(step.get("tolerance", 0.001)):
                raise AssertionError(f"{key}: expected {expected_value}, received {actual}")
        elif actual != expected_value:
            raise AssertionError(f"{key}: expected {expected_value!r}, received {actual!r}")


def _assert_rect(actual: dict, expected: dict, tolerance: float = 1.0) -> None:
    """Compare selected rectangle fields while allowing raster-coordinate rounding."""
    for key, expected_value in expected.items():
        if key not in {"x", "y", "width", "height"}:
            raise ValueError(f"Unsupported rectangle field: {key!r}")
        if abs(float(actual[key]) - float(expected_value)) > tolerance:
            raise AssertionError(
                f"Rectangle {key}: expected {expected_value}, received {actual[key]}"
            )


def _assert_minimum_dimensions(rect: dict, step: dict, viewport_size, subject: str) -> None:
    minimum_tolerance = float(step.get("minimum_tolerance", 0.0))
    for attribute in ("min_width", "min_height"):
        if attribute not in step:
            continue
        dimension = attribute[4:]
        viewport_limit = float(viewport_size[0 if dimension == "width" else 1])
        requested_minimum = float(step[attribute])
        effective_minimum = min(requested_minimum, viewport_limit) if viewport_limit > 0 else requested_minimum
        if float(rect[dimension]) + minimum_tolerance < effective_minimum:
            raise AssertionError(f"{subject} does not satisfy {attribute}")


def _overlap_check_applies(step: dict, viewport_size) -> bool:
    minimum_width = float(step.get("no_overlap_min_viewport_width", 0.0))
    return float(viewport_size[0]) >= minimum_width


def _relative_rect_check_applies(step: dict, viewport_size) -> bool:
    # Compact layouts preserve visibility while compressing source-relative positions.
    minimum_width = float(step.get("relative_rect_min_viewport_width", 0.0))
    minimum_height = float(step.get("relative_rect_min_viewport_height", 0.0))
    return (
        float(viewport_size[0]) >= minimum_width
        and float(viewport_size[1]) >= minimum_height
    )


def _assert_relative_rect(rect: dict, step: dict, telemetry) -> None:
    if "relative_rect" in step and _relative_rect_check_applies(
        step, telemetry.viewport_size,
    ):
        parent = telemetry.region(step["relative_to"])
        if parent is None:
            raise KeyError(f"No UI region has test_id '{step['relative_to']}'.")
        for key, expected in step["relative_rect"].items():
            actual = rect[key]
            if key in {"x", "y"}:
                actual -= parent["rect"][key]
            if abs(actual - float(expected)) > float(step.get("tolerance", 1.0)):
                raise AssertionError(f"Relative {key}: expected {expected}, received {actual}")


def _assert_widget(step, target, telemetry, driver) -> None:
    widget = telemetry.widget(target)
    for attribute in ("visible", "enabled", "value", "type", "label"):
        if attribute in step and widget[attribute] != step[attribute]:
            raise AssertionError(f"{attribute}: expected {step[attribute]!r}, received {widget[attribute]!r}")
    _assert_minimum_dimensions(
        widget["rect"], step, telemetry.viewport_size, "Widget",
    )
    if "inside" in step:
        parent = telemetry.region(step["inside"])
        if parent is None or not contains(parent["rect"], widget["rect"]):
            raise AssertionError("Widget is outside the requested region")
    if "no_overlap" in step and _overlap_check_applies(step, telemetry.viewport_size):
        other = telemetry.widget(driver.find(step["no_overlap"]))
        if overlaps(widget["rect"], other["rect"]):
            raise AssertionError("Widgets overlap")
    _assert_relative_rect(widget["rect"], step, telemetry)


def _assert_region(step, selector, telemetry) -> None:
    if not isinstance(selector, str):
        raise ValueError("Region assertions require an exact semantic region ID.")
    region = telemetry.region(selector)
    if region is None:
        raise KeyError(f"No UI region has test_id '{selector}'.")
    for attribute in ("present", "visible", "kind", "label"):
        if attribute in step and region[attribute] != step[attribute]:
            raise AssertionError(
                f"{attribute}: expected {step[attribute]!r}, received {region[attribute]!r}"
            )
    if not region["present"] and step.get("visible") is not False:
        raise KeyError(f"UI region '{selector}' is not present in the current frame.")
    if "rect" in step:
        _assert_rect(
            region["rect"],
            step["rect"],
            float(step.get("tolerance", 1.0)),
        )
    _assert_minimum_dimensions(
        region["rect"], step, telemetry.viewport_size, "Region",
    )
    if step.get("inside_viewport"):
        viewport_width, viewport_height = telemetry.viewport_size
        rect = region["rect"]
        if (rect["x"] < 0 or rect["y"] < 0
                or rect["x"] + rect["width"] > viewport_width
                or rect["y"] + rect["height"] > viewport_height):
            raise AssertionError(f"Region '{selector}' is outside the viewport")
    if "no_overlap" in step and _overlap_check_applies(step, telemetry.viewport_size):
        other = telemetry.region(str(step["no_overlap"]))
        if other is None:
            raise KeyError(f"No UI region has test_id '{step['no_overlap']}'.")
        if overlaps(region["rect"], other["rect"]):
            raise AssertionError(
                f"UI region '{selector}' overlaps '{step['no_overlap']}'."
            )
    _assert_relative_rect(region["rect"], step, telemetry)


def _capture_checkpoint(context, telemetry, capture_dir: Path, index: int, selector) -> dict:
    checkpoint = {}
    capture_dir.mkdir(parents=True, exist_ok=True)
    filename = capture_dir / f"{index:03d}.png"
    # Capture at the destination, before subsequent steps close or replace it.
    context.capture_reset()
    context.capture_set_filename(str(filename.resolve()))
    if not context.capture_screenshot():
        raise RuntimeError(f"Could not capture destination {selector}")
    snapshot = telemetry.to_dict()
    filename.with_suffix(".json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint["screenshot"] = str(filename.resolve())
    checkpoint["region"] = selector
    checkpoint["geometry_errors"] = [f for f in analyze_layout(snapshot) if f["severity"] == "error"]
    return checkpoint


@dataclass
class JourneyRuntime:
    context: Any
    telemetry: Any
    driver: UITestDriver
    actions: list
    deliver_event: Callable | None = None
    deliver_snapshot: Callable | None = None
    viewport_requests: list | None = None
    navigation_requests: list | None = None

    def execute(self, step: dict) -> None:
        operation = step.get('op')
        selector = step.get('target')
        target = self.driver.find(selector) if selector is not None and operation not in {'assert_absent', 'assert_region', 'close_window', 'drag_window', 'server_event', 'server_snapshot'} else None
        if operation == 'click':
            self.driver.click(target)
        elif operation == 'hold':
            if 'duration_ms' in step:
                self.driver.hold_for(target, int(step['duration_ms']))
            else:
                frames = int(step.get('frames', 1))
                if not 1 <= frames <= 600:
                    raise ValueError('Hold must be between 1 and 600 frames.')
                self.driver.hold(target, frames)
        elif operation == 'hover':
            self.driver.hover(target)
        elif operation == 'input':
            self.driver.input_value(target, step['value'])
        elif operation == 'replace':
            self.driver.replace_focused_value(target, step['value'])
        elif operation == 'replace_text':
            self.driver.replace_focused_text(target, step['value'])
        elif operation == 'drag':
            self.driver.drag_to_fraction(target, float(step['fraction']))
        elif operation == 'drag_window':
            if not isinstance(selector, str):
                raise ValueError('Window drag requires an exact semantic window ID.')
            self.driver.drag_window(selector, float(step['dx']), float(step['dy']))
        elif operation == 'open':
            self.driver.open(target)
        elif operation == 'check':
            self.driver.check(target, bool(step.get('value', True)))
        elif operation == 'select':
            self.driver.select(target, step['value'])
        elif operation == 'scroll':
            self.driver.scroll(target)
        elif operation == 'close_window':
            if not isinstance(selector, str):
                raise ValueError('Window-close operations require an exact semantic window ID.')
            self.driver.close_window(selector)
        elif operation in {'key', 'key_down', 'key_up'}:
            key = getattr(imgui.Key, step['key'], None)
            if key is None:
                raise ValueError(f"Unknown ImGui key: {step['key']}")
            {'key': self.context.key_press, 'key_down': self.context.key_down, 'key_up': self.context.key_up}[operation](key)
        elif operation == 'wait':
            frames = int(step.get('frames', 2))
            if not 0 <= frames <= 600:
                raise ValueError('Wait must be between 0 and 600 frames.')
            self.context.yield_(frames)
        elif operation == 'assert':
            _assert_widget(step, target, self.telemetry, self.driver)
        elif operation == 'assert_region':
            _assert_region(step, selector, self.telemetry)
        elif operation == 'assert_absent':
            if self.driver.matches(selector):
                raise AssertionError(f'Widget is still present: {selector!r}')
        elif operation == 'server_event':
            if self.deliver_event is None:
                raise ValueError('This surface has no authoritative event-delivery fixture.')
            self.deliver_event(str(step['target']), step['payload'], str(step['event_id']))
        elif operation == 'server_snapshot':
            if self.deliver_snapshot is None:
                raise ValueError('This surface has no snapshot-delivery fixture.')
            self.deliver_snapshot(json.loads(Path(step['fixture']).read_text(encoding='utf-8')))
        elif operation == 'assert_action':
            _assert_action(step, self.actions)
        elif operation == 'assert_viewport_request':
            _assert_viewport_request(step, self.viewport_requests or [])
        elif operation == 'assert_navigation_request':
            _assert_navigation_request(step, self.navigation_requests or [])
        else:
            raise ValueError(f'Unsupported journey operation: {operation!r}')


def run_steps(context, telemetry, steps: list[dict], actions: list, results: list[dict],
              capture_dir: Path | None = None, deliver_event=None, deliver_snapshot=None,
              viewport_requests: list | None = None,
              navigation_requests: list | None = None) -> None:
    driver = UITestDriver(context, telemetry)
    runtime = JourneyRuntime(
        context, telemetry, driver, actions, deliver_event, deliver_snapshot,
        viewport_requests, navigation_requests,
    )
    context.yield_(6)
    for index, step in enumerate(steps):
        operation = step.get("op")
        try:
            selector = step.get("target")
            runtime.execute(step)
            context.yield_(2)
            if context.is_error():
                raise AssertionError("ImGui Test Engine rejected the interaction; inspect test_engine.log")
            result = {"step": index, "op": operation, "passed": True}
            if capture_dir is not None and operation == "assert_region" and step.get("visible", True):
                result.update(_capture_checkpoint(context, telemetry, capture_dir, index, selector))
            results.append(result)
        except Exception as exc:
            results.append({"step": index, "op": operation, "passed": False, "error": str(exc)})
            imgui.test_engine.check(__file__, "run_steps", 0, imgui.test_engine.TestCheckFlags_.none,
                                    False, f"Step {index}: {operation}: {exc}")
            return


def _assert_viewport_request(step: dict, requests: list[dict]) -> None:
    expected_type = str(step["type"])
    matching = [
        request for request in requests
        if request.get(
            "type",
            next((key for key in ("country", "region", "map_mode") if key in request), ""),
        ) == expected_type
    ]
    expected_count = int(step.get("count", 1))
    if len(matching) != expected_count:
        raise AssertionError(
            f"Unexpected count for viewport request {expected_type}: {len(matching)}"
        )
    if expected_count == 0:
        return

    request_index = int(step.get("index", -1))
    try:
        selected_request = matching[request_index]
    except IndexError as exc:
        raise AssertionError(
            f"Viewport request index {request_index} is outside {expected_type} results."
        ) from exc
    for key, expected_value in step.get("fields", {}).items():
        actual = selected_request
        for part in key.split("."):
            actual = actual[part]
        if isinstance(actual, (int, float)) and isinstance(expected_value, (int, float)):
            if abs(float(actual) - float(expected_value)) <= float(step.get("tolerance", 0.001)):
                continue
        elif actual == expected_value:
            continue
        if actual != expected_value:
            raise AssertionError(f"{key}: expected {expected_value!r}, received {actual!r}")


def _assert_navigation_request(step: dict, requests: list) -> None:
    expected_type = str(step["type"])
    matching = [
        request for request in requests
        if (
            str(request.get("type") or "")
            if isinstance(request, dict)
            else str(request)
        ) == expected_type
    ]
    expected_count = int(step.get("count", 1))
    if len(matching) != expected_count:
        raise AssertionError(
            f"Unexpected count for navigation request {expected_type}: {len(matching)}"
        )
    if expected_count == 0:
        return

    request_index = int(step.get("index", -1))
    try:
        selected_request = matching[request_index]
    except IndexError as exc:
        raise AssertionError(
            f"Navigation request index {request_index} is outside {expected_type} results."
        ) from exc
    if isinstance(selected_request, dict):
        for key, expected_value in step.get("fields", {}).items():
            actual = selected_request
            for part in key.split("."):
                actual = actual[part]
            if actual != expected_value:
                raise AssertionError(f"{key}: expected {expected_value!r}, received {actual!r}")
    elif step.get("fields"):
        raise ValueError("String navigation requests cannot inspect request fields.")
