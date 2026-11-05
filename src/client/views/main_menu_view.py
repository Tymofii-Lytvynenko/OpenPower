import arcade
import sys
from typing import TYPE_CHECKING

from src.client.views.base_view import BaseImGuiView
from src.client.services.imgui_service import ImGuiService
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.settings_content import GameSettingsContent
from src.client.ui.components.main_menu_content import MainMenuContent, build_main_menu_actions
from src.client.renderers.map_renderer import MapRenderer
from src.client.controllers.camera_controller import CameraController

if TYPE_CHECKING:
    from src.shared.config import GameConfig
    from src.shared.protocols import SessionPort


class MainMenuView(BaseImGuiView):
    def __init__(self, session: "SessionPort", config: "GameConfig"):
        super().__init__()
        self.session = session
        self.config = config
        self.ui = UIComposer(GAMETHEME)
        self._settings_content = GameSettingsContent(self.window.settings, self.window, staged=True)
        self._menu_content = MainMenuContent(
            self.ui,
            self._settings_content,
            build_main_menu_actions(
                lambda: self.nav.show_new_game_screen(self.session, self.config),
                lambda: self.nav.show_load_game_screen(self.config),
                self._exit_to_desktop,
            ),
        )

        # --- SHARED RENDERER LOGIC ---
        if self.window.shared_renderer is None:
            print("[MainMenuView] Initializing Shared Renderer...")

            # BIGGER GLOBE: Set default distance closer (was 4.5, now 2.3)
            self.cam_ctrl = CameraController(distance=2.3)
            # Keep the original framing proportional when a mod uses a different map size.
            map_width = session.map_data.width
            map_height = session.map_data.height
            self.cam_ctrl.look_at_pixel_fraction(
                0.75,
                0.30,
                map_width,
                map_height,
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
        ctx.viewport = (0, 0, *self.window.get_size())
        ctx.enable_only(ctx.DEPTH_TEST, ctx.BLEND)

        self.renderer.draw()

        self._render_menu_window()
        self.imgui.render()

    def _render_menu_window(self):
        screen_w, screen_h = self.window.get_size()
        self._menu_content.render(screen_w, screen_h)

    def _exit_to_desktop(self) -> None:
        arcade.exit()
        sys.exit()

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_LEFT:
            self.cam_ctrl.drag(dx, dy)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.cam_ctrl.zoom_scroll(scroll_y)
