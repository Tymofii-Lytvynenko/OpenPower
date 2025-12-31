import arcade
from imgui_bundle import imgui
from imgui_bundle.python_backends.opengl3_backend import OpenGL3Backend

class ImGuiController:
    """
    A bridge between Arcade (Pyglet) events and Dear ImGui (via imgui-bundle).
    
    This controller handles:
    1. ImGui context initialization.
    2. Input event translation (Mouse, Keyboard, Scroll).
    3. Rendering the ImGui draw data over the Arcade context.
    
    It allows ImGui to function as an overlay within the existing Arcade window.
    """

    def __init__(self, window: arcade.Window):
        self.window = window
        
        # Initialize ImGui context. 
        # We need a dedicated context for this window to store widget states.
        self.context = imgui.create_context()
        self.io = imgui.get_io()
        
        # Enable Docking and Keyboard Navigation as requested for a complex strategy GUI.
        # See: https://github.com/ocornut/imgui/wiki/Docking
        self.io.config_flags |= imgui.ConfigFlags_.docking_enable
        self.io.config_flags |= imgui.ConfigFlags_.nav_enable_keyboard

        # Initialize the OpenGL3 renderer provided by imgui-bundle.
        # This abstraction handles the low-level shader compilation and VBO/IBO management.
        self.renderer = OpenGL3Backend()

        # Map Arcade (Pyglet) key constants to ImGui keys to ensure proper input handling.
        # This mapping is essential for widgets like InputText to recognize navigation keys.
        self.key_map = self._create_key_map()

        # TODO: Load custom fonts here (e.g., Cyrillic support).
        # Without a custom font with Cyrillic ranges, Ukrainian text will render as '?'
        # Example:
        # self._load_fonts()

    def update(self, delta_time: float):
        """
        Prepares a new ImGui frame.
        Must be called before any imgui.* widget calls in the update/draw loop.
        """
        # ImGui needs to know the window size and time delta to animate widgets properly.
        self.io.display_size = (self.window.width, self.window.height)
        self.io.delta_time = delta_time
        
        imgui.new_frame()

    def render(self):
        """
        Finalizes the frame and issues draw calls to OpenGL.
        Must be called at the very end of the window.on_draw() method.
        """
        imgui.render()
        draw_data = imgui.get_draw_data()
        self.renderer.render_draw_data(draw_data)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """
        Propagates mouse movement to ImGui.
        """
        # Arcade uses a bottom-left coordinate system, while ImGui uses top-left.
        # We must invert the Y-axis to align the cursor correctly.
        self.io.add_mouse_pos_event(x, self.window.height - y)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        """
        Propagates mouse clicks to ImGui.
        """
        imgui_button = self._map_mouse_button(button)
        if imgui_button != -1:
            self.io.add_mouse_button_event(imgui_button, True)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        """
        Propagates mouse release to ImGui.
        """
        imgui_button = self._map_mouse_button(button)
        if imgui_button != -1:
            self.io.add_mouse_button_event(imgui_button, False)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        """
        Propagates mouse wheel events.
        """
        self.io.add_mouse_wheel_event(scroll_x, scroll_y)

    def on_key_press(self, key: int, modifiers: int):
        """
        Handles key presses for shortcuts and navigation (e.g., Ctrl+C, Arrows).
        """
        self._update_modifiers(modifiers)
        
        imgui_key = self.key_map.get(key)
        if imgui_key:
            self.io.add_key_event(imgui_key, True)

    def on_key_release(self, key: int, modifiers: int):
        """
        Handles key releases.
        """
        self._update_modifiers(modifiers)

        imgui_key = self.key_map.get(key)
        if imgui_key:
            self.io.add_key_event(imgui_key, False)

    def on_text(self, text: str):
        """
        Handles character input (typing).
        This is distinct from on_key_press and is required for proper text entry 
        (case sensitivity, unicode characters).
        """
        for char in text:
            self.io.add_input_character(ord(char))

    def _update_modifiers(self, modifiers: int):
        """
        Syncs the state of modifier keys (Ctrl, Shift, Alt, Super).
        ImGui uses these for standard shortcuts (e.g., Ctrl+C to copy).
        """
        self.io.add_key_event(imgui.Key.mod_ctrl, (modifiers & arcade.key.MOD_CTRL) != 0)
        self.io.add_key_event(imgui.Key.mod_shift, (modifiers & arcade.key.MOD_SHIFT) != 0)
        self.io.add_key_event(imgui.Key.mod_alt, (modifiers & arcade.key.MOD_ALT) != 0)
        self.io.add_key_event(imgui.Key.mod_super, (modifiers & arcade.key.MOD_COMMAND) != 0)

    def _map_mouse_button(self, button: int) -> int:
        """Maps Arcade mouse constants to ImGui button indices."""
        if button == arcade.MOUSE_BUTTON_LEFT: return 0
        if button == arcade.MOUSE_BUTTON_RIGHT: return 1
        if button == arcade.MOUSE_BUTTON_MIDDLE: return 2
        return -1

    def _create_key_map(self) -> dict[int, int]:
        """
        Creates a mapping from Arcade (Pyglet) keys to ImGui keys.
        Only essential keys for navigation and editing are mapped to keep overhead low.
        """
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
            arcade.key.PRINTSCREEN: imgui.Key.print_screen,
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