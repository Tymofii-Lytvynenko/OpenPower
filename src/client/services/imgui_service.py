import arcade
from pathlib import Path
from typing import Optional
from imgui_bundle import imgui
from imgui_bundle.python_backends.opengl_backend_programmable import ProgrammablePipelineRenderer as OpenGL3Backend

from src.client.ui.core.font_loader import FontLoader

class ImGuiService:
    """
    Manages the integration between Arcade (Pyglet) and Dear ImGui.
    
    Architecture:
        This class acts as a composable service. It does not control the window;
        instead, the View delegates input and rendering tasks to this service.
    
    Key Responsibilities:
        1. Translating Arcade inputs to ImGui inputs.
        2. Rendering the ImGui draw data using OpenGL 3.3+.
        3. Reporting whether ImGui has 'captured' an input event to prevent fall-through.
    """

    def __init__(self, window: arcade.Window, font_path: Optional[Path] = None):
        self.window = window
        self.window.switch_to()
        
        # Create a dedicated ImGui context
        self._context = imgui.create_context()
        self.io = imgui.get_io()
        
        # Enable Docking and Keyboard Nav
        self.io.config_flags |= imgui.ConfigFlags_.docking_enable
        self.io.config_flags |= imgui.ConfigFlags_.nav_enable_keyboard

        # --- FONT LOADING ---
        pixel_ratio = self.window.get_pixel_ratio()

        if font_path:
            # 1. Load Big: Load texture at physical resolution (e.g., 28px)
            base_font_size = 14.0
            FontLoader.load_primary_font(
                self.io, 
                font_path, 
                size_pixels=base_font_size * pixel_ratio, 
                load_cjk=False,
                load_icons=True
            )

            # 2. Scale Down: Use the new Style API to scale the UI back to logical size
            #    Old API: self.io.font_global_scale = 1.0 / pixel_ratio  <-- REMOVED
            #    New API: Use imgui.get_style().font_scale_main
            style = imgui.get_style()
            style.font_scale_main = 1.0 / pixel_ratio

        # Initialize the programmable pipeline renderer
        self.renderer = OpenGL3Backend()

        # Input mapping cache
        self.key_map = self._create_key_map()
        
        self._frame_started = False
        self._current_delta_time = 1.0 / 60.0

    def resize(self, width: int, height: int):
        """
        Updates ImGui display size immediately upon window resize.
        
        Why this is needed:
            Arcade's on_resize happens asynchronously to the draw loop. If we don't 
            update ImGui's display_size here, there may be a frame mismatch where 
            ImGui renders at the old resolution while the window is at the new one, 
            causing visual artifacts or 'black bars'.
        """
        self.io.display_size = imgui.ImVec2(float(width), float(height))

    def update_time(self, delta_time: float):
        """
        Called by the View's on_update to sync game speed with UI speed.
        """
        self._current_delta_time = delta_time

    def new_frame(self):
        """Prepares the ImGui context using the actual stored delta time."""
        if self._frame_started:
            imgui.end_frame()

        # 1. Use the real delta time captured from the game loop
        self.io.delta_time = self._current_delta_time
        
        # 2. Sync Display Size
        width, height = self.window.get_size()
        self.io.display_size = imgui.ImVec2(float(width), float(height))
        
        # 3. Sync DPI
        pixel_ratio = self.window.get_pixel_ratio()
        self.io.display_framebuffer_scale = imgui.ImVec2(pixel_ratio, pixel_ratio)

        imgui.new_frame()
        self._frame_started = True

    def render(self):
        """Finalizes the frame and issues the OpenGL draw calls."""
        if not self._frame_started:
            return

        imgui.render()
        draw_data = imgui.get_draw_data()
        self.renderer.render(draw_data)
        
        # --- FIX: CRITICAL RESET FOR ARCADE ---
        # ImGui enables GL_SCISSOR_TEST to clip UI elements. If we don't disable it,
        # Arcade's subsequent `self.clear()` will only clear the tiny scissor box 
        # left by ImGui, leaving "garbage" artifacts on the rest of the screen.
        try:
            # Arcade 3.0 way to disable scissor test
            self.window.ctx.scissor = None
        except Exception:
            # Fallback for older OpenGL contexts or Pyglet direct access if needed
            from pyglet.gl import glDisable, GL_SCISSOR_TEST
            glDisable(GL_SCISSOR_TEST)

        self._frame_started = False

    # --- Input Handling (Returns True if ImGui captured the event) ---

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        # Invert Y because Arcade is Bottom-Left, ImGui is Top-Left
        self.io.add_mouse_pos_event(x, self.window.height - y)
        
        imgui_btn = self._map_mouse_button(button)
        if imgui_btn != -1:
            self.io.add_mouse_button_event(imgui_btn, True)
        
        # Return True if the mouse is hovering over an ImGui window.
        # This tells the View: "Do NOT click on the map, the user clicked a button."
        return self.io.want_capture_mouse

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        self.io.add_mouse_pos_event(x, self.window.height - y)
        
        imgui_btn = self._map_mouse_button(button)
        if imgui_btn != -1:
            self.io.add_mouse_button_event(imgui_btn, False)
            
        return self.io.want_capture_mouse

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        self.io.add_mouse_pos_event(x, self.window.height - y)
        self._update_modifiers(modifiers)
        
        # Even if dragging, if we started the drag on a window, we block the map.
        return self.io.want_capture_mouse

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> bool:
        self.io.add_mouse_pos_event(x, self.window.height - y)
        # Usually we don't block motion, but if we need to show a custom cursor, we might check this.
        return self.io.want_capture_mouse

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> bool:
        self.io.add_mouse_wheel_event(scroll_x, scroll_y)
        return self.io.want_capture_mouse

    def on_key_press(self, key: int, modifiers: int) -> bool:
        self._update_modifiers(modifiers)
        
        imgui_key = self.key_map.get(key)
        if imgui_key:
            self.io.add_key_event(imgui_key, True)
            
        # Return True if ImGui has keyboard focus (e.g., typing in a text field).
        # This prevents game hotkeys (like WASD) from triggering while typing.
        return self.io.want_capture_keyboard

    def on_key_release(self, key: int, modifiers: int) -> bool:
        self._update_modifiers(modifiers)
        
        imgui_key = self.key_map.get(key)
        if imgui_key:
            self.io.add_key_event(imgui_key, False)
            
        return self.io.want_capture_keyboard

    def on_text(self, text: str) -> bool:
        """Handles unicode character input (essential for text fields)."""
        for char in text:
            self.io.add_input_character(ord(char))
        return self.io.want_capture_keyboard

    # --- Internals ---

    def _update_modifiers(self, modifiers: int):
        """Syncs key modifiers (Ctrl, Alt, Shift) with ImGui state."""
        self.io.add_key_event(imgui.Key.mod_ctrl, (modifiers & arcade.key.MOD_CTRL) != 0)
        self.io.add_key_event(imgui.Key.mod_shift, (modifiers & arcade.key.MOD_SHIFT) != 0)
        self.io.add_key_event(imgui.Key.mod_alt, (modifiers & arcade.key.MOD_ALT) != 0)
        self.io.add_key_event(imgui.Key.mod_super, (modifiers & arcade.key.MOD_COMMAND) != 0)

    def _map_mouse_button(self, button: int) -> int:
        if button == arcade.MOUSE_BUTTON_LEFT: return 0
        if button == arcade.MOUSE_BUTTON_RIGHT: return 1
        if button == arcade.MOUSE_BUTTON_MIDDLE: return 2
        return -1

    def _create_key_map(self) -> dict[int, imgui.Key]:
        """Maps Arcade key constants to ImGui Key constants."""
        return {
            arcade.key.ESCAPE: imgui.Key.escape,
            arcade.key.ENTER: imgui.Key.enter,
            arcade.key.TAB: imgui.Key.tab,
            arcade.key.BACKSPACE: imgui.Key.backspace,
            arcade.key.INSERT: imgui.Key.insert,
            arcade.key.DELETE: imgui.Key.delete,
            arcade.key.RIGHT: imgui.Key.right_arrow,
            arcade.key.LEFT: imgui.Key.left_arrow,
            arcade.key.DOWN: imgui.Key.down_arrow,
            arcade.key.UP: imgui.Key.up_arrow,
            arcade.key.PAGEUP: imgui.Key.page_up,
            arcade.key.PAGEDOWN: imgui.Key.page_down,
            arcade.key.HOME: imgui.Key.home,
            arcade.key.END: imgui.Key.end,
            arcade.key.CAPSLOCK: imgui.Key.caps_lock,
            arcade.key.SCROLLLOCK: imgui.Key.scroll_lock,
            arcade.key.NUMLOCK: imgui.Key.num_lock,
            arcade.key.PAUSE: imgui.Key.pause,
            arcade.key.F1: imgui.Key.f1,
            arcade.key.F2: imgui.Key.f2,
            arcade.key.F3: imgui.Key.f3,
            arcade.key.F4: imgui.Key.f4,
            arcade.key.F5: imgui.Key.f5,
            arcade.key.F6: imgui.Key.f6,
            arcade.key.F7: imgui.Key.f7,
            arcade.key.F8: imgui.Key.f8,
            arcade.key.F9: imgui.Key.f9,
            arcade.key.F10: imgui.Key.f10,
            arcade.key.F11: imgui.Key.f11,
            arcade.key.F12: imgui.Key.f12,
            arcade.key.NUM_0: imgui.Key.keypad0,
            arcade.key.NUM_1: imgui.Key.keypad1,
            arcade.key.NUM_2: imgui.Key.keypad2,
            arcade.key.NUM_3: imgui.Key.keypad3,
            arcade.key.NUM_4: imgui.Key.keypad4,
            arcade.key.NUM_5: imgui.Key.keypad5,
            arcade.key.NUM_6: imgui.Key.keypad6,
            arcade.key.NUM_7: imgui.Key.keypad7,
            arcade.key.NUM_8: imgui.Key.keypad8,
            arcade.key.NUM_9: imgui.Key.keypad9,
            arcade.key.NUM_DECIMAL: imgui.Key.keypad_decimal,
            arcade.key.NUM_DIVIDE: imgui.Key.keypad_divide,
            arcade.key.NUM_MULTIPLY: imgui.Key.keypad_multiply,
            arcade.key.NUM_SUBTRACT: imgui.Key.keypad_subtract,
            arcade.key.NUM_ADD: imgui.Key.keypad_add,
            arcade.key.NUM_ENTER: imgui.Key.keypad_enter,
            arcade.key.NUM_EQUAL: imgui.Key.keypad_equal,
            arcade.key.A: imgui.Key.a,
            arcade.key.C: imgui.Key.c,
            arcade.key.V: imgui.Key.v,
            arcade.key.X: imgui.Key.x,
            arcade.key.Y: imgui.Key.y,
            arcade.key.Z: imgui.Key.z,
        }
        
    @staticmethod
    def get_texture_id(texture: arcade.Texture) -> int:
        """
        Safely extracts the OpenGL ID from an Arcade Texture.
        Compatible with Arcade 3.0 (.glo.glo_id) and Legacy (.gl_id).
        """
        # Arcade 3.0+
        if hasattr(texture, "glo"):
            return int(texture.glo.glo_id) # type: ignore
        
        # Fallback for Arcade 2.6
        return int(getattr(texture, "gl_id", 0)) # type: ignore