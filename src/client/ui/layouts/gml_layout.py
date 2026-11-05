"""Python runtime support for extracted reference implementation GML layout references."""
from __future__ import annotations

import contextvars
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Sequence


_LAYOUT_DATA = Path(__file__).with_name("gml_layouts.json")
_ACTIVE_LAYOUT: contextvars.ContextVar["GMLLayoutSession | None"] = contextvars.ContextVar(
    "openpower_gml_layout", default=None
)
_API_KINDS = {
    "button": {"button"},
    "small_button": {"button"},
    "invisible_button": {"meter", "button", "trackbar", "slider"},
    "checkbox": {"toggle"},
    "radio_button": {"toggle", "button"},
    "selectable": {"button", "list_item"},
    "combo": {"combobox"},
    "begin_combo": {"combobox"},
    # Dynamic row content is rendered inside source list and combo bounds.
    "begin_child": {"frame", "custom", "label", "combobox", "listbox"},
    "begin_table": {"listbox", "frame"},
    "list_box": {"combobox", "listbox"},
    # GML numeric edit controls are catalogued as `input`, not as text boxes.
    # Leaving that kind unmatched makes their ImGui fields fall back to flow layout.
    "input_text": {"textbox", "text_input", "input"},
    "input_text_multiline": {"textbox", "text_input", "input"},
    "input_int": {"textbox", "text_input", "input"},
    "input_float": {"textbox", "text_input", "input"},
    "slider_int": {"slider", "trackbar"},
    "slider_float": {"slider", "trackbar"},
    "progress_bar": {"meter", "progressbar"},
    "text": {"label"},
    "text_unformatted": {"label"},
    "text_colored": {"label"},
    "text_disabled": {"label"},
    "text_wrapped": {"label"},
    "bullet_text": {"label"},
    "label_text": {"label"},
}
_WINDOW_TEMPLATE_BY_TEST_ID = {
    "hud.system_bar": "System_Bar_Window",
    "advisor.settings.panel": "Advisor_Settings_Window",
    "budget.panel": "Budget_Window",
    "constitutional_form.panel": "Constitutional_Form",
    "country_more_info.panel": "Country_Information_Window",
    "new_game.country_profile.dialog": "Country_Profile_Window",
    "new_game.scenario.dialog": "Scenarios_Window",
    "new_game.panel": "Start_Single_Player",
    "covert_ops.panel": "Covert_Actions_Window",
    "covert.cell_creation.dialog": "Covert_Actions_Cell_Creation",
    "covert.cell_training.dialog": "Covert_Actions_Cell_Training",
    "covert.new_mission.dialog": "Covert_Actions_New_Mission",
    "economic_health.panel": "Economic_Health_Window",
    "economy.panel": "Economic_Window",
    "history.panel": "History_Window",
    "generic_message.dialog": "Generic_Message_Window",
    "resources.increase_production.dialog": "Increase_Production_Window",
    "internal_laws.panel": "Internal_Laws",
    "laws.panel": "Internal_Laws",
    "mail.panel": "Mail_Window",
    "military.panel": "Military_Window",
    "news.panel": "Event_Log",
    "politics.panel": "Politic_Window",
    "relations.panel": "Relations_Window",
    "resources.panel": "Resources_Window",
    "treaties.panel": "Treaties_Window",
    "treaties.details.dialog": "Treaty_Details_Window",
    "treaty.participants.dialog": "Add_Remove_Window",
    "trade.panel": "Trade_Detailed_Window",
    "treaty_proposal.panel": "Treaty_Details_Window",
    "unit_design.panel": "Unit_Design_New",
    "unit_design.create.dialog": "Unit_New_Design",
    "unit_list.panel": "Unit_List_Window_New",
    "unit_market.panel": "Unit_Buy_Used_Window",
    "unit_production.panel": "Unit_Production_Window",
    "unit_research.panel": "Unit_Research_Window",
    "unit_reserves.panel": "Unit_Ground_Deployment_Window",
    "war_list.panel": "War_List_Window",
}
_WINDOW_TEMPLATE_BY_TITLE = {
    "settings": "Options_Window",
    "treaty details": "Treaty_Details_Window",
}


@dataclass(frozen=True, slots=True)
class GMLRect:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class GMLTabLayout:
    button_type: str
    button_width: float
    button_height: float
    button_distance: float
    button_offset_left: float
    frame_offset_top: float
    active_tab: int
    tab_names: tuple[str, ...]

    @property
    def page_offset_y(self) -> float:
        return self.button_height - self.frame_offset_top


@dataclass(frozen=True, slots=True)
class GMLComponent:
    path: str
    component_id: str
    kind: str
    gml_type: str
    parent: str
    order: int
    sequence: int
    z_order: int | None
    rect: GMLRect
    local_rect: GMLRect
    anchor: str
    text_token: str
    tooltip_token: str
    enabled: bool
    visible: bool
    text_offset: tuple[float, float] = (0.0, 0.0)
    text_align: str = ""
    font_size: float | None = None
    tab_layout: GMLTabLayout | None = None


@dataclass(frozen=True, slots=True)
class GMLWindowLayout:
    template: str
    width: int
    height: int
    sections: tuple[str, ...]
    components: tuple[GMLComponent, ...]
    component_template_sizes: dict[str, tuple[float, float]] = field(default_factory=dict)

    def components_named(self, component_id: str) -> tuple[GMLComponent, ...]:
        wanted = component_id.casefold()
        return tuple(
            component for component in self.components
            if component.component_id.casefold() == wanted
        )

    def component(self, path_or_id: str) -> GMLComponent | None:
        for component in self.components:
            if component.path == path_or_id:
                return component
        matches = self.components_named(path_or_id)
        return matches[0] if matches else None


def _rect(payload: dict) -> GMLRect:
    return GMLRect(
        float(payload.get("x", 0)),
        float(payload.get("y", 0)),
        float(payload.get("width", 0)),
        float(payload.get("height", 0)),
    )


@lru_cache(maxsize=1)
def all_gml_layouts() -> dict[str, GMLWindowLayout]:
    with _LAYOUT_DATA.open("r", encoding="utf-8") as source:
        payload = json.load(source)

    component_template_sizes = {
        name: (float(size["width"]), float(size["height"]))
        for name, size in payload.get("component_template_sizes", {}).items()
    }
    layouts = {}
    for window_id, raw in payload["windows"].items():
        components = tuple(
            GMLComponent(
                path=item["path"],
                component_id=item["id"],
                kind=item["kind"],
                gml_type=item["type"],
                parent=item["parent"],
                order=int(item["order"]),
                sequence=int(item["sequence"]),
                z_order=(
                    int(item["z_order"])
                    if item.get("z_order") is not None
                    else None
                ),
                rect=_rect(item["rect"]),
                local_rect=_rect(item["local_rect"]),
                anchor=item["anchor"],
                text_token=item["text_token"],
                tooltip_token=item.get("tooltip_token", ""),
                enabled=bool(item["enabled"]),
                visible=bool(item["visible"]),
                text_offset=tuple(item.get("text_offset", (0.0, 0.0))),
                text_align=item.get("text_align", ""),
                font_size=(
                    float(item["font_size"])
                    if item.get("font_size") is not None
                    else None
                ),
                tab_layout=(
                    GMLTabLayout(
                        button_type=str(item["tab_layout"].get("button_type", "")),
                        button_width=float(item["tab_layout"]["button_width"]),
                        button_height=float(item["tab_layout"]["button_height"]),
                        button_distance=float(item["tab_layout"].get("button_distance", 0)),
                        button_offset_left=float(item["tab_layout"].get("button_offset_left", 0)),
                        frame_offset_top=float(item["tab_layout"].get("frame_offset_top", 0)),
                        active_tab=int(item["tab_layout"].get("active_tab", 1)),
                        tab_names=tuple(str(name) for name in item["tab_layout"].get("tab_names", ())),
                    )
                    if item.get("tab_layout") is not None
                    else None
                ),
            )
            for item in raw["components"]
        )
        layouts[window_id] = GMLWindowLayout(
            template=raw["template"],
            width=int(raw["width"]),
            height=int(raw["height"]),
            sections=tuple(raw["sections"]),
            components=components,
            component_template_sizes=component_template_sizes,
        )
    return layouts


def get_gml_layout(template: str) -> GMLWindowLayout:
    try:
        return all_gml_layouts()[template]
    except KeyError as error:
        raise KeyError(f"No reachable GML window layout is registered for {template!r}.") from error


def resolve_gml_layout(
    template: str | None,
    *,
    test_id: str | None = None,
    title: str = "",
) -> GMLWindowLayout | None:
    resolved_template = template or _WINDOW_TEMPLATE_BY_TEST_ID.get(test_id or "")
    if resolved_template is None:
        resolved_template = _WINDOW_TEMPLATE_BY_TITLE.get(title.split("###", 1)[0].strip().casefold())
    return get_gml_layout(resolved_template) if resolved_template else None


class GMLLayoutSession:
    """Places explicitly bound Python widgets into their source GML rectangles."""

    def __init__(
        self,
        layout: GMLWindowLayout,
        window_position: tuple[float, float],
        window_size: tuple[float, float],
    ) -> None:
        self.layout = layout
        self.window_position = window_position
        self.window_size = window_size
        self._used: set[str] = set()
        self._tab_page_offsets_applied: set[str] = set()
        self._rects = self._resolve_anchored_rects()

    def _resolve_anchored_rects(self) -> dict[str, GMLRect]:
        rects: dict[str, GMLRect] = {}
        components_by_path = {component.path: component for component in self.layout.components}
        root = GMLRect(0.0, 0.0, self.window_size[0], self.window_size[1])

        for component in self.layout.components:
            if not component.parent:
                rects[component.path] = root
                continue

            parent = components_by_path.get(component.parent)
            parent_rect = rects.get(component.parent, root)
            template_size = (
                self.layout.component_template_sizes.get(parent.gml_type)
                if parent is not None else None
            )
            source_parent_width = (
                template_size[0] if template_size is not None
                else self.layout.width if parent is None
                else parent.local_rect.width
            )
            source_parent_height = (
                template_size[1] if template_size is not None
                else self.layout.height if parent is None
                else parent.local_rect.height
            )
            delta_width = parent_rect.width - source_parent_width
            delta_height = parent_rect.height - source_parent_height
            x = component.local_rect.x
            y = component.local_rect.y
            width = component.local_rect.width
            height = component.local_rect.height
            anchors = {
                part.strip().casefold()
                for part in component.anchor.split(",")
                if part.strip()
            }
            # GML omits Anchor for default-anchored controls; WinForms defaults to Top|Left.
            # https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.control.anchor
            if not anchors:
                anchors = {"top", "left"}

            if "left" in anchors and "right" in anchors:
                width = max(0.0, width + delta_width)
            elif "right" in anchors:
                x += delta_width
            elif "left" not in anchors:
                x += delta_width / 2.0

            if "top" in anchors and "bottom" in anchors:
                height = max(0.0, height + delta_height)
            elif "bottom" in anchors:
                y += delta_height
            elif "top" not in anchors:
                y += delta_height / 2.0

            rects[component.path] = GMLRect(
                parent_rect.x + x,
                parent_rect.y + y,
                width,
                height,
            )
        return rects

    def rect_for(self, component: GMLComponent | str) -> GMLRect:
        path = component.path if isinstance(component, GMLComponent) else component
        return self._rects.get(path, GMLRect(0.0, 0.0, 0.0, 0.0))

    def resize_component(self, path: str, *, width: float | None = None, height: float | None = None) -> None:
        """Apply verified source Update geometry only to this rendered instance."""
        rect = self.rect_for(path)
        self._rects[path] = replace(rect, width=rect.width if width is None else max(0, width),
                                    height=rect.height if height is None else max(0, height))

    def move_component(self, path: str, *, x: float = 0.0, y: float = 0.0) -> None:
        """Apply a verified source runtime offset without mutating shared layout data."""
        rect = self.rect_for(path)
        self._rects[path] = replace(rect, x=rect.x + x, y=rect.y + y)

    def move_subtree(self, path: str, *, x: float = 0.0, y: float = 0.0) -> None:
        """Apply one source runtime offset to a component and all of its descendants."""
        prefix = f"{path.rstrip('/')}/"
        paths = [
            component.path
            for component in self.layout.components
            if component.path == path or component.path.startswith(prefix)
        ]
        if not paths:
            raise KeyError(f"No GML component exists at {path!r}.")
        for component_path in paths:
            rect = self.rect_for(component_path)
            self._rects[component_path] = replace(
                rect,
                x=rect.x + x,
                y=rect.y + y,
            )

    def tab_button_rect(self, path: str, index: int) -> GMLRect | None:
        component = self.layout.component(path)
        if component is None or component.tab_layout is None:
            return None
        tab = component.tab_layout
        if index < 0 or index >= len(tab.tab_names):
            return None
        group_rect = self.rect_for(component)
        return GMLRect(
            group_rect.x + tab.button_offset_left
            + index * (tab.button_width + tab.button_distance),
            group_rect.y,
            tab.button_width,
            tab.button_height,
        )

    def apply_tab_page_runtime_geometry(self, path: str) -> GMLTabLayout | None:
        """Place GML tab pages below their auto-generated selector row."""
        component = self.layout.component(path)
        if component is None or component.tab_layout is None:
            return None
        if path not in self._tab_page_offsets_applied:
            for page in self.layout.components:
                if page.parent == path:
                    self.move_subtree(page.path, y=component.tab_layout.page_offset_y)
            self._tab_page_offsets_applied.add(path)
        return component.tab_layout

    def apply_base_window_titlebar_rules(self) -> None:
        """Mirror the inherited GBaseWindow title Apply relocation for this instance."""
        apply_path = f"{self.layout.template}/frmTitle/btnApply"
        lock_path = f"{self.layout.template}/frmTitle/togLockWindow"
        if self.layout.component(apply_path) is None or self.layout.component(lock_path) is None:
            return

        apply_rect = self.rect_for(apply_path)
        lock_rect = self.rect_for(lock_path)
        # GBaseWindow::OnCreate hides the lock toggle, then places Apply in its title slot.
        self.move_component(apply_path, x=lock_rect.x - apply_rect.x)

    def scale_subtree_x(self, path: str, scale: float) -> None:
        """Scale a rendered component subtree around its left edge."""
        factor = float(scale)
        if not math.isfinite(factor) or factor <= 0.0:
            raise ValueError("Horizontal layout scale must be finite and positive.")

        root_rect = self._rects.get(path)
        virtual_root = root_rect is None and path == self.layout.template
        if root_rect is None:
            if not virtual_root:
                raise KeyError(f"No GML component or layout root has path {path!r}.")
            root_rect = GMLRect(0.0, 0.0, self.window_size[0], self.window_size[1])

        for component in self.layout.components:
            rect = self._rects.get(component.path)
            if rect is None:
                continue
            if component.path == path:
                self._rects[component.path] = replace(rect, width=rect.width * factor)
            elif component.path.startswith(f"{path}/"):
                self._rects[component.path] = replace(
                    rect,
                    x=root_rect.x + (rect.x - root_rect.x) * factor,
                    width=rect.width * factor,
                )

        if virtual_root:
            self.window_size = (self.window_size[0] * factor, self.window_size[1])

    def place_widget(
        self,
        api_name: str,
        args: Sequence,
        *,
        explicit_id: str | None = None,
        align: str | None = None,
        enabled_override: bool | None = None,
    ) -> tuple[tuple, GMLComponent] | None:
        if api_name not in _API_KINDS:
            return None

        # Display text and call order depend on live country data. They cannot
        # identify a layout slot: guessing here moved unrelated widgets and
        # corrupted the cursor used by the surrounding ImGui flow layout.
        if not explicit_id:
            return None
        component = self.layout.component(explicit_id)
        source_control_compatibility = (
            component is not None
            and (
                (component.gml_type == "frmGradientBar" and api_name in {"slider_float", "progress_bar"})
                # The source technology meter is an interactive value control, so it hosts the OpenPower bounded slider.
                or (component.gml_type == "frmTechnologyMeterBlue" and api_name == "slider_float")
                # The source meter shares a row with both quantity fields; a flow-positioned slider would overflow the fixed popup.
                or (component.gml_type == "frmSplitMeter" and api_name == "slider_int")
                or (component.gml_type == "lstComboArrowUp" and api_name == "begin_child")
                or (component.gml_type == "g_def_lstbx" and api_name == "begin_child")
                # The scenario details tab control is the source-sized host for OpenPower's read-only tabs.
                or (component.gml_type == "g_def_tabbd" and api_name == "begin_child")
                or (component.gml_type == "g_def_toggl" and api_name == "invisible_button")
                # Normal GML toggles also use this custom-drawn, source-sized hit box.
                or (component.kind == "toggle" and api_name == "invisible_button")
                # Unit-list row frames are the source selection targets; the frame carries the click area.
                or (
                    component.gml_type == "g_def_frame"
                    and api_name == "invisible_button"
                    and component.path.startswith(
                        "Unit_List_Window_New/frmInner/frmList/frmList/frm"
                    )
                )
                # REFERENCE implements this vertical scroll track as a custom GML object rather than a native widget.
                or (component.gml_type == "vscrNormal" and api_name == "invisible_button")
                # The country selector uses a custom popup over the source listbox slot.
                or (component.gml_type == "cboListboxLess" and api_name == "button")
                # The create window reuses its source-rendered cost label as an editable value.
                or (
                    component.path == (
                        "Unit_New_Design/frmDesignSpecs/frm1stLvlInner1/"
                        "frmUnitInfo1/txtCost"
                    )
                    and api_name == "input_float"
                )
                # OpenPower exposes training selection and points in the source's value-label slots.
                or (
                    component.path == (
                        "Covert_Actions_Cell_Training/frmInner/frmCell/txtName"
                    )
                    and api_name == "combo"
                )
                or (
                    component.path == (
                        "Covert_Actions_Cell_Training/frmInner/frmCell/txtTraining"
                    )
                    and api_name == "slider_float"
                )
            )
        )
        if (
            component is None
            or component.path in self._used
            or not component.visible
            or self._is_native_chrome(component)
            or (component.kind not in _API_KINDS[api_name] and not source_control_compatibility)
        ):
            return None
        self._used.add(component.path)
        # GML enabled flags are initial states. Verified Python selection
        # handlers may enable a control without mutating the shared catalog.
        if enabled_override is not None:
            component = replace(component,enabled=bool(enabled_override))
        return self._place(component, api_name, args, align=align)

    @staticmethod
    def _is_native_chrome(component: GMLComponent) -> bool:
        if component.path.endswith("/frmTitle"):
            return True
        return (
            "/frmTitle/" in component.path
            and component.component_id in {"btnExit", "togLockWindow", "lblTitle"}
        )

    @staticmethod
    def _label(api_name: str, args: Sequence) -> str:
        index = 1 if api_name == "text_colored" else 0
        if len(args) <= index:
            return ""
        value = args[index]
        return value.split("##", 1)[0] if isinstance(value, str) else ""

    def _place(
        self,
        component: GMLComponent,
        api_name: str,
        args: Sequence,
        *,
        align: str | None = None,
    ) -> tuple[tuple, GMLComponent]:
        from src.client.ui.core.instrumented_imgui import imgui

        rect = self.rect_for(component)
        x = self.window_position[0] + rect.x - imgui.get_scroll_x()
        y = self.window_position[1] + rect.y - imgui.get_scroll_y()
        width = rect.width
        height = rect.height
        text_apis = {
            "text", "text_unformatted", "text_colored", "text_disabled",
            "text_wrapped", "bullet_text", "label_text",
        }
        if align is None:
            if component.text_align.endswith("Right"):
                align = "right"
            elif component.text_align.endswith("Center"):
                align = "center"
        if align in {"right", "center"} and api_name in text_apis:
            text_width = float(imgui.calc_text_size(self._label(api_name, args)).x)
            if align == "right":
                x += max(0.0, width - text_width)
            else:
                x += max(0.0, (width - text_width) / 2.0)
        if api_name in text_apis:
            # Some source labels overlap neighboring controls geometrically;
            # their TextOffset keeps the actual text clear of those controls.
            x += component.text_offset[0]
            y += component.text_offset[1]
            if component.text_align.startswith("Middle"):
                text_height = (float(imgui.calc_text_size(self._label(api_name, args), wrap_width=max(1.0, width - abs(component.text_offset[0]))).y)
                               if api_name == "text_wrapped" else float(imgui.get_font_size()))
                y += max(0.0, (height - text_height) / 2.0)
        imgui.set_cursor_screen_pos((x, y))

        updated_args = tuple(args)
        if api_name in {"button", "invisible_button"}:
            size = (width, height)
            if api_name == "invisible_button" and updated_args:
                if len(updated_args) > 1:
                    updated_args = (updated_args[0], size, *updated_args[2:])
                else:
                    updated_args = (*updated_args, size)
            elif len(updated_args) > 1:
                updated_args = (updated_args[0], size, *updated_args[2:])
            else:
                updated_args = (*updated_args, size)
        elif api_name == "begin_child":
            if len(updated_args) > 1:
                updated_args = (*updated_args[:1], (width, height), *updated_args[2:])
        elif api_name == "begin_table":
            if len(updated_args) > 3:
                updated_args = (*updated_args[:3], (width, height), *updated_args[4:])
        elif api_name == "progress_bar":
            if len(updated_args) > 1:
                updated_args = (updated_args[0], (width, height), *updated_args[2:])
        elif api_name == "input_text_multiline":
            imgui.set_next_item_width(width)
            if len(updated_args) > 2:
                updated_args = (*updated_args[:2], (width, height), *updated_args[3:])
        elif api_name in {"combo", "begin_combo", "list_box", "input_text"}:
            imgui.set_next_item_width(width)
        elif api_name.startswith(("input_", "slider_")):
            imgui.set_next_item_width(width)
        return updated_args, component

@contextmanager
def use_gml_layout(session: GMLLayoutSession) -> Iterator[GMLLayoutSession]:
    token = _ACTIVE_LAYOUT.set(session)
    try:
        yield session
    finally:
        _ACTIVE_LAYOUT.reset(token)


@contextmanager
def gml_style() -> Iterator[None]:
    """Use logical metrics that fit the source's 12–18 px control slots."""
    from src.client.ui.core.instrumented_imgui import imgui

    style = imgui.get_style()
    scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
    # The general theme's 10px vertical padding made 16px source inputs overlap.
    imgui.push_font(None, 12.0 / scale)
    imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 1.0))
    imgui.push_style_var(imgui.StyleVar_.item_spacing, (4.0, 3.0))
    try:
        yield
    finally:
        imgui.pop_style_var(2)
        imgui.pop_font()


def active_gml_layout() -> GMLLayoutSession | None:
    return _ACTIVE_LAYOUT.get()


def suspend_gml_layout() -> contextvars.Token | None:
    if _ACTIVE_LAYOUT.get() is None:
        return None
    return _ACTIVE_LAYOUT.set(None)


def resume_gml_layout(token: contextvars.Token | None) -> None:
    if token is not None:
        _ACTIVE_LAYOUT.reset(token)


def draw_gml_separator(component_path: str, *, color: tuple, thickness: float = 1.0) -> bool:
    """Draw a GML divider along the source rectangle's longer axis."""
    session = active_gml_layout()
    component = session.layout.component(component_path) if session else None
    if component is None or not component.visible:
        return False

    rect = session.rect_for(component)
    if rect.width <= 0 or rect.height <= 0:
        return False

    from src.client.ui.core.instrumented_imgui import imgui

    x = session.window_position[0] + rect.x
    y = session.window_position[1] + rect.y
    if rect.height > rect.width:
        start = (x + rect.width / 2.0, y)
        end = (start[0], y + rect.height)
    else:
        start = (x, y + rect.height / 2.0)
        end = (x + rect.width, start[1])
    imgui.get_window_draw_list().add_line(start, end, imgui.get_color_u32(color), thickness)
    return True


def create_gml_layout_session(
    template: str,
    window_position: tuple[float, float],
    window_size: tuple[float, float],
) -> GMLLayoutSession:
    return GMLLayoutSession(get_gml_layout(template), window_position, window_size)


@contextmanager
def gml_child_frame(
    component_path: str,
    *,
    padding: tuple[float, float] = (2.0, 1.0),
    bordered: bool = True,
    window_flags: int = 0,
    test_id: str | None = None,
) -> Iterator[bool]:
    """Render a child region at a named GML frame's exact rectangle."""
    from src.client.ui.core.instrumented_imgui import imgui

    session = active_gml_layout()
    component = session.layout.component(component_path) if session else None
    if component is None:
        yield False
        return

    child_flags = imgui.ChildFlags_.borders if bordered else 0
    imgui.push_style_var(imgui.StyleVar_.window_padding, padding)
    rect = session.rect_for(component)
    opened = imgui.begin_child(
        f"{component.component_id}##gml:{component.path}",
        (rect.width, rect.height),
        child_flags=child_flags,
        window_flags=window_flags,
        gml_id=component.path,
        test_id=test_id,
    )
    imgui.pop_style_var()
    try:
        yield opened
    finally:
        imgui.end_child()


def render_gml_title(
    layout: GMLWindowLayout,
    title: str,
    session: GMLLayoutSession | None = None,
) -> None:
    """Draw the title text in the source title-label rectangle using OpenPower styling."""
    title_frame = next(
        (component for component in layout.components if component.path.endswith("/frmTitle")),
        None,
    )
    title_label = next(
        (
            component for component in layout.components
            if component.component_id == "lblTitle"
            and component.parent.endswith("/frmTitle")
        ),
        None,
    )
    if title_frame is None or title_label is None:
        return

    from src.client.ui.core.instrumented_imgui import imgui
    from src.client.ui.core.theme import GAMETHEME

    session = session or GMLLayoutSession(
        layout,
        (0.0, 0.0),
        (float(layout.width), float(layout.height)),
    )
    window_position = imgui.get_window_pos()
    old_cursor = imgui.get_cursor_screen_pos()
    frame = session.rect_for(title_frame)
    frame_min = (
        float(window_position.x) + frame.x,
        float(window_position.y) + frame.y,
    )
    frame_max = (
        frame_min[0] + frame.width,
        frame_min[1] + frame.height,
    )
    imgui.get_window_draw_list().add_rect_filled(
        frame_min,
        frame_max,
        imgui.get_color_u32(GAMETHEME.colors.bg_popup),
    )

    label = session.rect_for(title_label)
    imgui.set_cursor_screen_pos((
        float(window_position.x) + label.x,
        float(window_position.y) + label.y,
    ))
    # Native ImGui hides ID suffixes; custom source title bars must do the same.
    imgui.text_colored(GAMETHEME.colors.text_main, title.split("##", 1)[0])
    inner_frame = next(
        (component for component in layout.components if component.component_id == "frmInner"),
        None,
    )
    if inner_frame is None:
        imgui.set_cursor_screen_pos(old_cursor)
    else:
        inner_rect = session.rect_for(inner_frame)
        imgui.set_cursor_screen_pos((
            float(window_position.x) + inner_rect.x,
            float(window_position.y) + inner_rect.y,
        ))


def gml_titlebar_close(layout: GMLWindowLayout) -> GMLComponent | None:
    close = next(
        (
            component for component in layout.components
            if component.component_id == "btnExit"
            and "/frmTitle/" in component.path
        ),
        None,
    )
    if close is None:
        return None
    rect = close.rect
    if (
        rect.x < 0
        or rect.y < 0
        or rect.x + rect.width > layout.width
        or rect.y + rect.height > layout.height
    ):
        return None
    return close
