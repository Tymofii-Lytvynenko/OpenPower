import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class EconomyPanel:
    def __init__(self, toggle_resources_cb=None, toggle_budget_cb=None):
        self.toggle_resources_cb = toggle_resources_cb
        self.toggle_budget_cb = toggle_budget_cb
        
        # Local UI state
        self.eco_model_val = 0.95  # Default towards Free Market as in screenshot

    def render(self, state, **kwargs) -> bool:
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        # Matched width from screenshot proportions
        with WindowManager.window("ECONOMY", x=1600, y=100, w=280, h=480) as is_open:
            if not is_open: return False
            self._render_content(state, target_tag, is_own)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Economy Data ---
        revenue = 0.0
        expenses = 0.0
        reserves = 0.0
        eco_health = 0.836  # Default fallback 83.6%
        resources_health = 1.0  # Default fallback 100%
        
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
                        eco_health = float(val_eh) if val_eh is not None else 0.836
            except Exception:
                pass

        balance = revenue - expenses

        # --- 2. Render UI ---
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        # ECONOMIC MODEL Section
        self._draw_header("ECONOMIC MODEL", "model_btn")
        
        imgui.push_style_color(imgui.Col_.frame_bg, imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)))
        imgui.push_style_color(imgui.Col_.slider_grab, imgui.get_color_u32((0.4, 0.8, 0.4, 1.0)))
        
        if not is_own: imgui.begin_disabled()
        
        # Slider without label
        imgui.set_next_item_width(-1)
        _, self.eco_model_val = imgui.slider_float("##eco_model", self.eco_model_val, 0.0, 1.0, "")
        
        if not is_own: imgui.end_disabled()
        imgui.pop_style_color(2)
        
        imgui.text_disabled("State-Controlled")
        imgui.same_line()
        Prims.right_align_text("Free Market", GAMETHEME.colors.text_dim)
        imgui.dummy((0, 5))

        # ECONOMIC HEALTH Section
        self._draw_header("ECONOMIC HEALTH", "health_btn", callback=lambda: None)  # Mock callback for visual 'more' button
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
        if imgui.button("TRADE", (-1, 28)):
            pass # TODO: Implement Trade Window toggle
        imgui.pop_style_color(2)

        imgui.pop_style_var()

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
        fill_w = avail_w * max(0.0, min(percentage, 1.0))
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