import arcade
from typing import Optional
from src.client.services.imgui_service import ImGuiService

class BaseImGuiView(arcade.View):
    """
    CRITICAL INFRASTRUCTURE:
    1. Manages the lifecycle of the ImGui Service.
    2. Routes inputs: ImGui gets first dibs. If ImGui ignores it, pass to 'game' methods.
    """
    def __init__(self):
        super().__init__()
        # Defer initialization to allow subclasses to prep data first
        self.imgui: Optional[ImGuiService] = None

    def setup_imgui(self):
        """Must be called by subclass after window is ready."""
        self.imgui = ImGuiService(self.window)

    def on_resize(self, width: int, height: int):
        if self.imgui:
            self.imgui.resize(width, height)
        # Standardize viewport reset to prevent artifacts
        self.window.ctx.viewport = (0, 0, width, height)
        self.on_game_resize(width, height)

    def on_update(self, delta_time: float):
        if self.imgui:
            self.imgui.update_time(delta_time)
        self.on_game_update(delta_time)

    # --- DRY INPUT ROUTING ---
    def on_mouse_press(self, x, y, button, modifiers):
        if self.imgui and self.imgui.on_mouse_press(x, y, button, modifiers):
            # Allow "Pass Through" for navigation (Right/Middle click) even if hovering UI
            if button not in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
                return
        self.on_game_mouse_press(x, y, button, modifiers)
    
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """
        CRITICAL FIX: Updates ImGui mouse position.
        Without this, hover states won't work and clicks will require double-pressing.
        """
        if self.imgui:
            self.imgui.on_mouse_motion(x, y, dx, dy)
        self.on_game_mouse_motion(x, y, dx, dy)

    def on_mouse_release(self, x, y, button, modifiers):
        if self.imgui and self.imgui.on_mouse_release(x, y, button, modifiers):
             if button not in (arcade.MOUSE_BUTTON_RIGHT, arcade.MOUSE_BUTTON_MIDDLE):
                return
        self.on_game_mouse_release(x, y, button, modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.imgui and self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers):
             # Bitwise check for Middle/Right drag pass-through
             if not (buttons & (arcade.MOUSE_BUTTON_RIGHT | arcade.MOUSE_BUTTON_MIDDLE)):
                return
        self.on_game_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.imgui and self.imgui.on_mouse_scroll(x, y, scroll_x, scroll_y):
            return
        self.on_game_mouse_scroll(x, y, scroll_x, scroll_y)

    # --- ABSTRACT HOOKS ---
    def on_game_mouse_motion(self, x, y, dx, dy): pass
    def on_game_resize(self, w, h): pass
    def on_game_update(self, dt): pass
    def on_game_mouse_press(self, x, y, btn, mod): pass
    def on_game_mouse_release(self, x, y, btn, mod): pass
    def on_game_mouse_drag(self, x, y, dx, dy, btn, mod): pass
    def on_game_mouse_scroll(self, x, y, sx, sy): pass