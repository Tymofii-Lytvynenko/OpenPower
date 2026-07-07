from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.politics.presenter import PoliticsPresenter


class InternalLawsPanel:
    def __init__(self):
        self._presenter = PoliticsPresenter()
        
        # --- MOCKED DATA ---
        # Explicitly mocking data that is not currently present in the game state (DATA_SCHEMA.md)
        self._mock_religions = [
            ("none", 9.9, "Legal"),
            ("other", 3.9, "Legal"),
            ("Protestant", 56.0, "Legal"),
            ("Jewish", 1.9, "Legal"),
            ("Roman Catholic", 27.9, "Legal"),
        ]
        self._mock_parties = [
            ("Democratic Party", 68.6, "In power"),
            ("Republican Party", 31.3, "Legal"),
        ]
        self._mock_migration = {
            "immigration_pct": 1.0,
            "emigration_pct": 0.5,
            "status": "Borders are opened"
        }

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("INTERNAL LAWS", x=280, y=140, w=450, h=560) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        SHOW_MOCKED_SECTIONS = False
        
        # Fetch real laws from state, or mock if missing
        real_laws = self._presenter.laws_for_country(state, country_tag)
        if real_laws:
            # Convert to tuples for the UI: (title, status)
            laws_data = [(str(row.get("title", "Unknown")), str(row.get("status", "Unknown"))) for row in real_laws]
        elif SHOW_MOCKED_SECTIONS:
            # Fallback mock data if table is empty or missing
            laws_data = [
                ("Freedom of speech (Mocked)", "Permitted"),
                ("Freedom of demonstration (Mocked)", "Permitted"),
                ("Women suffrage (Mocked)", "Permitted"),
                ("Number of children by family (Mocked)", "Unlimited"),
                ("Contraception (Mocked)", "Permitted"),
            ]
        else:
            laws_data = []

        if SHOW_MOCKED_SECTIONS:
            # DEMOGRAPHIC GROUPS
            Prims.header("DEMOGRAPHIC GROUPS")
            
            imgui.push_style_color(imgui.Col_.child_bg, (0.1, 0.1, 0.1, 1.0))
            imgui.begin_child("##demographics_block", (0.0, 140.0), True, imgui.WindowFlags_.no_scrollbar)
            
            if imgui.begin_tab_bar("demographics_tabs"):
                if imgui.begin_tab_item("Religions")[0]:
                    self._render_demographics_table(self._mock_religions)
                    imgui.end_tab_item()
                if imgui.begin_tab_item("Languages")[0]:
                    imgui.text("No data available (Mocked)")
                    imgui.end_tab_item()
                imgui.end_tab_bar()
                
            imgui.end_child()
            imgui.pop_style_color()
            imgui.dummy((0, 5))

        # LAWS
        if laws_data:
            Prims.header("LAWS")
            imgui.push_style_color(imgui.Col_.child_bg, (0.1, 0.1, 0.1, 1.0))
            imgui.begin_child("##laws_block", (0.0, 130.0), True, imgui.WindowFlags_.no_scrollbar)
            self._render_laws_table(laws_data)
            imgui.end_child()
            imgui.pop_style_color()
            imgui.dummy((0, 5))
        elif not SHOW_MOCKED_SECTIONS:
            imgui.text_disabled("No internal law table is available for the selected country.")
            imgui.dummy((0, 5))

        if SHOW_MOCKED_SECTIONS:
            # POLITICAL PARTIES
            Prims.header("POLITICAL PARTIES (MOCKED)")
            imgui.push_style_color(imgui.Col_.child_bg, (0.1, 0.1, 0.1, 1.0))
            imgui.begin_child("##parties_block", (0.0, 95.0), True, imgui.WindowFlags_.no_scrollbar)
            self._render_parties_table(self._mock_parties)
            imgui.end_child()
            imgui.pop_style_color()
            imgui.dummy((0, 5))
    
            # HUMAN MIGRATION
            Prims.header("HUMAN MIGRATION (MOCKED)")
            imgui.push_style_color(imgui.Col_.child_bg, (0.1, 0.1, 0.1, 1.0))
            imgui.begin_child("##migration_block", (0.0, 70.0), True)
            self._render_migration_block(self._mock_migration)
            imgui.end_child()
            imgui.pop_style_color()

    def _render_demographics_table(self, data):
        flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y
        if imgui.begin_table("demographics_table", 3, flags):
            imgui.table_setup_column("Name", imgui.TableColumnFlags_.width_stretch, 2.0)
            imgui.table_setup_column("Percentage", imgui.TableColumnFlags_.width_fixed, 60.0)
            imgui.table_setup_column("Status", imgui.TableColumnFlags_.width_fixed, 110.0)
            
            for i, (name, pct, status) in enumerate(data):
                imgui.table_next_row()
                
                imgui.table_next_column()
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 3.0)
                imgui.text(name)
                
                imgui.table_next_column()
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 3.0)
                Prims.right_align_text(f"{pct:.1f} %", GAMETHEME.colors.text_main)
                
                imgui.table_next_column()
                imgui.set_next_item_width(-1)
                imgui.combo(f"##demo_status_{i}", 0, [f"{status}"])
                
            imgui.end_table()

    def _render_laws_table(self, data):
        flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y
        if imgui.begin_table("laws_table", 2, flags):
            imgui.table_setup_column("Name", imgui.TableColumnFlags_.width_stretch, 2.0)
            imgui.table_setup_column("Status", imgui.TableColumnFlags_.width_fixed, 120.0)
            
            for i, (name, status) in enumerate(data):
                imgui.table_next_row()
                
                imgui.table_next_column()
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 3.0)
                imgui.text(name)
                
                imgui.table_next_column()
                imgui.set_next_item_width(-1)
                imgui.combo(f"##law_status_{i}", 0, [f"{status}"])
                
            imgui.end_table()

    def _render_parties_table(self, data):
        flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y
        if imgui.begin_table("parties_table", 3, flags):
            imgui.table_setup_column("Name", imgui.TableColumnFlags_.width_stretch, 2.0)
            imgui.table_setup_column("Percentage", imgui.TableColumnFlags_.width_fixed, 60.0)
            imgui.table_setup_column("Status", imgui.TableColumnFlags_.width_fixed, 110.0)
            
            for i, (name, pct, status) in enumerate(data):
                imgui.table_next_row()
                
                imgui.table_next_column()
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 3.0)
                imgui.text(name)
                
                imgui.table_next_column()
                imgui.set_cursor_pos_y(imgui.get_cursor_pos_y() + 3.0)
                Prims.right_align_text(f"{pct:.1f} %", GAMETHEME.colors.text_main)
                
                imgui.table_next_column()
                imgui.set_next_item_width(-1)
                imgui.combo(f"##party_status_{i}", 0, [f"{status}"])
                
            imgui.end_table()

    def _render_migration_block(self, data):
        if imgui.begin_table("migration_table", 2, imgui.TableFlags_.none):
            imgui.table_setup_column("Immigration", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("Emigration", imgui.TableColumnFlags_.width_stretch)
            imgui.table_next_row()
            
            imgui.table_next_column()
            imgui.text("Immigration")
            imgui.same_line()
            imgui.set_next_item_width(60.0)
            imgui.input_text("##imm_pct", f"{data['immigration_pct']:.1f} %", imgui.InputTextFlags_.read_only)
            
            imgui.set_next_item_width(-1)
            imgui.combo("##immigration_status", 0, [data["status"]])
            
            imgui.table_next_column()
            imgui.text("Emigration")
            imgui.same_line()
            imgui.set_next_item_width(60.0)
            imgui.input_text("##emi_pct", f"{data['emigration_pct']:.1f} %", imgui.InputTextFlags_.read_only)
            
            imgui.set_next_item_width(-1)
            imgui.combo("##emigration_status", 0, [data["status"]])
            
            imgui.end_table()
