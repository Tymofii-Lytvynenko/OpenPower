import arcade
from pyglet.math import Vec2

from src.server.session import GameSession
from src.shared.config import GameConfig
from src.client.network_client import NetworkClient
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.editor_layout import EditorLayout
from src.client.ui.imgui_controller import ImGuiController
from src.client.camera_controller import CameraController

class EditorView(arcade.View):
    """
    The main visual interface for the Map Editor.
    
    Responsibilities:
    1. Render the Game World (Map) via MapRenderer.
    2. Render the UI (ImGui) via EditorLayout.
    3. Handle Input (Mouse/Keyboard) and route it to either ImGui or the Game World.
    4. Manage the Camera (Pan/Zoom).
    """

    def __init__(self, session: GameSession, config: GameConfig):
        super().__init__()
        self.game_config = config
        self.is_panning_map = False
        
        # 1. Initialize Network Bridge
        self.net = NetworkClient(session)
        
        # 2. Resolve Map Data Path
        map_path = None
        for data_dir in config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                map_path = candidate
                break
        
        if not map_path:
             map_path = config.get_asset_path("map/regions.png")

        if not map_path or not map_path.exists():
             print(f"[EditorView] CRITICAL: 'regions.png' not found.")
             map_path = config.project_root / "missing_map_placeholder.png"

        print(f"[EditorView] Initializing MapRenderer with source: {map_path}")
        self.map_renderer = MapRenderer(map_path, config.cache_dir)
        
        # 3. Initialize UI
        self.imgui_controller = ImGuiController(self.window)
        self.ui_layout = EditorLayout(self.net)
        self.ui_layout.on_focus_request = self.focus_on_coordinates
        
        # 4. Initialize Cameras (Arcade 3.0 Standard)
        self.world_camera = arcade.Camera2D()
        self.ui_camera = arcade.Camera2D()
        
        # Custom controller for smooth zooming/panning logic
        # We start centered on the map
        center_pos = self.map_renderer.get_center()
        self.camera_controller = CameraController(center_pos)
        
        # 5. Interaction State
        self.selected_region_int_id = None
        self.highlight_layer = arcade.SpriteList()

    def on_show_view(self):
        """Called when this view is switched to."""
        self.window.background_color = arcade.color.DARK_SLATE_GRAY
        # Sync camera immediately
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_draw(self):
        """Render the screen."""
        self.clear()
        
        # 1. Update ImGui
        self.imgui_controller.update(1.0 / 60.0)

        # 2. Render World Layer (Camera Applied)
        self.world_camera.use()
        self.map_renderer.draw_map()
        self.highlight_layer.draw()
        
        # 3. Render UI Layer (Identity Transform)
        self.ui_camera.use()
        self.ui_layout.render(self.selected_region_int_id, 1.0/60.0)
        self.imgui_controller.render()

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse click events."""
        # 1. Pass input to ImGui first
        self.imgui_controller.on_mouse_press(x, y, button, modifiers)
        
        # 2. Check if ImGui wants the mouse right now
        if self.imgui_controller.io.want_capture_mouse:
            self.is_panning_map = False # ImGui has priority
            return

        # 3. Handle Map Interaction
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)
        
        # 4. Prepare for panning logic
        # If Right or Middle click is pressed, and ImGui didn't take it, allow panning
        if button == arcade.MOUSE_BUTTON_RIGHT or button == arcade.MOUSE_BUTTON_MIDDLE:
            self.is_panning_map = True

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int):
        self.imgui_controller.on_mouse_release(x, y, button, modifiers)
        
        # Stop panning when buttons are released
        if button == arcade.MOUSE_BUTTON_RIGHT or button == arcade.MOUSE_BUTTON_MIDDLE:
            self.is_panning_map = False

    def on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int):
        """
        Handle mouse movement while a button is held down (Panning).
        """
        # 1. ALWAYS update ImGui position, otherwise UI sliders won't drag correctly!
        self.imgui_controller.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

        # 2. Map Panning Logic
        # We only pan if we decided we were panning during on_mouse_press.
        # This prevents the camera from getting stuck if we drag FROM map OVER UI.
        if self.is_panning_map:
            # Check if correct buttons are still held (safety check)
            if buttons & arcade.MOUSE_BUTTON_MIDDLE or buttons & arcade.MOUSE_BUTTON_RIGHT:
                scale = 1.0 / self.camera_controller.zoom
                
                # Invert logic: Move mouse LEFT -> Camera moves RIGHT
                new_x = self.camera_controller.position.x - (dx * scale)
                new_y = self.camera_controller.position.y - (dy * scale)
                
                self.camera_controller.position = Vec2(new_x, new_y)
                self.camera_controller.update_arcade_camera(self.world_camera)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        """Handle zoom events (Mouse Wheel Scroll)."""
        self.imgui_controller.on_mouse_scroll(x, y, scroll_x, scroll_y)
        if self.imgui_controller.io.want_capture_mouse:
            return
        
        # Determine zoom direction
        zoom_dir = 1.0 if scroll_y > 0 else -1.0
        zoom_speed = 0.1
        
        # Apply zoom
        self.camera_controller.zoom += zoom_dir * zoom_speed
        
        # Clamp zoom to reasonable limits (0.1x to 5.0x)
        self.camera_controller.zoom = max(0.1, min(self.camera_controller.zoom, 5.0))
        
        # Optional: Zoom towards mouse cursor logic could be added here
        # For now, we zoom towards the center of the camera
        
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_key_press(self, symbol: int, modifiers: int):
        """Handle hotkeys."""
        if symbol == arcade.key.S and (modifiers & arcade.key.MOD_CTRL):
            self.net.request_save()

    def _handle_selection(self, screen_x: int, screen_y: int):
        """Converts a screen click into a region selection."""
        # Unproject handles camera zoom/pan to find world coords
        world_pos = self.world_camera.unproject((screen_x, screen_y))
        wx, wy = world_pos.x, world_pos.y
        
        region_int_id = self.map_renderer.get_region_id_at_world_pos(wx, wy)
        
        if region_int_id is not None:
            self.selected_region_int_id = region_int_id
            
            self.highlight_layer.clear()
            highlight_sprite = self.map_renderer.create_highlight_sprite(
                [region_int_id], 
                (255, 255, 0)
            )
            if highlight_sprite:
                self.highlight_layer.append(highlight_sprite)
        else:
            self.selected_region_int_id = None
            self.highlight_layer.clear()

    def focus_on_coordinates(self, x: float, y: float):
        """Callback to jump camera to specific location."""
        # Flip Y if necessary based on data vs rendering coords
        world_y = self.map_renderer.height - y
        self.world_camera.position = (x, world_y)
        self.camera_controller.update_arcade_camera(self.world_camera)