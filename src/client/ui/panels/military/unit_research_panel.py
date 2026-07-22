from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class UnitResearchPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT RESEARCH", x=600, y=180, w=520, h=390) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("research_tracks",))
        imgui.separator()

        tracks = self._presenter.research_tracks_for_country(state, country_tag)
        if not tracks:
            draw_empty_state("No research tracks are defined for the selected country.")
            return

        for row in tracks:
            label = str(row.get("focus") or row.get("branch") or "Track")
            funding = float(row.get("funding_ratio") or 0.0) * 100.0
            progress = float(row.get("progress") or 0.0) * 100.0
            imgui.text(label)
            imgui.same_line()
            Prims.right_align_text(f"Funding {funding:.1f}%")
            Prims.meter("", progress, (0.45, 0.55, 0.80, 1.0))
