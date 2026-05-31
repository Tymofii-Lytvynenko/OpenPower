from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class ObjectivesPanel:
    def __init__(self):
        self._presenter = FeedPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("OBJECTIVES", x=980, y=120, w=520, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        objectives = self._presenter.objectives_for_country(state, country_tag)
        if not objectives:
            draw_empty_state("No strategic objectives are assigned to the selected country.")
            return

        for row in objectives:
            title = str(row.get("title") or "Objective")
            description = str(row.get("description") or "")
            status = str(row.get("status") or "active").upper()
            progress = max(0.0, min(100.0, float(row.get("progress") or 0.0) * 100.0))
            color = GAMETHEME.colors.positive if status == "COMPLETED" else GAMETHEME.colors.info

            imgui.text_colored(GAMETHEME.colors.text_main, title)
            imgui.same_line()
            Prims.right_align_text(status, color)
            imgui.push_text_wrap_pos(0.0)
            imgui.text_colored(GAMETHEME.colors.text_dim, description)
            imgui.pop_text_wrap_pos()
            Prims.meter("", progress, color)
            imgui.dummy((0.0, 6.0))
