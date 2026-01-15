import arcade
from typing import Optional
from src.client.services.imgui_service import ImGuiService

class BaseImGuiView(arcade.View):
    """
    A base view that handles the boilerplate of connecting Arcade inputs to ImGui.
    
    Child classes should implement:
    - setup_ui(): Initialize self.imgui
    - on_game_resize(): Handle window resizing logic
    - on_game_mouse_press(), on_game_mouse_motion(), etc.: Handle world interaction
    """
    
    def __init__(self):
        super().__init__()
        # Child MUST initialize this in their __init__
        self.imgui: Optional[ImGuiService] = None

    def on_resize(self, width: int, height: int):
        """Standard resize logic."""
        if self.imgui:
            self.imgui.resize(width, height)
        self.on_game_resize(width, height)
        
    def on_game_update(self, delta_time: float): 
        pass
    
    def on_update(self, delta_time: float):
        """
        Automatically syncs the physics engine time with the UI engine.
        """
        if self.imgui:
            self.imgui.update_time(delta_time)
        
        self.on_game_update(delta_time)
        
    # --- INPUT PLUMBING ---
    # These methods automatically check ImGui first.

    def on_mouse_press(self, x, y, button, modifiers):
        # 1. Let ImGui process the input
        imgui_handled = False
        if self.imgui:
            imgui_handled = self.imgui.on_mouse_press(x, y, button, modifiers)

        # 2. Pass-through Logic:
        # If the user clicks Right (Pan) or Middle (Pan/Zoom), we send it to the game
        # EVEN IF ImGui is hovering over a window. This fixes the "stuck camera" 
        # issue when dragging immediately after using a UI dropdown.
        force_pass_through = (button == arcade.MOUSE_BUTTON_RIGHT) or (button == arcade.MOUSE_BUTTON_MIDDLE)

        # 3. If ImGui handled it (Left Click on UI) and it's not a nav button, stop here.
        if imgui_handled and not force_pass_through:
            return

        self.on_game_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        imgui_handled = False
        if self.imgui:
            imgui_handled = self.imgui.on_mouse_release(x, y, button, modifiers)

        force_pass_through = (button == arcade.MOUSE_BUTTON_RIGHT) or (button == arcade.MOUSE_BUTTON_MIDDLE)

        if imgui_handled and not force_pass_through:
            return
            
        self.on_game_mouse_release(x, y, button, modifiers)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        # 1. Let ImGui process the drag
        imgui_handled = False
        if self.imgui:
            imgui_handled = self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

        # 2. Check for held buttons (Bitmask in Arcade 3.0)
        is_right_held = buttons & arcade.MOUSE_BUTTON_RIGHT
        is_middle_held = buttons & arcade.MOUSE_BUTTON_MIDDLE
        force_pass_through = is_right_held or is_middle_held

        # 3. Block game input only if ImGui took it AND we aren't panning
        if imgui_handled and not force_pass_through:
            return

        self.on_game_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        # Scroll is usually contextual (zoom map vs scroll UI window).
        # Standard behavior: If ImGui captured it, do NOT pass to game.
        if self.imgui and self.imgui.on_mouse_scroll(x, y, scroll_x, scroll_y):
            return
        self.on_game_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_mouse_motion(self, x, y, dx, dy):
        if self.imgui:
            self.imgui.on_mouse_motion(x, y, dx, dy)
        self.on_game_mouse_motion(x, y, dx, dy)

    def on_key_press(self, symbol, modifiers):
        if self.imgui and self.imgui.on_key_press(symbol, modifiers):
            return
        self.on_game_key_press(symbol, modifiers)

    def on_key_release(self, symbol, modifiers):
        if self.imgui:
            self.imgui.on_key_release(symbol, modifiers)
        self.on_game_key_release(symbol, modifiers)

    def on_text(self, text):
        if self.imgui:
            self.imgui.on_text(text)

    # --- HOOKS (Override these in your views) ---
    def on_game_resize(self, width, height): pass
    def on_game_mouse_press(self, x, y, button, modifiers): pass
    def on_game_mouse_release(self, x, y, button, modifiers): pass
    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers): pass
    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y): pass
    def on_game_mouse_motion(self, x, y, dx, dy): pass
    def on_game_key_press(self, symbol, modifiers): pass
    def on_game_key_release(self, symbol, modifiers): pass