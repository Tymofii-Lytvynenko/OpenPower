import arcade
from pyglet.math import Vec2

from src.server.session import GameSession
from src.shared.config import GameConfig
from src.client.network_client import NetworkClient
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.editor_layout import EditorLayout
from src.client.services.imgui_service import ImGuiService
from src.client.camera_controller import CameraController

class EditorView(arcade.View):
    """
    The main visual interface for the Map Editor.
    
    Refactoring Status:
        - Implements Composition (Network, ImGui, Layout, MapRenderer, CameraController).
        - Logic for inputs is delegated to specific components.
    """

    def __init__(self, session: GameSession, config: GameConfig):
        super().__init__()
        self.game_config = config
        self.is_panning_map = False
        self.background_color = arcade.color.DARK_SLATE_GRAY
        
        # --- 1. Composition: Logic Components ---
        self.net = NetworkClient(session)
        self.imgui = ImGuiService(self.window)
        
        # --- 2. Composition: UI Layout ---
        self.ui_layout = EditorLayout(self.net)
        self.ui_layout.on_focus_request = self.focus_on_coordinates
        
        # --- 3. Composition: Visual Components ---
        
        # Resolve Map Path
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
             # Fallback to project root placeholder if needed
             map_path = config.project_root / "missing_map_placeholder.png"

        self.map_renderer = MapRenderer(map_path, config.cache_dir)
        
        # --- 4. Composition: Camera System ---
        self.world_camera = arcade.Camera2D()
        
        # Initialize Controller centered on the map
        center_pos = self.map_renderer.get_center()
        self.camera_controller = CameraController(center_pos)
        
        # --- 5. State ---
        self.selected_region_int_id = None
        self.highlight_layer = arcade.SpriteList()

    def on_resize(self, width: int, height: int):
        """Syncs resize events with ImGui."""
        self.imgui.resize(width, height)
        self.world_camera.match_window()

    def on_show_view(self):
        """Initial setup when view appears."""
        self.camera_controller.update_arcade_camera(self.world_camera)

    def on_draw(self):
        """Render loop."""
        self.clear()
        
        # 1. UI Update
        self.imgui.new_frame(1.0 / 60.0) 

        # 2. World Render
        self.world_camera.use()
        self.map_renderer.draw_map()
        self.highlight_layer.draw()
        
        # 3. UI Generation
        self.ui_layout.render(self.selected_region_int_id, 1.0/60.0)

        # 4. UI Render (Overlay)
        self.window.use() 
        self.imgui.render()

    # --- Input Delegation ---

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int):
        # 1. ImGui Priority
        if self.imgui.on_mouse_press(x, y, button, modifiers):
            self.is_panning_map = False 
            return

        # 2. Map Interaction
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_selection(x, y)
        
        # 3. Camera Control State
        if button == arcade.MOUSE_BUTTON_RIGHT or button == arcade.MOUSE_BUTTON_MIDDLE:
            self.is_panning_map = True

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int):
        if self.imgui.on_mouse_release(x, y, button, modifiers):
            return
        
        if button == arcade.MOUSE_BUTTON_RIGHT or button == arcade.MOUSE_BUTTON_MIDDLE:
            self.is_panning_map = False

    def on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int):
        if self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers):
            return

        if self.is_panning_map:
            # Delegate math to Controller
            self.camera_controller.pan(dx, dy)
            self.camera_controller.update_arcade_camera(self.world_camera)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        if self.imgui.on_mouse_scroll(x, y, scroll_x, scroll_y):
            return
        
        # Delegate logic to Controller
        self.camera_controller.zoom_scroll(scroll_y)
        self.camera_controller.update_arcade_camera(self.world_camera)
        
    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int):
        self.imgui.on_mouse_motion(x, y, dx, dy)

    def on_key_press(self, symbol: int, modifiers: int):
        if self.imgui.on_key_press(symbol, modifiers):
            return

        if symbol == arcade.key.S and (modifiers & arcade.key.MOD_CTRL):
            self.net.request_save()

    def on_key_release(self, symbol: int, modifiers: int):
        self.imgui.on_key_release(symbol, modifiers)

    def on_text(self, text: str):
        self.imgui.on_text(text)

    # --- Internal Helpers ---

    def _handle_selection(self, screen_x: int, screen_y: int):
        """Converts screen click -> World Pos -> Region ID."""
        # Unproject allows us to get the world coordinates considering the camera
        world_pos = self.world_camera.unproject((screen_x, screen_y))
        
        region_int_id = self.map_renderer.get_region_id_at_world_pos(world_pos.x, world_pos.y)
        
        if region_int_id is not None:
            self.selected_region_int_id = region_int_id
            
            # Update visual highlight
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
        """
        Callback used by UI to jump to a specific region center.
        We flip Y here because UI/Data usually treats Y=0 as Top, while World is Bottom.
        """
        world_y = self.map_renderer.height - y
        
        self.camera_controller.jump_to(x, world_y)
        self.camera_controller.update_arcade_camera(self.world_camera)