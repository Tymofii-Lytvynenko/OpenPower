from imgui_bundle import imgui
from src.client.ui.panels.base_panel import BasePanel
from src.client.ui.composer import UIComposer
from src.client.ui.theme import GAMETHEME

class MilitaryPanel(BasePanel):
    def __init__(self):
        super().__init__("MILITARY", x=260, y=100, w=250, h=520)

    def _render_content(self, composer: UIComposer, state, **kwargs):
        # Context Data
        target_tag = kwargs.get("target_tag", "")
        is_own = kwargs.get("is_own_country", False)

        # 1. Conventional Forces (Visible for all, effectively 'Intel')
        composer.draw_section_header("CONVENTIONAL FORCES")
        
        table_flags = (imgui.TableFlags_.borders_inner_h | 
                        imgui.TableFlags_.pad_outer_x)
                        
        if imgui.begin_table("MilTable", 3, table_flags):
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_fixed, 80)
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("RANK", imgui.TableColumnFlags_.width_fixed, 40)
            
            # NOTE: In the future, these numbers could be "estimates" if is_own is False
            self._draw_row("SOLDIER", "60 768", "30")
            self._draw_row("LAND", "4 262", "32")
            self._draw_row("AIR", "270", "37")
            self._draw_row("NAVAL", "20", "50")
            
            imgui.end_table()

        imgui.dummy((0, 5))
        
        # 2. Action Buttons (Hidden if not own country)
        if is_own:
            avail_w = imgui.get_content_region_avail().x
            btn_w = (avail_w - 5) / 2
            
            imgui.button("BUY", (btn_w, 0))
            imgui.same_line()
            imgui.button("BUILD", (btn_w, 0))
            
            imgui.button("RESEARCH", (btn_w, 0))
            imgui.same_line()
            imgui.button("DESIGN", (btn_w, 0))
            
            imgui.button("DEPLOY", (-1, 0)) 
            imgui.dummy((0, 10))
        else:
            imgui.text_disabled("[Actions Restricted]")
            imgui.dummy((0, 10))

        # 3. Strategic Forces
        composer.draw_section_header("STRATEGIC FORCES", show_more_btn=False)
        imgui.dummy((0, 25))
        
        if is_own:
            last_y = imgui.get_cursor_pos_y()
            imgui.set_cursor_pos_y(last_y - 28)
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            imgui.button("RESEARCH##strat", (90, 0))
        else:
            imgui.text_colored(GAMETHEME.col_text_disabled, "Classified Intel")
        
        # 4. Missile Defense
        composer.draw_section_header("MISSILE DEFENSE", show_more_btn=False)
        imgui.text_colored(GAMETHEME.col_negative, "N/A")
        
        if is_own:
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            imgui.button("RESEARCH##md", (90, 0))

        imgui.dummy((0, 15))
        
        # 5. Footer (Hide sensitive covert actions)
        if is_own:
            imgui.button("COVERT ACTIONS", (-1, 0))
            imgui.button("STRATEGIC WARFARE", (-1, 0))
            imgui.button("WAR LIST", (-1, 0))
        else:
            # Maybe show Espionage button instead?
            imgui.button("INITIATE ESPIONAGE", (-1, 0))

    def _draw_row(self, label, count, rank):
        imgui.table_next_row()
        imgui.table_next_column()
        imgui.text_disabled(label)
        imgui.table_next_column()
        
        txt_w = imgui.calc_text_size(count).x
        col_w = imgui.get_content_region_avail().x
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + col_w - txt_w)
        imgui.text(count)
        
        imgui.table_next_column()
        imgui.text_disabled(rank)