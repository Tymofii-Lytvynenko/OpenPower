from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class InternalLawsPanel:
    def __init__(self):
        self._presenter = PoliticsPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("INTERNAL LAWS", x=280, y=140, w=640, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("country_laws",))
        imgui.separator()

        law_rows = self._presenter.laws_for_country(state, country_tag)
        if not law_rows:
            draw_empty_state("No internal law table is available for the selected country.")
            return

        flags = imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y | imgui.TableFlags_.sizing_stretch_prop
        if not imgui.begin_table("internal_laws_table", 5, flags, (0.0, 0.0)):
            return

        imgui.table_setup_column("GROUP", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("LAW", imgui.TableColumnFlags_.width_fixed, 160.0)
        imgui.table_setup_column("STATUS", imgui.TableColumnFlags_.width_fixed, 130.0)
        imgui.table_setup_column("VALUE")
        imgui.table_setup_column("NOTES")
        imgui.table_headers_row()

        for row in law_rows:
            imgui.table_next_row()
            imgui.table_next_column()
            imgui.text(str(row.get("group_name") or ""))
            imgui.table_next_column()
            imgui.text(str(row.get("title") or ""))
            imgui.table_next_column()
            imgui.text(str(row.get("status") or ""))
            imgui.table_next_column()
            imgui.text(str(row.get("value") or ""))
            imgui.table_next_column()
            imgui.text_wrapped(str(row.get("notes") or ""))

        imgui.end_table()
