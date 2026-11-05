"""Explicit source slots for compact panels; dynamic content stays in flow regions."""
from __future__ import annotations

from contextlib import contextmanager

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.core.testability import set_widget_value
from src.client.ui.core.theme import GAMETHEME, with_alpha
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    resume_gml_layout,
    suspend_gml_layout,
)


@contextmanager
def _font_scope(font_size: float | None):
    if font_size is None:
        yield
        return

    style = imgui.get_style()
    scale = max(0.1, float(style.font_scale_main) * float(style.font_scale_dpi))
    imgui.push_font(None, float(font_size) / scale)
    try:
        yield
    finally:
        imgui.pop_font()


class GMLWidgets:
    """Compose text, meters and actions without inferring bindings from labels."""

    def __init__(self, root: str) -> None:
        self.root = root.rstrip("/")

    def path(self, slot: str) -> str:
        return f"{self.root}/{slot}"

    def rect(self, slot: str):
        session = active_gml_layout()
        component = session.layout.component(self.path(slot)) if session else None
        return session.rect_for(component) if component is not None else None

    def frame(self, slot: str) -> None:
        """Draw a source frame behind controls that OpenPower renders manually."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return

        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        minimum = (x, y)
        maximum = (x + rect.width, y + rect.height)
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            minimum, maximum,
            imgui.get_color_u32(GAMETHEME.colors.panel_bg_dark),
        )
        draw_list.add_rect(
            minimum, maximum,
            imgui.get_color_u32((0.3, 0.3, 0.3, 0.55)),
            0.0, flags=0, thickness=1.0,
        )

    def picture(self, slot: str, draw) -> None:
        """Render an existing texture provider inside an anchored picture slot."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return
        previous = imgui.get_cursor_screen_pos()
        # Source pictures must follow the same virtual canvas as text when panned.
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        ))
        try:
            draw(rect.width, rect.height)
        finally:
            imgui.set_cursor_screen_pos(previous)

    def rule(self, slot: str, color=None) -> None:
        """Draw a horizontal rule inside a source picture slot."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return

        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        center_y = y + rect.height / 2.0
        draw = imgui.get_window_draw_list()
        draw.add_line(
            (x, center_y),
            (x + rect.width, center_y),
            imgui.get_color_u32(color or GAMETHEME.colors.text_dim),
            max(1.0, rect.height / 4.0),
        )

    def text(self, slot: str, value: object, *, color=None, right=False,
             max_width: float | None = None, tooltip: str | None = None,
             test_id: str | None = None, font_size: float | None = None) -> None:
        session = active_gml_layout()
        component = session.layout.component(self.path(slot)) if session else None
        if font_size is None and component is not None:
            font_size = component.font_size
        text = str(value)
        rect = self.rect(slot)
        width = min(rect.width, max_width) if rect and max_width is not None else (
            rect.width if rect else max_width
        )
        if width is not None and component is not None:
            width = max(0.0, width - abs(component.text_offset[0]))
        with _font_scope(font_size):
            display = UIPrimitives.fit_text(text, width) if width is not None else text
            imgui.text_colored(
                color or GAMETHEME.colors.text_main, display,
                gml_id=self.path(slot), gml_align="right" if right else None,
                test_id=test_id,
            )
        if imgui.is_item_hovered() and (tooltip or display != text):
            imgui.set_tooltip(tooltip or text)

    def text_at(self, slot: str, value: object, *, offset=(0.0, 0.0),
                max_width: float | None = None, color=None,
                tooltip: str | None = None, test_id: str | None = None,
                font_size: float | None = None) -> None:
        """Place dynamic text relative to an existing source frame or control."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return

        text = str(value)
        component = session.layout.component(self.path(slot))
        if font_size is None and component is not None:
            font_size = component.font_size
        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            with _font_scope(font_size):
                # Fit against the requested font; measuring before the push can truncate text that would fit.
                width = max_width if max_width is not None else rect.width - offset[0]
                display = UIPrimitives.fit_text(text, max(0.0, width))
                imgui.set_cursor_screen_pos((
                    session.window_position[0] + rect.x + offset[0] - imgui.get_scroll_x(),
                    session.window_position[1] + rect.y + offset[1] - imgui.get_scroll_y(),
                ))
                imgui.text_colored(color or GAMETHEME.colors.text_main, display, test_id=test_id)
                # Keep disabled source controls discoverable by explaining their unavailable state.
                if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                    imgui.set_tooltip(tooltip)
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)

    def hitbox(self, slot: str, test_id: str, *, enabled: bool = True,
               tooltip: str | None = None, width: float | None = None,
               height: float | None = None) -> bool:
        clicked, _ = self.hitbox_state(
            slot, test_id, enabled=enabled, tooltip=tooltip,
            width=width, height=height,
        )
        return clicked

    def hitbox_state(self, slot: str, test_id: str, *, enabled: bool = True,
                     tooltip: str | None = None,
                     width: float | None = None,
                     height: float | None = None) -> tuple[bool, bool]:
        """Add a source-sized action target and report its active hold state."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return False, False
        hit_width = rect.width if width is None else min(rect.width, max(0.0, width))
        hit_height = rect.height if height is None else min(rect.height, max(0.0, height))
        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((
                session.window_position[0] + rect.x - imgui.get_scroll_x(),
                session.window_position[1] + rect.y - imgui.get_scroll_y(),
            ))
            imgui.begin_disabled(not enabled)
            try:
                clicked = imgui.invisible_button(
                    f"##{test_id}",
                    (hit_width, hit_height),
                    test_id=test_id,
                    # A narrowed hit target is measured from two source slots,
                    # so native GML placement must not expand it back to one slot.
                    gml_id=self.path(slot) if width is None and height is None else None,
                    gml_enabled=enabled,
                )
                active = imgui.is_item_active()
            finally:
                imgui.end_disabled()
            # Disabled hitboxes still need to explain why an action is unavailable.
            if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                imgui.set_tooltip(tooltip)
            return bool(clicked), bool(active)
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)

    def button(self, slot: str, label: str, test_id: str, *, enabled=True,
               tooltip: str | None = None,dynamic_enabled=False) -> bool:
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 0.0))
        imgui.begin_disabled(not enabled)
        try:
            clicked = UIPrimitives.button(
                label,
                test_id=test_id,
                enabled=enabled,
                gml_id=self.path(slot),
                gml_enabled=enabled if dynamic_enabled else None,
            )
        finally:
            imgui.end_disabled()
            imgui.pop_style_var()
        if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(tooltip)
        return clicked

    def input_float(self, slot: str, label: str, value: float, test_id: str, *,
                    format: str = "%.1f", step: float = 0.0,
                    step_fast: float = 0.0, enabled: bool = True,
                    font_size: float | None = None) -> tuple[bool, float]:
        """Bind an editable numeric value to its source GML input rectangle."""
        with _font_scope(font_size):
            imgui.begin_disabled(not enabled)
            try:
                return imgui.input_float(
                    label,
                    float(value),
                    float(step),
                    float(step_fast),
                    format,
                    test_id=test_id,
                    gml_id=self.path(slot),
                )
            finally:
                imgui.end_disabled()

    def button_at(self, slot: str, label: str, test_id: str, *, offset=(0.0, 0.0),
                  size=(100.0, 18.0), enabled=True, tooltip=None, padding=(2.0, 0.0)) -> bool:
        """Place an OpenPower-specific action relative to an anchored source slot."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return False
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x + offset[0] - imgui.get_scroll_x(),
            session.window_position[1] + rect.y + offset[1] - imgui.get_scroll_y(),
        ))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, padding)
        imgui.begin_disabled(not enabled)
        try:
            clicked = imgui.button(label, size, test_id=test_id)
        finally:
            imgui.end_disabled()
            imgui.pop_style_var()
        if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(tooltip)
        return clicked

    def arrow_button(self, slot: str, direction: str, test_id: str, *,
                     enabled: bool = True, tooltip: str | None = None,
                     gml_id: str | None = None) -> bool:
        """Render a compact source-sized arrow action for GML stepper buttons."""
        clicked, _ = self.arrow_button_state(
            slot, direction, test_id, enabled=enabled, tooltip=tooltip,
            gml_id=gml_id,
        )
        return clicked

    def arrow_button_state(self, slot: str, direction: str, test_id: str, *,
                           enabled: bool = True, tooltip: str | None = None,
                           gml_id: str | None = None) -> tuple[bool, bool]:
        """Render a GML stepper and return its click and held states."""
        if direction not in {"up", "down"}:
            raise ValueError("Arrow direction must be 'up' or 'down'.")

        rect = self.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return False, False

        position = (
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        )
        return self.arrow_button_at_state(
            position,
            (rect.width, rect.height),
            direction,
            test_id,
            enabled=enabled,
            tooltip=tooltip,
            gml_id=gml_id,
        )

    def arrow_button_at(self, position, size, direction: str, test_id: str, *,
                        enabled: bool = True, tooltip: str | None = None,
                        gml_id: str | None = None) -> bool:
        """Render an arrow action at an absolute slot when another child owns its hit layer."""
        clicked, _ = self.arrow_button_at_state(
            position, size, direction, test_id, enabled=enabled,
            tooltip=tooltip, gml_id=gml_id,
        )
        return clicked

    def arrow_button_at_state(self, position, size, direction: str, test_id: str, *,
                              enabled: bool = True, tooltip: str | None = None,
                              gml_id: str | None = None) -> tuple[bool, bool]:
        """Render an arrow action and report whether the pointer is holding it."""
        if direction not in {"up", "down"}:
            raise ValueError("Arrow direction must be 'up' or 'down'.")

        width, height = map(float, size)
        hit_width = max(width, 12.0)
        hit_height = max(height, 16.0)
        hit_x = float(position[0]) + (width - hit_width) / 2.0
        hit_y = float(position[1]) + (height - hit_height) / 2.0
        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((hit_x, hit_y))
            imgui.begin_disabled(not enabled)
            try:
                # The source sprites are 9x8 px; keep the arrow on that slot but enlarge its transparent hit area.
                clicked = imgui.invisible_button(
                    f"##{test_id}",
                    (hit_width, hit_height),
                    test_id=test_id,
                    gml_id=gml_id,
                    gml_enabled=enabled,
                )
                active = imgui.is_item_active()
                hovered = imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled)
            finally:
                imgui.end_disabled()
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)
        if tooltip and hovered:
            imgui.set_tooltip(tooltip)
        color = (
            GAMETHEME.colors.accent if hovered and enabled
            else GAMETHEME.colors.text_main if enabled
            else with_alpha(GAMETHEME.colors.text_main, 0.4)
        )
        center_x = float(position[0]) + width / 2.0
        center_y = float(position[1]) + height / 2.0
        half_width = max(1.0, min(3.0, width * 0.34))
        half_height = max(1.0, min(2.5, height * 0.32))
        if direction == "up":
            points = (
                (center_x - half_width, center_y + half_height),
                (center_x + half_width, center_y + half_height),
                (center_x, center_y - half_height),
            )
        else:
            points = (
                (center_x - half_width, center_y - half_height),
                (center_x + half_width, center_y - half_height),
                (center_x, center_y + half_height),
            )
        imgui.get_window_draw_list().add_triangle_filled(
            *points,
            imgui.get_color_u32(color),
        )
        return bool(clicked), bool(active)

    def combo_at(self, slot: str, label: str, current_item: int, items,
                 test_id: str, *, enabled=True) -> tuple[bool, int]:
        """Place a combo in a source rectangle even when the source control has another kind."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return False, current_item

        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((
                session.window_position[0] + rect.x - imgui.get_scroll_x(),
                session.window_position[1] + rect.y - imgui.get_scroll_y(),
            ))
            imgui.set_next_item_width(rect.width)
            # Source combo slots are 16 px high; the shared GML font needs 2 px vertical padding to match them.
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
            imgui.begin_disabled(not enabled)
            try:
                return imgui.combo(
                    label,
                    current_item,
                    items,
                    test_id=test_id,
                    gml_id=self.path(slot),
                )
            finally:
                imgui.end_disabled()
                imgui.pop_style_var()
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)

    def toggle(self, slot: str, value: bool, test_id: str, *, icon: str,
               color: tuple, tooltip: str | None = None,
               enabled: bool = True) -> tuple[bool, bool]:
        """Render a compact source toggle using its full GML hit rectangle."""
        session = active_gml_layout()
        component_path = self.path(slot)
        rect = self.rect(slot)
        if session is None or rect is None:
            return False, value

        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        ))
        imgui.begin_disabled(not enabled)
        try:
            changed = imgui.invisible_button(
                f"##{test_id}",
                (rect.width, rect.height),
                test_id=test_id,
                gml_id=component_path,
            )
        finally:
            imgui.end_disabled()
        if changed:
            value = not value
        # The native invisible button reports the click, not the toggle's persistent state.
        set_widget_value(test_id, value)

        draw = imgui.get_window_draw_list()
        minimum = (
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        )
        maximum = (minimum[0] + rect.width, minimum[1] + rect.height)
        fill = with_alpha(color, 0.6 if value else 0.16)
        draw.add_rect_filled(minimum, maximum, imgui.get_color_u32(fill))
        draw.add_rect(minimum, maximum, imgui.get_color_u32(with_alpha(color, 0.85 if value else 0.4)))
        icon_size = imgui.calc_text_size(icon)
        draw.add_text(
            (minimum[0] + (rect.width - icon_size.x) / 2.0,
             minimum[1] + (rect.height - icon_size.y) / 2.0),
            imgui.get_color_u32(GAMETHEME.colors.text_main if value else color),
            icon,
        )
        if tooltip and imgui.is_item_hovered():
            imgui.set_tooltip(tooltip)
        return changed, value

    def meter(self, slot: str, fraction: float, color: tuple, *, cursor=False,
              max_width: float | None = None, background_color: tuple | None = None,
              marker_slot: str | None = None, marker_color: tuple | None = None) -> None:
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return
        fraction = max(0.0, min(1.0, float(fraction)))
        width = min(rect.width, max_width) if max_width is not None else rect.width
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled((x, y), (x + width, y + rect.height),
                             imgui.get_color_u32(background_color or GAMETHEME.colors.bg_input))
        if cursor:
            start = x + (width - 6.0) * fraction
            draw.add_rect_filled((start, y), (start + 6.0, y + rect.height),
                                 imgui.get_color_u32(color))
        elif fraction > 0:
            draw.add_rect_filled((x, y), (x + width * fraction, y + rect.height),
                                 imgui.get_color_u32(color))
        if marker_slot is not None:
            marker = self.rect(marker_slot)
            if marker is not None:
                marker_y = session.window_position[1] + marker.y - imgui.get_scroll_y()
                marker_x = x + width * fraction - 2.0
                draw.add_rect_filled(
                    (marker_x, marker_y),
                    (marker_x + marker.width, marker_y + marker.height),
                    imgui.get_color_u32(marker_color or GAMETHEME.colors.text_main),
                )

    def segmented_meter(self, slot: str, fraction: float, color: tuple,
                        test_id: str, *, tooltip: str | None = None) -> None:
        """Render a segmented meter using the child frames in its source layout."""
        session = active_gml_layout()
        component = session.layout.component(self.path(slot)) if session else None
        if session is None or component is None:
            return

        segments = sorted(
            (
                child for child in session.layout.components
                if child.parent == component.path and child.kind == "frame"
            ),
            key=lambda child: child.local_rect.x,
        )
        if not segments:
            return

        fraction = max(0.0, min(1.0, float(fraction)))
        filled_segments = fraction * len(segments)
        draw = imgui.get_window_draw_list()
        background = GAMETHEME.colors.bg_input
        border = with_alpha(GAMETHEME.colors.text_dim, 0.7)
        for index, segment in enumerate(segments):
            rect = session.rect_for(segment)
            x = session.window_position[0] + rect.x - imgui.get_scroll_x()
            y = session.window_position[1] + rect.y - imgui.get_scroll_y()
            minimum = (x, y)
            maximum = (x + rect.width, y + rect.height)
            draw.add_rect_filled(minimum, maximum, imgui.get_color_u32(background))
            draw.add_rect(minimum, maximum, imgui.get_color_u32(border))

            fill_fraction = max(0.0, min(1.0, filled_segments - index))
            inner_width = max(0.0, rect.width - 2.0)
            inner_height = max(0.0, rect.height - 2.0)
            if fill_fraction > 0.0 and inner_width > 0.0 and inner_height > 0.0:
                draw.add_rect_filled(
                    (x + 1.0, y + 1.0),
                    (x + 1.0 + inner_width * fill_fraction, y + 1.0 + inner_height),
                    imgui.get_color_u32(color),
                )

        self.hitbox(slot, test_id, tooltip=tooltip)

    def meter_slider(self, slot: str, fraction: float, test_id: str, color: tuple,
                     *, enabled: bool = True, tooltip: str | None = None,
                     show_cursor: bool = True) -> tuple[bool, float]:
        """Render an interactive source-sized meter and return its edited ratio."""
        session = active_gml_layout()
        rect = self.rect(slot)
        if session is None or rect is None:
            return False, fraction

        fraction = max(0.0, min(1.0, float(fraction)))
        updated = fraction
        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((
                session.window_position[0] + rect.x - imgui.get_scroll_x(),
                session.window_position[1] + rect.y - imgui.get_scroll_y(),
            ))
            imgui.begin_disabled(not enabled)
            try:
                imgui.invisible_button(
                    f"##{test_id}",
                    (rect.width, rect.height),
                    test_id=test_id,
                    gml_id=self.path(slot),
                )
                if imgui.is_item_active():
                    minimum = imgui.get_item_rect_min()
                    maximum = imgui.get_item_rect_max()
                    mouse_x = imgui.get_io().mouse_pos.x
                    updated = max(
                        0.0,
                        min(1.0, (mouse_x - minimum.x) / max(1.0, maximum.x - minimum.x)),
                    )
                if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                    imgui.set_tooltip(tooltip)
            finally:
                imgui.end_disabled()
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)

        self.meter(slot, updated, color)
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        if show_cursor:
            marker_x = x + rect.width * updated
            draw = imgui.get_window_draw_list()
            draw.add_rect_filled(
                (marker_x - 2.0, y - 2.0),
                (marker_x + 2.0, y + rect.height + 2.0),
                imgui.get_color_u32(GAMETHEME.colors.text_main),
            )
        return abs(updated - fraction) > 0.0001, updated
