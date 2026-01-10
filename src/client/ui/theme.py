from dataclasses import dataclass
from imgui_bundle import imgui

@dataclass
class UITheme:
    """
    Defines the visual properties of the UI.
    Restored to the original Cyan/Dark Blue "Cyber" aesthetic.
    """
    # --- Text Colors ---
    text_main: tuple = (0.0, 1.0, 1.0, 1.0)        # Cyan
    text_dim: tuple = (0.0, 0.7, 0.7, 1.0)
    
    # --- Window & Border ---
    window_bg: tuple = (0.05, 0.05, 0.1, 0.85)     # Dark Blue Semi-transparent
    border: tuple = (0.0, 1.0, 1.0, 0.5)           # Thin Cyan Border
    
    # Adapted Header BG (Dark Cyan to match the theme)
    header_bg: tuple = (0.0, 0.2, 0.3, 0.8)        
    
    # --- Standard Buttons ---
    button_normal: tuple = (0.0, 0.2, 0.3, 0.6)
    button_hover: tuple = (0.0, 0.4, 0.6, 0.8)
    button_active: tuple = (0.0, 0.6, 0.8, 1.0)
    
    # --- Game Pillar Colors (Required for Toggles/Meters) ---
    # We keep these distinct so the toggle buttons (Pol/Mil/Eco) still stand out
    col_politics: tuple = (0.9, 0.8, 0.2, 1.0)     # Gold
    col_military: tuple = (0.9, 0.2, 0.2, 1.0)     # Red
    col_economy: tuple = (0.2, 0.9, 0.2, 1.0)      # Green

    # Geometry
    rounding: float = 0.0  # Sharp corners (Original style)
    padding: tuple = (15.0, 10.0)
    
    def apply_global_styles(self):
        style = imgui.get_style()
        style.window_rounding = self.rounding
        style.frame_rounding = self.rounding
        style.popup_rounding = self.rounding
        style.scrollbar_rounding = self.rounding
        
        # Colors
        style.set_color_(imgui.Col_.text, self.text_main)
        style.set_color_(imgui.Col_.window_bg, self.window_bg)
        style.set_color_(imgui.Col_.border, self.border)
        style.set_color_(imgui.Col_.button, self.button_normal)
        style.set_color_(imgui.Col_.button_hovered, self.button_hover)
        style.set_color_(imgui.Col_.button_active, self.button_active)
        
        # Headers (Used in tables and collapsing headers)
        style.set_color_(imgui.Col_.header, self.button_normal)
        style.set_color_(imgui.Col_.header_hovered, self.button_hover)
        style.set_color_(imgui.Col_.header_active, self.button_active)

# Pre-defined Theme Instance
GAMETHEME = UITheme()