import arcade
import ctypes  # Required for raw pointer handling in ImGui
from typing import Optional
from imgui_bundle import imgui
from src.client.ui.theme import UITheme
from src.client.services.imgui_service import ImGuiService

class UIComposer:
    """
    A high-level UI composition helper.
    Abstracts raw ImGui calls into semantic components (Panels, Meters, Toggles)
    styled according to the provided UITheme.
    """
    def __init__(self, theme: UITheme):
        self.theme = theme

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
        imgui.end()

    def begin_centered_panel(self, name: str, sw: float, sh: float, w: float = 300, h: float = 400):
        """
        Starts a modal-like window centered on screen.
        Used for Menus, Loading Screens, etc.
        """
        # Center calculation
        pos_x = (sw - w) / 2
        pos_y = (sh - h) / 2
        
        imgui.set_next_window_pos((pos_x, pos_y))
        imgui.set_next_window_size((w, h))
        
        # Thicker border for modal look
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 8.0)
        
        flags = (imgui.WindowFlags_.no_title_bar | 
                 imgui.WindowFlags_.no_resize | 
                 imgui.WindowFlags_.no_move)
        
        # Pass None for p_open to hide close button
        is_visible, _ = imgui.begin(name, None, flags)
        
        imgui.pop_style_var(2)
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

    def draw_menu_button(self, label: str, w: float = -1, h: float = 40) -> bool:
        """
        Draws a large menu button (standard height 40px).
        Returns True if clicked.
        """
        clicked = imgui.button(label, (w, h))
        self.dummy((0, 5)) # Spacing below
        return clicked

    def draw_section_header(self, label: str, show_more_btn: bool = True):
        """
        Draws a styled header bar with a background color.
        """
        draw_list = imgui.get_window_draw_list()
        p = imgui.get_cursor_screen_pos()
        width = imgui.get_content_region_avail().x
        height = 24.0
        
        # Draw Background Rect
        draw_list.add_rect_filled(
            p, 
            (p.x + width, p.y + height), 
            imgui.get_color_u32(self.theme.colors.bg_input),
            4.0 # Rounding
        )
        
        # Draw Text (Vertically Centered)
        text_size = imgui.calc_text_size(label)
        text_y = p.y + (height - text_size.y) / 2
        
        # Padding Left
        imgui.set_cursor_screen_pos((p.x + 8, text_y))
        imgui.text_colored(self.theme.colors.text_main, label)
        
        # Reset Cursor for next item
        imgui.set_cursor_screen_pos((p.x, p.y + height + 5))

    def draw_meter(self, label: str, value: float, color: tuple, show_percentage: bool = True):
        """
        Draws a label and a horizontal progress bar (0-100 range).
        """
        if label:
            imgui.text(label)
            
        w = imgui.get_content_region_avail().x
        h = 12.0
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        
        # Clamp value 0-100
        clamped_val = max(0.0, min(value, 100.0))
        fraction = clamped_val / 100.0

        # Background (Track)
        draw_list.add_rect_filled(
            p, (p.x + w, p.y + h), 
            imgui.get_color_u32(self.theme.colors.bg_input),
            h / 2
        )
        
        # Foreground (Fill)
        if fraction > 0.01:
            # Convert color tuple (r,g,b,a) to U32
            col_u32 = imgui.get_color_u32(color if len(color) == 4 else (*color, 1.0))
            draw_list.add_rect_filled(
                p, (p.x + w * fraction, p.y + h), 
                col_u32,
                h / 2
            )

        self.dummy((0, h + 5))

    def draw_currency_row(self, label: str, value: float, color_val: Optional[tuple] = None):
        """
        Draws a row with 'Label ......... $ Value'.
        Value is formatted with spaces as thousand separators.
        """
        imgui.text(label)
        imgui.same_line()
        
        # Format: 1 000 000
        val_str = f"$ {value:,.0f}".replace(",", " ")
        
        # Right align the value
        self.right_align(imgui.calc_text_size(val_str).x)
        
        col = color_val if color_val else self.theme.colors.text_main
        imgui.text_colored(col, val_str)

    def draw_progress_bar(self, fraction: float, text: str = "", width: float = -1, height: float = 20):
        """
        Standard ImGui ProgressBar wrapper with theme colors.
        """
        p = imgui.get_cursor_screen_pos()
        w = width if width > 0 else imgui.get_content_region_avail().x
        
        draw_list = imgui.get_window_draw_list()
        
        # Background
        draw_list.add_rect_filled(
            p, (p.x + w, p.y + height), 
            imgui.get_color_u32(self.theme.colors.bg_window)
        )
        
        # Fill
        fill_w = w * max(0.0, min(fraction, 1.0))
        draw_list.add_rect_filled(
            p, (p.x + fill_w, p.y + height), 
            imgui.get_color_u32(self.theme.colors.accent)
        )
        
        # Border
        draw_list.add_rect(
            p, (p.x + w, p.y + height), 
            imgui.get_color_u32(self.theme.colors.accent)
        )
        
        # Centered Text
        if text:
            text_size = imgui.calc_text_size(text)
            text_x = p.x + (w - text_size.x) / 2
            text_y = p.y + (height - text_size.y) / 2
            
            # Shadow for readability
            draw_list.add_text((text_x + 1, text_y + 1), 0xFF000000, text) 
            # Text
            draw_list.add_text((text_x, text_y), 0xFFFFFFFF, text)
            
        self.dummy((w, height + 5))

    def draw_icon_toggle(self, icon: str, color: tuple, is_active: bool, width: float = 50, height: float = 50) -> bool:
        """
        Draws a large toggle button for the main HUD toolbar.
        Includes a colored underline indicator when active.
        """
        # 1. Custom Button Style
        # Use Active color for background if selected, else Normal
        bg_col = self.theme.colors.interaction_active if is_active else self.theme.colors.bg_input
        imgui.push_style_color(imgui.Col_.button, bg_col)
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 8.0) # Softer corners for icons
        
        clicked = imgui.button(icon, (width, height))
        
        imgui.pop_style_var()
        imgui.pop_style_color()
        
        # 2. Draw Indicator Line (Manually via DrawList)
        p_min = imgui.get_item_rect_min()
        p_max = imgui.get_item_rect_max()
        
        draw_list = imgui.get_window_draw_list()
        
        # Indicator color: The specific category color (e.g. Red for Mil, Green for Eco)
        ind_col_tuple = (*color[:3], 1.0) if is_active else self.theme.colors.text_dim
        ind_col = imgui.get_color_u32(ind_col_tuple)
        
        # Draw a small bar at the bottom
        bar_height = 4.0
        padding = 5.0
        
        draw_list.add_rect_filled(
            (p_min.x + padding, p_max.y - bar_height - 2), 
            (p_max.x - padding, p_max.y - 2), 
            ind_col,
            2.0 # Rounding
        )
        
        return clicked

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

        except Exception as e:
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

    def draw_menu_item(self, label: str, shortcut: str = "") -> bool:
        """Draws a clickable menu item. Returns True if clicked."""
        clicked, _ = imgui.menu_item(label, shortcut, False, True)
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