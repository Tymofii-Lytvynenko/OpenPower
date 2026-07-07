from __future__ import annotations

import random
from imgui_bundle import imgui, icons_fontawesome_6

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_data import resolve_country_name
from src.client.ui.panels.shared.panel_widgets import draw_required_tables, draw_empty_state
from src.shared.actions import ActionOfferPeace

class WarListPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()
        self._selected_war_id = None

    def render(self, state, context: PanelRenderContext) -> bool:
        flags = imgui.WindowFlags_.no_collapse | imgui.WindowFlags_.no_scrollbar
        with WindowManager.window("WAR LIST###War List", x=300, y=150, w=720, h=520, flags=flags) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country, context.net_client)
            return True

    def _get_flag_color(self, tag: str):
        rng = random.Random(tag)
        return (rng.random(), rng.random(), rng.random(), 1.0)

    def _render_content(self, state, country_tag: str, is_own_country: bool, net_client) -> None:
        wars_data = self._presenter.all_wars(state)
        
        # Ensure a war is selected
        if self._selected_war_id is None and wars_data:
            self._selected_war_id = wars_data[0].get("id")
            
        selected_war = next((w for w in wars_data if w.get("id") == self._selected_war_id), None)
        if not selected_war and wars_data:
            selected_war = wars_data[0]
            self._selected_war_id = selected_war.get("id")

        # TOP SECTION
        if imgui.begin_child("top_section", (-1, 200), True):
            w = imgui.get_content_region_avail().x
            half_w = (w - 40) / 2
            
            # Headers
            imgui.text_disabled("COUNTRY")
            imgui.same_line(half_w - 40)
            imgui.text_disabled("ALLIES")
            
            imgui.same_line(half_w + 10)
            imgui.text_disabled("vs.")
            
            imgui.same_line(half_w + 40)
            imgui.text_disabled("COUNTRY")
            
            imgui.same_line(w - 45)
            imgui.text_disabled("ALLIES")
            
            imgui.dummy((0, 2))
            
            # Dark list box
            with Prims.dark_child_box("top_list", -1, -1):
                for war in wars_data:
                    wid = war.get("id")
                    side_a = war.get("side_a", [])
                    side_b = war.get("side_b", [])
                    
                    leader_a = war.get("leader_a", "UNK")
                    leader_b = war.get("leader_b", "UNK")
                    
                    name_a = resolve_country_name(state, leader_a)
                    name_b = resolve_country_name(state, leader_b)
                    
                    is_selected = self._selected_war_id == wid
                    
                    # We use a trick to make the row selectable
                    if imgui.selectable(f"##war_row_{wid}", is_selected, imgui.SelectableFlags_.span_all_columns)[0]:
                        self._selected_war_id = wid
                    
                    # Since selectable moves cursor to next line, we need to go back up
                    imgui.same_line(0, 0)
                    imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() - 4) # Adjust back to same line
                    
                    # Left side
                    imgui.color_button(f"##t_fa_{wid}", self._get_flag_color(leader_a), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                    imgui.same_line()
                    imgui.text(name_a)
                    
                    imgui.same_line(half_w - 20)
                    imgui.text(str(len(side_a)))
                    
                    # vs
                    imgui.same_line(half_w + 10)
                    imgui.text_disabled("vs.")
                    
                    # Right side
                    imgui.same_line(half_w + 40)
                    imgui.color_button(f"##t_fb_{wid}", self._get_flag_color(leader_b), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                    imgui.same_line()
                    imgui.text(name_b)
                    
                    imgui.same_line(w - 30)
                    imgui.text(str(len(side_b)))
            
        imgui.end_child()
        
        imgui.dummy((0, 5))
        
        # BOTTOM SECTION
        if imgui.begin_child("bottom_section", (-1, 260), True):
            w = imgui.get_content_region_avail().x
            half_w = (w - 40) / 2
            
            # Headers
            imgui.text_disabled("COUNTRY")
            imgui.same_line(half_w - 50)
            imgui.text_disabled("STATUS")
            
            imgui.same_line(half_w + 10)
            imgui.text_disabled("vs.")
            
            imgui.same_line(half_w + 40)
            imgui.text_disabled("COUNTRY")
            
            imgui.same_line(w - 55)
            imgui.text_disabled("STATUS")
            
            imgui.dummy((0, 2))
            
            side_a_members = selected_war.get("side_a", []) if selected_war else []
            side_b_members = selected_war.get("side_b", []) if selected_war else []
            
            leader_a = selected_war.get("leader_a", "") if selected_war else ""
            leader_b = selected_war.get("leader_b", "") if selected_war else ""
            intent_a = selected_war.get("intent_a", "war") if selected_war else "war"
            intent_b = selected_war.get("intent_b", "war") if selected_war else "war"
            
            # Left box
            with Prims.dark_child_box("bottom_left_list", half_w, 180):
                for tag in side_a_members:
                    imgui.color_button(f"##bl_f_{tag}", self._get_flag_color(tag), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                    imgui.same_line()
                    imgui.text(resolve_country_name(state, tag))
                    
                    imgui.same_line(half_w - 30)
                    if tag == leader_a:
                        icon = icons_fontawesome_6.ICON_FA_GUN if intent_a == "war" else icons_fontawesome_6.ICON_FA_FLAG
                        imgui.text(icon)
            
            imgui.same_line(half_w + 40)
            
            # Right box
            with Prims.dark_child_box("bottom_right_list", half_w, 180):
                for tag in side_b_members:
                    imgui.color_button(f"##br_f_{tag}", self._get_flag_color(tag), imgui.ColorEditFlags_.no_tooltip, (20, 14))
                    imgui.same_line()
                    imgui.text(resolve_country_name(state, tag))
                    
                    imgui.same_line(half_w - 30)
                    if tag == leader_b:
                        icon = icons_fontawesome_6.ICON_FA_GUN if intent_b == "war" else icons_fontawesome_6.ICON_FA_FLAG
                        imgui.text(icon)
            
            imgui.dummy((0, 4))
            
            # Buttons
            btn_w = 60
            
            # Action handles for Side A (Attacker Leader)
            can_act_a = is_own_country and net_client is not None and selected_war is not None and country_tag == leader_a
            imgui.begin_disabled(not can_act_a)
            
            # Left side buttons
            imgui.set_cursor_pos_x(half_w - (btn_w * 2 + 8))
            if imgui.button("PEACE##1", (btn_w, 24)):
                if can_act_a:
                    net_client.send_action(ActionOfferPeace(
                        player_id=net_client.player_id,
                        war_id=self._selected_war_id,
                        source_country_tag=country_tag,
                        terms="peace"
                    ))
            imgui.same_line()
            if imgui.button("WAR##1", (btn_w, 24)):
                if can_act_a:
                    net_client.send_action(ActionOfferPeace(
                        player_id=net_client.player_id,
                        war_id=self._selected_war_id,
                        source_country_tag=country_tag,
                        terms="war"
                    ))
            imgui.end_disabled()
                
            # Action handles for Side B (Defender Leader)
            can_act_b = is_own_country and net_client is not None and selected_war is not None and country_tag == leader_b
            imgui.begin_disabled(not can_act_b)
            
            # Right side buttons
            imgui.same_line()
            imgui.set_cursor_pos_x(half_w + 40 + half_w - (btn_w * 2 + 8))
            if imgui.button("PEACE##2", (btn_w, 24)):
                if can_act_b:
                    net_client.send_action(ActionOfferPeace(
                        player_id=net_client.player_id,
                        war_id=self._selected_war_id,
                        source_country_tag=country_tag,
                        terms="peace"
                    ))
            imgui.same_line()
            if imgui.button("WAR##2", (btn_w, 24)):
                if can_act_b:
                    net_client.send_action(ActionOfferPeace(
                        player_id=net_client.player_id,
                        war_id=self._selected_war_id,
                        source_country_tag=country_tag,
                        terms="war"
                    ))
            imgui.end_disabled()
                
        imgui.end_child()

