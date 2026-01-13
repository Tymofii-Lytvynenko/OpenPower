import arcade
import polars as pl
from typing import TYPE_CHECKING, Optional

from src.client.services.imgui_service import ImGuiService
from src.client.services.network_client_service import NetworkClient
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.shared.config import GameConfig
from src.client.views.game_view import GameView
from src.client.utils.coords_util import calculate_centroid

if TYPE_CHECKING:
    from src.server.session import GameSession

class NewGameView(arcade.View):
    """
    Screen to select a country and start the campaign.
    """
    def __init__(self, session: "GameSession", config: GameConfig):
        super().__init__()
        self.session = session # Kept only to pass to GameView later
        self.config = config
        
        # Use NetworkClient for reading data (Passive Observer)
        self.net = NetworkClient(session)
        
        self.imgui = ImGuiService(self.window)
        self.ui = UIComposer(GAMETHEME)
        
        self.selected_country_id: Optional[str] = None
        self.playable_countries = self._fetch_playable_countries()

    def _fetch_playable_countries(self) -> pl.DataFrame:
        """Helper to get list of countries from the network state."""
        try:
            # CORRECT: Going through the network client abstraction
            state = self.net.get_state()
            df = state.get_table("countries")
            return df.filter(pl.col("is_playable") == True).sort("id")
        except KeyError:
            print("[NewGameView] 'countries' table not found in state.")
            return pl.DataFrame()

    def on_show_view(self):
        self.window.background_color = arcade.color.BLACK_OLIVE

    def on_resize(self, width: int, height: int):
        self.imgui.resize(width, height)

    def on_draw(self):
        self.clear()
        self.imgui.new_frame(1.0 / 60.0)
        self.ui.setup_frame()
        self._render_ui()
        self.imgui.render()

    def _render_ui(self):
        screen_w, screen_h = self.window.get_size()
        
        if self.ui.begin_centered_panel("New Game", screen_w, screen_h, w=600, h=500):
            self.ui.draw_title("SELECT NATION")
            
            from imgui_bundle import imgui
            
            # --- Country List (Left Side) ---
            imgui.begin_child("CountryList", (250, 350), True)
            
            if not self.playable_countries.is_empty():
                for row in self.playable_countries.iter_rows(named=True):
                    c_id = row['id']
                    label = f"{c_id}"
                    
                    is_selected = (self.selected_country_id == c_id)
                    if imgui.selectable(label, is_selected)[0]:
                        self.selected_country_id = c_id
            else:
                imgui.text_disabled("No countries loaded.")
                
            imgui.end_child()
            
            imgui.same_line()
            
            # --- Details Panel (Right Side) ---
            imgui.begin_group()
            imgui.dummy((300, 0))
            
            if self.selected_country_id:
                imgui.text_colored(GAMETHEME.col_active_accent, f"Selected: {self.selected_country_id}")
                imgui.separator()
                
                # Fetch details using Polars through the state snapshot
                state = self.net.get_state()
                try:
                    df = state.get_table("countries")
                    # In a real scenario, efficient filtering would happen here
                    # For UI rendering, simple checks are okay
                    balance = 0
                    row = df.filter(pl.col("id") == self.selected_country_id)
                    if not row.is_empty():
                         balance = row["money_balance"][0]
                    imgui.text(f"Starting Balance: ${balance:,}")
                except Exception:
                    pass
                    
                imgui.text_wrapped("Description placeholder.")
            else:
                imgui.text_disabled("Select a nation from the list.")
                
            imgui.end_group()
            
            imgui.dummy((0, 20))
            imgui.separator()
            imgui.dummy((0, 10))
            
            # --- Bottom Buttons ---
            if imgui.button("BACK", (100, 40)):
                # Avoid circular import at module level
                from src.client.views.main_menu_view import MainMenuView
                self.window.show_view(MainMenuView(self.session, self.config))
                
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

    def _start_game(self):
        if not self.selected_country_id:
            return

        print(f"[NewGameView] Starting game as {self.selected_country_id}")
        
        state = self.net.get_state()
        start_pos = None

        try:
            if "regions" in state.tables:
                df = state.tables["regions"]
                
                # Filter for the country's regions
                owned_regions = df.filter(pl.col("owner") == self.selected_country_id)
                
                # --- NEW UTILITY USAGE ---
                # Calculates the center AND handles the Y-flip automatically
                map_height = self.session.map_data.height
                start_pos = calculate_centroid(owned_regions, map_height)
                
                if start_pos:
                    print(f"[NewGameView] Centered on {self.selected_country_id} at {start_pos}")
                    
        except Exception as e:
            print(f"[NewGameView] Error calculating center: {e}")

        game_view = GameView(
            self.session, 
            self.config, 
            self.selected_country_id, 
            initial_pos=start_pos
        )
        self.window.show_view(game_view)

    # --- Input Passthrough ---
    def on_mouse_press(self, x, y, button, modifiers): self.imgui.on_mouse_press(x, y, button, modifiers)
    def on_mouse_release(self, x, y, button, modifiers): self.imgui.on_mouse_release(x, y, button, modifiers)
    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers): self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers)
    def on_mouse_motion(self, x, y, dx, dy): self.imgui.on_mouse_motion(x, y, dx, dy)