"""Geometry diagnostics independent of ImGui and the rendering backend."""
from __future__ import annotations

import math


def contains(outer: dict, inner: dict, tolerance: float = 1.0) -> bool:
    return (inner["x"] >= outer["x"] - tolerance and inner["y"] >= outer["y"] - tolerance
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + tolerance
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + tolerance)


def overlaps(a: dict, b: dict, tolerance: float = 1.0) -> bool:
    return (min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]) > tolerance
            and min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]) > tolerance)


def analyze_layout(snapshot: dict) -> list[dict]:
    viewport = {"x": 0, "y": 0, **snapshot["viewport"]}
    regions = {r["id"]: r for r in snapshot["regions"] if r.get("present", True)}
    findings = []

    def emit(code, item, severity="error", related=None):
        findings.append({"code": code, "severity": severity, "id": item["id"],
                         "rect": item["rect"], "source": item.get("source", {}), "related_id": related})

    items = list(regions.values()) + [w for w in snapshot["widgets"] if w.get("present", True)]
    for item in items:
        rect = item["rect"]
        if not all(math.isfinite(v) for v in rect.values()) or rect["width"] < 0 or rect["height"] < 0:
            emit("invalid_geometry", item)
        if item.get("kind") == "window" and item["visible"] and not contains(viewport, rect):
            emit("window_outside_viewport", item)
        if item.get("interactive") and item["visible"]:
            if rect["width"] <= 0 or rect["height"] <= 0:
                emit("zero_size_control", item)
            parent = regions.get(item.get("parent_id"))
            if parent and not contains(parent["rect"], rect):
                emit("control_partially_clipped", item, "warning", parent["id"])
    controls = [w for w in snapshot["widgets"] if w.get("present", True) and w["visible"]
                and w.get("interactive") and w["enabled"] and w["type"] not in {"tree_node_ex", "tree_node", "collapsing_header", "begin_menu", "begin_tab_item", "begin_combo"}]
    for i, left in enumerate(controls):
        for right in controls[i + 1:]:
            if left.get("parent_id") == right.get("parent_id") and overlaps(left["rect"], right["rect"]):
                emit("controls_overlap", left, "warning", right["id"])
    native_ids = {}
    for item in controls:
        native_id = item.get("imgui_id", 0)
        if native_id and native_id in native_ids:
            emit("duplicate_imgui_id", item, "error", native_ids[native_id])
        elif native_id:
            native_ids[native_id] = item["id"]
    return findings
