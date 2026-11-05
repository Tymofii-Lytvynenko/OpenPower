import ctypes  # Required for raw pointer handling in ImGui

import arcade

from src.client.services.imgui_service import ImGuiService
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.core.theme import UITheme
from src.client.ui.layouts.gml_layout import (
    create_gml_layout_session,
    render_gml_title,
    resolve_gml_layout,
    use_gml_layout,
)


class UIComposer:
    """
    A high-level UI composition helper.
    Abstracts raw ImGui calls into semantic components (Panels, Meters, Toggles)
    styled according to the provided UITheme.
    """
    def __init__(self, theme: UITheme):
        self.theme = theme
        self._gml_layout_scopes = []

    def setup_frame(self):
        """Applies global theme styles for the current frame."""
        self.theme.apply()

    # =========================================================
    # 1. WINDOW / PANEL MANAGEMENT
    # =========================================================

    def begin_panel(self, name: str, x: float, y: float, w: float, h: float, is_visible: bool = True):
        """
        Starts a standard floating window with a close button.
        
        Args:
            name: Window title (also used as ID).
            x, y: Default position (only applies on first run).
            w, h: Default size (only applies on first run).
            is_visible: Boolean reference for the close button.

        Returns:
            (expanded, opened):
                - expanded (bool): True if window content is visible (not collapsed).
                - opened (bool): False if the user clicked the 'X' close button.
        """
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((w, h), imgui.Cond_.first_use_ever)
        
        # Standard flags: No collapsing to title bar only
        flags = imgui.WindowFlags_.no_collapse

        # Begin returns: (is_expanded, is_open)
        expanded, opened = imgui.begin(name, is_visible, flags)
        
        return expanded, opened

    def end_panel(self):
        """Ends the current window context."""
        if self._gml_layout_scopes:
            self._gml_layout_scopes.pop().__exit__(None, None, None)
        imgui.end()

    def begin_centered_panel(self, name: str, sw: float, sh: float, w: float = 300, h: float = 400,
                             test_id: str | None = None,
                             gml_template: str | None = None,
                             force_size: bool = False,
                             size_override: tuple[float, float] | None = None):
        """
        Starts a modal-like window centered on screen.
        Used for Menus, Loading Screens, etc.
        """
        layout = resolve_gml_layout(gml_template, title=name)
        if layout is not None:
            w, h = float(layout.width), float(layout.height)
        if size_override is not None:
            w, h = map(float, size_override)

        # Center calculation
        pos_x = (sw - w) / 2
        pos_y = (sh - h) / 2
        
        imgui.set_next_window_pos((pos_x, pos_y))
        size_condition = (
            imgui.Cond_.always
            if layout is not None or force_size
            else imgui.Cond_.first_use_ever
        )
        imgui.set_next_window_size((w, h), size_condition)
        
        # Thicker border for modal look
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 8.0)
        if layout is not None:
            imgui.push_style_var(imgui.StyleVar_.window_padding, (0.0, 0.0))
        
        flags = (imgui.WindowFlags_.no_title_bar | 
                 imgui.WindowFlags_.no_resize | 
                 imgui.WindowFlags_.no_move)
        
        # Pass None for p_open to hide close button
        is_visible, _ = imgui.begin(name, None, flags, test_id=test_id)

        imgui.pop_style_var(3 if layout is not None else 2)
        if layout is not None and is_visible:
            window_position = imgui.get_window_pos()
            window_size = imgui.get_window_size()
            layout_session = create_gml_layout_session(
                gml_template or layout.template,
                (float(window_position.x), float(window_position.y)),
                (float(window_size.x), float(window_size.y)),
            )
            render_gml_title(layout, name, layout_session)
            scope = use_gml_layout(layout_session)
            scope.__enter__()
            self._gml_layout_scopes.append(scope)
        elif not is_visible:
            imgui.end()
        return is_visible

    # =========================================================
    # 2. LAYOUT HELPERS
    # =========================================================

    def dummy(self, size: tuple[float, float]):
        """Inserts empty space of specific size."""
        imgui.dummy(imgui.ImVec2(size[0], size[1]))

    def space(self, w: float):
        """Advances cursor horizontally by 'w' pixels."""
        imgui.dummy((w, 0))

    def right_align(self, width: float):
        """
        Moves the cursor to the right side of the available region,
        leaving exactly `width` pixels for the next item.
        Useful for right-aligned text or buttons in headers.
        """
        avail_w = imgui.get_content_region_avail().x
        if avail_w > width:
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - width)

    def centered_text(self, text: str):
        """Draws text centered horizontally in the current window."""
        width = imgui.calc_text_size(text).x
        self.right_align(imgui.get_content_region_avail().x / 2 + width / 2)
        imgui.text(text)

    # =========================================================
    # 3. WIDGETS & COMPONENTS
    # =========================================================

    def draw_title(self, text: str):
        """Draws a large centered title with a separator."""
        # Center calculation
        window_w = imgui.get_window_width()
        text_w = imgui.calc_text_size(text).x
        imgui.set_cursor_pos_x((window_w - text_w) / 2)
        
        imgui.text(text)
        imgui.separator()
        self.dummy((0, 10))

    def draw_menu_button(self, label: str, w: float = -1, h: float = 40,
                         test_id: str | None = None,
                         gml_id: str | None = None,
                         enabled: bool = True,
                         tooltip: str | None = None) -> bool:
        """
        Draws a large menu button (standard height 40px).
        Returns True if clicked.
        """
        imgui.begin_disabled(not enabled)
        try:
            clicked = UIPrimitives.button(
                label,
                test_id=test_id,
                size=(w, h),
                enabled=enabled,
                gml_id=gml_id,
                gml_enabled=enabled,
            )
        finally:
            imgui.end_disabled()
        if tooltip and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(tooltip)
        self.dummy((0, 5)) # Spacing below
        return clicked

    def draw_section_header(self, label: str, show_more_btn: bool = True):
        """
        Draws a styled header bar with a background color.
        """
        UIPrimitives.header(label, theme=self.theme)

    def draw_meter(self, label: str, value: float, color: tuple, show_percentage: bool = True):
        """
        Draws a label and a horizontal progress bar (0-100 range).
        """
        UIPrimitives.meter(label, value, color, theme=self.theme)

    def draw_currency_row(self, label: str, value: float, color_val: tuple | None = None):
        """
        Draws a row with 'Label ......... $ Value'.
        Value is formatted with spaces as thousand separators.
        """
        UIPrimitives.currency_row(label, value, color_val, theme=self.theme)

    def draw_progress_bar(self, fraction: float, text: str = "", width: float = -1, height: float = 20):
        """
        Standard ImGui ProgressBar wrapper with theme colors.
        """
        UIPrimitives.progress_bar(
            fraction,
            text,
            width,
            height,
            theme=self.theme,
        )

    def draw_icon_toggle(self, icon: str, color: tuple, is_active: bool, width: float = 50, height: float = 50) -> bool:
        """
        Draws a large toggle button for the main HUD toolbar.
        Includes a colored underline indicator when active.
        """
        return UIPrimitives.icon_toggle(
            icon,
            color,
            is_active,
            width,
            height,
            show_inactive_indicator=True,
            theme=self.theme,
        )

    # =========================================================
    # 4. IMAGES & TEXTURES
    # =========================================================

    def draw_image(self, texture: arcade.Texture, width: float, height: float):
        """
        Draws an Arcade Texture in ImGui. 
        Handles GL ID extraction and ImVec2 type casting automatically.
        """
        if not texture:
            self.dummy((width, height))
            return

        try:
            # 1. Get ID via Service (Returns int)
            tex_id = ImGuiService.get_texture_id(texture)
            
            if tex_id == 0:
                self.dummy((width, height))
                return
            
            # 2. Draw with Correct Binding
            imgui.image(ctypes.c_void_p(tex_id), imgui.ImVec2(width, height)) # type: ignore

        except Exception:
            # Fallback to prevent crashes
            # print(f"[UIComposer] draw_image error: {e}")
            self.dummy((width, height))

    # =========================================================
    # 5. POPUP & MENU METHODS
    # =========================================================

    def begin_context_menu(self, str_id: str = "map_context"):
        """Triggers a popup context window on right-click."""
        return imgui.begin_popup_context_window(str_id, imgui.PopupFlags_.mouse_button_right)

    def open_popup(self, str_id: str):
        """Manually triggers a popup to open."""
        imgui.open_popup(str_id)

    def begin_popup(self, str_id: str) -> bool:
        """Starts rendering the popup content if it was opened."""
        return imgui.begin_popup(str_id)

    def end_popup(self):
        """Ends the current popup context."""
        imgui.end_popup()

    def begin_menu(self, label: str) -> bool:
        """Starts a menu dropdown (e.g., File, Edit)."""
        return imgui.begin_menu(label)

    def end_menu(self):
        """Ends a menu dropdown."""
        imgui.end_menu()

    def draw_menu_item(
        self,
        label: str,
        shortcut: str = "",
        *,
        test_id: str | None = None,
    ) -> bool:
        """Draws a clickable menu item. Returns True if clicked."""
        clicked, _ = imgui.menu_item(label, shortcut, False, True, test_id=test_id)
        return clicked

    def is_background_clicked(self) -> bool:
        """
        Detects a clean right-click release on the background.
        Calculates the drag delta to ensure the user wasn't panning the map.
        """
        # If user interacts with UI, don't trigger context menu
        if imgui.get_io().want_capture_mouse:
            return False

        # Check Right Mouse Button drag delta
        drag_delta = imgui.get_mouse_drag_delta(imgui.MouseButton_.right)
        drag_dist_sq = drag_delta.x**2 + drag_delta.y**2
        
        # Threshold: < 25.0 (5 pixels) counts as a click
        return drag_dist_sq < 25.0

    def show_if(self, condition: bool) -> bool:
        """Syntactic sugar for feature flags."""
        return condition
