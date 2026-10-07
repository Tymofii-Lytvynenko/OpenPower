import arcade
import polars as pl
from typing import Optional, Callable, Dict
from enum import Enum, auto

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.services.network_client_service import NetworkClient
from src.client.utils.coords_util import calculate_centroid

# Strategy Imports
from src.client.visualization.map_modes.base_map_mode import BaseMapMode
from src.client.visualization.map_modes.political_mode import PoliticalMapMode
from src.client.visualization.map_modes.gradient_mode import GradientMapMode
from src.client.visualization.map_modes.empire_mode import EmpireMapMode


class SelectionMode(Enum):
    REGION = auto()
    COUNTRY = auto()


class ViewportController:
    """
    The Brains of the Map.
    Handles Input -> Camera, Input -> Selection, and State -> Map Modes.
    """

    def __init__(self,
                 cam_ctrl: CameraController,
                 world_camera: arcade.Camera2D,
                 map_renderer: MapRenderer,
                 net_client: NetworkClient,
                 on_selection_change: Callable[[Optional[int]], None]):

        self.cam = cam_ctrl
        self.world_cam = world_camera
        self.renderer = map_renderer
        self.net = net_client
        self.on_selection_change = on_selection_change

        self.selection_mode = SelectionMode.COUNTRY
        self.selected_country_tag: Optional[str] = None
        self.show_all_units: bool = False
        self.show_engagement_zones: bool = True
        self._map_layer_cache_key: tuple | None = None

        # --- MAP MODES (Composition) ---
        self.map_modes: Dict[str, BaseMapMode] = {
            "political": PoliticalMapMode(),
            "empire": EmpireMapMode(),
            "gdp_per_capita": GradientMapMode(
                mode_name="GDP (Per Capita)",
                column_name="gdp_per_capita",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "gdp_total": GradientMapMode(
                mode_name="GDP (Total)",
                column_name="gdp",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "gvt_stability": GradientMapMode(
                mode_name="Government Stability",
                column_name="gvt_stability",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "war_exhaustion": GradientMapMode(
                mode_name="War Exhaustion",
                column_name="war_exhaustion",
                fallback_to_country=True,
                steps=10,
            ),
            "aggressive_expansion": GradientMapMode(
                mode_name="Expansion Threat",
                column_name="aggressive_expansion",
                fallback_to_country=True,
                steps=10,
            ),
            "coalition_memberships": GradientMapMode(
                mode_name="Defensive Coalition Memberships",
                column_name="coalition_membership_count",
                fallback_to_country=True,
                steps=5,
            ),
            "active_wars": GradientMapMode(
                mode_name="Active Wars",
                column_name="active_war_count",
                fallback_to_country=True,
                steps=5,
            ),
            "money_reserves": GradientMapMode(
                mode_name="Money Reserves",
                column_name="money_reserves",
                fallback_to_country=True,
                use_percentile=True,
                steps=10
            ),
            "human_dev": GradientMapMode(
                mode_name="Human Development",
                column_name="human_dev",
                fallback_to_country=True,
                use_percentile=True,
                steps=10,
            ),
            "poverty_rate": GradientMapMode(
                mode_name="Poverty Rate",
                column_name="poverty_rate",
                fallback_to_country=True,
                use_percentile=True,
                steps=10,
            ),
            "military_count": GradientMapMode(
                mode_name="Military Strength",
                column_name="military_count",
                fallback_to_country=True,
                use_percentile=True,
                steps=10,
            ),
            "corruption_index": GradientMapMode(
                mode_name="Corruption Index",
                column_name="corruption_index",
                fallback_to_country=True,
                use_percentile=True,
                steps=10,
            ),
            "life_expectancy": GradientMapMode(
                mode_name="Life Expectancy",
                column_name="life_expectancy",
                fallback_to_country=True,
                use_percentile=True,
                steps=10,
            ),
        }
        self.current_mode_key = "political"

    def set_selection_mode(self, mode: SelectionMode):
        self.selection_mode = mode
        self.renderer.clear_highlight()
        self.on_selection_change(None)

    def set_map_mode(self, mode_key: str):
        """
        Switches the visual map mode.
        Handles 'terrain' as a special case to disable overlays.
        """
        # 1. Special Case: Terrain Mode (No Overlay)
        if mode_key == "terrain":
            self.renderer.set_overlay_style(enabled=False, opacity=0.0)
            self.current_mode_key = "terrain"
            return

        # 2. Standard Data Modes
        if mode_key in self.map_modes:
            self.current_mode_key = mode_key
            self._sync_empire_focus()
            # Ensure overlay is visible if we are switching from terrain
            self.renderer.set_overlay_style(enabled=True, opacity=0.90)
            self.refresh_map_layer()

    # --- VISUALIZATION HELPERS ---

    def refresh_map_layer(self, state=None):
        if state is None:
            state = self.net.get_state()
        
        # Safety check if we are in 'terrain' mode or invalid key
        if self.current_mode_key not in self.map_modes:
            self._map_layer_cache_key = self._map_layer_state_key(state)
            return

        active_mode = self.map_modes[self.current_mode_key]
        color_map = active_mode.calculate_colors(state)

        # We rely on set_map_mode to have set the enabled/opacity state correctly,
        # but we re-assert it here just in case.
        self.renderer.set_overlay_style(
            enabled=active_mode.overlay_enabled,
            opacity=active_mode.opacity
        )
        self.renderer.update_overlay(color_map)
        self._map_layer_cache_key = self._map_layer_state_key(state)

    def refresh_map_layer_if_stale(self, state=None) -> bool:
        """Refresh the map overlay only after relevant state has changed."""
        if state is None:
            state = self.net.get_state()

        cache_key = self._map_layer_state_key(state)
        if cache_key == self._map_layer_cache_key:
            return False

        self.refresh_map_layer(state)
        return True

    def _map_layer_state_key(self, state) -> tuple:
        revisions = getattr(state, "table_revisions", {})
        mode = self.current_mode_key
        selected_country = self.selected_country_tag if mode == "empire" else None
        if mode == "political":
            source_revisions = (int(revisions.get("regions", 0)),)
        elif mode == "empire":
            source_revisions = (
                int(revisions.get("regions", 0)),
                int(revisions.get("countries_treaties", 0)),
                int(revisions.get("countries_wars", 0)),
                int(revisions.get("annexation_claims", 0)),
            )
        else:
            source_revisions = (
                int(revisions.get("regions", 0)),
                int(revisions.get("countries", 0)),
            )

        return (mode, selected_country, *source_revisions)

    def refresh_political_layer(self):
        self.set_map_mode("political")

    def focus_on_region(self, region_id: int):
        """Finds a region and rotates the globe to face it."""
        state = self.net.get_state()
        if "regions" not in state.tables: return

        df = state.tables["regions"]
        row = df.filter(pl.col("id") == region_id)

        if not row.is_empty():
            cx = row["center_x"][0]
            cy = row["center_y"][0]

            if self.renderer.projection_mode == "planar":
                self.renderer.focus_planar_pixel(cx, cy)
            else:
                self.cam.look_at_pixel_coords(
                    cx,
                    cy,
                    self.renderer.width,
                    self.renderer.height,
                )
            
            # Force selection
            self.select_region_by_id(region_id)

    # --- INPUT HANDLING ---
    
    def on_mouse_press(self, x: float, y: float, button: int):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self._handle_click_selection(x, y)

    def on_mouse_release(self, x: float, y: float, button: int):
        pass

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int):
        if buttons & arcade.MOUSE_BUTTON_RIGHT:
            if self.renderer.projection_mode == "planar":
                self.renderer.pan_planar(dx, dy)
            else:
                self.cam.drag(dx, dy)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int):
        if self.renderer.projection_mode == "planar":
            self.renderer.zoom_planar_at(x, y, scroll_y)
        else:
            self.cam.zoom_scroll(scroll_y)

    # --- SELECTION LOGIC ---
    def focus_on_country(self, country_tag: str | None) -> Optional[int]:
        """Focus and select a country exactly as a country-mode map click would."""
        normalized_tag = str(country_tag).strip() if country_tag else ""
        if not normalized_tag:
            return None

        state = self.net.get_state()
        regions = getattr(state, "tables", {}).get("regions")
        if regions is None or regions.is_empty():
            return None

        authority_col = "controller" if "controller" in regions.columns else "owner"
        if authority_col not in regions.columns or "id" not in regions.columns:
            return None

        country_regions = regions.filter(pl.col(authority_col) == normalized_tag)
        if country_regions.is_empty():
            return None

        region_ids = [
            int(region_id)
            for region_id in country_regions["id"].drop_nulls().to_list()
            if int(region_id) > 0
        ]
        if not region_ids:
            return None

        representative_region_id = self._representative_region_id(country_regions, region_ids[0])
        centroid = None
        if {"center_x", "center_y"}.issubset(set(country_regions.columns)):
            centroid = calculate_centroid(
                country_regions,
                self.renderer.height,
                self.renderer.width,
            )
        if centroid is not None:
            world_x, world_y = centroid
            if self.renderer.projection_mode == "planar":
                self.renderer.focus_planar_pixel(world_x, self.renderer.height - world_y)
            else:
                self.cam.look_at_pixel_coords(
                    world_x,
                    self.renderer.height - world_y,
                    self.renderer.width,
                    self.renderer.height,
                )

        self._commit_selection(
            representative_region_id,
            normalized_tag,
            region_ids,
        )
        return representative_region_id

    def select_country_viewpoint(self, country_tag: str | None) -> None:
        """Compatibility wrapper for callers that do not need the focused region."""
        self.focus_on_country(country_tag)

    def _representative_region_id(self, country_regions, fallback_region_id: int) -> int:
        if "area_km2" not in country_regions.columns:
            return fallback_region_id
        ranked_regions = country_regions.sort("area_km2", descending=True, nulls_last=True)
        if ranked_regions.is_empty():
            return fallback_region_id
        return int(ranked_regions["id"][0])

    def select_region_by_id(self, region_id: int):
        if region_id is None or region_id <= 0:
            self.renderer.clear_highlight()
            self.selected_country_tag = None
            self._sync_empire_focus()
            if self.current_mode_key == "empire":
                self.refresh_map_layer()
            self.on_selection_change(None)
            return
        self._apply_selection_logic(region_id)

    def _handle_click_selection(self, screen_x: float, screen_y: float):
        region_id = self.renderer.get_region_id_at_screen_pos(screen_x, screen_y)
        self.select_region_by_id(region_id)

    def _apply_selection_logic(self, region_id: int):
        highlight_ids = [region_id]
        selected_owner = None

        if self.selection_mode == SelectionMode.COUNTRY:
            state = self.net.get_state()
            if "regions" in state.tables:
                df = state.tables["regions"]
                authority_col = "controller" if "controller" in df.columns else "owner"
                authority_rows = df.filter(pl.col("id") == region_id)
                if not authority_rows.is_empty():
                    authority = authority_rows[authority_col][0]
                    if authority and authority != "None":
                        selected_owner = authority
                        highlight_ids = df.filter(pl.col(authority_col) == authority)["id"].to_list()

        self._commit_selection(region_id, selected_owner, highlight_ids)

    def _commit_selection(
        self,
        region_id: int,
        selected_country_tag: Optional[str],
        highlight_ids: list[int],
    ) -> None:
        self.selected_country_tag = selected_country_tag
        self._sync_empire_focus()

        if self.current_mode_key == "empire":
            self.renderer.clear_highlight()
            self.refresh_map_layer()
        else:
            self.renderer.set_highlight(highlight_ids)
        self.on_selection_change(region_id)

    def get_region_at(self, screen_x: float, screen_y: float) -> Optional[int]:
        try:
            region_id = self.renderer.get_region_id_at_screen_pos(screen_x, screen_y)
            return region_id if region_id > 0 else None
        except Exception:
            return None

    def _sync_empire_focus(self):
        mode = self.map_modes.get("empire")
        if hasattr(mode, "set_selected_country"):
            mode.set_selected_country(self.selected_country_tag)
