from imgui_bundle import imgui
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter


class MilitaryPanel:
    def __init__(
        self,
        open_unit_list_cb=None,
        open_production_cb=None,
        open_research_cb=None,
        open_design_cb=None,
        open_market_cb=None,
        open_covert_cb=None,
        open_wars_cb=None,
        open_battle_cb=None,
        open_strategic_cb=None,
    ):
        self._presenter = MilitaryPresenter()
        self._open_unit_list_cb = open_unit_list_cb
        self._open_production_cb = open_production_cb
        self._open_research_cb = open_research_cb
        self._open_design_cb = open_design_cb
        self._open_market_cb = open_market_cb
        self._open_covert_cb = open_covert_cb
        self._open_wars_cb = open_wars_cb
        self._open_battle_cb = open_battle_cb
        self._open_strategic_cb = open_strategic_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        # Use Composition for Window Management
        with WindowManager.window("MILITARY", x=260, y=100, w=250, h=520) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        summary = self._presenter.build_summary(state, target_tag)

        # 1. Conventional Forces (Visible for all, effectively 'Intel')
        Prims.header("CONVENTIONAL FORCES")
        
        table_flags = (imgui.TableFlags_.borders_inner_h | 
                       imgui.TableFlags_.pad_outer_x)
                       
        if imgui.begin_table("MilTable", 3, table_flags):
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_fixed, 85)
            imgui.table_setup_column("", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("UNITS", imgui.TableColumnFlags_.width_fixed, 45)
            
            for bucket in summary.branches:
                self._draw_row(
                    bucket.label,
                    f"{bucket.strength:,}".replace(",", " "),
                    str(bucket.unit_count),
                )
            
            imgui.end_table()

        imgui.dummy((0, 5))
        imgui.text_disabled(f"Moving units: {summary.moving_units}")
        imgui.text_disabled(f"Active wars: {summary.active_wars}")
        imgui.text_disabled(f"Covert cells: {summary.covert_cells}")
        imgui.dummy((0, 8))
        
        # 2. Action Buttons (Hidden if not own country)
        if is_own:
            avail_w = imgui.get_content_region_avail().x
            # 2 buttons per row, small gap
            btn_w = (avail_w - imgui.get_style().item_spacing.x) / 2
            
            if imgui.button("BUY", (btn_w, 0)) and self._open_market_cb:
                self._open_market_cb()
            imgui.same_line()
            if imgui.button("BUILD", (btn_w, 0)) and self._open_production_cb:
                self._open_production_cb()
            
            if imgui.button("RESEARCH", (btn_w, 0)) and self._open_research_cb:
                self._open_research_cb()
            imgui.same_line()
            if imgui.button("DESIGN", (btn_w, 0)) and self._open_design_cb:
                self._open_design_cb()
            
            if imgui.button("UNIT LIST", (-1, 0)) and self._open_unit_list_cb:
                self._open_unit_list_cb()
            imgui.dummy((0, 10))
        else:
            imgui.text_disabled("[Actions Restricted]")
            imgui.dummy((0, 10))

        # 3. Strategic Forces
        Prims.header("STRATEGIC FORCES")
        # Header adds some spacing, but we want the button near it or below it
        
        imgui.text(f"{summary.strategic_ready} ready / {summary.strategic_total} total")
        if is_own and self._open_strategic_cb and imgui.button("OVERVIEW", (-1, 0)):
            self._open_strategic_cb()
        imgui.dummy((0, 5))
        
        # 4. Missile Defense
        Prims.header("MISSILE DEFENSE")
        imgui.text_colored(
            GAMETHEME.colors.positive if summary.missile_defense_pct >= 50.0 else GAMETHEME.colors.warning,
            f"{summary.missile_defense_pct:.0f}%",
        )
        if is_own and self._open_research_cb:
            imgui.same_line()
            imgui.set_cursor_pos_x(max(0.0, imgui.get_window_width() - 108.0))
            if imgui.button("RESEARCH##md", (90, 0)):
                self._open_research_cb()

        imgui.dummy((0, 15))
        
        # 5. Footer (Hide sensitive covert actions)
        if is_own:
            if imgui.button("COVERT ACTIONS", (-1, 0)) and self._open_covert_cb:
                self._open_covert_cb()
            if imgui.button("STRATEGIC WARFARE", (-1, 0)) and self._open_strategic_cb:
                self._open_strategic_cb()
            if imgui.button("WAR LIST", (-1, 0)) and self._open_wars_cb:
                self._open_wars_cb()
            if imgui.button("BATTLE OVERVIEW", (-1, 0)) and self._open_battle_cb:
                self._open_battle_cb()
        else:
            if imgui.button("WAR LIST", (-1, 0)) and self._open_wars_cb:
                self._open_wars_cb()

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
