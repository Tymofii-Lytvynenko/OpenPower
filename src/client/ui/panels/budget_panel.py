import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class BudgetPanel:
    """
    Detailed National Budget Panel.
    Calculates UI previews of sector expenses dynamically based on global economic demand.
    """
    def __init__(self):
        # Base multiplier logic identical to the server-side simulation
        self.K_BUDGET = 0.15
        self.M_SECTOR = {
            "HEALTH CARE": 0.25,
            "EDUCATION": 0.23,
            "GOVERNMENT": 0.14,
            "ENVIRONMENT": 0.10,
            "RESEARCH": 0.09,
            "INFRASTRUCTURE": 0.07,
            "TELECOM": 0.04,
            "IMF": 0.04,
            "PROPAGANDA": 0.03,
            "TOURISM": 0.01
        }
        
        self.allocations = {k: 0.50 for k in self.M_SECTOR.keys()}
        self.requirements = {
            "HEALTH CARE": 0.40,
            "EDUCATION": 0.40,
            "GOVERNMENT": 0.38,
            "ENVIRONMENT": 0.40,
            "RESEARCH": 0.40,
            "INFRASTRUCTURE": 0.40,
            "TELECOM": 0.40,
            "IMF": 0.15,
            "PROPAGANDA": 0.35,
            "TOURISM": 0.40
        }

    def render(self, state, **kwargs) -> bool:
        with WindowManager.window("BUDGET", x=300, y=100, w=480, h=750) as is_open:
            if not is_open: 
                return False
            self._render_content(state)
            return True

    def _get_player_total_demand(self, state) -> float:
        # Extracts current total consumption demand to seed the UI preview calculations.
        if "resource_ledger" not in state.tables:
            return 0.0
            
        # FIXME: 'UKR' is hardcoded for MVP. Query the actual active session context tag here.
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
        
        # We calculate total discretionary expenses by summing all sliders locally 
        # so the 'TOTAL' block stays perfectly synced during dragging without network delay.
        total_expense = sum(
            total_demand * self.K_BUDGET * self.M_SECTOR[label] * self.allocations[label]
            for label in self.M_SECTOR.keys()
        )
        
        self._draw_total_bar("TOTAL", total_expense, GAMETHEME.colors.negative)
        
        # Ensure iteration order respects UI design hierarchy, not dict key order
        ui_order = ["INFRASTRUCTURE", "PROPAGANDA", "ENVIRONMENT", "HEALTH CARE", 
                    "EDUCATION", "TELECOM", "GOVERNMENT", "IMF", "RESEARCH", "TOURISM"]
                    
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
                pass # TODO: Implement state transition to specific breakdown sub-panel
                
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
        imgui.dummy((avail_w, h))

        val_str = self._fmt_money(value)
        imgui.same_line()
        Prims.right_align_text(val_str, color)

    def _draw_expense_slider(self, label: str, value: float):
        imgui.text(label)
        imgui.same_line(180)

        req_pct = self.requirements.get(label, 0.2)
        alloc_pct = self.allocations.get(label, 0.5)

        p = imgui.get_cursor_screen_pos()
        slider_w = 120.0
        slider_h = 14.0
        
        # Invisible button creates a hit-box over custom rendering for input capture
        imgui.invisible_button(f"##drag_{label}", (slider_w, slider_h))
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            new_pct = max(0.0, min((mouse_x - p.x) / slider_w, 1.0))
            self.allocations[label] = new_pct
            alloc_pct = new_pct

        draw_list = imgui.get_window_draw_list()
        
        draw_list.add_rect_filled(
            p, (p.x + slider_w, p.y + slider_h), 
            imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)), 2.0
        )

        red_w = slider_w * req_pct
        draw_list.add_rect_filled(
            p, (p.x + red_w, p.y + slider_h), 
            imgui.get_color_u32((0.6, 0.2, 0.2, 1.0)), 2.0
        )

        if alloc_pct > req_pct:
            alloc_w = slider_w * alloc_pct
            draw_list.add_rect_filled(
                (p.x + red_w, p.y), (p.x + alloc_w, p.y + slider_h), 
                imgui.get_color_u32((0.3, 0.7, 0.4, 1.0)), 2.0
            )
        elif alloc_pct > 0:
            alloc_w = slider_w * alloc_pct
            draw_list.add_rect_filled(
                p, (p.x + alloc_w, p.y + slider_h), 
                imgui.get_color_u32((0.4, 0.2, 0.2, 1.0)), 2.0
            )

        thumb_x = p.x + (slider_w * alloc_pct)
        draw_list.add_rect_filled(
            (thumb_x - 1, p.y - 1), (thumb_x + 1, p.y + slider_h + 1), 
            imgui.get_color_u32((0.9, 0.9, 0.9, 1.0))
        )

        imgui.same_line()
        val_str = self._fmt_short_money(value)
        Prims.right_align_text(val_str, GAMETHEME.colors.text_main)