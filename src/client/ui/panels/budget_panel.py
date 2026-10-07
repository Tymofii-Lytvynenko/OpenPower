import math

import polars as pl
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.shared.actions import ActionUpdateBudget


class BudgetPanel:
    """
    Detailed National Budget Menu.
    Uses real data from the simulation and allows interaction for the player's country.
    """
    ROW_DETAILS = {
        "income-tax": (
            "Annual income-tax revenue, calculated from GDP, human development, "
            "and the effective personal tax rate."
        ),
        "income-trade": "Annual public revenue recorded by the global trade market.",
        "fixed-security": "Recurring security-services expenditure recorded for this country.",
        "fixed-diplomacy": "Diplomatic aid and treaty-maintenance expenditure recorded for this country.",
        "fixed-trade": "Government trade-import and trade-agreement expenditure recorded for this country.",
        "fixed-military-upkeep": (
            "Annual military operating costs based on force size, readiness, "
            "and active design maintenance."
        ),
    }
    PERSONAL_INCOME_TAX_KEY = "personal_income_tax_rate"

    def __init__(self):
        self.K_BUDGET = 0.15
        self.PERSONAL_INCOME_TAX_CONSTANT = 3.0
        
        # Mapping of column names to UI labels
        self.M_SECTOR_LABELS = {
            "budget_health_ratio": "HEALTH CARE",
            "budget_edu_ratio": "EDUCATION",
            "budget_social_ratio": "SOCIAL SUPPORT",
            "budget_gov_ratio": "GOVERNMENT",
            "budget_env_ratio": "ENVIRONMENT",
            "budget_research_ratio": "RESEARCH",
            "budget_infra_ratio": "INFRASTRUCTURE",
            "budget_telecom_ratio": "TELECOM",
            "budget_imf_ratio": "FOREIGN AID (IMF)",
            "budget_propaganda_ratio": "PROPAGANDA",
            "budget_tourism_promo_ratio": "TOURISM"
        }
        
        # Sector multipliers from BudgetSystem
        self.M_SECTOR_WEIGHTS = {
            "budget_health_ratio": 0.25,
            "budget_edu_ratio": 0.23,
            "budget_social_ratio": 0.15,
            "budget_gov_ratio": 0.14,
            "budget_env_ratio": 0.10,
            "budget_research_ratio": 0.09,
            "budget_infra_ratio": 0.07,
            "budget_telecom_ratio": 0.04,
            "budget_imf_ratio": 0.04,
            "budget_propaganda_ratio": 0.03,
            "budget_tourism_promo_ratio": 0.01
        }
        
        self.allocations = {k: 0.50 for k in self.M_SECTOR_LABELS.keys()}
        self.allocations[self.PERSONAL_INCOME_TAX_KEY] = 0.20
        self.draft_allocations = self.allocations.copy()
        
        self.REQUIREMENT_THRESHOLD = 0.50
        self.show_close_confirm = False
        self.current_tag = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        target_tag = context.target_tag
        is_own = context.is_own_country
        net_client = context.net_client

        # Sync with state if country changed
        if target_tag != self.current_tag:
            self._sync_with_state(state, target_tag)
            self.current_tag = target_tag

        flags = imgui.WindowFlags_.menu_bar
        
        with WindowManager.window("BUDGET MENU", x=300, y=100, w=480, h=780, flags=flags) as is_open:
            has_changes = self.draft_allocations != self.allocations

            # 1. Capture close signal
            if not is_open and not self.show_close_confirm: 
                if has_changes:
                    self.show_close_confirm = True 
                else:
                    return False

            # 2. Rendering the Menu Bar for window actions
            if imgui.begin_menu_bar():
                avail_w = imgui.get_content_region_avail().x
                imgui.dummy((max(0.0, avail_w - 32.0), 0))
                
                if has_changes and is_own:
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_main)
                    imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.interaction_active)
                    imgui.push_style_color(imgui.Col_.button_hovered, GAMETHEME.colors.accent)
                else:
                    imgui.begin_disabled()
                    imgui.push_style_color(imgui.Col_.text, GAMETHEME.colors.text_dim)
                    imgui.push_style_color(imgui.Col_.button, (0, 0, 0, 0))

                if imgui.button("apply"):
                    if net_client and is_own:
                        self._dispatch_budget_update(net_client, target_tag)

                imgui.pop_style_color(2)
                if has_changes and is_own:
                    imgui.pop_style_color()
                else:
                    imgui.end_disabled()
                    
                imgui.end_menu_bar()

            # 3. Content
            self._render_content(state, target_tag, is_own)

            # 4. Confirmation Modal
            if self.show_close_confirm:
                imgui.open_popup("Unsaved Changes##Budget")
                
            if self._render_close_modal():
                return False

            return True

    def _sync_with_state(self, state, target_tag):
        if "countries" not in state.tables: return
        df = state.get_table("countries").filter(pl.col("id") == target_tag)
        if df.is_empty(): return
        
        row = df.to_dicts()[0]
        for col in (*self.M_SECTOR_LABELS.keys(), self.PERSONAL_INCOME_TAX_KEY):
            if col in row:
                fallback = 0.20 if col == self.PERSONAL_INCOME_TAX_KEY else 0.50
                self.allocations[col] = self._bounded_ratio(row[col], fallback)
        
        self.draft_allocations = self.allocations.copy()

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

    def _get_player_total_demand(self, state, target_tag) -> float:
        if "resource_ledger" not in state.tables: return 0.0
        country_ledger = state.get_table("resource_ledger").filter(pl.col("country_id") == target_tag)
        if country_ledger.is_empty(): return 0.0
        return country_ledger["consumption_usd"].sum()

    def _render_content(self, state, target_tag, is_own):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))
        total_demand = self._get_player_total_demand(state, target_tag)

        # Get country data for income and fixed expenses
        country_row = {}
        if "countries" in state.tables:
            df = state.get_table("countries").filter(pl.col("id") == target_tag)
            if not df.is_empty():
                country_row = df.to_dicts()[0]

        # 1. INCOME
        revenue_tax = country_row.get("revenue_tax", 0.0)
        trade_income = country_row.get("trade_income", 0.0)
        tourism_income = country_row.get("tourism_income", 0.0)
        budget_imf_ratio = country_row.get("budget_imf_ratio", 0.0)
        total_income = country_row.get("total_annual_revenue", revenue_tax + trade_income + tourism_income + budget_imf_ratio)

        Prims.header("INCOME", show_bg=False)
        self._draw_total_bar("TOTAL", total_income, GAMETHEME.colors.positive)
        self._draw_standard_row(
            "PERSONAL INCOME TAX", revenue_tax, has_more=True, detail_key="income-tax"
        )
        self._draw_income_tax_slider(is_own)
        self._draw_standard_row("TRADE", trade_income, has_more=True, detail_key="income-trade")
        self._draw_standard_row("TOURISM", tourism_income)
        if budget_imf_ratio > 0:
            self._draw_standard_row("IMF AID", budget_imf_ratio)
        imgui.dummy((0, 5))

        # 2. SECTOR EXPENSES (Dynamic Preview)
        total_expense_dynamic = sum(
            total_demand * self.K_BUDGET * self.M_SECTOR_WEIGHTS[col] * self.draft_allocations[col]
            for col in self.M_SECTOR_LABELS.keys()
        )
        
        Prims.header("EXPENSES", show_bg=False)
        self._draw_total_bar("TOTAL", total_expense_dynamic, GAMETHEME.colors.negative)
        
        # Define UI order
        ui_order = [
            "budget_infra_ratio", "budget_propaganda_ratio", "budget_env_ratio", "budget_health_ratio", 
            "budget_edu_ratio", "budget_telecom_ratio", "budget_gov_ratio", "budget_imf_ratio", 
            "budget_research_ratio", "budget_tourism_promo_ratio", "budget_social_ratio"
        ]
                    
        for col in ui_order:
            label = self.M_SECTOR_LABELS[col]
            preview_cost = total_demand * self.K_BUDGET * self.M_SECTOR_WEIGHTS[col] * self.draft_allocations[col]
            self._draw_expense_slider(col, label, preview_cost, is_own)
            
        imgui.dummy((0, 5))

        # 3. FIXED EXPENSES
        expense_corruption = country_row.get("expense_corruption", 0.0)
        security_upkeep = country_row.get("security_upkeep", 0.0)
        diplomacy_upkeep = country_row.get("diplomacy_upkeep", 0.0)
        trade_expense = country_row.get("trade_expense", 0.0)
        military_upkeep = country_row.get("expense_military_upkeep", 0.0)
        debt_interest = country_row.get("expense_debt_interest", 0.0)
        
        total_fixed = (expense_corruption + security_upkeep + diplomacy_upkeep + 
                       trade_expense + military_upkeep + debt_interest)

        Prims.header("FIXED EXPENSES", show_bg=False)
        self._draw_total_bar("TOTAL", total_fixed, GAMETHEME.colors.negative)
        self._draw_standard_row("SECURITY", security_upkeep, has_more=True, detail_key="fixed-security")
        self._draw_standard_row("DIPLOMACY", diplomacy_upkeep, has_more=True, detail_key="fixed-diplomacy")
        self._draw_standard_row("TRADE", trade_expense, has_more=True, detail_key="fixed-trade")
        self._draw_standard_row(
            "MILITARY UPKEEP", military_upkeep, has_more=True, detail_key="fixed-military-upkeep"
        )
        self._draw_standard_row("DEBT INTEREST", debt_interest)
        self._draw_standard_row("CORRUPTION", expense_corruption)
        imgui.dummy((0, 5))

        # 4. SUMMARY
        total_expenses = total_expense_dynamic + total_fixed
        surplus = total_income - total_expenses
        money_reserves = country_row.get("money_reserves", 0.0)

        Prims.header("SURPLUS / DEFICIT", show_bg=False)
        self._draw_total_bar("", surplus, GAMETHEME.colors.positive if surplus >= 0 else GAMETHEME.colors.negative, hide_label=True)
        imgui.dummy((0, 5))

        Prims.header("AVAILABLE FUNDS", show_bg=False)
        self._draw_total_bar("", money_reserves, GAMETHEME.colors.positive if money_reserves >= 0 else GAMETHEME.colors.negative, hide_label=True)

        imgui.pop_style_var()

    # Helpers
    def _fmt_money(self, val: float) -> str:
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(val):,.0f}".replace(",", " ")

    def _fmt_short_money(self, val: float) -> str:
        abs_val = abs(val)
        if abs_val >= 1_000_000_000: return f"$ {abs_val / 1_000_000_000:,.1f} B".replace(",", " ")
        elif abs_val >= 1_000_000: return f"$ {abs_val / 1_000_000:,.1f} M".replace(",", " ")
        return self._fmt_money(val)

    def _draw_standard_row(
        self,
        label: str,
        value: float,
        has_more: bool = False,
        detail_key: str | None = None,
    ):
        imgui.text(label)
        if has_more and detail_key in self.ROW_DETAILS:
            imgui.same_line(180)
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (6, 1))
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_input)
            popup_id = f"Budget details##{detail_key}"
            if imgui.button(f"more##{detail_key}"):
                imgui.open_popup(popup_id)
            imgui.pop_style_color()
            imgui.pop_style_var()
            if imgui.begin_popup(popup_id):
                imgui.text_wrapped(self._standard_row_details(detail_key, value))
                imgui.end_popup()
        Prims.right_align_text(self._fmt_money(value), GAMETHEME.colors.text_main)

    def _standard_row_details(self, detail_key: str, value: float) -> str:
        description = self.ROW_DETAILS.get(detail_key)
        if description is None:
            description = "Additional information is not available for this budget row."
        return f"{description}\nCurrent recorded amount: {self._fmt_money(value)}"

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

    def _draw_expense_slider(self, col: str, label: str, value: float, is_own: bool):
        imgui.text(label)
        imgui.same_line(180)

        alloc_pct = self.draft_allocations.get(col, 0.5)

        p = imgui.get_cursor_screen_pos()
        slider_w = 120.0
        slider_h = 14.0
        
        if not is_own: imgui.begin_disabled()
        
        imgui.invisible_button(f"##drag_{col}", (slider_w, slider_h))
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            new_pct = max(0.0, min((mouse_x - p.x) / slider_w, 1.0))
            
            if 0.48 <= new_pct <= 0.52:
                new_pct = self.REQUIREMENT_THRESHOLD
                
            self.draft_allocations[col] = new_pct
            alloc_pct = new_pct

        if not is_own: imgui.end_disabled()

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

    def _draw_income_tax_slider(self, is_own: bool) -> None:
        key = self.PERSONAL_INCOME_TAX_KEY
        current = self.draft_allocations[key]
        imgui.set_next_item_width(220)
        if not is_own:
            imgui.begin_disabled()
        changed, percentage = imgui.slider_float(
            "PERSONAL INCOME TAX RATE", current * 100.0, 0.0, 100.0, "%.0f%%"
        )
        if not is_own:
            imgui.end_disabled()
        if changed:
            self.draft_allocations[key] = self._bounded_ratio(percentage / 100.0, current)

    def _dispatch_budget_update(self, net_client, country_tag: str) -> None:
        action = ActionUpdateBudget(
            player_id=net_client.player_id,
            country_tag=country_tag,
            allocations={
                key: self._bounded_ratio(value, self.allocations.get(key, 0.0))
                for key, value in self.draft_allocations.items()
            },
        )
        net_client.send_action(action)
        self.allocations = action.allocations.copy()
        self.draft_allocations = self.allocations.copy()

    @staticmethod
    def _bounded_ratio(value, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            number = fallback
        if not math.isfinite(number):
            number = fallback
        return max(0.0, min(number, 1.0))
