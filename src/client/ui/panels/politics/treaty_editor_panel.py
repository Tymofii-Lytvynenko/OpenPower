from __future__ import annotations

import random
from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_required_tables


class TreatyEditorPanel:
    def __init__(self):
        self._presenter = PoliticsPresenter()
        # Mock data state
        self._type_idx = 0
        self._types = ["Economic partnership", "Military alliance", "Defensive pact"]
        self._name = "Asian Development Bank (AsDB)"
        self._desc = "- All members receive a bonus to their resource production. More productive countries generate a bigger bonus then the less productive ones."
        
        self._conditions = {
            "RELATIONS": 0, "GEOGRAPHIC PROXIMITY": 0, "POLITICAL SIMILITUDE": 0,
            "ECONOMIC STRENGTH": 0, "MILITARY STRENGTH": 0, "RESEARCH LEVEL": 0
        }
        self._condition_opts = ["No limit", "High", "Medium", "Low"]
        
        self._is_open_to_new = True
        
        # Mock active members
        self._members = [
            ("AFG", "Afghanistan", "Active"), ("AGO", "Angola", "Active"), ("ALB", "Albania", "Active"),
            ("AUT", "Austria", "Active"), ("AUS", "Australia", "Active"), ("AZE", "Azerbaijan", "Active"),
            ("BGD", "Bangladesh", "Active"), ("BEL", "Belgium", "Active"), ("MMR", "Myanmar", "Active"),
            ("BTN", "Bhutan", "Active"), ("BHR", "Bahrain", "Active"), ("BDI", "Burundi", "Active"),
            ("KHM", "Cambodia", "Active"), ("CAN", "Canada", "Active"), ("DNK", "Denmark", "Active"),
            ("CHN", "China", "Active"), ("FSM", "Micronesia", "Active"), ("FJI", "Fiji", "Active"),
            ("FIN", "Finland", "Active"), ("FRA", "France", "Active"), ("IND", "India", "Active"),
            ("DEU", "Germany", "Active"),
        ]

    def render(self, state, context: PanelRenderContext) -> bool:
        flags = imgui.WindowFlags_.no_collapse | imgui.WindowFlags_.no_scrollbar
        with WindowManager.window("Treaty Details", x=350, y=200, w=640, h=480, flags=flags) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country, context.net_client)
            return True

    def _render_content(self, state, country_tag: str, is_own_country: bool, net_client) -> None:
        draw_required_tables(state, ("countries_relations", "countries_treaties", "pending_treaties"))
        
        w = imgui.get_content_region_avail().x
        left_w = w * 0.55
        right_w = w - left_w - 8
        
        # --- LEFT PANEL ---
        imgui.begin_child("left_panel", (left_w, 0), False)
        
        with Prims.dark_child_box("top_left_box", -1, 140):
            self._type_idx = Prims.combo_row("TYPE", self._type_idx, self._types, 50)
            
            imgui.align_text_to_frame_padding()
            imgui.text_disabled("NAME")
            imgui.same_line(50)
            imgui.set_next_item_width(-1)
            _, self._name = imgui.input_text_multiline("##Name", self._name, (0, 30))
            
            imgui.dummy((0, 5))
            
            imgui.push_style_color(imgui.Col_.frame_bg, (0.05, 0.05, 0.05, 1.0))
            imgui.input_text_multiline("##Desc", self._desc, (-1, 50), imgui.InputTextFlags_.read_only)
            imgui.pop_style_color()
            
            # Draw "more" button inside the box
            old_pos = imgui.get_cursor_pos()
            imgui.set_cursor_pos((imgui.get_window_width() - 50, imgui.get_window_height() - 25))
            imgui.button("more", (40, 18))
            imgui.set_cursor_pos(old_pos)
        
        imgui.dummy((0, 5))
        
        # Members list
        with Prims.dark_child_box("members_list_box", -1, 180):
            if imgui.begin_table("members_table", 6, imgui.TableFlags_.scroll_y, (0, 140)):
                imgui.table_setup_column("F1", imgui.TableColumnFlags_.width_fixed, 20)
                imgui.table_setup_column("C1", imgui.TableColumnFlags_.width_fixed, 40)
                imgui.table_setup_column("S1", imgui.TableColumnFlags_.width_stretch)
                imgui.table_setup_column("F2", imgui.TableColumnFlags_.width_fixed, 20)
                imgui.table_setup_column("C2", imgui.TableColumnFlags_.width_fixed, 40)
                imgui.table_setup_column("S2", imgui.TableColumnFlags_.width_stretch)
                
                # Use fixed random seed to keep colors consistent between frames
                rng = random.Random(42)
                for i in range(0, len(self._members), 2):
                    imgui.table_next_row()
                    
                    # Col 1
                    m1 = self._members[i]
                    imgui.table_next_column()
                    imgui.color_button(f"##f{i}", (rng.random(), rng.random(), rng.random(), 1.0), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                    imgui.table_next_column()
                    imgui.text(m1[0])
                    imgui.table_next_column()
                    imgui.text(m1[2])
                    
                    # Col 2
                    if i + 1 < len(self._members):
                        m2 = self._members[i+1]
                        imgui.table_next_column()
                        imgui.color_button(f"##f{i+1}", (rng.random(), rng.random(), rng.random(), 1.0), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                        imgui.table_next_column()
                        imgui.text(m2[0])
                        imgui.table_next_column()
                        imgui.text(m2[2])
                        
                imgui.end_table()
                
            old_pos = imgui.get_cursor_pos()
            imgui.set_cursor_pos((imgui.get_window_width() - 80, imgui.get_window_height() - 30))
            imgui.button("JOIN", (70, 24))
            imgui.set_cursor_pos(old_pos)
            
        imgui.end_child()
        imgui.pop_style_color()
        
        imgui.dummy((0, 5))
        
        with Prims.dark_child_box("bottom_left_box", -1, 60):
            _, self._is_open_to_new = imgui.checkbox("Treaty is open to new members", self._is_open_to_new)
            imgui.dummy((0, 5))
            
            c_w = (imgui.get_window_width() - 16) / 2
            
            # Center the buttons
            imgui.set_cursor_pos_x((imgui.get_window_width() - (c_w * 2 + 8)) / 2)
            
            if imgui.button("CONFIRM", (c_w, 24)):
                pass
            imgui.same_line()
            if imgui.button("CANCEL", (c_w, 24)):
                pass
            
        imgui.end_child()
        
        imgui.same_line()
        
        # --- RIGHT PANEL ---
        imgui.begin_child("right_panel", (right_w, 0), False)
        
        imgui.text_colored(GAMETHEME.colors.text_main, "CONDITIONS")
        with Prims.dark_child_box("conditions_box", -1, 160):
            imgui.push_item_width(-1)
            for cond in self._conditions:
                self._conditions[cond] = Prims.combo_row(cond, self._conditions[cond], self._condition_opts, 150)
            imgui.pop_item_width()
        
        imgui.dummy((0, 5))
        
        imgui.text_colored(GAMETHEME.colors.text_main, "ELIGIBLE COUNTRIES")
        with Prims.dark_child_box("eligible_list", -1, 140):
            avail = imgui.get_content_region_avail().x
            items_per_row = max(1, int(avail / 70))
            
            rng = random.Random(123)
            for i, m in enumerate(self._members):
                imgui.color_button(f"##ef{i}", (rng.random(), rng.random(), rng.random(), 1.0), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                imgui.same_line(0, 4)
                imgui.text(m[0])
                if (i + 1) % items_per_row != 0 and i != len(self._members) - 1:
                    imgui.same_line(0, 10)
        imgui.end_child()
        
        imgui.dummy((0, 5))
        
        imgui.text_colored(GAMETHEME.colors.text_main, "PRESSURE")
        with Prims.dark_child_box("pressure_box", -1, 60):
            imgui.align_text_to_frame_padding()
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 40)
            imgui.text("N/A")
            imgui.same_line(80)
            
            imgui.push_style_color(imgui.Col_.plot_histogram, (0.4, 0.1, 0.1, 1.0))
            imgui.progress_bar(0.0, (-1, 14), "")
            imgui.pop_style_color()
        
        imgui.dummy((0, 5))
        imgui.button("SPONSOR TREATY", (-1, 24))
        
        imgui.end_child()

