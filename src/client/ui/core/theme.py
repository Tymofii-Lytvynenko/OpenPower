from dataclasses import dataclass, field
from imgui_bundle import imgui

def with_alpha(color: tuple, alpha: float) -> tuple:
    """Helper: Returns a new color tuple with modified alpha."""
    return (color[0], color[1], color[2], alpha)

@dataclass
class UIColors:
    """
    Single Source of Truth. 
    Contains all semantic colors used in the game and UI.
    """
    # --- 1. Base Text ---
    text_main: tuple     = (0.95, 0.96, 0.98, 1.00)
    text_dim: tuple      = (0.36, 0.42, 0.47, 1.00)

    # --- 2. Backgrounds ---
    bg_window: tuple     = (0.11, 0.15, 0.17, 1.00)  # Main panels
    bg_child: tuple      = (0.15, 0.18, 0.22, 1.00)  # Sub-panels / Menus
    bg_popup: tuple      = (0.08, 0.08, 0.08, 0.94)  # Tooltips / Modals
    bg_input: tuple      = (0.20, 0.25, 0.29, 1.00)  # Input fields / Buttons

    # --- 3. Main Accent (The "Brand" Color) ---
    # Used for: Borders, checks, sliders, active headers, info text
    accent: tuple        = (0.28, 0.56, 1.00, 1.00)

    # --- 4. Game Pillars (Preserved) ---
    politics: tuple      = (1.00, 0.85, 0.25, 1.00)
    military: tuple      = (1.00, 0.35, 0.35, 1.00)
    economy: tuple       = (0.30, 0.95, 0.60, 1.00)
    demographics: tuple  = (0.70, 0.40, 0.90, 1.00)

    # --- 5. Status Indicators (Preserved) ---
    # Note: Even if these match Pillar colors now, we keep them distinct 
    # so you can change "Negative" without changing "Military" later.
    positive: tuple      = (0.30, 0.95, 0.60, 1.00)
    negative: tuple      = (1.00, 0.35, 0.35, 1.00)
    error: tuple         = (1.00, 0.20, 0.20, 1.00)
    warning: tuple       = (1.00, 0.65, 0.00, 1.00)
    info: tuple          = (0.28, 0.56, 1.00, 1.00)

    # --- 6. Interaction States ---
    # Used for: Button click, active tabs, header active
    interaction_active: tuple = (0.06, 0.53, 0.98, 1.00) 
    
    # --- 7. Special Overrides ---
    # Specific elements that had unique colors in your original code
    drag_drop: tuple     = (1.00, 1.00, 0.00, 0.90)
    plot_histogram: tuple= (0.90, 0.70, 0.00, 1.00)

@dataclass
class UITheme:
    """
    Applies the UIColors to the ImGui Style engine.
    """
    colors: UIColors = field(default_factory=UIColors)
    rounding: float = 4.0

    def apply(self):
        style = imgui.get_style()
        c = self.colors
        
        # --- Helper for cleaner syntax ---
        def set_c(idx, color): style.set_color_(idx, color)

        # 1. Geometry Defaults
        style.window_padding    = (10, 10)
        style.frame_padding     = (6, 4)
        style.item_spacing      = (10, 6)
        style.window_rounding   = self.rounding
        style.frame_rounding    = self.rounding
        style.popup_rounding    = self.rounding
        style.grab_rounding     = self.rounding
        style.scrollbar_size    = 12.0
        style.scrollbar_rounding = 12.0

        # 2. Base Colors
        set_c(imgui.Col_.text,           c.text_main)
        set_c(imgui.Col_.text_disabled,  c.text_dim)
        set_c(imgui.Col_.window_bg,      c.bg_window)
        set_c(imgui.Col_.child_bg,       c.bg_child)
        set_c(imgui.Col_.popup_bg,       c.bg_popup)
        set_c(imgui.Col_.border,         (0.08, 0.10, 0.12, 1.00))
        
        # 3. Inputs & Buttons (Unified Logic)
        # Idle: Dark Grey | Hover: Accent Blue | Active: Bright Blue
        set_c(imgui.Col_.frame_bg,        c.bg_input)
        set_c(imgui.Col_.frame_bg_hovered, with_alpha(c.bg_input, 0.8))
        set_c(imgui.Col_.frame_bg_active,  with_alpha(c.interaction_active, 0.5))

        set_c(imgui.Col_.button,          c.bg_input)
        set_c(imgui.Col_.button_hovered,  c.accent)
        set_c(imgui.Col_.button_active,   c.interaction_active)

        set_c(imgui.Col_.check_mark,      c.accent)
        set_c(imgui.Col_.slider_grab,     c.accent)
        set_c(imgui.Col_.slider_grab_active, c.interaction_active)

        # 4. Headers & Tabs
        set_c(imgui.Col_.header,          with_alpha(c.accent, 0.55))
        set_c(imgui.Col_.header_hovered,  with_alpha(c.accent, 0.80))
        set_c(imgui.Col_.header_active,   c.accent)

        set_c(imgui.Col_.tab,             c.bg_window)
        set_c(imgui.Col_.tab_hovered,     with_alpha(c.accent, 0.80))
        set_c(imgui.Col_.tab_selected,    c.bg_input)
        set_c(imgui.Col_.tab_dimmed,          c.bg_window)
        set_c(imgui.Col_.tab_dimmed_selected, c.bg_window)

        # 5. Windows & Navigation
        set_c(imgui.Col_.title_bg,            with_alpha(c.bg_popup, 0.65))
        set_c(imgui.Col_.title_bg_active,     with_alpha(c.bg_popup, 1.00))
        set_c(imgui.Col_.title_bg_collapsed,  (0.0, 0.0, 0.0, 0.51))
        set_c(imgui.Col_.menu_bar_bg,         c.bg_child)
        set_c(imgui.Col_.scrollbar_bg,        (0.02, 0.02, 0.02, 0.39))
        set_c(imgui.Col_.scrollbar_grab,      c.bg_input)
        set_c(imgui.Col_.scrollbar_grab_hovered, c.text_dim)
        set_c(imgui.Col_.scrollbar_grab_active,  c.accent)

        # 6. Separators & Resize
        set_c(imgui.Col_.separator,           c.bg_input)
        set_c(imgui.Col_.separator_hovered,   c.accent)
        set_c(imgui.Col_.separator_active,    c.accent)
        set_c(imgui.Col_.resize_grip,         with_alpha(c.accent, 0.25))
        set_c(imgui.Col_.resize_grip_hovered, with_alpha(c.accent, 0.67))
        set_c(imgui.Col_.resize_grip_active,  c.interaction_active)

        # 7. Plots & Tables
        set_c(imgui.Col_.plot_lines,          (0.61, 0.61, 0.61, 1.00))
        set_c(imgui.Col_.plot_lines_hovered,  c.military) # Reddish from original
        set_c(imgui.Col_.plot_histogram,      c.plot_histogram)
        set_c(imgui.Col_.plot_histogram_hovered, (1.00, 0.60, 0.00, 1.00))

        set_c(imgui.Col_.table_header_bg,     with_alpha(c.bg_input, 0.55))
        set_c(imgui.Col_.table_border_strong, with_alpha(c.text_dim, 0.5))
        set_c(imgui.Col_.table_border_light,  with_alpha(c.text_dim, 0.2))
        set_c(imgui.Col_.table_row_bg,        (0,0,0,0))
        set_c(imgui.Col_.table_row_bg_alt,    with_alpha(c.text_main, 0.03))

        set_c(imgui.Col_.text_selected_bg,    with_alpha(c.accent, 0.35))
        set_c(imgui.Col_.drag_drop_target,    c.drag_drop)
        set_c(imgui.Col_.nav_windowing_highlight, (1.00, 1.00, 1.00, 0.70))

# Initialize Singleton
GAMETHEME = UITheme()