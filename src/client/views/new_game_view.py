import arcade
import polars as pl
from typing import TYPE_CHECKING, Optional

from src.client.views.base_view import BaseImGuiView
from src.client.services.network_client_service import NetworkClient
from src.client.services.campaign_selection import (
    filter_playable_countries,
    filter_selectable_countries,
    preview_campaign_scenario,
)
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.composer import UIComposer
from src.shared.config import GameConfig
from src.client.utils.coords_util import calculate_centroid
from src.client.utils.color_generator import generate_political_colors
from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.client.ui.components.shared.country_profile_window import CountryProfileWindow
from src.client.ui.components.shared.party_selection_window import PartySelectionWindow
from src.client.ui.components.shared.campaign_scenario_selection_window import CampaignScenarioSelectionWindow
from src.client.ui.components.shared.single_player_setup_window import SinglePlayerSetupWindow

if TYPE_CHECKING:
    from src.shared.protocols import SessionPort


COUNTRY_SELECTION_FOCUS_DISTANCE = 1.55


class NewGameView(BaseImGuiView):
    def __init__(self, session: "SessionPort", config: GameConfig):
        super().__init__()
        self.session = session 
        self.config = config
        # A navigation transition creates a fresh view, so it cannot reuse the main menu's composer.
        self.ui = UIComposer(GAMETHEME)
        
        self.net = NetworkClient(session)
        
        self.setup_stage = "scenario"
        self.scenario_selection_window = CampaignScenarioSelectionWindow()
        self.single_player_setup_window = SinglePlayerSetupWindow()
        self.selected_country_id: Optional[str] = None
        self.country_profile_window = CountryProfileWindow(self._select_country)
        self.selected_party_id = ""
        self.party_selection_window = PartySelectionWindow(self._select_party)
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
            return filter_playable_countries(df).sort("id")
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
        ctx.viewport = (0, 0, *self.window.get_size())
        ctx.enable_only(ctx.DEPTH_TEST, ctx.BLEND)

        self.renderer.draw()

        self._render_ui()
        self.imgui.render()

    def _render_ui(self):
        screen_w, screen_h = self.window.get_size()
        state = self.net.get_state()

        if self.setup_stage == "scenario":
            self.scenario_selection_window.render(
                screen_w,
                screen_h,
                self.campaign_scenarios,
                self.selected_scenario_id,
                self._select_scenario,
                self._enter_country_setup,
                self._return_to_main_menu,
            )
        else:
            country_options = [
                (
                    str(row["id"]).strip().upper(),
                    f"{str(row['id']).strip().upper()} - {resolve_country_name(state, str(row['id']).strip().upper())}",
                )
                for row in self.playable_countries.iter_rows(named=True)
            ]
            party_options = (
                PartySelectionWindow.party_options(state, self.selected_country_id)
                if self.selected_country_id else []
            )
            selected_party = next(
                (
                    row for row in party_options
                    if str(row.get("party_id") or "").strip() == self.selected_party_id
                ),
                None,
            )
            self.single_player_setup_window.render(
                screen_w,
                screen_h,
                country_options,
                self.selected_country_id,
                str(selected_party.get("display_name") or self.selected_party_id) if selected_party else "",
                bool(party_options),
                preview_campaign_scenario(self._selected_scenario()),
                self._select_country,
                lambda: self._open_country_profile(state),
                lambda: self._open_party_selection(state),
                self._start_game,
                self._return_to_scenario_selection,
            )

        self.country_profile_window.render(screen_w, screen_h)
        self.party_selection_window.render(screen_w, screen_h)

    def _enter_country_setup(self) -> None:
        self.setup_stage = "country"

    def _return_to_scenario_selection(self) -> None:
        self.setup_stage = "scenario"

    def _return_to_main_menu(self) -> None:
        self.renderer.clear_highlight()
        self.renderer.set_overlay_style(enabled=False, opacity=0.0)
        self.nav.show_main_menu(self.session, self.config)

    def _open_country_profile(self, state) -> None:
        eligible_ids = (
            self.playable_countries["id"].to_list()
            if "id" in self.playable_countries.columns
            else []
        )
        self.country_profile_window.show(state, eligible_ids)

    def _open_party_selection(self, state) -> None:
        if not self.selected_country_id:
            return
        self.country_profile_window.close()
        self.party_selection_window.show(
            state,
            self.selected_country_id,
            self.selected_party_id,
        )

    def _select_country(self, country_id: str) -> None:
        self.selected_country_id = str(country_id or "").strip().upper() or None
        if self.selected_country_id is None:
            self.selected_party_id = ""
            self.renderer.clear_highlight()
            return
        self.selected_party_id = PartySelectionWindow.default_party_id(
            self.net.get_state(), self.selected_country_id
        )
        self._focus_camera_on_country(self.selected_country_id)
        self._highlight_country(self.selected_country_id)

    def _select_party(self, party_id: str) -> None:
        self.selected_party_id = str(party_id or "").strip()

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
            self.selected_party_id,
        )
        self.nav.show_loading(task, on_success=on_task_complete)

    def on_game_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if buttons == arcade.MOUSE_BUTTON_LEFT:
            self.cam_ctrl.drag(dx, dy)

    def on_game_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self.cam_ctrl.zoom_scroll(scroll_y)
