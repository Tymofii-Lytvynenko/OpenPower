"""A data-only interaction language for AI agents and reusable UI scenarios."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

from imgui_bundle import imgui

from src.client.ui.testing.driver import UITestDriver
from src.client.ui.testing.layout_checks import contains, overlaps


def action_record(action) -> dict:
    return {"type": type(action).__name__,
            **(asdict(action) if is_dataclass(action) else {"value": str(action)})}


def run_steps(context, telemetry, steps: list[dict], actions: list, results: list[dict]) -> None:
    driver = UITestDriver(context, telemetry)
    context.yield_(2)
    for index, step in enumerate(steps):
        operation = step.get("op")
        try:
            selector = step.get("target")
            target = driver.find(selector) if selector is not None and operation != "assert_absent" else None
            if operation == "click":
                driver.click(target)
            elif operation == "input":
                driver.input_value(target, step["value"])
            elif operation == "drag":
                driver.drag_to_fraction(target, float(step["fraction"]))
            elif operation == "open":
                driver.open(target)
            elif operation == "check":
                driver.check(target, bool(step.get("value", True)))
            elif operation == "select":
                driver.select(target, step["value"])
            elif operation == "scroll":
                driver.scroll(target)
            elif operation == "key":
                key = getattr(imgui.Key, step["key"], None)
                if key is None:
                    raise ValueError(f"Unknown ImGui key: {step['key']}")
                context.key_press(key)
            elif operation == "wait":
                frames = int(step.get("frames", 2))
                if not 0 <= frames <= 600:
                    raise ValueError("Wait must be between 0 and 600 frames.")
                context.yield_(frames)
            elif operation == "assert":
                widget = telemetry.widget(target)
                for attribute in ("visible", "enabled", "value", "type", "label"):
                    if attribute in step and widget[attribute] != step[attribute]:
                        raise AssertionError(f"{attribute}: expected {step[attribute]!r}, received {widget[attribute]!r}")
                for attribute in ("min_width", "min_height"):
                    if attribute in step and widget["rect"][attribute[4:]] < float(step[attribute]):
                        raise AssertionError(f"Widget does not satisfy {attribute}")
                if "inside" in step:
                    parent = telemetry.region(step["inside"])
                    if parent is None or not contains(parent["rect"], widget["rect"]):
                        raise AssertionError("Widget is outside the requested region")
                if "no_overlap" in step:
                    other = telemetry.widget(driver.find(step["no_overlap"]))
                    if overlaps(widget["rect"], other["rect"]):
                        raise AssertionError("Widgets overlap")
            elif operation == "assert_absent":
                if driver.matches(selector):
                    raise AssertionError(f"Widget is still present: {selector!r}")
            elif operation == "assert_action":
                records = [action_record(a) for a in actions]
                expected = step["type"]
                matching = [a for a in records if a["type"] == expected]
                if len(matching) != int(step.get("count", 1)):
                    raise AssertionError(f"Unexpected count for {expected}: {len(matching)}")
                for key, expected_value in step.get("fields", {}).items():
                    actual = matching[-1]
                    for part in key.split("."):
                        actual = actual[part]
                    if isinstance(actual, float) and isinstance(expected_value, (int, float)):
                        if abs(actual - expected_value) > float(step.get("tolerance", 0.001)):
                            raise AssertionError(f"{key}: expected {expected_value}, received {actual}")
                    elif actual != expected_value:
                        raise AssertionError(f"{key}: expected {expected_value!r}, received {actual!r}")
            else:
                raise ValueError(f"Unsupported journey operation: {operation!r}")
            context.yield_(2)
            if context.is_error():
                raise AssertionError("ImGui Test Engine rejected the interaction; inspect test_engine.log")
            results.append({"step": index, "op": operation, "passed": True})
        except Exception as exc:
            results.append({"step": index, "op": operation, "passed": False, "error": str(exc)})
            imgui.test_engine.check(__file__, "run_steps", 0, imgui.test_engine.TestCheckFlags_.none,
                                    False, f"Step {index}: {operation}: {exc}")
            return
