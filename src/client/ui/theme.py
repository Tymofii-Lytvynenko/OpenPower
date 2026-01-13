from dataclasses import dataclass, field
from imgui_bundle import imgui

@dataclass
class UITheme:
    """
    Revised Dark Theme.
    """
    
    # =========================================================
    # 1. SEMANTIC COLORS
    # =========================================================

    # Main Accent
    col_active_accent: tuple   = (0.28, 0.56, 1.00, 1.00)  
    col_inactive_accent: tuple = (0.28, 0.56, 1.00, 0.40)
    col_border_accent: tuple   = (0.28, 0.56, 1.00, 0.80)  
    
    # Text Colors
    col_text_bright: tuple     = (0.95, 0.96, 0.98, 1.00)
    col_text_disabled: tuple   = (0.36, 0.42, 0.47, 1.00)
    
    # Game Pillars
    col_politics: tuple = (1.00, 0.85, 0.25, 1.00)
    col_military: tuple = (1.00, 0.35, 0.35, 1.00)
    col_economy: tuple  = (0.30, 0.95, 0.60, 1.00)

    # Status Colors
    col_positive: tuple = (0.30, 0.95, 0.60, 1.00)
    col_negative: tuple = (1.00, 0.35, 0.35, 1.00)
    col_error: tuple    = (1.00, 0.20, 0.20, 1.00)
    col_info: tuple     = (0.28, 0.56, 1.00, 1.00)
    col_warning: tuple  = (1.00, 0.65, 0.00, 1.00)
    
    # Backgrounds & Special Areas
    col_overlay_bg: tuple   = (0.08, 0.08, 0.08, 0.94)
    col_black: tuple        = (0.00, 0.00, 0.00, 1.00)
    col_panel_bg: tuple     = (0.11, 0.15, 0.17, 1.00)
    col_inactive_bg: tuple  = (0.15, 0.18, 0.22, 1.00)

    # Custom Button Colors
    col_button_idle: tuple      = (0.20, 0.25, 0.29, 1.00)
    col_button_text_idle: tuple = (0.95, 0.96, 0.98, 1.00)

    # =========================================================
    # 2. IMGUI INTERNAL STYLE ATTRIBUTES
    # =========================================================
    
    # Text & Window
    text_main: tuple      = (0.95, 0.96, 0.98, 1.00)
    text_dim: tuple       = (0.36, 0.42, 0.47, 1.00)
    
    window_bg: tuple      = (0.11, 0.15, 0.17, 1.00)
    child_bg: tuple       = (0.15, 0.18, 0.22, 1.00)
    popup_bg: tuple       = (0.08, 0.08, 0.08, 0.94)
    
    # Borders
    border: tuple         = (0.08, 0.10, 0.12, 1.00)
    border_shadow: tuple  = (0.00, 0.00, 0.00, 0.00)
    
    # Input Fields
    frame_bg: tuple         = (0.20, 0.25, 0.29, 1.00)
    frame_bg_hovered: tuple = (0.12, 0.20, 0.28, 1.00)
    frame_bg_active: tuple  = (0.09, 0.12, 0.14, 1.00)
    
    # Title Bars
    title_bg: tuple           = (0.09, 0.12, 0.14, 0.65)
    title_bg_active: tuple    = (0.08, 0.10, 0.12, 1.00)
    title_bg_collapsed: tuple = (0.00, 0.00, 0.00, 0.51)
    
    menubar_bg: tuple = (0.15, 0.18, 0.22, 1.00)
    
    # Scrollbars
    scrollbar_bg: tuple          = (0.02, 0.02, 0.02, 0.39)
    scrollbar_grab: tuple        = (0.20, 0.25, 0.29, 1.00)
    scrollbar_grab_hovered: tuple = (0.18, 0.22, 0.25, 1.00)
    scrollbar_grab_active: tuple  = (0.09, 0.21, 0.31, 1.00)
    
    # Checkbox & Sliders
    check_mark: tuple         = (0.28, 0.56, 1.00, 1.00)
    slider_grab: tuple        = (0.28, 0.56, 1.00, 1.00)
    slider_grab_active: tuple = (0.37, 0.61, 1.00, 1.00)
    
    # Buttons
    button_normal: tuple = (0.20, 0.25, 0.29, 1.00)
    button_hover: tuple  = (0.28, 0.56, 1.00, 1.00)
    button_active: tuple = (0.06, 0.53, 0.98, 1.00)
    
    # Headers
    header_bg: tuple      = (0.20, 0.25, 0.29, 0.55)
    header_hovered: tuple = (0.26, 0.59, 0.98, 0.80)
    header_active: tuple  = (0.26, 0.59, 0.98, 1.00)
    
    # Separators
    separator: tuple         = (0.20, 0.25, 0.29, 1.00)
    separator_hovered: tuple = (0.10, 0.40, 0.75, 0.78)
    separator_active: tuple  = (0.10, 0.40, 0.75, 1.00)
    
    # Tabs
    tab: tuple            = (0.11, 0.15, 0.17, 1.00)
    tab_hovered: tuple    = (0.26, 0.59, 0.98, 0.80)
    tab_active: tuple     = (0.20, 0.25, 0.29, 1.00)
    tab_unfocused: tuple  = (0.11, 0.15, 0.17, 1.00)
    tab_unfocused_active: tuple = (0.11, 0.15, 0.17, 1.00)

    # Resize Grip
    resize_grip: tuple         = (0.26, 0.59, 0.98, 0.25)
    resize_grip_hovered: tuple = (0.26, 0.59, 0.98, 0.67)
    resize_grip_active: tuple  = (0.26, 0.59, 0.98, 0.95)

    # Plotting
    plot_lines: tuple        = (0.61, 0.61, 0.61, 1.00)
    plot_lines_hovered: tuple = (1.00, 0.43, 0.35, 1.00)
    plot_histogram: tuple    = (0.90, 0.70, 0.00, 1.00)
    plot_histogram_hovered: tuple = (1.00, 0.60, 0.00, 1.00)

    # Navigation & Special
    text_selected_bg: tuple = (0.26, 0.59, 0.98, 0.35)
    drag_drop_target: tuple = (1.00, 1.00, 0.00, 0.90)
    nav_windowing_highlight: tuple = (1.00, 1.00, 1.00, 0.70)
    nav_windowing_dim_bg: tuple = (0.80, 0.80, 0.80, 0.20)
    modal_window_dim_bg: tuple  = (0.80, 0.80, 0.80, 0.35)

    # Table
    table_header_bg: tuple     = (0.20, 0.25, 0.29, 0.55)
    table_border_strong: tuple = (0.31, 0.31, 0.35, 1.00)
    table_border_light: tuple  = (0.23, 0.23, 0.25, 1.00)
    table_row_bg: tuple        = (0.00, 0.00, 0.00, 0.00)
    table_row_bg_alt: tuple    = (1.00, 1.00, 1.00, 0.03)

    # Geometry Defaults
    rounding: float = 4.0 

    def apply_global_styles(self):
        """
        Pushes theme settings to the active ImGui Context.
        """
        style = imgui.get_style()
        
        # 1. Geometry & Layout
        style.alpha = 1.0
        style.disabled_alpha = 0.50
        style.window_padding = (10.0, 10.0)
        style.window_rounding = self.rounding
        style.window_border_size = 1.0
        style.window_min_size = (32.0, 32.0)
        style.window_title_align = (0.5, 0.5)
        
        style.child_rounding = self.rounding
        style.child_border_size = 1.0
        style.popup_rounding = self.rounding
        style.popup_border_size = 1.0
        
        style.frame_padding = (6.0, 4.0)
        style.frame_rounding = 4.0
        style.frame_border_size = 0.0
        
        style.item_spacing = (10.0, 6.0)
        style.item_inner_spacing = (6.0, 4.0)
        style.cell_padding = (6.0, 4.0)
        style.indent_spacing = 20.0
        
        style.scrollbar_size = 12.0
        style.scrollbar_rounding = 12.0
        
        style.grab_min_size = 10.0
        style.grab_rounding = 4.0
        
        style.tab_rounding = 4.0
        style.tab_border_size = 0.0
        
        # 2. Map Color Properties
        def c(idx, val): style.set_color_(idx, val)

        # Core
        c(imgui.Col_.text, self.text_main)
        c(imgui.Col_.text_disabled, self.text_dim)
        c(imgui.Col_.window_bg, self.window_bg)
        c(imgui.Col_.child_bg, self.child_bg)
        c(imgui.Col_.popup_bg, self.popup_bg)
        c(imgui.Col_.border, self.border)
        c(imgui.Col_.border_shadow, self.border_shadow)
        
        # Inputs
        c(imgui.Col_.frame_bg, self.frame_bg)
        c(imgui.Col_.frame_bg_hovered, self.frame_bg_hovered)
        c(imgui.Col_.frame_bg_active, self.frame_bg_active)
        
        # Title
        c(imgui.Col_.title_bg, self.title_bg)
        c(imgui.Col_.title_bg_active, self.title_bg_active)
        c(imgui.Col_.title_bg_collapsed, self.title_bg_collapsed)
        c(imgui.Col_.menu_bar_bg, self.menubar_bg)
        
        # Scroll
        c(imgui.Col_.scrollbar_bg, self.scrollbar_bg)
        c(imgui.Col_.scrollbar_grab, self.scrollbar_grab)
        c(imgui.Col_.scrollbar_grab_hovered, self.scrollbar_grab_hovered)
        c(imgui.Col_.scrollbar_grab_active, self.scrollbar_grab_active)
        
        # Interactive
        c(imgui.Col_.check_mark, self.check_mark)
        c(imgui.Col_.slider_grab, self.slider_grab)
        c(imgui.Col_.slider_grab_active, self.slider_grab_active)
        
        # Buttons
        c(imgui.Col_.button, self.button_normal)
        c(imgui.Col_.button_hovered, self.button_hover)
        c(imgui.Col_.button_active, self.button_active)
        
        # Headers / Lists
        c(imgui.Col_.header, self.header_bg)
        c(imgui.Col_.header_hovered, self.header_hovered)
        c(imgui.Col_.header_active, self.header_active)
        
        # Tabs
        c(imgui.Col_.tab, self.tab)
        c(imgui.Col_.tab_hovered, self.tab_hovered)
        c(imgui.Col_.tab_selected, self.tab_active)
        c(imgui.Col_.tab_dimmed, self.tab_unfocused)
        c(imgui.Col_.tab_dimmed_selected, self.tab_unfocused_active)
        
        # Misc
        c(imgui.Col_.separator, self.separator)
        c(imgui.Col_.separator_hovered, self.separator_hovered)
        c(imgui.Col_.separator_active, self.separator_active)
        
        # Resizing
        c(imgui.Col_.resize_grip, self.resize_grip)
        c(imgui.Col_.resize_grip_hovered, self.resize_grip_hovered)
        c(imgui.Col_.resize_grip_active, self.resize_grip_active)
        
        # Plotting
        c(imgui.Col_.plot_lines, self.plot_lines)
        c(imgui.Col_.plot_lines_hovered, self.plot_lines_hovered)
        c(imgui.Col_.plot_histogram, self.plot_histogram)
        c(imgui.Col_.plot_histogram_hovered, self.plot_histogram_hovered)
        
        # Special / Nav
        c(imgui.Col_.text_selected_bg, self.text_selected_bg)
        c(imgui.Col_.drag_drop_target, self.drag_drop_target)
        # NavHighlight skipped per request
        c(imgui.Col_.nav_windowing_highlight, self.nav_windowing_highlight)
        c(imgui.Col_.nav_windowing_dim_bg, self.nav_windowing_dim_bg)
        c(imgui.Col_.modal_window_dim_bg, self.modal_window_dim_bg)
        
        # Tables
        c(imgui.Col_.table_header_bg, self.table_header_bg)
        c(imgui.Col_.table_border_strong, self.table_border_strong)
        c(imgui.Col_.table_border_light, self.table_border_light)
        c(imgui.Col_.table_row_bg, self.table_row_bg)
        c(imgui.Col_.table_row_bg_alt, self.table_row_bg_alt)

# Initialize Singleton
GAMETHEME = UITheme()