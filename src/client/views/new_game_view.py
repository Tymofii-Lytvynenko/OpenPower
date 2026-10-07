import arcade
import polars as pl
from typing import TYPE_CHECKING, Optional

from src.client.views.base_view import BaseImGuiView
from src.client.services.network_client_service import NetworkClient
from src.client.services.campaign_selection import filter_selectable_countries, preview_campaign_scenario
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.theme import GAMETHEME
from src.shared.config import GameConfig
from src.client.utils.coords_util import calculate_centroid
from src.client.utils.color_generator import generate_political_colors

if TYPE_CHECKING:
    from src.shared.protocols import SessionPort


COUNTRY_SELECTION_FOCUS_DISTANCE = 1.55


class NewGameView(BaseImGuiView):
    def __init__(self, session: "SessionPort", config: GameConfig):
        super().__init__()
        self.session = session 
        self.config = config
        
        self.net = NetworkClient(session)
        self.ui = UIComposer(GAMETHEME)
        
        self.selected_country_id: Optional[str] = None
        self.all_playable_countries = self._fetch_playable_countries()
        self.campaign_scenarios = self._fetch_campaign_scenarios()
        self.selected_scenario_id: Optional[str] = (
            str(self.campaign_scenarios[0].get("id")) if self.campaign_scenarios else None
        )
        self.playable_countries = filter_selectable_countries(
            self.all_playable_countries,
            self._selected_scenario(),
        )

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
            
            # Convert theme dim color to 0-255 INT tuple for fallback
            fallback_c = tuple(int(c * 255) for c in GAMETHEME.colors.text_dim[:3])

            region_color_map = {}
            for row in df.select(["id", "owner"]).iter_rows(named=True):
                rid = row["id"]
                owner = row["owner"]
                # Use the generated palette or the theme fallback
                color = tag_palette.get(owner, fallback_c)
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

    def _fetch_campaign_scenarios(self) -> list[dict]:
        try:
            state = self.net.get_state()
            table = state.tables.get("campaign_scenarios")
            if table is None or table.is_empty():
                return []
            return [row for row in table.to_dicts() if bool(row.get("enabled", True))]
        except (AttributeError, KeyError):
            return []

    def _selected_scenario(self) -> dict | None:
        return next(
            (row for row in self.campaign_scenarios if str(row.get("id") or "") == self.selected_scenario_id),
            None,
        )

    def _select_scenario(self, scenario_id: str) -> None:
        self.selected_scenario_id = scenario_id
        self.playable_countries = filter_selectable_countries(
            self.all_playable_countries,
            self._selected_scenario(),
        )
        eligible_ids = {str(value).strip().upper() for value in self.playable_countries["id"].to_list()}
        if str(self.selected_country_id or "").strip().upper() not in eligible_ids:
            self.selected_country_id = None

    def on_show_view(self):
        pass

    def on_draw(self):
        self.clear()
        
        self.imgui.new_frame()
        self.ui.setup_frame()
        
        # Draw 3D Globe
        ctx = self.window.ctx
        ctx.scissor = None
        ctx.viewport = (0, 0, self.window.width, self.window.height)
        ctx.enable_only(ctx.DEPTH_TEST, ctx.BLEND)

        self.renderer.draw()

        self._render_ui()
        self.imgui.render()

    def _render_ui(self):
        screen_w, screen_h = self.window.get_size()
        
        # Increase height to 650 to fit content without clipping
        if self.ui.begin_centered_panel("New Game", screen_w, screen_h, w=600, h=600):
            self.ui.draw_title("SELECT NATION")
            
            from imgui_bundle import imgui
            
            # Left Column: Country List
            # Height 400 allows enough space for list while leaving room for bottom buttons
            imgui.begin_child("CountryList", (250, 400), True)
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
                imgui.text_disabled(
                    "No eligible countries are available for this scenario."
                    if self._selected_scenario() is not None
                    else "No countries loaded."
                )
            imgui.end_child()
            
            imgui.same_line()
            
            # Right Column: Details
            imgui.begin_group()
            imgui.dummy((300, 0)) # Spacing
            imgui.text("Campaign scenario")
            imgui.begin_child("CampaignScenarioList", (300, 150), True)
            for scenario in self.campaign_scenarios:
                scenario_id = str(scenario.get("id") or "")
                title = str(scenario.get("title") or scenario_id)
                if imgui.selectable(
                    f"{title}##scenario-{scenario_id}",
                    self.selected_scenario_id == scenario_id,
                )[0]:
                    self._select_scenario(scenario_id)
            if not self.campaign_scenarios:
                imgui.text_disabled("No enabled scenarios are available.")
            imgui.end_child()
            selected_scenario = next(
                (row for row in self.campaign_scenarios if str(row.get("id")) == self.selected_scenario_id),
                None,
            )
            if selected_scenario is not None:
                preview = preview_campaign_scenario(selected_scenario)
                imgui.push_text_wrap_pos(0.0)
                imgui.text_wrapped(str(selected_scenario.get("description") or ""))
                imgui.pop_text_wrap_pos()
                imgui.text_disabled(f"Scope: {preview.scope}")
                imgui.text_disabled(f"Enabled rules: {', '.join(preview.enabled_rules) or 'none'}")
                if preview.max_duration_minutes > 0:
                    imgui.text_disabled(f"Campaign deadline: {preview.max_duration_minutes} minute(s) after start")
                for objective in preview.objectives[:3]:
                    imgui.bullet_text(f"{objective.title} — {objective.deadline}")
                if len(preview.objectives) > 3:
                    imgui.text_disabled(f"And {len(preview.objectives) - 3} more objective(s)")
                imgui.text_disabled(
                    "Sandbox continuation enabled" if selected_scenario.get("sandbox_allowed", True)
                    else "Scenario outcome ends this campaign"
                )
            imgui.separator()
            if self.selected_country_id:
                imgui.text_colored(GAMETHEME.colors.accent, f"Selected: {self.selected_country_id}")
                imgui.separator()
                imgui.dummy((0, 10))
                imgui.text_wrapped("Country Details:")
                imgui.text_wrapped("")
                imgui.text_wrapped("")
            else:
                imgui.text_disabled("Select a nation from the list.")
            imgui.end_group()
            
            # Bottom Controls Area
            imgui.dummy((0, 30)) # Vertical Spacer
            imgui.separator()
            imgui.dummy((0, 10)) # Vertical Spacer
            
            # Back Button
            if imgui.button("BACK", (100, 40)):
                self.renderer.clear_highlight()
                self.renderer.set_overlay_style(enabled=False, opacity=0.0)
                self.nav.show_main_menu(self.session, self.config)
            
            imgui.same_line()
            
            # Right Align "Start" Button
            avail_w = imgui.get_content_region_avail().x
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - 150)
            
            if self.selected_country_id and self.selected_scenario_id:
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
        map_width = self.session.map_data.width
        centroid = calculate_centroid(owned_regions, map_height, map_width)
        
        if centroid:
            world_x, world_y = centroid
            px = world_x
            py = map_height - world_y 
            
            self.cam_ctrl.look_at_pixel_coords(
                px, py, 
                self.session.map_data.width, 
                self.session.map_data.height
            )
            self._apply_country_selection_zoom()

    def _apply_country_selection_zoom(self):
        self.cam_ctrl.distance = float(
            max(
                self.cam_ctrl.min_distance,
                min(COUNTRY_SELECTION_FOCUS_DISTANCE, self.cam_ctrl.max_distance),
            )
        )

    def _start_game(self):
        if not self.selected_country_id or not self.selected_scenario_id: return
        
        from src.client.tasks.new_game_task import NewGameTask, NewGameContext

        def on_task_complete(ctx: NewGameContext):
            self.window.session = ctx.session
            self.nav.show_game_view(
                session=ctx.session,
                config=self.config,
                player_tag=ctx.player_tag,
                initial_pos=ctx.start_pos
            )
            return None

        task = NewGameTask(
            self.window,
            self.config,
            self.selected_country_id,
            self.selected_scenario_id,
        )
        self.nav.show_loading(task, on_success=on_task_complete)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_LEFT:
            self.cam_ctrl.drag(dx, dy)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.cam_ctrl.zoom_scroll(scroll_y)
