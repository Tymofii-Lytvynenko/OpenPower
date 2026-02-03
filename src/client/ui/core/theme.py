from dataclasses import dataclass, field
from imgui_bundle import imgui

def with_alpha(color: tuple, alpha: float) -> tuple:
    """Helper: Returns a new color tuple with modified alpha."""
    return (color[0], color[1], color[2], alpha)

@dataclass
class UIColors:
    """
    Complete Single Source of Truth.
    Combines Modern Glass UI (Neutrals) with Game Semantics (Vibrant).
    """
    # --- 1. Base Text ---
    text_main: tuple     = (1.00, 1.00, 1.00, 1.00)
    text_dim: tuple      = (0.60, 0.60, 0.60, 1.00)

    # --- 2. Backgrounds (Glass/Modern) ---
    # Dark charcoal, high alpha for readability, but still semi-transparent
    bg_window: tuple     = (0.08, 0.09, 0.10, 0.85) 
    bg_child: tuple      = (0.00, 0.00, 0.00, 0.00) # Transparent (letting window bg show)
    bg_popup: tuple      = (0.05, 0.05, 0.05, 0.85)
    bg_input: tuple      = (0.16, 0.18, 0.21, 0.60) # Dark neutral for inputs

    # --- 3. Main Accent (Used sparingly) ---
    # Desaturated Steel Blue - Professional, not neon.
    accent: tuple        = (0.26, 0.59, 0.85, 1.00)

    # --- 4. Game Pillars (RESTORED) ---
    # Adjusted slightly to pop against the dark transparent background
    politics: tuple      = (1.00, 0.78, 0.25, 1.00) # Gold
    military: tuple      = (1.00, 0.40, 0.40, 1.00) # Soft Red
    economy: tuple       = (0.30, 0.95, 0.60, 1.00) # Emerald Green
    demographics: tuple  = (0.75, 0.50, 1.00, 1.00) # Lavender

    # --- 5. Status Indicators (RESTORED) ---
    positive: tuple      = (0.30, 0.95, 0.60, 1.00)
    negative: tuple      = (1.00, 0.40, 0.40, 1.00)
    error: tuple         = (0.80, 0.20, 0.20, 1.00)
    warning: tuple       = (0.90, 0.70, 0.00, 1.00)
    info: tuple          = (0.26, 0.59, 0.85, 1.00) # Matches Accent

    # --- 6. Interaction States (Neutral logic) ---
    # We use these for button clicks instead of blue to keep it clean.
    hover_neutral: tuple = (0.25, 0.27, 0.30, 0.80)
    pressed_neutral: tuple = (0.12, 0.14, 0.16, 1.00) 
    interaction_active: tuple = (0.26, 0.59, 0.85, 0.5) # Fallback alias for accent

    # --- 7. Special Overrides ---
    drag_drop: tuple     = (0.90, 0.90, 0.00, 0.50) 
    plot_histogram: tuple= (0.90, 0.70, 0.00, 1.00)

@dataclass
class UITheme:
    """
    Applies the UIColors to the ImGui Style engine.
    """
    colors: UIColors = field(default_factory=UIColors)
    rounding: float = 0.0

    def apply(self):
        style = imgui.get_style()
        c = self.colors
        
        # Helper
        def set_c(idx, color): style.set_color_(idx, color)

        # 1. Geometry Defaults
        style.window_padding    = (14, 14)
        style.frame_padding     = (8, 5)
        style.item_spacing      = (10, 8)
        style.window_rounding   = self.rounding
        style.frame_rounding    = self.rounding
        style.popup_rounding    = self.rounding
        style.grab_rounding     = self.rounding
        style.tab_rounding      = self.rounding
        
        style.window_border_size = 0.0
        style.frame_border_size  = 0.0

        # 2. Base Colors
        set_c(imgui.Col_.text,           c.text_main)
        set_c(imgui.Col_.text_disabled,  c.text_dim)
        set_c(imgui.Col_.window_bg,      c.bg_window)
        set_c(imgui.Col_.child_bg,       c.bg_child)
        set_c(imgui.Col_.popup_bg,       c.bg_popup)
        set_c(imgui.Col_.border,         (0.3, 0.3, 0.3, 0.2))

        # 3. Inputs & Buttons (Neutral Style)
        # Normal
        set_c(imgui.Col_.frame_bg,        c.bg_input)
        set_c(imgui.Col_.button,          c.bg_input)
        
        # Hover (Lighter Grey)
        set_c(imgui.Col_.frame_bg_hovered, c.hover_neutral)
        set_c(imgui.Col_.button_hovered,   c.hover_neutral)
        
        # Active/Pressed (Darker Grey - No Blue!)
        set_c(imgui.Col_.frame_bg_active,  c.pressed_neutral)
        set_c(imgui.Col_.button_active,    c.pressed_neutral)

        # 4. Accent Usage (Specific Data Only)
        set_c(imgui.Col_.check_mark,          c.accent)
        set_c(imgui.Col_.slider_grab,         c.accent)
        set_c(imgui.Col_.slider_grab_active,  c.accent)
        set_c(imgui.Col_.text_selected_bg,    with_alpha(c.accent, 0.40))
        set_c(imgui.Col_.nav_windowing_highlight, c.accent)
        set_c(imgui.Col_.separator_active,    c.accent) # Resize grip active

        # 5. Structure (Headers & Tabs)
        set_c(imgui.Col_.header,          (0,0,0,0)) # Transparent
        set_c(imgui.Col_.header_hovered,  c.hover_neutral)
        set_c(imgui.Col_.header_active,   c.pressed_neutral)

        set_c(imgui.Col_.tab,             (0,0,0,0))
        set_c(imgui.Col_.tab_hovered,     c.hover_neutral)
        set_c(imgui.Col_.tab_selected,    c.bg_input)
        set_c(imgui.Col_.tab_dimmed,          with_alpha(c.text_dim, 0.2))
        set_c(imgui.Col_.tab_dimmed_selected, with_alpha(c.text_dim, 0.4))

        # 6. Windows & Navigation
        set_c(imgui.Col_.title_bg,            c.bg_popup)
        set_c(imgui.Col_.title_bg_active,     c.bg_popup)
        set_c(imgui.Col_.title_bg_collapsed,  c.bg_popup)
        set_c(imgui.Col_.menu_bar_bg,         with_alpha(c.bg_popup, 0.8))
        
        set_c(imgui.Col_.scrollbar_bg,        (0,0,0,0))
        set_c(imgui.Col_.scrollbar_grab,      with_alpha(c.text_dim, 0.3))
        set_c(imgui.Col_.scrollbar_grab_hovered, with_alpha(c.text_dim, 0.5))
        set_c(imgui.Col_.scrollbar_grab_active,  with_alpha(c.text_dim, 0.6))

        # 7. Separators & Utilities
        set_c(imgui.Col_.separator,           with_alpha(c.text_dim, 0.15))
        set_c(imgui.Col_.separator_hovered,   with_alpha(c.text_dim, 0.40))
        set_c(imgui.Col_.resize_grip,         (0,0,0,0))
        set_c(imgui.Col_.resize_grip_hovered, with_alpha(c.text_dim, 0.4))
        set_c(imgui.Col_.resize_grip_active,  c.pressed_neutral)

        # 8. Plots & Tables
        set_c(imgui.Col_.plot_lines,          c.accent)
        set_c(imgui.Col_.plot_lines_hovered,  c.text_main)
        set_c(imgui.Col_.plot_histogram,      c.plot_histogram)
        set_c(imgui.Col_.plot_histogram_hovered, c.text_main)

        set_c(imgui.Col_.table_header_bg,     with_alpha(c.bg_input, 0.4))
        set_c(imgui.Col_.table_border_strong, (0,0,0,0))
        set_c(imgui.Col_.table_border_light,  with_alpha(c.text_dim, 0.1))
        set_c(imgui.Col_.table_row_bg,        (0,0,0,0))
        set_c(imgui.Col_.table_row_bg_alt,    with_alpha(c.text_main, 0.02))
        set_c(imgui.Col_.drag_drop_target,    c.drag_drop)

# Initialize Singleton
GAMETHEME = UITheme()