import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class BudgetPanel:
    """
    Detailed National Budget Panel.
    Calculates UI previews of sector expenses dynamically based on global economic demand.
    Sliders are anchored at 50% (0.5), representing the neutral baseline.
    """
    def __init__(self):
        self.K_BUDGET = 0.15
        
        self.M_SECTOR = {
            "INFRASTRUCTURE": 0.07,
            "PROPAGANDA": 0.03,
            "ENVIRONMENT": 0.10,
            "HEALTH CARE": 0.25,
            "EDUCATION": 0.23,
            "TELECOM": 0.04,
            "GOVERNMENT": 0.14,
            "FOREIGN AID (IMF)": 0.04,
            "RESEARCH": 0.09,
            "TOURISM": 0.01,
            "SOCIAL SUPPORT": 0.15
        }
        
        # All sectors start at exactly 50% (neutral point)
        self.allocations = {k: 0.50 for k in self.M_SECTOR.keys()}
        self.REQUIREMENT_THRESHOLD = 0.50

    def render(self, state, **kwargs) -> bool:
        with WindowManager.window("BUDGET", x=300, y=100, w=480, h=780) as is_open:
            if not is_open: 
                return False
            self._render_content(state)
            return True

    def _get_player_total_demand(self, state) -> float:
        if "resource_ledger" not in state.tables:
            return 0.0
            
        player_id = state.globals.get("player_country_id", "UKR")
        ledger = state.get_table("resource_ledger")
        
        country_ledger = ledger.filter(pl.col("country_id") == player_id)
        if country_ledger.is_empty():
            return 0.0
            
        return country_ledger["consumption_usd"].sum()

    def _render_content(self, state):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        total_demand = self._get_player_total_demand(state)

        # --- INCOME SECTION ---
        Prims.header("INCOME")
        self._draw_total_bar("TOTAL", 168073420861, GAMETHEME.colors.positive)
        self._draw_standard_row("PERSONNAL INCOME TAX", 128131699398, has_more=True)
        self._draw_standard_row("TRADE", 37533665787, has_more=True)
        self._draw_standard_row("TOURISM", 2408055675)
        imgui.dummy((0, 5))

        # --- EXPENSES SECTION ---
        Prims.header("EXPENSES")
        
        total_expense = sum(
            total_demand * self.K_BUDGET * self.M_SECTOR[label] * self.allocations[label]
            for label in self.M_SECTOR.keys()
        )
        
        self._draw_total_bar("TOTAL", total_expense, GAMETHEME.colors.negative)
        
        ui_order = [
            "INFRASTRUCTURE", "PROPAGANDA", "ENVIRONMENT", "HEALTH CARE", 
            "EDUCATION", "TELECOM", "GOVERNMENT", "FOREIGN AID (IMF)", 
            "RESEARCH", "TOURISM", "SOCIAL SUPPORT"
        ]
                    
        for label in ui_order:
            preview_cost = total_demand * self.K_BUDGET * self.M_SECTOR[label] * self.allocations[label]
            self._draw_expense_slider(label, preview_cost)
            
        imgui.dummy((0, 5))

        # --- FIXED EXPENSES SECTION ---
        Prims.header("FIXED EXPENSES")
        self._draw_total_bar("TOTAL", 62836834738, GAMETHEME.colors.negative)
        self._draw_standard_row("SECURITY", 290000000, has_more=True)
        self._draw_standard_row("DIPLOMACY", 4852013165, has_more=True)
        self._draw_standard_row("TRADE", 895046693, has_more=True)
        self._draw_standard_row("UNITS UPKEEP", 16272926235, has_more=True)
        self._draw_standard_row("DEBT", 39522983326)
        self._draw_standard_row("CORRUPTION", 1003865316)
        imgui.dummy((0, 5))

        # --- SUMMARY SECTIONS ---
        Prims.header("SURPLUS / DEFICIT")
        self._draw_total_bar("", -103451826209, GAMETHEME.colors.negative, hide_label=True)
        imgui.dummy((0, 5))

        Prims.header("AVAILABLE FUNDS")
        self._draw_total_bar("", -395229827376, GAMETHEME.colors.negative, hide_label=True)

        imgui.pop_style_var()

    # =========================================================================
    # Helpers & Custom Drawing Routines
    # =========================================================================

    def _fmt_money(self, val: float) -> str:
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(val):,.0f}".replace(",", " ")

    def _fmt_short_money(self, val: float) -> str:
        abs_val = abs(val)
        if abs_val >= 1_000_000_000:
            return f"$ {abs_val / 1_000_000_000:,.0f} B".replace(",", " ")
        elif abs_val >= 1_000_000:
            return f"$ {abs_val / 1_000_000:,.0f} M".replace(",", " ")
        return self._fmt_money(val)

    def _draw_standard_row(self, label: str, value: float, has_more: bool = False):
        imgui.text(label)
        
        if has_more:
            imgui.same_line(180)
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (6, 1))
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_input)
            
            if imgui.button(f"more##{label}"):
                pass 
                
            imgui.pop_style_color()
            imgui.pop_style_var()

        val_str = self._fmt_money(value)
        Prims.right_align_text(val_str, GAMETHEME.colors.text_main)

    def _draw_total_bar(self, label: str, value: float, color: tuple, hide_label: bool = False):
        if not hide_label:
            imgui.text(label)
            imgui.same_line(180)
        else:
            imgui.set_cursor_pos_x(180)

        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        h = 18.0
        
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.12, 0.12, 0.12, 1.0))
        )
        draw_list.add_rect(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        )
        imgui.dummy((avail_w, h))

        val_str = self._fmt_money(value)
        imgui.same_line()
        Prims.right_align_text(val_str, color)

    def _draw_expense_slider(self, label: str, value: float):
        imgui.text(label)
        imgui.same_line(180)

        alloc_pct = self.allocations.get(label, 0.5)

        p = imgui.get_cursor_screen_pos()
        slider_w = 120.0
        slider_h = 14.0
        
        # Input handling with snapping anchor
        imgui.invisible_button(f"##drag_{label}", (slider_w, slider_h))
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            new_pct = max(0.0, min((mouse_x - p.x) / slider_w, 1.0))
            
            # Magnetic anchor in the middle: if deviation is less than 2%, snap to 0.5
            if 0.48 <= new_pct <= 0.52:
                new_pct = self.REQUIREMENT_THRESHOLD
                
            self.allocations[label] = new_pct
            alloc_pct = new_pct

        draw_list = imgui.get_window_draw_list()
        
        mid_x = p.x + (slider_w * self.REQUIREMENT_THRESHOLD)
        alloc_x = p.x + (slider_w * alloc_pct)

        # 1. Permanent darkened background for the left half (Dark Red)
        draw_list.add_rect_filled(
            p, (mid_x, p.y + slider_h), 
            imgui.get_color_u32((0.2, 0.05, 0.05, 1.0))
        )
        
        # 2. Permanent darkened background for the right half (Dark Green)
        draw_list.add_rect_filled(
            (mid_x, p.y), (p.x + slider_w, p.y + slider_h), 
            imgui.get_color_u32((0.05, 0.15, 0.05, 1.0))
        )

        # 3. Dynamic bright fill
        if alloc_pct < self.REQUIREMENT_THRESHOLD:
            # Deficit: bright red grows from center to current slider position
            if alloc_pct > 0:
                draw_list.add_rect_filled(
                    (alloc_x, p.y), (mid_x, p.y + slider_h), 
                    imgui.get_color_u32((0.8, 0.15, 0.15, 1.0))
                )
        elif alloc_pct > self.REQUIREMENT_THRESHOLD:
            # Surplus: green bar grows from the center to the right
            draw_list.add_rect_filled(
                (mid_x, p.y), (alloc_x, p.y + slider_h), 
                imgui.get_color_u32((0.2, 0.7, 0.2, 1.0))
                )

        # 4. Central marker (anchor)
        draw_list.add_line(
            (mid_x, p.y - 3), (mid_x, p.y + slider_h + 3),
            imgui.get_color_u32((0.4, 0.4, 0.4, 1.0)), 2.0
        )

        # 5. Black border around the slider
        draw_list.add_rect(
            p, (p.x + slider_w, p.y + slider_h), 
            imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        )

        # 6. Slider Thumb
        draw_list.add_rect_filled(
            (alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), 
            imgui.get_color_u32((0.9, 0.9, 0.9, 1.0))
        )
        draw_list.add_rect(
            (alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), 
            imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        )

        # Values on the right
        imgui.same_line()
        val_str = self._fmt_short_money(value)
        Prims.right_align_text(val_str, GAMETHEME.colors.text_main)