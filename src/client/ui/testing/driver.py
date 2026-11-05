from __future__ import annotations

import math
import time
from typing import Any

from imgui_bundle import imgui

from src.client.ui.core.testability import UIRunTelemetry


class UITestDriver:
    """Resolve stable OpenPower test IDs to the live ImGui Test Engine."""

    def __init__(self, context: imgui.test_engine.TestContext, telemetry: UIRunTelemetry):
        self._context = context
        self._telemetry = telemetry

    def exists(self, test_id: str) -> bool:
        current = self._telemetry.widget(test_id)
        if current is None or not current["present"]:
            return False
        widget, region = self._resolve(test_id)
        if not widget["imgui_id"]:
            return bool(widget["visible"])
        return self._context.item_exists(imgui.test_engine.TestRef(int(widget["imgui_id"])))

    def click(self, test_id: str) -> None:
        widget, _ = self._resolve(test_id)
        if not widget["enabled"]:
            raise ValueError(f"Widget '{test_id}' is disabled.")
        rect = widget["rect"]
        center = (
            float(rect["x"]) + float(rect["width"]) / 2.0,
            float(rect["y"]) + float(rect["height"]) / 2.0,
        )
        self._context.mouse_teleport_to_pos(center)
        self._context.mouse_click()

    def hold(self, test_id: str, frames: int) -> None:
        widget, _ = self._resolve(test_id)
        if not widget["enabled"]:
            raise ValueError(f"Widget '{test_id}' is disabled.")
        rect = widget["rect"]
        center = (
            float(rect["x"]) + float(rect["width"]) / 2.0,
            float(rect["y"]) + float(rect["height"]) / 2.0,
        )
        self._context.mouse_teleport_to_pos(center)
        self._context.mouse_down()
        self._context.yield_(frames)
        self._context.mouse_up()

    def hold_for(self, test_id: str, duration_ms: int) -> None:
        if duration_ms <= 0 or duration_ms > 10_000:
            raise ValueError("Timed hold must be between 1 and 10000 milliseconds.")
        widget, _ = self._resolve(test_id)
        if not widget["enabled"]:
            raise ValueError(f"Widget '{test_id}' is disabled.")
        rect = widget["rect"]
        center = (
            float(rect["x"]) + float(rect["width"]) / 2.0,
            float(rect["y"]) + float(rect["height"]) / 2.0,
        )
        self._context.mouse_teleport_to_pos(center)
        self._context.mouse_down()
        deadline = time.perf_counter() + duration_ms / 1000.0
        try:
            while time.perf_counter() < deadline:
                self._context.yield_(1)
        finally:
            self._context.mouse_up()

    def hover(self, test_id: str) -> None:
        widget, _ = self._resolve(test_id)
        rect = widget["rect"]
        self._context.mouse_teleport_to_pos((rect["x"] + rect["width"] / 2,
                                               rect["y"] + rect["height"] / 2))

    def input_value(self, test_id: str, value: int | float | str | list) -> None:
        widget, region = self._resolve(test_id)
        if widget.get("components"):
            if not isinstance(value, list) or len(value) != len(widget["components"]):
                raise ValueError("Vector input requires one value per component.")
            for component, entry in zip(widget["components"], value):
                self._context.item_input_value(imgui.test_engine.TestRef(component["imgui_id"]), entry)
            return
        if not widget["imgui_id"]:
            raise ValueError(f"Widget '{test_id}' has no native input ID.")
        if widget["type"] in {"slider_float", "slider_int"}:
            scalar = float(value) if widget["type"] == "slider_float" else int(value)
            self._context.item_input_value(
                imgui.test_engine.TestRef(int(widget["imgui_id"])),
                scalar,
            )
            return
        rect = widget["rect"]
        center = (
            float(rect["x"]) + float(rect["width"]) / 2.0,
            float(rect["y"]) + float(rect["height"]) / 2.0,
        )
        self._context.mouse_teleport_to_pos(center)
        self._context.mouse_click()
        self._context.key_chars_replace_enter(str(value))

    def replace_focused_value(self, test_id: str, value: int | float | str) -> None:
        widget, _ = self._resolve(test_id)
        if widget["type"] != "input_text":
            raise ValueError("Focused text replacement requires a native text input.")
        self._context.key_chars_replace_enter(str(value))

    def replace_focused_text(self, test_id: str, value: int | float | str) -> None:
        widget, _ = self._resolve(test_id)
        if widget["type"] != "input_text":
            raise ValueError("Focused text replacement requires a native text input.")
        self._context.key_chars_replace(str(value))

    def drag_to_fraction(self, test_id: str, fraction: float) -> None:
        widget, _ = self._resolve(test_id)
        if widget["type"] not in {"invisible_button", "slider_int", "slider_float"}:
            raise ValueError(f"Widget '{test_id}' is not a supported drag target.")
        fraction = max(0.0, min(float(fraction), 1.0))
        rect = widget["rect"]
        x = float(rect["x"])
        y = float(rect["y"])
        width = float(rect["width"])
        height = float(rect["height"])
        center_y = y + height / 2.0
        if widget["type"] in {"slider_int", "slider_float"}:
            end_x = min(width - 0.5, max(0.5, width * fraction))
            self._context.item_drag_with_delta(
                imgui.test_engine.TestRef(int(widget["imgui_id"])),
                imgui.ImVec2(end_x - width / 2.0, 0.0),
            )
            return
        vertical = widget["type"] == "invisible_button" and height > width
        start = (x + width / 2.0, center_y)
        if vertical:
            end_y = min(y + height - 0.5, max(y + 0.5, y + height * fraction))
            end = (start[0], end_y)
        else:
            # Keep the pointer within the item; an endpoint exactly on the right edge misses it.
            end_x = min(x + width - 0.5, max(x + 0.5, x + width * fraction))
            end = (end_x, center_y)
        self._context.mouse_teleport_to_pos(start)
        self._context.mouse_down()
        self._context.yield_(1)
        # Source GML scrollbars are vertical; their requested fraction follows the y axis.
        self._context.mouse_teleport_to_pos(end)
        self._context.yield_(2)
        self._context.mouse_up()

    def drag_window(self, test_id: str, dx: float, dy: float) -> None:
        region = self._telemetry.region(test_id)
        if not region or not region["present"] or not region["visible"] or region["kind"] != "window":
            raise ValueError(f"Window '{test_id}' is not visible.")
        rect = region["rect"]
        if not math.isfinite(dx) or not math.isfinite(dy) or abs(dx) + abs(dy) < 10:
            raise ValueError("Window drag must exceed the ImGui drag threshold.")
        # Deterministic screenshot runs normally pin windows each frame, preventing any user drag.
        self._telemetry.movable_window_ids.add(test_id)
        self._context.yield_(2)
        start = (
            float(rect["x"]) + min(80.0, float(rect["width"]) / 2),
            float(rect["y"]) + 7.0,
        )
        self._context.mouse_teleport_to_pos(start)
        self._context.mouse_down()
        self._context.yield_(3)
        for fraction in (0.25, 0.5, 0.75, 1.0):
            self._context.mouse_teleport_to_pos((start[0] + dx * fraction, start[1] + dy * fraction))
            self._context.yield_(2)
        self._context.mouse_up()
        self._context.yield_(3)
        moved = self._telemetry.region(test_id)
        if (
            not moved
            or abs(float(moved["rect"]["x"]) - float(rect["x"]) - dx) > 3
            or abs(float(moved["rect"]["y"]) - float(rect["y"]) - dy) > 3
        ):
            raise AssertionError(
                f"Window '{test_id}' did not move by ({dx}, {dy}): {moved and moved['rect']}"
            )

    def _resolve(self, test_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        widget = self._telemetry.widget(test_id)
        if widget is None or not widget["present"]:
            raise KeyError(f"No visible UI widget has test_id '{test_id}'.")
        parent_id = widget.get("parent_id")
        region = self._telemetry.region(str(parent_id)) if parent_id else None
        if region is None:
            raise KeyError(f"No semantic UI region contains widget '{test_id}'.")
        return widget, region

    def find(self, selector: str | dict) -> str:
        """Resolve an exact ID or an unambiguous semantic selector."""
        matches = self.matches(selector)
        if len(matches) != 1:
            raise ValueError(f"Selector {selector!r} matched {len(matches)} widgets: {matches}")
        return matches[0]

    def matches(self, selector: str | dict) -> list[str]:
        if isinstance(selector, str):
            widget = self._telemetry.widget(selector)
            return [selector] if widget is not None and widget["present"] else []
        allowed = {"id", "label", "type", "source", "region"}
        if not selector or set(selector) - allowed:
            raise ValueError(f"Unsupported or empty UI selector: {selector!r}")
        snapshot = self._telemetry.to_dict()
        regions = {r["id"]: r for r in snapshot["regions"]}
        matches = []
        for widget in snapshot["widgets"]:
            if not widget["present"]:
                continue
            if any(widget.get(k) != v for k, v in selector.items() if k in {"id", "label", "type"}):
                continue
            if "source" in selector and selector["source"] not in widget.get("source", {}).get("path", ""):
                continue
            ancestor = regions.get(widget.get("parent_id"))
            ancestors = []
            while ancestor:
                ancestors.extend([ancestor["id"], ancestor["label"]])
                ancestor = regions.get(ancestor.get("parent_id"))
            if "region" in selector and selector["region"] not in ancestors:
                continue
            matches.append(widget["id"])
        return matches

    def open(self, test_id: str) -> None:
        widget, _ = self._resolve(test_id)
        self._context.item_open(imgui.test_engine.TestRef(int(widget["imgui_id"])))

    def check(self, test_id: str, checked: bool = True) -> None:
        widget, _ = self._resolve(test_id)
        operation = self._context.item_check if checked else self._context.item_uncheck
        operation(imgui.test_engine.TestRef(int(widget["imgui_id"])))

    def select(self, test_id: str, option: str | int) -> None:
        widget, _ = self._resolve(test_id)
        if widget["type"] != "combo" or not widget.get("options"):
            raise ValueError("Selection requires a combo with recorded options.")
        index = widget["options"].index(option) if isinstance(option, str) else int(option)
        if not 0 <= index < len(widget["options"]):
            raise ValueError("Combo option index is out of range.")
        self.click(test_id)
        self._context.yield_(2)
        # Mouse-opened combos retain navigation focus differently across ImGui
        # versions. Select the actual native option rather than guessing key counts.
        if len(widget["options"]) > 8:
            # Native Combo clips long lists; make the requested item exist
            # before asking the test engine to resolve its label.
            self._context.scroll_to_y("##Combo_00", index * widget["rect"]["height"])
            self._context.yield_(2)
        # Slashes in option labels are path characters to ImGui Test Engine.
        option_label = widget["options"][index].replace("/", "\\/")
        self._context.item_click(f"**/{option_label}")
        # Allow the closed combo and its parent window to be recorded in a fresh frame.
        self._context.yield_(2)

    def scroll(self, test_id: str) -> None:
        widget, _ = self._resolve(test_id)
        if not widget["imgui_id"]:
            if widget["visible"]:
                return
            region_id = widget.get("parent_id")
            while region_id:
                region = self._telemetry.region(str(region_id))
                if region is None:
                    break
                if region.get("kind") == "child":
                    item_rect = widget["rect"]
                    viewport = region["rect"]
                    item_top = float(item_rect["y"])
                    item_bottom = item_top + float(item_rect["height"])
                    viewport_top = float(viewport["y"])
                    viewport_bottom = viewport_top + float(viewport["height"])
                    if item_top < viewport_top:
                        distance = viewport_top - item_top
                        wheel_direction = 1.0
                    elif item_bottom > viewport_bottom:
                        distance = item_bottom - viewport_bottom
                        wheel_direction = -1.0
                    else:
                        return
                    line_height = max(float(item_rect["height"]), 1.0)
                    wheel_steps = min(50, max(1, math.ceil(distance / (5.0 * line_height))))
                    self._context.mouse_teleport_to_pos((
                        float(viewport["x"]) + float(viewport["width"]) / 2.0,
                        viewport_top + float(viewport["height"]) / 2.0,
                    ))
                    # Display-only rows have no native ImGui ID; use the same
                    # wheel gesture a player uses over their nearest child list.
                    self._context.mouse_wheel_y(wheel_direction * wheel_steps)
                    return
                region_id = region.get("parent_id")
            raise ValueError(
                f"Widget '{test_id}' has no ImGui ID or scrollable child ancestor."
            )
        # Fixed source canvases can exceed both viewport axes. Scrolling only
        # vertically left their right-edge controls unreachable in small runs.
        self._context.scroll_to_item_x(imgui.test_engine.TestRef(int(widget["imgui_id"])))
        self._context.scroll_to_item_y(imgui.test_engine.TestRef(int(widget["imgui_id"])))

    def close_window(self, region_id: str) -> None:
        region = self._telemetry.region(region_id)
        if region is None or not region["present"] or not region["visible"]:
            raise KeyError(f"No visible UI window has test_id '{region_id}'.")
        if region.get("kind") != "window":
            raise ValueError(f"UI region '{region_id}' is not a window.")
        custom_close = self._telemetry.widget(f"{region_id}.close")
        if custom_close is not None and custom_close["present"] and custom_close["visible"]:
            self.click(f"{region_id}.close")
            return
        rect = region["rect"]
        self._context.mouse_teleport_to_pos(
            (float(rect["x"]) + float(rect["width"]) - 14.0, float(rect["y"]) + 12.0)
        )
        self._context.mouse_click()
