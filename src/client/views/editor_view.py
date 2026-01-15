import arcade
from src.shared.config import GameConfig
from src.client.services.imgui_service import ImGuiService
from src.client.ui.theme import GAMETHEME

# Base Class
from src.client.views.base_view import BaseImGuiView

# Composition Components
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.editor_layout import EditorLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors
from src.client.tasks.editor_loading_task import EditorContext

class EditorView(BaseImGuiView):
    """
    The main Map Editor state.
    Uses Composition (Controllers, Renderer) and Inheritance (BaseImGuiView).
    """
    def __init__(self, context: EditorContext, config: GameConfig):
        super().__init__()
        
        # 1. Infrastructure Services
        self.net = context.net_client
        self.imgui = ImGuiService(self.window)  # Required by BaseImGuiView
        
        # 2. UI Layout
        self.layout = EditorLayout(self.net, None) # ViewportController set later
        
        # 3. Visuals (Map Renderer)
        self.renderer = MapRenderer(
            map_path=context.map_path, 
            terrain_path=context.terrain_path, 
            cache_dir=config.cache_dir, 
            preloaded_atlas=context.atlas
        )
        
        # 4. Camera System
        self.world_cam = arcade.Camera2D()
        self.cam_ctrl = CameraController(self.renderer.get_center())
        
        # 5. Input Controller
        # Mediates between Raw Input -> Camera Movement / Map Selection
        self.viewport_ctrl = ViewportController(
            camera_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            on_selection_change=self.on_selection_changed
        )
        
        self.selected_region_id = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.col_black
        # Ensure camera is synced before first frame
        self.cam_ctrl.sync_with_arcade(self.world_cam)
        # Generate initial political map
        self._refresh_political_data()

    def _refresh_political_data(self):
        """Fetches region data and generates country colors."""
        state = self.net.get_state()
        if "regions" not in state.tables: return
        
        df = state.get_table("regions")
        if "owner" not in df.columns: return

        # Create mapping: {RegionID: OwnerTag}
        region_map = dict(zip(df["id"], df["owner"]))
        unique_owners = df["owner"].unique().to_list()
        
        # Generate consistent colors
        color_map = generate_political_colors(unique_owners)
        
        self.renderer.update_political_layer(region_map, color_map)

    def on_selection_changed(self, region_id: int | None):
        """Callback from ViewportController."""
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        
        # 1. Start UI Frame
        self.imgui.new_frame()
        
        # 2. Draw World
        self.world_cam.use()
        self.renderer.draw(mode=self.layout.get_current_render_mode())
        
        # 3. Generate UI
        self.window.use()
        self.layout.render(self.selected_region_id, self.imgui.io.framerate)
        
        # 4. Render UI
        self.imgui.render()

    # --- IMPLEMENTING BASE HOOKS ---
    # No need to manually check self.imgui here; the Base class does it.

    def on_game_resize(self, width, height):
        self.world_cam.match_window()

    def on_game_mouse_press(self, x, y, button, modifiers):
        self.viewport_ctrl.on_mouse_press(x, y, button)

    def on_game_mouse_release(self, x, y, button, modifiers):
        self.viewport_ctrl.on_mouse_release(x, y, button)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.viewport_ctrl.on_mouse_drag(x, y, dx, dy, buttons)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.viewport_ctrl.on_mouse_scroll(x, y, scroll_x, scroll_y)

    def on_game_key_press(self, symbol, modifiers):
        if symbol == arcade.key.S and (modifiers & arcade.key.MOD_CTRL):
            self.net.request_save()