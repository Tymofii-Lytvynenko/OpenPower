from imgui_bundle import imgui
import polars as pl
from typing import Optional, Callable, List
from src.client.services.network_client_service import NetworkClient

class EditorLayout:
    """
    Manages the ImGui layout for the Editor.
    
    Responsibility:
        - Draws the Menu Bar, Inspector, and Region List.
        - Stores the *State of the UI* (which window is open, which mode is selected).
        - Does NOT handle game logic (rendering the map, moving camera).
    """
    
    def __init__(self, net_client: NetworkClient):
        self.net = net_client
        
        # --- Events ---
        # The View subscribes to this to move the camera when a user clicks a region in the list
        self.on_focus_request: Optional[Callable[[float, float], None]] = None 
        
        # --- UI State (Windows) ---
        self.show_region_list = False
        
        # --- Map Visualization Settings ---
        # These control what the MapRenderer draws.
        # Format: "UI Label": "Renderer internal mode string"
        self.layer_options = {
            "Physical (Terrain)": "terrain",
            "Political (Countries)": "political",
            "Debug (Region IDs)": "debug_regions"
        }
        self.layer_keys = list(self.layer_options.keys())
        self.current_layer_label = "Physical (Terrain)" # Default

    def get_current_render_mode(self) -> str:
        """Returns the internal mode string for the MapRenderer."""
        return self.layer_options[self.current_layer_label]

    def render(self, selected_region_int_id: Optional[int], fps: float):
        """
        Main entry point to draw all editor UI panels.
        Called once per frame by EditorView.
        """
        self._render_menu()
        self._render_inspector(selected_region_int_id)
        
        if self.show_region_list:
            self._render_region_list()
        
        # Debug / Info Overlay
        self._render_info_overlay(fps)

    def _render_menu(self):
        """Draws the main menu bar at the top of the screen."""
        if imgui.begin_main_menu_bar():
            
            # --- File Menu ---
            if imgui.begin_menu("File"):
                if imgui.menu_item("Save Map Data", "Ctrl+S")[0]:
                    self.net.request_save()
                imgui.end_menu()
                
            # --- View Menu ---
            if imgui.begin_menu("View"):
                # 1. Map Layer Dropdown
                imgui.text("Map Layer:")
                if imgui.begin_combo("##layer_combo", self.current_layer_label):
                    for label in self.layer_keys:
                        is_selected = (label == self.current_layer_label)
                        if imgui.selectable(label, is_selected)[0]:
                            self.current_layer_label = label
                        
                        if is_selected:
                            imgui.set_item_default_focus()
                    imgui.end_combo()
                
                imgui.separator()

                # 2. Window Toggles
                _, self.show_region_list = imgui.menu_item("Show Region List", "", self.show_region_list)
                
                imgui.end_menu()
                
            imgui.end_main_menu_bar()

    def _render_info_overlay(self, fps: float):
        """
        Transparent overlay in the top-left corner showing stats.
        """
        # Position 10px from left, 50px from top (below menu bar)
        imgui.set_next_window_pos((10, 50), imgui.Cond_.first_use_ever)
        
        flags = (imgui.WindowFlags_.always_auto_resize | 
                 imgui.WindowFlags_.no_decoration | 
                 imgui.WindowFlags_.no_nav)
                 
        # Make background semi-transparent black
        imgui.push_style_color(imgui.Col_.window_bg, (0, 0, 0, 0.5))
        
        if imgui.begin("Overlay", flags=flags):
            imgui.text_colored((0, 1, 0, 1), f"FPS: {fps:.0f}")
            imgui.text(f"Layer: {self.current_layer_label}")
            imgui.separator()
            imgui.text_disabled("Right Click: Pan Map")
            imgui.text_disabled("Scroll: Zoom")
            imgui.text_disabled("Left Click: Select Region")
        imgui.end()
        
        imgui.pop_style_color()

    def _render_inspector(self, region_int_id: Optional[int]):
        """
        Side panel showing details of the currently selected region.
        """
        imgui.begin("Region Inspector")
        
        if region_int_id is not None:
            # Fetch data lazily from the authoritative Game State
            state = self.net.get_state()
            regions = state.get_table("regions")
            
            try:
                # Find the row for this ID
                # Polars optimization: filter and take 1
                row = regions.filter(pl.col("id") == region_int_id).row(0, named=True)
                
                # --- HEADER ---
                imgui.text_colored((0, 1, 1, 1), f"REGION: {row.get('name', 'Unknown')}")
                imgui.separator()
                
                # --- TECHNICAL ---
                if imgui.tree_node("Technical Data"):
                    imgui.text(f"ID: {region_int_id}")
                    imgui.text(f"Color Hex: {row.get('hex', 'N/A')}")
                    imgui.text(f"Center: ({row.get('center_x', 0)}, {row.get('center_y', 0)})")
                    imgui.tree_pop()
                
                imgui.dummy((0, 10))
                
                # --- GEOGRAPHY ---
                imgui.text("Geography:")
                imgui.bullet_text(f"Type:  {row.get('type', 'Plains')}")
                imgui.bullet_text(f"Biome: {row.get('biome', 'Temperate')}")
                
                imgui.dummy((0, 10))

                # --- DEMOGRAPHICS (New) ---
                imgui.text("Demographics:")
                
                # safely get values, defaulting to 0 if column missing
                p14 = row.get('pop_14', 0)
                p15 = row.get('pop_15_64', 0)
                p65 = row.get('pop_65', 0)
                total_pop = p14 + p15 + p65
                
                imgui.bullet_text(f"Total: {total_pop:,}")
                
                if total_pop > 0:
                    imgui.indent()
                    imgui.text_disabled(f"0-14:  {p14:,} ({p14/total_pop:.1%})")
                    imgui.text_disabled(f"15-64: {p15:,} ({p15/total_pop:.1%})")
                    imgui.text_disabled(f"65+:   {p65:,} ({p65/total_pop:.1%})")
                    imgui.unindent()
                
                imgui.dummy((0, 10))

                # --- POLITICAL & OWNER (New) ---
                imgui.text("Political Context:")
                owner_tag = row.get('owner', 'None')
                
                if owner_tag and owner_tag != "None":
                    imgui.bullet_text(f"Owner: {owner_tag}")
                    
                    # Look up Country Data
                    try:
                        countries = state.get_table("countries")
                        c_row = countries.filter(pl.col("id") == owner_tag)
                        
                        if not c_row.is_empty():
                            c_data = c_row.row(0, named=True)
                            
                            imgui.indent()
                            imgui.separator()
                            
                            # Stability (Green if high, Red if low)
                            stab = c_data.get("gvt_stability", 50)
                            col = (0, 1, 0, 1) if stab >= 50 else (1, 0.2, 0.2, 1)
                            imgui.text("Stability: ")
                            imgui.same_line()
                            imgui.text_colored(col, f"{stab}%")
                            
                            imgui.text(f"Approval:  {c_data.get('gvt_approval', 0)}%")
                            imgui.text(f"Treasury:  ${c_data.get('money_balance', 0):,}")
                            imgui.text(f"Tax Rate:  {c_data.get('global_tax_perc', 0)}%")
                            
                            imgui.separator()
                            imgui.unindent()
                        else:
                            imgui.indent()
                            imgui.text_colored((1, 0.5, 0, 1), "[Country data missing]")
                            imgui.unindent()
                            
                    except Exception as e:
                        # Fallback if countries table isn't loaded yet
                        imgui.text_disabled(f"[Data lookup failed: {e}]")
                else:
                    imgui.bullet_text("Owner: Unclaimed / Wilderness")

                imgui.dummy((0, 10))
                
                # --- CORE STATUS ---
                is_core = row.get('is_core', False)
                if is_core:
                    imgui.text_colored((0, 1, 0, 1), "[CORE REGION]")
                else:
                    imgui.text_disabled("[Non-Core / Colony]")
                
            except Exception as e:
                imgui.text_colored((1, 0, 0, 1), "Region Data Error")
                if imgui.is_item_hovered():
                    imgui.set_tooltip(str(e))
        else:
            imgui.text_disabled("Select a region on the map\nto view details.")
            
        imgui.end()

    def _render_region_list(self):
        """
        A scrollable list of all regions. Clicking one focuses the camera.
        """
        # Set a default size for the window
        imgui.set_next_window_size((300, 500), imgui.Cond_.first_use_ever)
        
        is_open = imgui.begin("All Regions", True)[1]
        self.show_region_list = is_open
        
        if is_open:
            state = self.net.get_state()
            regions = state.get_table("regions")
            
            # Optimization: Don't render 10,000 items at once.
            # In a real app, use ImGui ListClipper. Here we just limit head.
            limit = 500
            imgui.text_disabled(f"Displaying top {limit} regions...")
            imgui.separator()
            
            # Iterate rows
            for row in regions.head(limit).iter_rows(named=True):
                r_id = row['id']
                name = row.get('name', f"Region {r_id}")
                
                # Selectable Item
                if imgui.selectable(f"{r_id}: {name}")[0]:
                    # Fire event to move camera
                    if self.on_focus_request:
                        cx = row.get('center_x', 0)
                        cy = row.get('center_y', 0)
                        self.on_focus_request(cx, cy)
                        
        imgui.end()