from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class UnitListPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT LIST", x=520, y=100, w=760, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        rows = self._presenter.unit_rows(state, context.target_tag)
        if not rows:
            draw_empty_state("No deployed units are tracked for the selected country.")
            return

        flags = imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y | imgui.TableFlags_.sizing_stretch_prop
        if not imgui.begin_table("unit_list_table", 6, flags, (0.0, 0.0)):
            return

        imgui.table_setup_column("UNIT")
        imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_fixed, 130.0)
        imgui.table_setup_column("STRENGTH", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("LOCATION")
        imgui.table_setup_column("STATUS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("MOVE", imgui.TableColumnFlags_.width_fixed, 80.0)
        imgui.table_headers_row()

        for row in rows:
            imgui.table_next_row()
            imgui.table_next_column()
            imgui.text(row.unit_id)
            imgui.table_next_column()
            imgui.text(row.unit_type)
            imgui.table_next_column()
            imgui.text(f"{row.strength:,}".replace(",", " "))
            imgui.table_next_column()
            imgui.text(row.location)
            imgui.table_next_column()
            status_color = GAMETHEME.colors.info if row.status == "Moving" else GAMETHEME.colors.text_main
            imgui.text_colored(status_color, row.status)
            imgui.table_next_column()
            imgui.text(f"{row.progress_pct:.0f}%")

        imgui.end_table()
