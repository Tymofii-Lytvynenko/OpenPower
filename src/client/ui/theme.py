from dataclasses import dataclass, field
from imgui_bundle import imgui

@dataclass
class UITheme:
    """
    Centralized theme configuration.
    Values mapped directly from C++ 'Dark Orange' style.
    """
    # =========================================================
    # 1. SEMANTIC COLORS
    # =========================================================

    # Accent Colors
    col_active_accent: tuple   = (1.00, 0.39, 0.00, 1.00) 
    col_inactive_accent: tuple = (0.27, 0.27, 0.27, 1.00) 
    
    # Game Pillars
    col_politics: tuple = (0.90, 0.80, 0.20, 1.00)
    col_military: tuple = (0.90, 0.20, 0.20, 1.00)
    col_economy: tuple  = (0.20, 0.90, 0.20, 1.00)

    # Status Colors
    col_positive: tuple = (0.20, 0.90, 0.20, 1.00)
    col_negative: tuple = (0.90, 0.20, 0.20, 1.00)
    col_info: tuple     = (0.00, 0.90, 0.90, 1.00)
    col_warning: tuple  = (1.00, 0.50, 0.00, 1.00)
    
    # Backgrounds
    col_overlay_bg: tuple      = (0.05, 0.05, 0.05, 0.80)
    col_black: tuple           = (0.00, 0.00, 0.00, 1.00)

    # =========================================================
    # 2. IMGUI STYLE ATTRIBUTES (Mapped from C++ Code)
    # =========================================================
    
    # --- Colors (Pre-calculated from ImVec4 and math) ---
    text_main: tuple      = (1.00, 1.00, 1.00, 1.00)
    text_dim: tuple       = (0.50, 0.50, 0.50, 1.00)
    
    window_bg: tuple      = (0.18, 0.18, 0.18, 1.00)
    child_bg: tuple       = (0.28, 0.28, 0.28, 0.00)
    popup_bg: tuple       = (0.31, 0.31, 0.31, 1.00)
    
    border: tuple         = (0.36, 0.36, 0.36, 0.60)
    border_shadow: tuple  = (0.00, 0.00, 0.00, 0.00)
    
    # Frame BG (0.156 * 1.5 ~= 0.235)
    frame_bg: tuple       = (0.24, 0.24, 0.24, 1.00)
    frame_bg_hovered: tuple = (0.25, 0.25, 0.25, 1.00)
    frame_bg_active: tuple = (0.28, 0.28, 0.28, 1.00)
    
    title_bg: tuple       = (0.15, 0.15, 0.15, 1.00)
    title_bg_active: tuple = (0.15, 0.15, 0.15, 1.00)
    title_bg_collapsed: tuple = (0.15, 0.15, 0.15, 1.00)
    
    menubar_bg: tuple     = (0.19, 0.19, 0.19, 1.00)
    
    scrollbar_bg: tuple   = (0.16, 0.16, 0.16, 1.00)
    scrollbar_grab: tuple = (0.27, 0.27, 0.27, 1.00)
    scrollbar_grab_hovered: tuple = (0.30, 0.30, 0.30, 1.00)
    scrollbar_grab_active: tuple = (1.00, 0.39, 0.00, 1.00)
    
    check_mark: tuple     = (1.00, 1.00, 1.00, 1.00)
    slider_grab: tuple    = (0.39, 0.39, 0.39, 1.00)
    slider_grab_active: tuple = (1.00, 0.39, 0.00, 1.00)
    
    # Button (Alpha 30/255 ~= 0.12)
    button_normal: tuple  = (1.00, 1.00, 1.00, 0.12)
    button_hover: tuple   = (1.00, 1.00, 1.00, 0.16)
    button_active: tuple  = (1.00, 1.00, 1.00, 0.39)
    
    header_bg: tuple      = (0.31, 0.31, 0.31, 1.00)
    header_hovered: tuple = (0.47, 0.47, 0.47, 1.00)
    header_active: tuple  = (0.47, 0.47, 0.47, 1.00)
    
    separator: tuple      = (0.26, 0.26, 0.26, 1.00)
    separator_hovered: tuple = (0.39, 0.39, 0.39, 1.00)
    separator_active: tuple = (1.00, 0.39, 0.00, 1.00)     
    
    resize_grip: tuple    = (1.00, 1.00, 1.00, 0.25)
    resize_grip_hovered: tuple = (1.00, 1.00, 1.00, 0.67)
    resize_grip_active: tuple = (1.00, 0.39, 0.00, 1.00)   
    
    tab: tuple            = (0.09, 0.09, 0.09, 1.00)
    tab_hovered: tuple    = (0.35, 0.35, 0.35, 1.00)
    tab_selected: tuple   = (0.19, 0.19, 0.19, 1.00)
    tab_dimmed: tuple     = (0.09, 0.09, 0.09, 1.00)
    tab_dimmed_selected: tuple = (0.19, 0.19, 0.19, 1.00)
    
    plot_lines: tuple          = (0.47, 0.47, 0.47, 1.00)
    plot_lines_hovered: tuple  = (1.00, 0.39, 0.00, 1.00)  
    plot_histogram: tuple      = (0.58, 0.58, 0.58, 1.00)
    plot_histogram_hovered: tuple = (1.00, 0.39, 0.00, 1.00)
    
    table_header_bg: tuple     = (0.19, 0.19, 0.20, 1.00)
    table_border_strong: tuple = (0.31, 0.31, 0.35, 1.00)
    table_border_light: tuple  = (0.23, 0.23, 0.25, 1.00)
    table_row_bg: tuple        = (0.00, 0.00, 0.00, 0.00)
    table_row_bg_alt: tuple    = (1.00, 1.00, 1.00, 0.06)
    
    text_selected_bg: tuple    = (1.00, 1.00, 1.00, 0.16)
    drag_drop_target: tuple    = (1.00, 0.39, 0.00, 1.00)
    nav_cursor: tuple          = (1.00, 0.39, 0.00, 1.00)
    nav_windowing_highlight: tuple = (1.00, 0.39, 0.00, 1.00)
    nav_windowing_dim_bg: tuple = (0.00, 0.00, 0.00, 0.59)
    modal_window_dim_bg: tuple  = (0.00, 0.00, 0.00, 0.59)

    # --- Geometry Defaults ---
    rounding: float = 4.0

    def apply_global_styles(self):
        """
        Pushes these settings to the active ImGui Context.
        Call this ONCE at game startup.
        """
        style = imgui.get_style()
        
        # 1. Apply Geometry (C++ Mappings)
        style.alpha = 1.0
        style.disabled_alpha = 0.60
        style.window_padding = (8.0, 8.0)
        style.window_rounding = 4.0
        style.window_border_size = 1.0
        style.window_min_size = (32.0, 32.0)
        style.window_title_align = (0.0, 0.5)
        style.window_menu_button_position = imgui.Dir_.left
        style.child_rounding = 4.0
        style.child_border_size = 1.0
        style.popup_rounding = 2.0
        style.popup_border_size = 1.0
        style.frame_padding = (4.0, 3.0)
        style.frame_rounding = 1.0
        style.frame_border_size = 1.0
        style.item_spacing = (8.0, 4.0)
        style.item_inner_spacing = (4.0, 4.0)
        style.cell_padding = (4.0, 2.0)
        style.indent_spacing = 21.0
        style.columns_min_spacing = 6.0
        style.scrollbar_size = 13.0
        style.scrollbar_rounding = 12.0
        style.grab_min_size = 7.0
        style.grab_rounding = 0.0
        style.tab_rounding = 0.0
        style.tab_border_size = 1.0
        
        # Version compatibility
        if hasattr(style, "tab_close_button_min_width_unselected"):
             style.tab_close_button_min_width_unselected = 0.0
        else:
             style.tab_min_width_for_close_button = 0.0
             
        style.color_button_position = imgui.Dir_.right
        style.button_text_align = (0.5, 0.5)
        style.selectable_text_align = (0.0, 0.0)

        # 2. Apply Colors
        def c(idx, val): style.set_color_(idx, val)

        c(imgui.Col_.text, self.text_main)
        c(imgui.Col_.text_disabled, self.text_dim)
        c(imgui.Col_.window_bg, self.window_bg)
        c(imgui.Col_.child_bg, self.child_bg)
        c(imgui.Col_.popup_bg, self.popup_bg)
        c(imgui.Col_.border, self.border)
        c(imgui.Col_.border_shadow, self.border_shadow)
        c(imgui.Col_.frame_bg, self.frame_bg)
        c(imgui.Col_.frame_bg_hovered, self.frame_bg_hovered)
        c(imgui.Col_.frame_bg_active, self.frame_bg_active)
        c(imgui.Col_.title_bg, self.title_bg)
        c(imgui.Col_.title_bg_active, self.title_bg_active)
        c(imgui.Col_.title_bg_collapsed, self.title_bg_collapsed)
        c(imgui.Col_.menu_bar_bg, self.menubar_bg)
        c(imgui.Col_.scrollbar_bg, self.scrollbar_bg)
        c(imgui.Col_.scrollbar_grab, self.scrollbar_grab)
        c(imgui.Col_.scrollbar_grab_hovered, self.scrollbar_grab_hovered)
        c(imgui.Col_.scrollbar_grab_active, self.scrollbar_grab_active)
        c(imgui.Col_.check_mark, self.check_mark)
        c(imgui.Col_.slider_grab, self.slider_grab)
        c(imgui.Col_.slider_grab_active, self.slider_grab_active)
        c(imgui.Col_.button, self.button_normal)
        c(imgui.Col_.button_hovered, self.button_hover)
        c(imgui.Col_.button_active, self.button_active)
        c(imgui.Col_.header, self.header_bg)
        c(imgui.Col_.header_hovered, self.header_hovered)
        c(imgui.Col_.header_active, self.header_active)
        c(imgui.Col_.separator, self.separator)
        c(imgui.Col_.separator_hovered, self.separator_hovered)
        c(imgui.Col_.separator_active, self.separator_active)
        c(imgui.Col_.resize_grip, self.resize_grip)
        c(imgui.Col_.resize_grip_hovered, self.resize_grip_hovered)
        c(imgui.Col_.resize_grip_active, self.resize_grip_active)
        c(imgui.Col_.tab, self.tab)
        c(imgui.Col_.tab_hovered, self.tab_hovered)
        c(imgui.Col_.tab_selected, self.tab_selected)
        c(imgui.Col_.tab_dimmed, self.tab_dimmed)
        c(imgui.Col_.tab_dimmed_selected, self.tab_dimmed_selected)
        c(imgui.Col_.plot_lines, self.plot_lines)
        c(imgui.Col_.plot_lines_hovered, self.plot_lines_hovered)
        c(imgui.Col_.plot_histogram, self.plot_histogram)
        c(imgui.Col_.plot_histogram_hovered, self.plot_histogram_hovered)
        c(imgui.Col_.table_header_bg, self.table_header_bg)
        c(imgui.Col_.table_border_strong, self.table_border_strong)
        c(imgui.Col_.table_border_light, self.table_border_light)
        c(imgui.Col_.table_row_bg, self.table_row_bg)
        c(imgui.Col_.table_row_bg_alt, self.table_row_bg_alt)
        c(imgui.Col_.text_selected_bg, self.text_selected_bg)
        c(imgui.Col_.drag_drop_target, self.drag_drop_target)
        c(imgui.Col_.nav_cursor, self.nav_cursor)
        c(imgui.Col_.nav_windowing_highlight, self.nav_windowing_highlight)
        c(imgui.Col_.nav_windowing_dim_bg, self.nav_windowing_dim_bg)
        c(imgui.Col_.modal_window_dim_bg, self.modal_window_dim_bg)

# Initialize Singleton
GAMETHEME = UITheme()