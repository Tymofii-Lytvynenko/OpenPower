from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager

class MilitaryPanel:
    def render(self, state, **kwargs) -> bool:
        # Extract context
        is_own = kwargs.get("is_own_country", False)
        
        # Use Composition for Window Management
        with WindowManager.window("MILITARY", x=260, y=100, w=250, h=520) as is_open:
            if not is_open: return False
            self._render_content(state, is_own)
            return True

    def _render_content(self, state, is_own):
        # 1. Conventional Forces (Visible for all, effectively 'Intel')
        Prims.header("CONVENTIONAL FORCES")
        
        table_flags = (imgui.TableFlags_.borders_inner_h | 
                       imgui.TableFlags_.pad_outer_x)
                       
        if imgui.begin_table("MilTable", 3, table_flags):
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_fixed, 80)
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("RANK", imgui.TableColumnFlags_.width_fixed, 40)
            
            # Data rows (Hardcoded as per original code)
            self._draw_row("SOLDIER", "60 768", "30")
            self._draw_row("LAND", "4 262", "32")
            self._draw_row("AIR", "270", "37")
            self._draw_row("NAVAL", "20", "50")
            
            imgui.end_table()

        imgui.dummy((0, 5))
        
        # 2. Action Buttons (Hidden if not own country)
        if is_own:
            avail_w = imgui.get_content_region_avail().x
            # 2 buttons per row, small gap
            btn_w = (avail_w - imgui.get_style().item_spacing.x) / 2
            
            if imgui.button("BUY", (btn_w, 0)): pass
            imgui.same_line()
            if imgui.button("BUILD", (btn_w, 0)): pass
            
            if imgui.button("RESEARCH", (btn_w, 0)): pass
            imgui.same_line()
            if imgui.button("DESIGN", (btn_w, 0)): pass
            
            if imgui.button("DEPLOY", (-1, 0)): pass
            imgui.dummy((0, 10))
        else:
            imgui.text_disabled("[Actions Restricted]")
            imgui.dummy((0, 10))

        # 3. Strategic Forces
        Prims.header("STRATEGIC FORCES")
        # Header adds some spacing, but we want the button near it or below it
        
        if is_own:
            # Right-aligned 'Research' button for this section
            Prims.right_align_text("RESEARCH", color=None) # Just calculating pos
            # Actually draw the button manually to ensure it's clickable
            # (Re-calculating position for button)
            imgui.same_line()
            current_x = imgui.get_cursor_pos_x()
            imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() - 30) # Move up into header line roughly
            Prims.right_align_text("       ") # Spacer
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            if imgui.button("RESEARCH##strat", (90, 20)): pass
            imgui.dummy((0, 5))
        else:
            imgui.text_colored(GAMETHEME.colors.text_dim, "Classified Intel")
            imgui.dummy((0, 10))
        
        # 4. Missile Defense
        Prims.header("MISSILE DEFENSE")
        imgui.text_colored(GAMETHEME.colors.negative, "N/A")
        
        if is_own:
            imgui.same_line()
            # Right align the button
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            if imgui.button("RESEARCH##md", (90, 0)): pass

        imgui.dummy((0, 15))
        
        # 5. Footer (Hide sensitive covert actions)
        if is_own:
            if imgui.button("COVERT ACTIONS", (-1, 0)): pass
            if imgui.button("STRATEGIC WARFARE", (-1, 0)): pass
            if imgui.button("WAR LIST", (-1, 0)): pass
        else:
            if imgui.button("INITIATE ESPIONAGE", (-1, 0)): pass

    def _draw_row(self, label, count, rank):
        imgui.table_next_row()
        
        # Column 1: Label
        imgui.table_next_column()
        imgui.text_disabled(label)
        
        # Column 2: Count (Right Aligned)
        imgui.table_next_column()
        Prims.right_align_text(count)
        
        # Column 3: Rank
        imgui.table_next_column()
        imgui.text_disabled(rank)