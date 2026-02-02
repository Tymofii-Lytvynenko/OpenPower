import arcade
import polars as pl
from typing import TYPE_CHECKING, Optional

from src.client.views.base_view import BaseImGuiView
from src.client.services.network_client_service import NetworkClient
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.shared.config import GameConfig
from src.client.utils.coords_util import calculate_centroid
from src.client.utils.color_generator import generate_political_colors

if TYPE_CHECKING:
    from src.server.session import GameSession

class NewGameView(BaseImGuiView):
    def __init__(self, session: "GameSession", config: GameConfig):
        super().__init__()
        self.session = session 
        self.config = config
        
        self.net = NetworkClient(session)
        self.ui = UIComposer(GAMETHEME)
        
        self.selected_country_id: Optional[str] = None
        self.playable_countries = self._fetch_playable_countries()

        # --- USE SHARED RENDERER ---
        if self.window.shared_renderer:
            self.renderer = self.window.shared_renderer
            self.cam_ctrl = self.renderer.camera
            
            # --- TERRAIN MODE CONFIGURATION ---
            # enabled=True:  Must be True so the shader processes ID lookups for highlighting.
            # opacity=0.0:   Makes the political colors invisible, revealing the Terrain texture.
            self.renderer.set_overlay_style(enabled=True, opacity=0.0)
            
            # We must still generate the data map so the renderer knows "USA = Region 45, 46..."
            # even if we aren't showing the colors right now.
            self._refresh_political_map()
            
            self.renderer.clear_highlight()
        else:
            # Fallback
            from src.client.renderers.map_renderer import MapRenderer
            from src.client.controllers.camera_controller import CameraController
            self.cam_ctrl = CameraController()
            self.renderer = MapRenderer(
                camera=self.cam_ctrl, 
                map_data=session.map_data,
                map_img_path=config.get_asset_path("map/regions.png"),
                terrain_img_path=config.get_asset_path("map/terrain.png")
            )
            self.renderer.set_overlay_style(enabled=True, opacity=0.0)
            self._refresh_political_map()

    def _refresh_political_map(self):
        """
        Generates the Region ID -> Color mapping.
        Required for the renderer to know which pixels belong to the selected country.
        """
        try:
            state = self.net.get_state()
            if "regions" not in state.tables: return

            df = state.get_table("regions")
            if "owner" not in df.columns or "id" not in df.columns: return

            unique_owners = df["owner"].unique().to_list()
            tag_palette = generate_political_colors(unique_owners)
            
            region_color_map = {}
            for row in df.select(["id", "owner"]).iter_rows(named=True):
                rid = row["id"]
                owner = row["owner"]
                color = tag_palette.get(owner, (50, 50, 50))
                region_color_map[rid] = color
            
            self.renderer.update_overlay(region_color_map)
            
        except Exception as e:
            print(f"[NewGameView] Color Generation Error: {e}")

    def _fetch_playable_countries(self) -> pl.DataFrame:
        try:
            state = self.net.get_state()
            df = state.get_table("countries")
            return df.filter(pl.col("is_playable") == True).sort("id")
        except KeyError:
            return pl.DataFrame()

    def on_show_view(self):
        self.window.background_color = (10, 10, 10, 255)

    def on_draw(self):
        self.clear()
        
        self.imgui.new_frame()
        self.ui.setup_frame()
        
        # Draw 3D Globe
        ctx = self.window.ctx
        ctx.scissor = None
        ctx.viewport = (0, 0, self.window.width, self.window.height)
        ctx.enable_only((ctx.DEPTH_TEST, ctx.BLEND))

        self.renderer.draw()

        self._render_ui()
        self.imgui.render()

    def _render_ui(self):
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("New Game", screen_w, screen_h, w=600, h=500):
            self.ui.draw_title("SELECT NATION")
            
            from imgui_bundle import imgui
            
            imgui.begin_child("CountryList", (250, 350), True)
            if not self.playable_countries.is_empty():
                for row in self.playable_countries.iter_rows(named=True):
                    c_id = row['id']
                    label = f"{c_id} - {row.get('name', '')}"
                    is_selected = (self.selected_country_id == c_id)
                    
                    if imgui.selectable(label, is_selected)[0]:
                        self.selected_country_id = c_id
                        self._focus_camera_on_country(c_id)
                        self._highlight_country(c_id)

                    if is_selected:
                        imgui.set_item_default_focus()

            else:
                imgui.text_disabled("No countries loaded.")
            imgui.end_child()
            
            imgui.same_line()
            
            imgui.begin_group()
            imgui.dummy((300, 0))
            if self.selected_country_id:
                imgui.text_colored(GAMETHEME.colors.accent, f"Selected: {self.selected_country_id}")
                imgui.separator()
                imgui.text_wrapped("Standard Campaign.")
                imgui.text_wrapped("Difficulty: Normal")
            else:
                imgui.text_disabled("Select a nation.")
            imgui.end_group()
            
            imgui.dummy((0, 20))
            imgui.separator()
            imgui.dummy((0, 10))
            
            if imgui.button("BACK", (100, 40)):
                self.renderer.clear_highlight()
                self.renderer.set_overlay_style(enabled=False, opacity=0.0)
                self.nav.show_main_menu(self.session, self.config)
            
            imgui.same_line()
            avail_w = imgui.get_content_region_avail().x
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - 150)
            
            if self.selected_country_id:
                if imgui.button("START CAMPAIGN", (150, 40)):
                    self._start_game()
            else:
                imgui.begin_disabled()
                imgui.button("START CAMPAIGN", (150, 40))
                imgui.end_disabled()

            self.ui.end_panel()

    def _highlight_country(self, country_tag: str):
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.tables["regions"]
        try:
            owned_ids = df.filter(pl.col("owner") == country_tag)["id"].to_list()
            self.renderer.set_highlight(owned_ids)
        except Exception as e:
            print(f"Highlight error: {e}")

    def _focus_camera_on_country(self, country_tag: str):
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.tables["regions"]
        owned_regions = df.filter(pl.col("owner") == country_tag)
        map_height = self.session.map_data.height
        centroid = calculate_centroid(owned_regions, map_height)
        
        if centroid:
            world_x, world_y = centroid
            px = world_x
            py = map_height - world_y 
            
            self.cam_ctrl.look_at_pixel_coords(
                px, py, 
                self.session.map_data.width, 
                self.session.map_data.height
            )

    def _start_game(self):
        if not self.selected_country_id: return
        
        # Don't clear highlight, user might like seeing their choice glow during load
        # self.renderer.clear_highlight() 

        from src.client.tasks.new_game_task import NewGameTask, NewGameContext

        def on_task_complete(ctx: NewGameContext):
            self.nav.show_game_view(
                session=ctx.session,
                config=self.config,
                player_tag=ctx.player_tag,
                initial_pos=ctx.start_pos
            )
            return None

        task = NewGameTask(self.session, self.config, self.selected_country_id)
        self.nav.show_loading(task, on_success=on_task_complete)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_LEFT:
            self.cam_ctrl.drag(dx, dy)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.cam_ctrl.zoom_scroll(scroll_y)