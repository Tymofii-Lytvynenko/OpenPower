import arcade
import polars as pl
from src.client.services.imgui_service import ImGuiService
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME
from src.shared.config import GameConfig
from src.server.session import GameSession
from src.client.views.game_view import GameView

class NewGameView(arcade.View):
    """
    Screen to select a country and start the campaign.
    """
    def __init__(self, session: GameSession, config: GameConfig):
        super().__init__()
        self.session = session
        self.config = config
        
        self.imgui = ImGuiService(self.window)
        self.ui = UIComposer(GAMETHEME)
        
        self.selected_country_id: str | None = None
        self.playable_countries = self._fetch_playable_countries()

    def _fetch_playable_countries(self) -> pl.DataFrame:
        """Helper to get list of countries from the loaded session state."""
        try:
            df = self.session.state.get_table("countries")
            # Sort by ID for now
            return df.sort("id")
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
        
        # Use a larger panel
        if self.ui.begin_centered_panel("New Game", screen_w, screen_h, width=600, height=500):
            self.ui.draw_title("SELECT NATION")
            
            from imgui_bundle import imgui
            
            # --- Country List (Left Side) ---
            imgui.begin_child("CountryList", (250, 350), True)
            
            if not self.playable_countries.is_empty():
                for row in self.playable_countries.iter_rows(named=True):
                    c_id = row['id']
                    # Use 'flag' column if it exists later
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
            imgui.dummy((300, 0)) # Fixed width for details
            
            if self.selected_country_id:
                imgui.text_colored((0, 1, 1, 1), f"Selected: {self.selected_country_id}")
                imgui.separator()
                imgui.text_wrapped("Description placeholder. Economy stats, military strength, and starting conditions will appear here.")
            else:
                imgui.text_disabled("Select a nation from the list.")
                
            imgui.end_group()
            
            imgui.dummy((0, 20))
            imgui.separator()
            imgui.dummy((0, 10))
            
            # --- Bottom Buttons ---
            if imgui.button("BACK", (100, 40)):
                # Return to Main Menu (Circular import avoidance: Instantiate locally or pass class)
                from src.client.views.main_menu_view import MainMenuView
                self.window.show_view(MainMenuView(self.session, self.config))
                
            imgui.same_line()
            
            # Right-align Start button
            avail_w = imgui.get_content_region_avail().x
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + avail_w - 150)
            
            # Start Game
            if self.selected_country_id:
                if imgui.button("START CAMPAIGN", (150, 40)):
                    self._start_game()
            else:
                imgui.begin_disabled()
                imgui.button("START CAMPAIGN", (150, 40))
                imgui.end_disabled()

            self.ui.end_panel()

    def _start_game(self):
        """Launch the GameView with the selected country."""
        print(f"[NewGameView] Starting game as {self.selected_country_id}")
        
        # TODO: Here we could set the 'local_player' in the session if we wanted validation
        
        game_view = GameView(self.session, self.config, self.selected_country_id)
        self.window.show_view(game_view)

    # --- Input Passthrough ---
    def on_mouse_press(self, x, y, button, modifiers): self.imgui.on_mouse_press(x, y, button, modifiers)
    def on_mouse_release(self, x, y, button, modifiers): self.imgui.on_mouse_release(x, y, button, modifiers)
    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers): self.imgui.on_mouse_drag(x, y, dx, dy, buttons, modifiers)
    def on_mouse_motion(self, x, y, dx, dy): self.imgui.on_mouse_motion(x, y, dx, dy)