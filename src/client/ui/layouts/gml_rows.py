"""Compose repeated GML rows using the same anchor placement as source windows."""
import json
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.layouts.gml_layout import GMLComponent, GMLRect, GMLWindowLayout, GMLLayoutSession, use_gml_layout


def _component_kind(component_type: str) -> str:
    normalized = component_type.casefold()
    if normalized.startswith("btn") or "button" in normalized:
        return "button"
    if "toggl" in normalized or "check" in normalized:
        return "toggle"
    # REFERENCE row controls use custom names such as cboBlackArrowUp; leaving those
    # classified as labels makes the combo fall back to ImGui flow placement.
    if normalized.startswith("cbo") or "combo" in normalized:
        return "combobox"
    return "label"


@lru_cache(maxsize=None)
def row_layout(name):
    raw = json.loads(Path(__file__).with_name("gml_rows.json").read_text(encoding="utf-8"))[name]
    props = raw["properties"]
    components = []

    def visit(child, parent_path, order):
        p = child["properties"]
        rect = GMLRect(*(float(p.get(key) or 0) for key in ("Left", "Top", "Width", "Height")))
        path = parent_path + "/" + child["name"]
        components.append(GMLComponent(
            path=path, component_id=child["name"],
            kind=_component_kind(child["type"]),
            gml_type=child["type"], parent=parent_path, order=order,
            sequence=len(components), z_order=None,
            rect=rect, local_rect=rect, anchor=p.get("Anchor", ""), text_token=p.get("Text", ""),
            tooltip_token=p.get("ToolTipText", ""), enabled=p.get("Enabled", "True") == "True",
            visible=p.get("Visible", "True") == "True",
            text_align=p.get("TextAlign", ""),
            text_offset=tuple(float(v.strip()) for v in p.get("TextOffset", "0, 0").split(",")),
            font_size=float(p["FontSize"]) if p.get("FontSize") else None))
        for child_order, nested in enumerate(child.get("children", [])):
            visit(nested, path, child_order)

    for index, child in enumerate(raw["children"]):
        visit(child, name, index)
    return GMLWindowLayout(name, int(props["Width"]), int(props["Height"]), (), tuple(components))


@contextmanager
def gml_row(name, identity, *, width: float | None = None):
    layout = row_layout(name)
    row_width = layout.width if width is None else min(layout.width, max(1.0, float(width)))
    horizontal_scale = row_width / layout.width
    start = imgui.get_cursor_screen_pos()
    # The child cursor already includes scrolling; the shared placement session
    # subtracts it, so restore the virtual origin once to avoid double scrolling.
    session = GMLLayoutSession(layout, (start.x + imgui.get_scroll_x(), start.y + imgui.get_scroll_y()),
                               (layout.width, layout.height))
    if horizontal_scale < 1.0:
        session.scale_subtree_x(layout.template, horizontal_scale)
    imgui.push_id(str(identity))
    imgui.push_style_var(imgui.StyleVar_.frame_padding, (3, 2))
    imgui.push_style_var(imgui.StyleVar_.item_spacing, (0, 0))
    try:
        with use_gml_layout(session):
            yield GMLWidgets(name)
    finally:
        imgui.set_cursor_screen_pos(start)
        imgui.dummy((row_width, layout.height))
        imgui.pop_style_var(2)
        imgui.pop_id()
