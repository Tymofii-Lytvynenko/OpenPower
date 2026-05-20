import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext


class EconomyPanel:
    def __init__(
        self,
        toggle_resources_cb=None,
        toggle_budget_cb=None,
        toggle_health_cb=None,
        toggle_trade_cb=None,
    ):
        self.toggle_resources_cb = toggle_resources_cb
        self.toggle_budget_cb = toggle_budget_cb
        self.toggle_health_cb = toggle_health_cb
        self.toggle_trade_cb = toggle_trade_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        # Matched width from screenshot proportions
        with WindowManager.window("ECONOMY", x=1600, y=100, w=280, h=480) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Economy Data ---
        revenue = 0.0
        expenses = 0.0
        reserves = 0.0
        eco_health = 0.0
        resources_health = self._get_resource_health(state, target_tag)
        market_model_val = self._get_market_model_value(state, target_tag)
        
        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    # Budget details
                    if "total_annual_revenue" in row.columns:
                        val_rev = row["total_annual_revenue"][0]
                        revenue = float(val_rev) if val_rev is not None else 0.0
                        
                    if "total_annual_expense" in row.columns:
                        val_exp = row["total_annual_expense"][0]
                        expenses = float(val_exp) if val_exp is not None else 0.0
                        
                    if "money_reserves" in row.columns:
                        val_res = row["money_reserves"][0]
                        reserves = float(val_res) if val_res is not None else 0.0
                        
                    if "economic_health" in row.columns:
                        val_eh = row["economic_health"][0]
                        eco_health = float(val_eh) if val_eh is not None else 0.0
            except Exception:
                pass

        balance = revenue - expenses

        # --- 2. Render UI ---
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        # ECONOMIC MODEL Section
        self._draw_header("ECONOMIC MODEL", "model_btn")
        
        imgui.push_style_color(imgui.Col_.frame_bg, imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)))
        imgui.push_style_color(imgui.Col_.slider_grab, imgui.get_color_u32((0.4, 0.8, 0.4, 1.0)))
        
        # This is intentionally read-only: policy changes happen through Resources.
        imgui.begin_disabled()
        imgui.set_next_item_width(-1)
        imgui.slider_float("##eco_model", market_model_val, 0.0, 1.0, "")
        imgui.end_disabled()
        
        imgui.pop_style_color(2)
        
        imgui.text_disabled("State-Controlled")
        imgui.same_line()
        Prims.right_align_text("Free Market", GAMETHEME.colors.text_dim)
        imgui.dummy((0, 5))

        # ECONOMIC HEALTH Section
        self._draw_header("ECONOMIC HEALTH", "health_btn", callback=self.toggle_health_cb)
        self._draw_meter_row(eco_health)
        imgui.dummy((0, 5))

        # BUDGET Section
        self._draw_header("BUDGET", "budget_btn", callback=self.toggle_budget_cb)
        self._draw_value_box("INCOME", revenue)
        self._draw_value_box("EXPENSES", expenses)
        self._draw_value_box("BALANCE", balance)
        self._draw_value_box("AVAILABLE", reserves, is_available=True)
        imgui.dummy((0, 5))

        # RESOURCES Section
        self._draw_header("RESOURCES", "resources_btn", callback=self.toggle_resources_cb)
        self._draw_meter_row(resources_health, has_plus=True)
        imgui.dummy((0, 15))

        # TRADE Button
        imgui.push_style_color(imgui.Col_.button, imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)))
        imgui.push_style_color(imgui.Col_.button_hovered, imgui.get_color_u32((0.25, 0.25, 0.25, 1.0)))
        if imgui.button("TRADE", (-1, 28)) and self.toggle_trade_cb:
            self.toggle_trade_cb()
        imgui.pop_style_color(2)

        imgui.pop_style_var()

    def _get_market_model_value(self, state, target_tag) -> float:
        """Returns the free-market share of domestic production, using real production policy data."""
        if "domestic_production" not in state.tables:
            return 0.0

        try:
            df = state.get_table("domestic_production")
            if "country_id" not in df.columns or "domestic_production" not in df.columns:
                return 0.0

            target_df = df.filter(pl.col("country_id") == target_tag)
            if target_df.is_empty():
                return 0.0

            total = float(target_df["domestic_production"].sum() or 0.0)
            if total <= 0.0:
                return 0.0

            if "is_gov_controlled" not in target_df.columns:
                return 1.0

            gov_total = float(
                target_df
                .filter(pl.col("is_gov_controlled") == True)
                .select(pl.col("domestic_production").sum())
                .item()
                or 0.0
            )
            return max(0.0, min(1.0, 1.0 - (gov_total / total)))
        except Exception:
            return 0.0

    def _get_resource_health(self, state, target_tag) -> float:
        """Estimates demand coverage from the country resource ledger."""
        if "resource_ledger" not in state.tables:
            return 0.0

        try:
            ledger = state.get_table("resource_ledger")
            if "country_id" not in ledger.columns:
                return 0.0

            country_ledger = ledger.filter(pl.col("country_id") == target_tag)
            if country_ledger.is_empty() or "consumption_usd" not in country_ledger.columns:
                return 0.0

            consumption = float(country_ledger["consumption_usd"].sum() or 0.0)
            if consumption <= 0.0:
                return 1.0

            if "balance_usd" not in country_ledger.columns:
                return 1.0

            shortage = abs(float(
                country_ledger
                .filter(pl.col("balance_usd") < 0)
                .select(pl.col("balance_usd").sum())
                .item()
                or 0.0
            ))
            return max(0.0, min(1.0, 1.0 - (shortage / consumption)))
        except Exception:
            return 0.0

    # =========================================================================
    # Helpers & Custom Drawing Routines for exact screenshot matching
    # =========================================================================

    def _fmt_money(self, val: float) -> str:
        """Formats numbers with space separators and specific negative formatting."""
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(val):,.0f}".replace(",", " ")

    def _draw_header(self, title: str, btn_id: str, callback=None):
        """Draws a section header with an optional right-aligned 'more' button."""
        imgui.text(title)
        
        if callback is not None:
            # Right-aligned small button
            imgui.same_line(imgui.get_window_width() - 55)
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (4, 1))
            imgui.push_style_color(imgui.Col_.button, imgui.get_color_u32((0.2, 0.2, 0.2, 1.0)))
            
            if imgui.button(f"more##{btn_id}"):
                callback()
                
            imgui.pop_style_color()
            imgui.pop_style_var()
            
        # Draw underline separator manually to control spacing
        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        draw_list = imgui.get_window_draw_list()
        draw_list.add_line((p.x, p.y), (p.x + avail_w, p.y), imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)), 2.0)
        imgui.dummy((0, 4))

    def _draw_value_box(self, label: str, value: float, is_available: bool = False):
        """Draws a budget row with a left label and a dark background box for the right-aligned value."""
        imgui.text(label)
        imgui.same_line(85)  # Fixed offset so all value boxes align vertically
        
        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        h = 18.0
        
        draw_list = imgui.get_window_draw_list()
        
        # Dark fill
        draw_list.add_rect_filled(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.12, 0.12, 0.12, 1.0))
        )
        # Inner black border
        draw_list.add_rect(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        )
        imgui.dummy((avail_w, h))
        
        # Overlay the formatted text
        imgui.same_line()
        color = GAMETHEME.colors.text_main
        if is_available and value < 0:
            color = GAMETHEME.colors.negative
            
        val_str = self._fmt_money(value)
        Prims.right_align_text(val_str, color)

    def _draw_meter_row(self, percentage: float, has_plus=False):
        """Draws a percentage text followed by a custom green gradient progress bar."""
        percentage = max(0.0, min(float(percentage), 1.0))
        pct_str = f"{percentage * 100:.1f} %"
        if percentage >= 1.0:
            pct_str = "100 %"
            
        imgui.text(pct_str)
        imgui.same_line(65)
        
        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        h = 14.0
        
        draw_list = imgui.get_window_draw_list()
        
        # Background box (Dark)
        draw_list.add_rect_filled(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.15, 0.15, 0.15, 1.0))
        )
        
        # Fill (Green)
        fill_w = avail_w * percentage
        if fill_w > 0:
            # Simulating the gradient/bright green from screenshot
            draw_list.add_rect_filled(
                p, (p.x + fill_w, p.y + h), 
                imgui.get_color_u32((0.3, 0.6, 0.2, 1.0)) 
            )
            
        # Draw the black border
        draw_list.add_rect(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.0, 0.0, 0.0, 1.0))
        )
        
        # Add the tiny '+' character for the resources bar
        if has_plus:
            imgui.set_cursor_screen_pos((p.x + avail_w - 15, p.y - 1))
            imgui.text("+")
            
        imgui.set_cursor_screen_pos((p.x, p.y + h))
