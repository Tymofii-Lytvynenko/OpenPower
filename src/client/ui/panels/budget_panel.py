import polars as pl
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class BudgetPanel:
    """
    Detailed National Budget Menu.
    Uses an ImGui Menu Bar for a clean, text-free Apply button.
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
        
        self.allocations = {k: 0.50 for k in self.M_SECTOR.keys()}
        self.draft_allocations = self.allocations.copy()
        
        self.REQUIREMENT_THRESHOLD = 0.50
        self.show_close_confirm = False

    def render(self, state, **kwargs) -> bool:
        # Додаємо прапорець menu_bar для вікна
        flags = imgui.WindowFlags_.menu_bar
        
        with WindowManager.window("BUDGET MENU", x=300, y=100, w=480, h=780, flags=flags) as is_open:
            
            has_changes = self.draft_allocations != self.allocations

            # 1. Перехоплення закриття вікна
            if not is_open and not self.show_close_confirm: 
                if has_changes:
                    self.show_close_confirm = True 
                else:
                    return False

            # 2. Rendering the Menu Bar for window actions
            if imgui.begin_menu_bar():
                avail_w = imgui.get_content_region_avail().x
                # Push the button to the far right of the bar
                imgui.dummy((max(0.0, avail_w - 32.0), 0))
                
                if has_changes:
                    # State: Active (using theme's interaction colors)
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_main)
                    imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
                    imgui.push_style_color(imgui.Col_.button_hovered, GAMETHEME.colors.accent)
                else:
                    # State: Inactive (dimmed, transparent background, non-clickable)
                    imgui.begin_disabled()
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
                    imgui.push_style_color(imgui.Col_.button, (0, 0, 0, 0))

                # Render the Checkmark icon button
                if imgui.button("apply"):
                    # Apply draft changes to the persistent state
                    if hasattr(self, 'draft_allocations'):
                        self.allocations = self.draft_allocations.copy()
                    if hasattr(self, 'has_unsaved_changes'):
                        self.has_unsaved_changes = False
                    
                    # NOTE: Network action should be dispatched here to notify the server

                # Cleanup style stack
                imgui.pop_style_color(2)
                if has_changes:
                    imgui.pop_style_color() # Pop hover color only if active
                else:
                    imgui.end_disabled()
                    
                imgui.end_menu_bar()

            # 3. Контент
            self._render_content(state)

            # 4. Модальне вікно підтвердження
            if self.show_close_confirm:
                imgui.open_popup("Unsaved Changes##Budget")
                
            if self._render_close_modal():
                return False

            return True

    def _render_close_modal(self) -> bool:
        viewport = imgui.get_main_viewport()
        imgui.set_next_window_pos(viewport.get_center(), imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        
        flags = imgui.WindowFlags_.always_auto_resize | imgui.WindowFlags_.no_saved_settings
        if imgui.begin_popup_modal("Unsaved Changes##Budget", None, flags)[0]:
            imgui.text("You have unapplied changes in your budget.")
            imgui.text("Do you want to discard them and close?")
            imgui.dummy((0, 15))
            
            if imgui.button("Discard & Close", (140, 30)):
                self.draft_allocations = self.allocations.copy()
                self.show_close_confirm = False
                imgui.close_current_popup()
                imgui.end_popup()
                return True
                
            imgui.same_line()
            
            if imgui.button("Cancel", (100, 30)):
                self.show_close_confirm = False
                imgui.close_current_popup()
                
            imgui.end_popup()
        return False

    def _get_player_total_demand(self, state) -> float:
        if "resource_ledger" not in state.tables: return 0.0
        player_id = state.globals.get("player_country_id", "UKR")
        country_ledger = state.get_table("resource_ledger").filter(pl.col("country_id") == player_id)
        if country_ledger.is_empty(): return 0.0
        return country_ledger["consumption_usd"].sum()

    def _render_content(self, state):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))
        total_demand = self._get_player_total_demand(state)

        Prims.header("INCOME", show_bg=False)
        self._draw_total_bar("TOTAL", 168073420861, GAMETHEME.colors.positive)
        self._draw_standard_row("PERSONNAL INCOME TAX", 128131699398, has_more=True)
        self._draw_standard_row("TRADE", 37533665787, has_more=True)
        self._draw_standard_row("TOURISM", 2408055675)
        imgui.dummy((0, 5))

        Prims.header("EXPENSES", show_bg=False)
        total_expense = sum(
            total_demand * self.K_BUDGET * self.M_SECTOR[label] * self.draft_allocations[label]
            for label in self.M_SECTOR.keys()
        )
        self._draw_total_bar("TOTAL", total_expense, GAMETHEME.colors.negative)
        
        ui_order = [
            "INFRASTRUCTURE", "PROPAGANDA", "ENVIRONMENT", "HEALTH CARE", 
            "EDUCATION", "TELECOM", "GOVERNMENT", "FOREIGN AID (IMF)", 
            "RESEARCH", "TOURISM", "SOCIAL SUPPORT"
        ]
                    
        for label in ui_order:
            preview_cost = total_demand * self.K_BUDGET * self.M_SECTOR[label] * self.draft_allocations[label]
            self._draw_expense_slider(label, preview_cost)
            
        imgui.dummy((0, 5))

        Prims.header("FIXED EXPENSES", show_bg=False)
        self._draw_total_bar("TOTAL", 62836834738, GAMETHEME.colors.negative)
        self._draw_standard_row("SECURITY", 290000000, has_more=True)
        self._draw_standard_row("DIPLOMACY", 4852013165, has_more=True)
        self._draw_standard_row("TRADE", 895046693, has_more=True)
        self._draw_standard_row("UNITS UPKEEP", 16272926235, has_more=True)
        self._draw_standard_row("DEBT", 39522983326)
        self._draw_standard_row("CORRUPTION", 1003865316)
        imgui.dummy((0, 5))

        Prims.header("SURPLUS / DEFICIT", show_bg=False)
        self._draw_total_bar("", -103451826209, GAMETHEME.colors.negative, hide_label=True)
        imgui.dummy((0, 5))

        Prims.header("AVAILABLE FUNDS", show_bg=False)
        self._draw_total_bar("", -395229827376, GAMETHEME.colors.negative, hide_label=True)

        imgui.pop_style_var()

    # Helpers
    def _fmt_money(self, val: float) -> str:
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(val):,.0f}".replace(",", " ")

    def _fmt_short_money(self, val: float) -> str:
        abs_val = abs(val)
        if abs_val >= 1_000_000_000: return f"$ {abs_val / 1_000_000_000:,.0f} B".replace(",", " ")
        elif abs_val >= 1_000_000: return f"$ {abs_val / 1_000_000:,.0f} M".replace(",", " ")
        return self._fmt_money(val)

    def _draw_standard_row(self, label: str, value: float, has_more: bool = False):
        imgui.text(label)
        if has_more:
            imgui.same_line(180)
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (6, 1))
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_input)
            if imgui.button(f"more##{label}"): pass 
            imgui.pop_style_color()
            imgui.pop_style_var()
        Prims.right_align_text(self._fmt_money(value), GAMETHEME.colors.text_main)

    def _draw_total_bar(self, label: str, value: float, color: tuple, hide_label: bool = False):
        if not hide_label:
            imgui.text(label)
            imgui.same_line(180)
        else: imgui.set_cursor_pos_x(180)

        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        draw_list = imgui.get_window_draw_list()
        
        draw_list.add_rect_filled(p, (p.x + avail_w, p.y + 18), imgui.get_color_u32((0.12, 0.12, 0.12, 1.0)))
        draw_list.add_rect(p, (p.x + avail_w, p.y + 18), imgui.get_color_u32((0.0, 0.0, 0.0, 1.0)))
        imgui.dummy((avail_w, 18))

        imgui.same_line()
        Prims.right_align_text(self._fmt_money(value), color)

    def _draw_expense_slider(self, label: str, value: float):
        imgui.text(label)
        imgui.same_line(180)

        alloc_pct = self.draft_allocations.get(label, 0.5)

        p = imgui.get_cursor_screen_pos()
        slider_w = 120.0
        slider_h = 14.0
        
        imgui.invisible_button(f"##drag_{label}", (slider_w, slider_h))
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            new_pct = max(0.0, min((mouse_x - p.x) / slider_w, 1.0))
            
            if 0.48 <= new_pct <= 0.52:
                new_pct = self.REQUIREMENT_THRESHOLD
                
            self.draft_allocations[label] = new_pct
            alloc_pct = new_pct

        draw_list = imgui.get_window_draw_list()
        mid_x = p.x + (slider_w * self.REQUIREMENT_THRESHOLD)
        alloc_x = p.x + (slider_w * alloc_pct)

        draw_list.add_rect_filled(p, (mid_x, p.y + slider_h), imgui.get_color_u32((0.2, 0.05, 0.05, 1.0)))
        draw_list.add_rect_filled((mid_x, p.y), (p.x + slider_w, p.y + slider_h), imgui.get_color_u32((0.05, 0.15, 0.05, 1.0)))

        if alloc_pct < self.REQUIREMENT_THRESHOLD:
            draw_list.add_rect_filled((alloc_x, p.y), (mid_x, p.y + slider_h), imgui.get_color_u32((0.8, 0.15, 0.15, 1.0)))
        elif alloc_pct > self.REQUIREMENT_THRESHOLD:
            draw_list.add_rect_filled((mid_x, p.y), (alloc_x, p.y + slider_h), imgui.get_color_u32((0.2, 0.7, 0.2, 1.0)))

        draw_list.add_line((mid_x, p.y - 3), (mid_x, p.y + slider_h + 3), imgui.get_color_u32((0.4, 0.4, 0.4, 1.0)), 2.0)
        draw_list.add_rect(p, (p.x + slider_w, p.y + slider_h), imgui.get_color_u32((0.0, 0.0, 0.0, 1.0)))
        draw_list.add_rect_filled((alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), imgui.get_color_u32((0.9, 0.9, 0.9, 1.0)))
        draw_list.add_rect((alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), imgui.get_color_u32((0.0, 0.0, 0.0, 1.0)))

        imgui.same_line()
        Prims.right_align_text(self._fmt_short_money(value), GAMETHEME.colors.text_main)