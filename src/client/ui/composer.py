import arcade
import ctypes  # <--- REQUIRED for ImGui Texture IDs
from imgui_bundle import imgui
from numpy import size
from src.client.ui.theme import UITheme
from src.client.services.imgui_service import ImGuiService

class UIComposer:
    def __init__(self, theme: UITheme):
        self.theme = theme

    def setup_frame(self):
        self.theme.apply_global_styles()

    def begin_panel(self, name, x, y, w, h, is_visible=True):
        """
        Starts a new ImGui window.
        Returns: (expanded, opened)
        - expanded: True if the window is not collapsed.
        - opened: False if the user clicked the 'X' close button.
        """
        imgui.set_next_window_pos((x, y), imgui.Cond_.first_use_ever)
        imgui.set_next_window_size((w, h), imgui.Cond_.first_use_ever)
        
        # We pass is_visible as a reference-like boolean for the close button
        expanded, opened = imgui.begin(name, is_visible, imgui.WindowFlags_.no_collapse)
        return expanded, opened

    def end_panel(self): 
        imgui.end()

    def show_if(self, condition: bool):
        """
        A helper for conditional rendering (feature flags).
        Usage: if composer.show_if(FEATURE_READY): ...
        """
        return condition

    def begin_centered_panel(self, name, sw, sh, w=300, h=400):
        imgui.set_next_window_pos(((sw - w)/2, (sh - h)/2))
        imgui.set_next_window_size((w, h))
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 1.0)
        v, _ = imgui.begin(name, None, imgui.WindowFlags_.no_title_bar | imgui.WindowFlags_.no_resize)
        imgui.pop_style_var()
        return v

    def draw_menu_button(self, label, w=-1, h=40):
        c = imgui.button(label, (w, h))
        imgui.dummy((0, 5))
        return c

    def draw_title(self, text):
        imgui.set_cursor_pos_x((imgui.get_window_width() - imgui.calc_text_size(text).x)/2)
        imgui.text(text)
        imgui.separator()
        imgui.dummy((0, 10))

    def draw_progress_bar(self, fraction, text="", width=-1, height=20):
        p = imgui.get_cursor_screen_pos()
        w = width if width > 0 else imgui.get_content_region_avail().x
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(p, (p.x + w, p.y + height), imgui.get_color_u32(self.theme.window_bg))
        draw.add_rect_filled(p, (p.x + w * fraction, p.y + height), imgui.get_color_u32(self.theme.button_active))
        draw.add_rect(p, (p.x + w, p.y + height), imgui.get_color_u32(self.theme.border))
        if text:
            ts = imgui.calc_text_size(text)
            draw.add_text((p.x + (w-ts.x)/2, p.y + (height-ts.y)/2), imgui.get_color_u32(self.theme.text_main), text)
        imgui.dummy((w, height + 5))

    def draw_section_header(self, label, show_more_btn=True):
        dl, p, w, h = imgui.get_window_draw_list(), imgui.get_cursor_screen_pos(), imgui.get_content_region_avail().x, 22.0
        dl.add_rect_filled(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.header_bg))
        imgui.set_cursor_pos((imgui.get_cursor_pos_x()+5, imgui.get_cursor_pos_y()+(h-imgui.calc_text_size(label).y)/2))
        imgui.text_colored(self.theme.text_main, label)
        imgui.set_cursor_screen_pos((p.x, p.y + h + 5))

    def draw_meter(self, label, value, color, show_percentage=True):
        if label: imgui.text(label)
        w, h, p, dl = imgui.get_content_region_avail().x, 12.0, imgui.get_cursor_screen_pos(), imgui.get_window_draw_list()
        dl.add_rect_filled(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.window_bg))
        dl.add_rect_filled(p, (p.x + (value/100.0)*w, p.y + h), imgui.get_color_u32((*color[:3], 1.0)))
        dl.add_rect(p, (p.x + w, p.y + h), imgui.get_color_u32(self.theme.border))
        imgui.dummy((0, h + 5))

    def draw_currency_row(self, label, value, color_val=None):
        imgui.text(label)
        imgui.same_line()
        val_str = f"$ {value:,.0f}".replace(",", " ")
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + imgui.get_content_region_avail().x - imgui.calc_text_size(val_str).x)
        imgui.text_colored(color_val or self.theme.text_main, val_str)

    def draw_icon_toggle(self, icon, color, is_active, width=50, height=50):
        imgui.push_style_color(imgui.Col_.button, self.theme.button_active if is_active else self.theme.button_normal)
        clicked = imgui.button(icon, (width, height))
        imgui.pop_style_color()
        p, pm = imgui.get_item_rect_min(), imgui.get_item_rect_max()
        col = imgui.get_color_u32((*color[:3], 1.0) if is_active else self.theme.text_dim)
        imgui.get_window_draw_list().add_rect_filled((p.x, pm.y - 4), (pm.x, pm.y), col)
        return clicked
    
    # --- POPUP & MENU METHODS ---

    def begin_context_menu(self, str_id="map_context"):
        """
        Triggers a popup when right-clicking the background/window.
        ImGui handles the mouse trigger internally via PopupFlags.
        """
        return imgui.begin_popup_context_window(str_id, imgui.PopupFlags_.mouse_button_right)

    def open_popup(self, str_id: str):
        """Manually triggers a popup to open."""
        imgui.open_popup(str_id)

    def begin_popup(self, str_id: str):
        """Starts rendering the popup content if it was opened."""
        return imgui.begin_popup(str_id)

    def end_popup(self):
        """Ends the current popup context."""
        imgui.end_popup()

    def is_background_clicked(self) -> bool:
        """
        Detects a clean right-click release on the background.
        Calculates the drag delta to ensure the user wasn't panning the map.
        """
        # If the user is currently interacting with an ImGui window (like a slider),
        # don't trigger the game world context menu.
        if imgui.get_io().want_capture_mouse:
            return False

        # ImGui internally tracks how far the mouse has moved since the last 'down' event.
        drag_delta = imgui.get_mouse_drag_delta(imgui.MouseButton_.right)
        drag_dist_sq = drag_delta.x**2 + drag_delta.y**2
        
        # 25.0 is 5 pixels squared. If they moved less than this, it's a click.
        return drag_dist_sq < 25.0

    def begin_menu(self, label: str):
        return imgui.begin_menu(label)

    def end_menu(self):
        imgui.end_menu()

    def draw_menu_item(self, label: str, shortcut: str = ""):
        """Returns True if the user clicked the item."""
        clicked, _ = imgui.menu_item(label, shortcut, False, True)
        return clicked
    
    def draw_image(self, texture: arcade.Texture, width: float, height: float):
        """
        Draws an Arcade Texture in ImGui. 
        Handles GL ID extraction and ImVec2 type casting automatically.
        Includes robust error handling to prevent stack crashes.
        """
        if not texture:
            # Render a placeholder rectangle if texture is missing
            self.dummy((width, height))
            return

        try:
            # 1. Get ID via Service (Returns int)
            tex_id = ImGuiService.get_texture_id(texture)
            
            # 2. Draw with Correct Binding
            # imgui_bundle requires specific types for texture IDs (often void*).
            # Passing a raw int will fail overload resolution in newer bindings.
            # We use ctypes.c_void_p to create a compatible pointer object.
            imgui.image(ctypes.c_void_p(tex_id), imgui.ImVec2(width, height)) # type: ignore

        except Exception as e:
            # SAFETY NET:
            # If drawing fails (e.g., bad cast, invalid GL context), we catch it here.
            # This prevents the Exception from bubbling up to GameLayout, which would
            # skip imgui.end_group() and cause the whole app to crash with "Missing EndGroup".
            print(f"[UIComposer] draw_image error: {e}")
            self.dummy((width, height))
       
    def dummy(self, size: tuple[float, float]):
        imgui.dummy(imgui.ImVec2(size[0], size[1]))