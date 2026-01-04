import arcade
from pathlib import Path

from src.client.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.imgui_controller import ImGuiController
from src.client.ui.editor_layout import EditorLayout

# Define paths relative to the project root for portability.
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MAP_PATH = PROJECT_ROOT / "modules" / "base" / "data" / "regions.png"
CACHE_DIR = PROJECT_ROOT / ".cache"

class EditorView(arcade.View):
    """
    The main view for the Map Editor mode.
    
    This class acts as the 'Composition Root' for the editor state, orchestrating:
    1. The Map Renderer (visuals)
    2. The Camera Controller (navigation)
    3. The UI Layout (ImGui interaction)
    
    It follows the standard Arcade View lifecycle (setup, on_draw, on_update).
    """

    def __init__(self):
        super().__init__()
        
        # --- Subsystems ---
        # Initialized in setup() to ensure the window context is ready.
        self.camera_controller: CameraController = None
        self.map_renderer: MapRenderer = None
        self.imgui_controller: ImGuiController = None
        self.editor_layout: EditorLayout = None

        # --- Cameras ---
        # We use separate cameras for the game world (zooms/pans) and the UI (static).
        # Arcade 3.0 uses Camera2D.
        self.world_camera: arcade.Camera2D = None
        self.ui_camera: arcade.Camera2D = None

        # --- Editor State ---
        self.highlight_layer = arcade.SpriteList()
        self.selected_region_id = None

    def setup(self):
        """
        Allocates resources and initializes systems.
        Called when switching to this view.
        """
        width = self.window.width
        height = self.window.height
        
        # 1. Initialize Cameras
        self.world_camera = arcade.Camera2D()
        
        # For the UI, we want a static view where (0,0) is the bottom-left corner.
        # Since Camera2D centers the view on its 'position', we must set the position
        # to the center of the screen to align coordinate systems.
        self.ui_camera = arcade.Camera2D()
        self.ui_camera.position = (width / 2, height / 2)
        
        # 2. Initialize Map Renderer
        # This handles loading the heavy map assets and generating the cache.
        self.map_renderer = MapRenderer(MAP_PATH, CACHE_DIR)
        
        # 3. Initialize Camera Controller
        # Start focused on the center of the map.
        start_pos = self.map_renderer.get_center()
        self.camera_controller = CameraController(start_pos)
        
        # Apply initial state to the Arcade camera
        self.camera_controller.update_arcade_camera(self.world_camera)

        # 4. Initialize UI Systems
        self.imgui_controller = ImGuiController(self.window)
        self.editor_layout = EditorLayout()
        
        print("[EditorView] Setup complete.")

    def on_show_view(self):
        """Called when the view is made active."""
        self.setup()
        # Set a neutral background color for empty space (ocean/void)
        self.window.background_color = arcade.color.DARK_SLATE_GRAY

    def on_draw(self):
        """Render the screen."""
        self.clear()
        
        # 1. Render World Layer
        # Activate the camera that handles zoom/pan
        self.world_camera.use()
        
        if self.map_renderer:
            self.map_renderer.draw_map()
            
        # Draw dynamic highlights (e.g., selected region borders) on top of the map
        self.highlight_layer.draw()
            
        # 2. Render UI Layer
        # Switch to the static camera for interface elements
        self.ui_camera.use()
        
        # 3. Render ImGui Interface
        # We delegate the layout logic to EditorLayout to keep the View clean.
        if self.editor_layout:
             # Calculate FPS for debug overlay
            fps = 1.0 / self.window.last_update_duration if self.window.last_update_duration > 0 else 60.0
            
            self.editor_layout.render(self.selected_region_id, fps)

        # Finalize ImGui render (flush draw commands to GPU)
        self.imgui_controller.render()

    def on_update(self, delta_time: float):
        """Game logic update."""
        self.imgui_controller.update(delta_time)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        """Handle mouse clicks."""
        # 1. Pass input to ImGui first. 
        # If the mouse is hovering a window, we shouldn't click the map behind it.
        self.imgui_controller.on_mouse_press(x, y, button, modifiers)
        if self.imgui_controller.io.want_capture_mouse:
            return

        # 2. Handle World Interaction (Map Selection)
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)

    def _handle_selection(self, screen_x: int, screen_y: int):
        """
        Translates a screen click into a region selection.
        """
        # Convert screen coordinates to world coordinates using the controller's logic
        wx, wy = self.camera_controller.screen_to_world(
            screen_x, screen_y, self.window.width, self.window.height
        )
        
        # Query the renderer (which queries the Atlas) for the region ID
        region_id = self.map_renderer.get_region_id_at_world_pos(wx, wy)
        
        # Update State
        if region_id is not None:
            self.selected_region_id = region_id
            
            # Debug info to console
            hex_code = self.map_renderer.get_color_hex_at_world_pos(wx, wy)
            print(f"[Editor] Selected Region ID: {region_id} (Color: {hex_code})")
            
            # Generate Visual Highlight
            self.highlight_layer.clear()
            # Yellow border for selection
            highlight_sprite = self.map_renderer.create_highlight_sprite([region_id], (255, 255, 0))
            if highlight_sprite:
                self.highlight_layer.append(highlight_sprite)
        else:
            # Deselect if clicked on empty space
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
            
        # Update logical zoom state
        self.camera_controller.scroll(scroll_y)
        # Apply new state to the Arcade camera
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.imgui_controller.io.want_capture_mouse:
            return

        # Pan the map with Middle Mouse Button
        if buttons == arcade.MOUSE_BUTTON_MIDDLE:
            self.camera_controller.drag(dx, dy)
            self.camera_controller.update_arcade_camera(self.world_camera)

    def on_resize(self, width, height):
        """Handle window resizing."""
        super().on_resize(width, height)
        
        # Keep the UI camera centered correctly relative to the new window size
        self.ui_camera.position = (width / 2, height / 2)
        
        # World camera is handled by the controller, but we might want to re-sync if needed.
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_key_press(self, key, modifiers):
        self.imgui_controller.on_key_press(key, modifiers)

    def on_key_release(self, key, modifiers):
        self.imgui_controller.on_key_release(key, modifiers)

    def on_text(self, text):
        self.imgui_controller.on_text(text)