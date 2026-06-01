import arcade
from typing import Optional, Any
from src.client.services.imgui_service import ImGuiService

class BaseImGuiView(arcade.View):
    """
    Base view that manages ImGui lifecycle.
    """
    def __init__(self):
        super().__init__()

    @property
    def nav(self) -> Any:
        """
        Quick access to the NavigationService attached to the window.
        Typed as 'Any' to preventing circular imports.
        """
        if hasattr(self.window, 'nav'):
            return self.window.nav # type: ignore
        raise AttributeError("NavigationService not found on Window.")
    
    # --- THIS PROPERTY IS WHAT FIXES YOUR ERROR ---
    @property
    def imgui(self) -> ImGuiService:
        """Access the singleton service from the window."""
        # This redirects 'self.imgui' to 'self.window.imgui'
        if hasattr(self.window, 'imgui'):
            return self.window.imgui # type: ignore
        
        # If this raises, MainWindow didn't initialize the service
        raise AttributeError("ImGuiService not found on Window.")

    def setup_imgui(self):
        '''
        Deprecated
        Initializes ImGui service with Font Configuration from the GameConfig.
        This is defined ONCE here, satisfying DRY.
        
        # 1. Attempt to find GameConfig on the window object
        font_path = None
        
        # We assume your Window class has 'self.game_config'
        if hasattr(self.window, "game_config"):
            config = getattr(self.window, "game_config")
            
            # Resolve the specific asset path using your Config logic
            possible_path = config.get_asset_path("fonts/unifont.ttf")
            
            if possible_path and possible_path.exists():
                font_path = possible_path
            else:
                print(f"[BaseView] Font not found at {possible_path}, falling back to default.")

        # 2. Inject the resolved path into the Service
        self.imgui = ImGuiService(self.window, font_path=font_path)
        '''
        pass

    def on_resize(self, width: int, height: int):
        self.on_game_resize(width, height)

    def on_update(self, delta_time: float):
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

    def on_key_press(self, symbol, modifiers):
        captured = self.imgui.on_key_press(symbol, modifiers) if self.imgui else False
        if self._handle_global_shortcut(symbol):
            return
        if not captured:
            self.on_game_key_press(symbol, modifiers)

    def on_key_release(self, symbol, modifiers):
        captured = self.imgui.on_key_release(symbol, modifiers) if self.imgui else False
        if not captured:
            self.on_game_key_release(symbol, modifiers)

    def on_text(self, text: str):
        if self.imgui and self.imgui.on_text(text):
            return
        self.on_game_text(text)

    def _handle_global_shortcut(self, symbol) -> bool:
        if symbol != arcade.key.F11:
            return False

        settings = getattr(self.window, "settings", None)
        if settings is None:
            return False

        settings.toggle_fullscreen(self.window)
        return True

    # --- ABSTRACT HOOKS ---
    def on_game_mouse_motion(self, x, y, dx, dy): pass
    def on_game_resize(self, w, h): pass
    def on_game_update(self, dt): pass
    def on_game_mouse_press(self, x, y, btn, mod): pass
    def on_game_mouse_release(self, x, y, btn, mod): pass
    def on_game_mouse_drag(self, x, y, dx, dy, btn, mod): pass
    def on_game_mouse_scroll(self, x, y, sx, sy): pass
    def on_game_key_press(self, symbol, modifiers): pass
    def on_game_key_release(self, symbol, modifiers): pass
    def on_game_text(self, text: str): pass
