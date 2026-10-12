from __future__ import annotations

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
        if widget["imgui_id"]:
            self._context.item_click(imgui.test_engine.TestRef(int(widget["imgui_id"])))
            return
        rect = widget["rect"]
        center = (
            float(rect["x"]) + float(rect["width"]) / 2.0,
            float(rect["y"]) + float(rect["height"]) / 2.0,
        )
        self._context.mouse_teleport_to_pos(center)
        self._context.mouse_click()

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
        self._context.item_input_value(
            imgui.test_engine.TestRef(int(widget["imgui_id"])), value
        )

    def drag_to_fraction(self, test_id: str, fraction: float) -> None:
        widget, _ = self._resolve(test_id)
        if widget["type"] != "invisible_button":
            raise ValueError(f"Widget '{test_id}' is not a custom drag target.")
        fraction = max(0.0, min(float(fraction), 1.0))
        rect = widget["rect"]
        x = float(rect["x"])
        y = float(rect["y"])
        width = float(rect["width"])
        height = float(rect["height"])
        center_y = y + height / 2.0
        self._context.mouse_teleport_to_pos((x + width / 2.0, center_y))
        self._context.mouse_down()
        self._context.yield_(1)
        self._context.mouse_teleport_to_pos((x + width * fraction, center_y))
        self._context.yield_(2)
        self._context.mouse_up()

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
        self._context.item_click(imgui.test_engine.TestRef(int(widget["imgui_id"])))
        self._context.key_press(imgui.Key.home)
        if index:
            self._context.key_press(imgui.Key.down_arrow, index)
        self._context.key_press(imgui.Key.enter)

    def scroll(self, test_id: str) -> None:
        widget, _ = self._resolve(test_id)
        self._context.scroll_to_item_y(imgui.test_engine.TestRef(int(widget["imgui_id"])))
