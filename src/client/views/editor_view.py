import arcade
from src.shared.config import GameConfig
from src.client.services.imgui_service import ImGuiService
from src.client.ui.theme import GAMETHEME
from src.client.views.base_view import BaseImGuiView
from src.client.renderers.map_renderer import MapRenderer
from src.client.ui.layouts.editor_layout import EditorLayout
from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.utils.color_generator import generate_political_colors
from src.client.tasks.editor_loading_task import EditorContext

class EditorView(BaseImGuiView):
    def __init__(self, context: EditorContext, config: GameConfig):
        super().__init__()
        
        self.net = context.net_client
        self.imgui: ImGuiService = ImGuiService(self.window)
        self.layout = EditorLayout(self.net, None)
        
        # 1. Camera
        self.cam_ctrl = CameraController()
        
        # 2. Renderer
        self.renderer = MapRenderer(
            camera=self.cam_ctrl,
            map_img_path=context.map_path, 
            terrain_img_path=context.terrain_path,
            map_data=context.map_data
        )
        
        self.world_cam = arcade.Camera2D()
        
        # 3. Viewport Controller
        self.viewport_ctrl = ViewportController(
            cam_ctrl=self.cam_ctrl,
            world_camera=self.world_cam,
            map_renderer=self.renderer,
            on_selection_change=self.on_selection_changed,
            net_client=self.net
        )
        
        self.selected_region_id = None

    def on_show_view(self):
        self.window.background_color = GAMETHEME.colors.black
        self._refresh_political_data()

    def _refresh_political_data(self):
        state = self.net.get_state()
        if "regions" not in state.tables: return
        
        df = state.get_table("regions")
        if "owner" not in df.columns: return

        unique_owners = df["owner"].unique().to_list()
        color_map = generate_political_colors(unique_owners)
        self.renderer.update_overlay(color_map)

    def on_selection_changed(self, region_id: int | None):
        self.selected_region_id = region_id

    def on_draw(self):
        self.clear()
        self.imgui.new_frame()
        
        self.world_cam.use()
        current_mode = self.layout.get_current_render_mode()
        is_overlay_enabled = (current_mode != "terrain")
        self.renderer.set_overlay_style(enabled=is_overlay_enabled, opacity=0.90)
        self.renderer.draw()
        
        self.window.use()
        self.layout.render(self.imgui.io.framerate)
        self.imgui.render()

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