from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_required_tables


class TreatiesPanel:
    def __init__(self, open_editor_cb=None):
        self._presenter = PoliticsPresenter()
        self._open_editor_cb = open_editor_cb
        self._selected_treaty_id = None
        self._filter_member_idx = 0
        self._filter_type_idx = 0
        
        # MOCK DATA
        self._filter_members = ["United States", "China", "Russia", "No filter"]
        self._filter_types = ["No filter", "Economic partnership", "Alliance", "Noble cause"]

    def render(self, state, context: PanelRenderContext) -> bool:
        # Window based on screenshot 1
        flags = imgui.WindowFlags_.no_collapse | imgui.WindowFlags_.no_scrollbar
        with WindowManager.window("Treaties", x=300, y=150, w=760, h=480, flags=flags) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country, context.net_client)
            return True

    def _render_content(self, state, country_tag: str, is_own_country: bool, net_client) -> None:
        draw_required_tables(state, ("countries_treaties", "pending_treaties", "countries_relations"))
        
        # Try to get real treaties, else use mock
        active_treaties = self._presenter.active_treaties_for_country(state, country_tag)
        pending_treaties = self._presenter.pending_treaties_for_country(state, country_tag)

        if not active_treaties:
            active_treaties = [
                {"id": "t1", "name": "African Development Bank (AfDB)", "type": "Economic partnership"},
                {"id": "t2", "name": "Asia-Pacific Economic Cooperation (APEC)", "type": "Economic partnership"},
                {"id": "t3", "name": "Asian Development Bank (AsDB)", "type": "Economic partnership"},
                {"id": "t4", "name": "Australia Group", "type": "Noble cause"},
                {"id": "t5", "name": "Australia-New Zealand-United States Security Treaty (ANZUS)", "type": "Alliance"},
            ]

        # ACTIVE TREATIES
        imgui.text_colored(GAMETHEME.colors.text_main, "ACTIVE TREATIES")
        with Prims.dark_child_box("active_treaties_box", -1, 240):
            flags = imgui.TableFlags_.scroll_y | imgui.TableFlags_.borders_inner | imgui.TableFlags_.row_bg
            if imgui.begin_table("active_treaties_table", 2, flags):
                imgui.table_setup_scroll_freeze(0, 1)
                imgui.table_setup_column("NAME", imgui.TableColumnFlags_.width_stretch, 2.5)
                imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_stretch, 1.0)
                imgui.table_headers_row()
                
                for row in active_treaties:
                    imgui.table_next_row()
                    imgui.table_next_column()
                    
                    treaty_id = str(row.get("id", ""))
                    is_selected = self._selected_treaty_id == treaty_id
                    
                    treaty_name = str(row.get("name") or row.get("title") or "Unnamed Treaty")
                    if imgui.selectable(f"{treaty_name}##{treaty_id}", is_selected, imgui.SelectableFlags_.span_all_columns)[0]:
                        self._selected_treaty_id = treaty_id
                    
                    imgui.table_next_column()
                    t_type = str(row.get("type") or "Unknown").replace("_", " ").capitalize()
                    imgui.text(t_type)
                    
                imgui.end_table()
        
        imgui.dummy((0, 5))
        
        # PENDING TREATIES
        imgui.text_colored(GAMETHEME.colors.text_main, "PENDING TREATIES")
        with Prims.dark_child_box("pending_treaties_box", -1, 160):
            flags = imgui.TableFlags_.scroll_y | imgui.TableFlags_.borders_inner | imgui.TableFlags_.row_bg
            if imgui.begin_table("pending_treaties_table", 2, flags):
                imgui.table_setup_scroll_freeze(0, 1)
                imgui.table_setup_column("NAME", imgui.TableColumnFlags_.width_stretch, 2.5)
                imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_stretch, 1.0)
                imgui.table_headers_row()
                
                for row in pending_treaties:
                    imgui.table_next_row()
                    imgui.table_next_column()
                    treaty_name = str(row.get("name") or row.get("title") or "Unnamed Treaty")
                    imgui.text(treaty_name)
                    imgui.table_next_column()
                    t_type = str(row.get("treaty_type") or "Unknown").replace("_", " ").capitalize()
                    imgui.text(t_type)
                
                # Mock empty rows if none
                if not pending_treaties:
                    for _ in range(5):
                        imgui.table_next_row()
                        imgui.table_next_column()
                        imgui.text("")
                        imgui.table_next_column()
                        imgui.text("")
                        
                imgui.end_table()
        
        imgui.dummy((0, 5))
        
        # FILTERS
        imgui.text_colored(GAMETHEME.colors.text_main, "FILTERS")
        with Prims.dark_child_box("filters_box", -1, 65):
            imgui.dummy((0, 2))
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 80)
            self._filter_member_idx = Prims.combo_row("MEMBER", self._filter_member_idx, self._filter_members, 80.0)
            
            imgui.set_cursor_pos_x(imgui.get_cursor_pos_x() + 80)
            self._filter_type_idx = Prims.combo_row("TYPE", self._filter_type_idx, self._filter_types, 80.0)
        
        imgui.dummy((0, 5))
        
        # BOTTOM BUTTONS
        avail = imgui.get_content_region_avail().x
        btn_w = (avail - 8) / 2
        
        # Center the buttons
        imgui.set_cursor_pos_x((imgui.get_window_width() - avail) / 2)
        
        if imgui.button("NEW TREATY", (btn_w, 24)):
            if self._open_editor_cb:
                self._open_editor_cb()
                
        imgui.same_line()
        
        imgui.begin_disabled(self._selected_treaty_id is None)
        if imgui.button("VIEW SELECTED", (btn_w, 24)):
            if self._open_editor_cb:
                # pass selected ID if we want
                self._open_editor_cb()
        imgui.end_disabled()

