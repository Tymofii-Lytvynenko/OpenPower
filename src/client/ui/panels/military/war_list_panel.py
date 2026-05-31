from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class WarListPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("WAR LIST", x=760, y=220, w=520, h=360) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("countries_wars",))
        imgui.separator()

        wars = self._presenter.wars_for_country(state, country_tag)
        if not wars:
            draw_empty_state("No active wars are associated with the selected country.")
            return

        for row in wars:
            imgui.text(str(row.get("front") or "Active front"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("status") or "ACTIVE").upper())
            imgui.separator()
