import arcade
from pathlib import Path

from src.client.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.imgui_controller import ImGuiController
from src.client.ui.editor_layout import EditorLayout

# Project root calculation
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MAP_PATH = PROJECT_ROOT / "modules" / "base" / "assets" / "maps" / "regions.png"
CACHE_DIR = PROJECT_ROOT / ".cache"

class EditorView(arcade.View):
    """
    Editor Mode view.
    Provides tools for editing maps, scenarios, and data.
    """
    def __init__(self):
        super().__init__()
        
        # Systems
        self.camera_controller: CameraController = None
        self.map_renderer: MapRenderer = None
        self.imgui_controller: ImGuiController = None
        self.editor_layout: EditorLayout = None

        # Cameras
        self.world_camera: arcade.Camera = None
        self.ui_camera: arcade.Camera = None

        # State
        self.highlight_layer = arcade.SpriteList()
        self.selected_region_id = None

    def setup(self):
        """Initializes scene resources and components."""
        width = self.window.width
        height = self.window.height
        
        # 1. Cameras
        self.world_camera = arcade.Camera(width, height)
        self.ui_camera = arcade.Camera(width, height)
        
        # 2. Renderer (integrating RegionAtlas)
        self.map_renderer = MapRenderer(MAP_PATH, CACHE_DIR)
        
        # 3. Camera Controller
        start_pos = self.map_renderer.get_center()
        self.camera_controller = CameraController(start_pos)
        self.camera_controller.update_arcade_camera(self.world_camera, width, height)

        # 4. UI
        self.imgui_controller = ImGuiController(self.window)
        self.editor_layout = EditorLayout()
        
        print("[EditorView] Setup complete.")

    def on_show_view(self):
        self.setup()
        self.window.background_color = arcade.color.DARK_SLATE_GRAY

    def on_draw(self):
        """Main rendering loop."""
        self.clear()
        
        # 1. World Layer
        self.world_camera.use()
        if self.map_renderer:
            self.map_renderer.draw_map()
            
        # Draw dynamic highlights (borders) on top of the map
        self.highlight_layer.draw()
            
        # 2. UI Layer
        self.ui_camera.use()
        
        # 3. Render ImGui Interface
        if self.editor_layout:
             # Calculate FPS safely
            fps = 1.0 / self.window.last_update_duration if self.window.last_update_duration > 0 else 60.0
            
            # Pass the state to the layout
            self.editor_layout.render(self.selected_region_id, fps)

        # Finalize ImGui render (flush to GPU)
        self.imgui_controller.render()

    def on_update(self, delta_time: float):
        self.imgui_controller.update(delta_time)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        # Pass input to ImGui first
        self.imgui_controller.on_mouse_press(x, y, button, modifiers)
        if self.imgui_controller.io.want_capture_mouse:
            return

        # Handle World Interaction
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)

    def _handle_selection(self, screen_x: int, screen_y: int):
        """Calculates world position and updates selection highlights."""
        # 1. Screen -> World
        wx, wy = self.camera_controller.screen_to_world(
            screen_x, screen_y, self.window.width, self.window.height
        )
        
        # 2. Get Region ID from Renderer (which asks Atlas)
        region_id = self.map_renderer.get_region_id_at_world_pos(wx, wy)
        
        # 3. Update State
        if region_id is not None:
            self.selected_region_id = region_id
            hex_code = self.map_renderer.get_color_hex_at_world_pos(wx, wy)
            print(f"[Editor] Selected Region ID: {region_id} (Color: {hex_code})")
            
            # 4. Generate Visual Highlight
            # Clear previous selection
            self.highlight_layer.clear()
            
            # Create new selection sprite
            # Using Yellow (255, 255, 0) for selection border
            highlight_sprite = self.map_renderer.create_highlight_sprite([region_id], (255, 255, 0))
            if highlight_sprite:
                self.highlight_layer.append(highlight_sprite)
        else:
            print("[Editor] Clicked void/ocean")
            self.selected_region_id = None
            self.highlight_layer.clear()

    # --- Input Propagation ---

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        self.imgui_controller.on_mouse_motion(x, y, dx, dy)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        self.imgui_controller.on_mouse_release(x, y, button, modifiers)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.imgui_controller.on_mouse_scroll(x, y, scroll_x, scroll_y)
        if self.imgui_controller.io.want_capture_mouse:
            return
            
        self.camera_controller.scroll(scroll_y)
        self.camera_controller.update_arcade_camera(
            self.world_camera, self.window.width, self.window.height
        )

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.imgui_controller.io.want_capture_mouse:
            return

        if buttons == arcade.MOUSE_BUTTON_MIDDLE:
            self.camera_controller.drag(dx, dy)
            self.camera_controller.update_arcade_camera(
                self.world_camera, self.window.width, self.window.height
            )

    def on_resize(self, width, height):
        self.world_camera.resize(width, height)
        self.ui_camera.resize(width, height)
        if self.camera_controller:
            self.camera_controller.update_arcade_camera(self.world_camera, width, height)

    def on_key_press(self, key, modifiers):
        self.imgui_controller.on_key_press(key, modifiers)

    def on_key_release(self, key, modifiers):
        self.imgui_controller.on_key_release(key, modifiers)

    def on_text(self, text):
        self.imgui_controller.on_text(text)