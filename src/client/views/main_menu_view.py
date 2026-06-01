import arcade
import sys
from dataclasses import dataclass
from typing import Callable
from typing import TYPE_CHECKING

from src.client.views.base_view import BaseImGuiView
from src.client.services.imgui_service import ImGuiService
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.settings_content import GameSettingsContent
from src.client.renderers.map_renderer import MapRenderer
from src.client.controllers.camera_controller import CameraController

if TYPE_CHECKING:
    from src.shared.config import GameConfig
    from src.server.session import GameSession


@dataclass(frozen=True, slots=True)
class MenuAction:
    label: str
    callback: Callable[[], None]
    spacer_after: float = 0.0


class MainMenuView(BaseImGuiView):
    def __init__(self, session: "GameSession", config: "GameConfig"):
        super().__init__()
        self.session = session
        self.config = config
        self.ui = UIComposer(GAMETHEME)
        self._show_settings = False
        self._settings_content = GameSettingsContent(self.window.settings, self.window)

        # --- SHARED RENDERER LOGIC ---
        if self.window.shared_renderer is None:
            print("[MainMenuView] Initializing Shared Renderer...")
            
            # BIGGER GLOBE: Set default distance closer (was 4.5, now 2.3)
            self.cam_ctrl = CameraController(distance=2.3)
            
            self.cam_ctrl.look_at_pixel_coords(
                12000, 2400,
                16000, 8000 # TODO: Replace with dynamic map size
            )
            
            map_path = None
            
            # 1. Search in data directories (mods first)
            for data_dir in config.get_data_dirs():
                candidate = data_dir / "regions" / "regions.png"
                if candidate.exists():
                    map_path = candidate
                    break
            
            # 2. Hard fallback to base module if not found
            if map_path is None:
                map_path = config.project_root / "modules" / "base" / "data" / "regions" / "regions.png"
                
            terrain_path = config.get_asset_path("map/terrain.png")

            self.window.shared_renderer = MapRenderer(
                camera=self.cam_ctrl,
                map_data=session.map_data,
                map_img_path=map_path,
                terrain_img_path=terrain_path
            )
        else:
            # SYNC: Just grab the existing controller. 
            # DO NOT reset distance or pitch here, so it persists from other screens.
            self.cam_ctrl = self.window.shared_renderer.camera

        self.renderer = self.window.shared_renderer
        
        # We still toggle the visual style (Terrain only for main menu)
        self.renderer.set_overlay_style(enabled=False, opacity=0.0)

    def on_show_view(self):
        self.window.background_color = (15, 15, 20, 255)

    def on_game_update(self, dt: float):
        # Gentle auto-rotation
        self.cam_ctrl.yaw += 0.05 * dt

    def on_draw(self):
        self.clear()

        self.imgui.new_frame()
        self.ui.setup_frame()

        # Reset Context & Draw
        ctx = self.window.ctx
        ctx.scissor = None
        ctx.viewport = (0, 0, self.window.width, self.window.height)
        ctx.enable_only((ctx.DEPTH_TEST, ctx.BLEND)) 
        
        self.renderer.draw()

        self._render_menu_window()
        self.imgui.render()

    def _render_menu_window(self):
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("Main Menu", screen_w, screen_h, w=350, h=450):
            if self._show_settings:
                self._render_settings_menu()
            else:
                self._render_main_menu()

            self.ui.end_panel()

    def _render_main_menu(self):
        self.ui.draw_title("OPENPOWER")

        for action in self._build_menu_actions():
            if self.ui.draw_menu_button(action.label):
                action.callback()
            if action.spacer_after:
                self.ui.dummy((0, action.spacer_after))

    def _build_menu_actions(self) -> tuple[MenuAction, ...]:
        return (
            MenuAction("SINGLEPLAYER", lambda: self.nav.show_new_game_screen(self.session, self.config)),
            MenuAction("LOAD GAME", lambda: self.nav.show_load_game_screen(self.config)),
            MenuAction("MAP EDITOR", lambda: self.nav.show_editor_loading(self.session, self.config)),
            MenuAction("SETTINGS", self._open_settings, spacer_after=50.0),
            MenuAction("EXIT TO DESKTOP", self._exit_to_desktop),
        )

    def _render_settings_menu(self):
        self.ui.draw_title("SETTINGS")
        self._settings_content.render()

        from imgui_bundle import imgui
        imgui.dummy((0, 42))
        if self.ui.draw_menu_button("BACK"):
            self._show_settings = False

    def _open_settings(self) -> None:
        self._show_settings = True

    def _exit_to_desktop(self) -> None:
        arcade.exit()
        sys.exit()

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_LEFT:
            self.cam_ctrl.drag(dx, dy)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.cam_ctrl.zoom_scroll(scroll_y)
