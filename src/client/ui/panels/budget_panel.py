import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class BudgetPanel:
    """
    Detailed National Budget Panel.
    Manages state revenue, discretionary expenses, and fixed upkeep costs.
    """
    def __init__(self):
        # 1. State for interactive sliders (Stored as percentages 0.0 - 1.0)
        # In a full implementation, these would sync to GameState actions.
        self.allocations = {
            "INFRASTRUCTURE": 0.65,
            "PROPAGANDA": 0.40,
            "ENVIRONMENT": 0.55,
            "HEALTH CARE": 0.85,
            "EDUCATION": 0.45,
            "TELECOM": 0.55,
            "GOVERNMENT": 0.40,
            "FOREIGN AID": 0.20,
            "RESEARCH": 0.85,
            "TOURISM": 0.90
        }
        
        # Red represents the baseline/minimum required percentage before penalties
        self.requirements = {
            "INFRASTRUCTURE": 0.40,
            "PROPAGANDA": 0.35,
            "ENVIRONMENT": 0.40,
            "HEALTH CARE": 0.40,
            "EDUCATION": 0.40,
            "TELECOM": 0.40,
            "GOVERNMENT": 0.38,
            "FOREIGN AID": 0.15,
            "RESEARCH": 0.40,
            "TOURISM": 0.40
        }

    def render(self, state, **kwargs) -> bool:
        # Match standard window styling but size appropriately for the dense layout
        with WindowManager.window("BUDGET", x=300, y=100, w=480, h=750) as is_open:
            if not is_open: 
                return False
            self._render_content(state)
            return True

    def _render_content(self, state):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        # --- INCOME SECTION ---
        Prims.header("INCOME")
        self._draw_total_bar("TOTAL", 168073420861, GAMETHEME.colors.positive)
        self._draw_standard_row("PERSONNAL INCOME TAX", 128131699398, has_more=True)
        self._draw_standard_row("TRADE", 37533665787, has_more=True)
        self._draw_standard_row("TOURISM", 2408055675)
        self._draw_standard_row("FOREIGN AID", 0)
        imgui.dummy((0, 5))

        # --- EXPENSES SECTION ---
        Prims.header("EXPENSES")
        self._draw_total_bar("TOTAL", 208688412331, GAMETHEME.colors.negative)
        
        # Draw interactive allocation sliders
        self._draw_expense_slider("INFRASTRUCTURE", 16_000_000_000)
        self._draw_expense_slider("PROPAGANDA", 2_542_000_000)
        self._draw_expense_slider("ENVIRONMENT", 16_000_000_000)
        self._draw_expense_slider("HEALTH CARE", 82_000_000_000)
        self._draw_expense_slider("EDUCATION", 35_000_000_000)
        self._draw_expense_slider("TELECOM", 6_739_000_000)
        self._draw_expense_slider("GOVERNMENT", 13_000_000_000)
        self._draw_expense_slider("FOREIGN AID", 1_238_000_000)
        self._draw_expense_slider("RESEARCH", 30_000_000_000)
        self._draw_expense_slider("TOURISM", 3_715_000_000)
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
        """Formats numbers with space separators as seen in the original UI."""
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(val):,.0f}".replace(",", " ")

    def _fmt_short_money(self, val: float) -> str:
        """Abbreviates large numbers into Billions (B) or Millions (M)."""
        abs_val = abs(val)
        if abs_val >= 1_000_000_000:
            return f"$ {abs_val / 1_000_000_000:,.0f} B".replace(",", " ")
        elif abs_val >= 1_000_000:
            return f"$ {abs_val / 1_000_000:,.0f} M".replace(",", " ")
        return self._fmt_money(val)

    def _draw_standard_row(self, label: str, value: float, has_more: bool = False):
        """Draws a standard line item (Label, optional 'more' button, Right-aligned value)."""
        imgui.text(label)
        
        if has_more:
            imgui.same_line(180)
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (6, 1))
            imgui.push_style_color(imgui.Col_.button, GAMETHEME.colors.bg_input)
            
            if imgui.button(f"more##{label}"):
                pass # TODO: Open detailed breakdown panel for this category
                
            imgui.pop_style_color()
            imgui.pop_style_var()

        val_str = self._fmt_money(value)
        Prims.right_align_text(val_str, GAMETHEME.colors.text_main)

    def _draw_total_bar(self, label: str, value: float, color: tuple, hide_label: bool = False):
        """Draws the dark grey central bar with the total value inside/next to it."""
        if not hide_label:
            imgui.text(label)
            imgui.same_line(180)
        else:
            imgui.set_cursor_pos_x(180)

        # Draw the dark background block
        p = imgui.get_cursor_screen_pos()
        avail_w = imgui.get_content_region_avail().x
        h = 18.0
        
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            p, (p.x + avail_w, p.y + h), 
            imgui.get_color_u32((0.12, 0.12, 0.12, 1.0))
        )
        imgui.dummy((avail_w, h))

        # Render the text over the background block, right-aligned
        val_str = self._fmt_money(value)
        imgui.same_line()
        Prims.right_align_text(val_str, color)

    def _draw_expense_slider(self, label: str, value: float):
        """
        Draws the iconic dual-color budget slider.
        Red indicates minimum required funding, Green indicates discretionary surplus.
        """
        imgui.text(label)
        imgui.same_line(180)

        req_pct = self.requirements.get(label, 0.2)
        alloc_pct = self.allocations.get(label, 0.5)

        # Interactive slider setup
        p = imgui.get_cursor_screen_pos()
        slider_w = 120.0
        slider_h = 14.0
        
        # We must use an invisible button to capture mouse interactions for the custom drawn slider
        imgui.invisible_button(f"##drag_{label}", (slider_w, slider_h))
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            # Calculate new percentage based on mouse position relative to the slider
            new_pct = max(0.0, min((mouse_x - p.x) / slider_w, 1.0))
            self.allocations[label] = new_pct
            alloc_pct = new_pct

        draw_list = imgui.get_window_draw_list()
        
        # 1. Base Track (Dark Grey)
        draw_list.add_rect_filled(
            p, (p.x + slider_w, p.y + slider_h), 
            imgui.get_color_u32((0.15, 0.15, 0.15, 1.0)), 2.0
        )

        # 2. Required Minimum (Deep Red)
        red_w = slider_w * req_pct
        draw_list.add_rect_filled(
            p, (p.x + red_w, p.y + slider_h), 
            imgui.get_color_u32((0.6, 0.2, 0.2, 1.0)), 2.0
        )

        # 3. Discretionary Allocation (Green)
        # Only draws if the user allocates more than the minimum required
        if alloc_pct > req_pct:
            alloc_w = slider_w * alloc_pct
            draw_list.add_rect_filled(
                (p.x + red_w, p.y), (p.x + alloc_w, p.y + slider_h), 
                imgui.get_color_u32((0.3, 0.7, 0.4, 1.0)), 2.0
            )
        elif alloc_pct > 0:
            # If underfunded, the allocated portion is drawn over the red track
            alloc_w = slider_w * alloc_pct
            draw_list.add_rect_filled(
                p, (p.x + alloc_w, p.y + slider_h), 
                imgui.get_color_u32((0.4, 0.2, 0.2, 1.0)), 2.0
            )

        # 4. Marker/Thumb (White Line)
        thumb_x = p.x + (slider_w * alloc_pct)
        draw_list.add_rect_filled(
            (thumb_x - 1, p.y - 1), (thumb_x + 1, p.y + slider_h + 1), 
            imgui.get_color_u32((0.9, 0.9, 0.9, 1.0))
        )

        # 5. Right Aligned Value
        imgui.same_line()
        val_str = self._fmt_short_money(value)
        Prims.right_align_text(val_str, GAMETHEME.colors.text_main)