from contextlib import ExitStack, contextmanager
import sys
from typing import Literal, Optional
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.testability import active_telemetry, semantic_region
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry
from src.client.ui.core.window_placement import (
    WindowPlacement,
    resolve_non_overlapping_position,
    resolve_window_placement,
)
from src.client.ui.layouts.gml_layout import (
    GMLLayoutSession,
    gml_titlebar_close,
    gml_style,
    resolve_gml_layout,
    render_gml_title,
    use_gml_layout,
)


_WINDOWS_WAITING_FOR_VIEWPORT: set[str] = set()
_GML_WINDOW_SETTINGS_REVISION = "v2"

class WindowManager:
    """
    Context manager for creating ImGui windows.
    """
    _close_requests: set[str] = set()
    _placements: dict[str, WindowPlacement] = {}
    _frame_placements: dict[str, WindowPlacement] = {}

    @classmethod
    def begin_frame(cls) -> None:
        """Forget last frame's visible windows before collecting current geometry."""
        cls._frame_placements.clear()
        UIAnchorRegistry.begin_frame()

    @classmethod
    def visible_frame_placements(cls) -> tuple[WindowPlacement, ...]:
        """Return positions for windows recorded during the current frame."""
        return tuple(cls._frame_placements.values())

    @classmethod
    def request_close(cls, test_id: str) -> None:
        """Use the same close path for shortcuts and title-bar buttons."""
        cls._close_requests.add(test_id)
    
    @staticmethod
    @contextmanager
    def window(title: str, x: float = 0, y: float = 0, w: float = 300, h: float = 400, 
               closable: bool = True, flags=0, test_id: str | None = None,
               gml_template: str | None = None, padding: tuple[float, float] | None = None,
               follow_position: bool = False, size_override: tuple[float, float] | None = None,
               horizontal_anchor: Literal["left", "right"] = "left",
               horizontal_margin: float = 0.0, fit_layout_width: bool = False,
               avoid_overlaps: bool = False, placement_margin: float = 8.0,
               bottom_clearance: float = 0.0, top_clearance: float = 0.0):
        """
        Creates a standard panel window.
        Yields 'True' if the window is open and expanded.
        """
        layout = resolve_gml_layout(
            gml_template,
            test_id=test_id,
            title=title,
        )
        if layout is not None:
            w, h = float(layout.width), float(layout.height)
        if size_override is not None:
            w, h = size_override

        telemetry = active_telemetry()
        if telemetry is not None:
            viewport_width, viewport_height = telemetry.viewport_size
        else:
            viewport = imgui.get_io().display_size
            if viewport.x <= 0 or viewport.y <= 0:
                viewport = imgui.get_main_viewport().size
            viewport_width, viewport_height = viewport.x, viewport.y
        window_key = test_id or title.split("###", 1)[0].strip()
        live_placement = telemetry is None or not telemetry.pin_windows
        previous_placement = WindowManager._placements.get(window_key) if live_placement and not follow_position else None
        same_viewport = previous_placement is not None and (
            previous_placement.viewport_width == viewport_width
            and previous_placement.viewport_height == viewport_height
        )
        if avoid_overlaps and same_viewport:
            x, y = previous_placement.x, previous_placement.y
        resolved_placement = resolve_window_placement(
            (x, y),
            (w, h),
            (viewport_width, viewport_height),
            previous_placement,
            horizontal_anchor=horizontal_anchor,
            horizontal_margin=horizontal_margin,
            fixed_size=layout is not None or size_override is not None,
        )
        x, y = resolved_placement.x, resolved_placement.y
        w, h = resolved_placement.width, resolved_placement.height
        if avoid_overlaps:
            x, y = resolve_non_overlapping_position(
                (x, y),
                (w, h),
                (viewport_width, viewport_height),
                tuple(
                    placement for key, placement in WindowManager._frame_placements.items()
                    if key != window_key
                ),
                margin=placement_margin,
                top_clearance=top_clearance,
                bottom_clearance=bottom_clearance,
            )
        position_condition = (
            imgui.Cond_.always
            if (telemetry is not None and telemetry.pin_windows and window_key not in telemetry.movable_window_ids)
            or follow_position or avoid_overlaps
            else imgui.Cond_.first_use_ever
        )
        if resolved_placement.viewport_changed:
            # A saved absolute coordinate can leave an anchored panel beyond a resized client area.
            position_condition = imgui.Cond_.always
        # Panels authored on a wide desktop must remain reachable on smaller
        # viewports; overflowing content remains accessible through scrolling.
        if viewport_width > 0 and viewport_height > 0:
            w, h = min(w, viewport_width), min(h, viewport_height)
            x = max(0, min(x, viewport_width - w))
            y = max(0, min(y, viewport_height - h))
            if window_key in _WINDOWS_WAITING_FOR_VIEWPORT:
                # ImGui may create the window before its first valid viewport size arrives.
                position_condition = imgui.Cond_.always
                _WINDOWS_WAITING_FOR_VIEWPORT.discard(window_key)
        else:
            _WINDOWS_WAITING_FOR_VIEWPORT.add(window_key)
        imgui.set_next_window_pos((x, y), position_condition)
        size_condition = (
            imgui.Cond_.always
            if layout is not None or resolved_placement.viewport_changed
            else imgui.Cond_.first_use_ever
        )
        imgui.set_next_window_size((w, h), size_condition)

        final_flags = flags | imgui.WindowFlags_.no_collapse
        close_component = gml_titlebar_close(layout) if layout is not None else None
        title_label = layout.component("lblTitle") if layout is not None else None
        custom_titlebar = bool(close_component and title_label)
        if custom_titlebar:
            final_flags |= imgui.WindowFlags_.no_title_bar
            if final_flags & imgui.WindowFlags_.menu_bar:
                final_flags &= ~imgui.WindowFlags_.menu_bar
        window_padding = padding if padding is not None else ((0.0, 0.0) if custom_titlebar else None)

        # False is a closed p_open value, not a request to hide the close button.
        # A non-closable source frame must pass None and stay logically open.
        imgui_title = title
        if layout is not None:
            # New GML windows must not inherit stale positions saved under their old visible titles.
            visible_title = title.split("##", 1)[0]
            viewport_key = f"{viewport_width:g}x{viewport_height:g}"
            imgui_title = (
                f"{visible_title}##openpower.gml.{_GML_WINDOW_SETTINGS_REVISION}:"
                f"{window_key}:{viewport_key}"
            )
        style_scope = gml_style() if layout is not None else None
        if style_scope is not None:
            style_scope.__enter__()
        try:
            # A failed Begin must still unwind padding and the GML style stack.
            if window_padding is not None:
                imgui.push_style_var(imgui.StyleVar_.window_padding, window_padding)
            try:
                expanded, opened = imgui.begin(imgui_title, True if closable else None, final_flags)
            finally:
                if window_padding is not None:
                    imgui.pop_style_var()
        except BaseException:
            if style_scope is not None:
                style_scope.__exit__(*sys.exc_info())
            raise

        try:
            WindowManager._update_placement(
                window_key, (viewport_width, viewport_height),
                live_placement=live_placement, follow_position=follow_position, opened=opened,
            )
            if not closable:
                opened = True
            layout_scope = None
            if layout is not None and expanded:
                layout_session, window_position = WindowManager._create_layout_session(
                    layout, fit_layout_width,
                )
                if custom_titlebar:
                    if WindowManager._render_titlebar(
                        layout, title, layout_session, window_position,
                        closable=closable, test_id=test_id,
                    ):
                        opened = False
                layout_scope = use_gml_layout(layout_session)

            if closable and window_key in WindowManager._close_requests:
                WindowManager._close_requests.discard(window_key)
                opened = False

            with ExitStack() as scopes:
                if layout_scope is not None:
                    scopes.enter_context(layout_scope)
                if test_id is not None:
                    scopes.enter_context(semantic_region(test_id, title, visible=opened and expanded))
                yield opened
        finally:
            try:
                if layout is not None and expanded:
                    # GML screen coordinates can extend past ImGui's cursor bounds.
                    imgui.dummy((1.0, 1.0))
            finally:
                try:
                    imgui.end()
                finally:
                    if style_scope is not None:
                        style_scope.__exit__(None, None, None)

    @staticmethod
    def _render_titlebar(layout, title, layout_session, window_position, *, closable, test_id) -> bool:
        close_clicked = False
        close_component = gml_titlebar_close(layout)
        render_gml_title(layout, title, layout_session)
        if closable and close_component is not None:
            close_rect = layout_session.rect_for(close_component)
            imgui.set_cursor_screen_pos((
                float(window_position.x) + close_rect.x,
                float(window_position.y) + close_rect.y,
            ))
            close_test_id = (
                f"{test_id}.close" if test_id
                else f"gml.{layout.template}.close"
            )
            if imgui.button(
                "×",
                (
                    close_rect.width,
                    close_rect.height,
                ),
                test_id=close_test_id,
            ):
                close_clicked = True
            inner_frame = layout.component("frmInner")
            if inner_frame is not None:
                inner_rect = layout_session.rect_for(inner_frame)
                imgui.set_cursor_screen_pos((
                    float(window_position.x) + inner_rect.x,
                    float(window_position.y) + inner_rect.y,
                ))
        return close_clicked

    @staticmethod
    def _update_placement(window_key, viewport_size, *, live_placement, follow_position, opened) -> None:
        viewport_width, viewport_height = viewport_size
        if viewport_width > 0 and viewport_height > 0:
            # ImGui can restore an old absolute position from imgui.ini before the
            # in-memory placement cache has a chance to re-anchor the panel.
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            visible_placement = resolve_window_placement(
                (float(actual_position.x), float(actual_position.y)),
                (float(actual_size.x), float(actual_size.y)),
                (float(viewport_width), float(viewport_height)),
            )
            if (visible_placement.width, visible_placement.height) != (actual_size.x, actual_size.y):
                imgui.set_window_size(
                    (visible_placement.width, visible_placement.height),
                    imgui.Cond_.always,
                )
            if (visible_placement.x, visible_placement.y) != (actual_position.x, actual_position.y):
                imgui.set_window_pos(
                    (visible_placement.x, visible_placement.y),
                    imgui.Cond_.always,
                )
        if live_placement and not follow_position and viewport_width > 0 and viewport_height > 0:
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            WindowManager._placements[window_key] = WindowPlacement(
                float(viewport_width),
                float(viewport_height),
                float(actual_position.x),
                float(actual_position.y),
                float(actual_size.x),
                float(actual_size.y),
            )
        if opened and viewport_width > 0 and viewport_height > 0:
            actual_position = imgui.get_window_pos()
            actual_size = imgui.get_window_size()
            active_placement = WindowPlacement(
                float(viewport_width),
                float(viewport_height),
                float(actual_position.x),
                float(actual_position.y),
                float(actual_size.x),
                float(actual_size.y),
            )
            WindowManager._frame_placements[window_key] = active_placement

    @staticmethod
    def _create_layout_session(layout, fit_layout_width):
        window_position = imgui.get_window_pos()
        window_size = imgui.get_window_size()
        layout_session = GMLLayoutSession(
            layout,
            (float(window_position.x), float(window_position.y)),
            (
                float(layout.width) if fit_layout_width and window_size.x < layout.width
                else float(window_size.x),
                float(window_size.y),
            ),
        )
        if fit_layout_width and 0.0 < window_size.x < layout.width:
            # Compress only when the viewport is narrower than the source frame.
            layout_session.scale_subtree_x(layout.template, float(window_size.x) / layout.width)
        layout_session.apply_base_window_titlebar_rules()
        return layout_session, window_position

    @staticmethod
    @contextmanager
    def popup(title: str):
        if imgui.begin_popup(title):
            try:
                yield
            finally:
                imgui.end_popup()

    @staticmethod
    @contextmanager
    def centered_modal(name: str, sw: float, sh: float, w: float = 300, h: float = 400):
        pos_x = (sw - w) / 2
        pos_y = (sh - h) / 2
        
        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((w, h))
        
        flags = (imgui.WindowFlags_.no_title_bar | 
                 imgui.WindowFlags_.no_move)
        
        if imgui.begin(name, None, flags):
            try:
                yield
            finally:
                imgui.end()
