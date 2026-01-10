from imgui_bundle import imgui
from src.client.ui.composer import UIComposer

class MilitaryPanel:
    def render(self, composer: UIComposer, state):
        # Position: Left-Center (offset from Politics)
        # We use a unique name "MILITARY" so ImGui tracks it separately
        expanded, _ = composer.begin_panel("MILITARY", 260, 100, 250, 520)
        
        if expanded:
            # 1. Conventional Forces
            composer.draw_section_header("CONVENTIONAL FORCES")
            
            # Table: 3 Columns [Type, Count, Rank]
            table_flags = (imgui.TableFlags_.borders_inner_h | 
                           imgui.TableFlags_.pad_outer_x)
                           
            if imgui.begin_table("MilTable", 3, table_flags):
                # Setup Headers
                imgui.table_setup_column("", imgui.TableColumnFlags_.width_fixed, 80)
                imgui.table_setup_column("", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("RANK", imgui.TableColumnFlags_.width_fixed, 40)
                
                # Rows
                self._draw_row("SOLDIER", "60 768", "30")
                self._draw_row("LAND", "4 262", "32")
                self._draw_row("AIR", "270", "37")
                self._draw_row("NAVAL", "20", "50")
                
                imgui.end_table()

            imgui.dummy((0, 5))
            
            # 2. Action Grid (2x2)
            avail_w = imgui.get_content_region_avail().x
            btn_w = (avail_w - 5) / 2
            
            imgui.button("BUY", (btn_w, 0))
            imgui.same_line()
            imgui.button("BUILD", (btn_w, 0))
            
            imgui.button("RESEARCH", (btn_w, 0))
            imgui.same_line()
            imgui.button("DESIGN", (btn_w, 0))
            
            # Full width Deploy
            imgui.button("DEPLOY", (-1, 0)) 

            imgui.dummy((0, 10))

            # 3. Strategic Forces
            composer.draw_section_header("STRATEGIC FORCES", show_more_btn=False)
            
            # Right aligned research button inside the section
            imgui.dummy((0, 25)) # Spacer
            last_y = imgui.get_cursor_pos_y()
            imgui.set_cursor_pos_y(last_y - 28)
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            imgui.button("RESEARCH##strat", (90, 0))
            
            # 4. Missile Defense
            composer.draw_section_header("MISSILE DEFENSE", show_more_btn=False)
            
            imgui.text_colored((0.8, 0.2, 0.2, 1.0), "N/A")
            
            imgui.same_line()
            imgui.set_cursor_pos_x(imgui.get_content_region_avail().x - 90)
            imgui.button("RESEARCH##md", (90, 0))

            imgui.dummy((0, 15))
            
            # 5. Footer Buttons
            imgui.button("COVERT ACTIONS", (-1, 0))
            imgui.button("STRATEGIC WARFARE", (-1, 0))
            imgui.button("WAR LIST", (-1, 0))

        composer.end_panel()

    def _draw_row(self, label, count, rank):
        imgui.table_next_row()
        
        # Col 1: Label
        imgui.table_next_column()
        imgui.text_disabled(label)
        
        # Col 2: Count
        imgui.table_next_column()
        txt_w = imgui.calc_text_size(count).x
        col_w = imgui.get_content_region_avail().x
        imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + col_w - txt_w)
        imgui.text(count)
        
        # Col 3: Rank
        imgui.table_next_column()
        imgui.text_disabled(rank)