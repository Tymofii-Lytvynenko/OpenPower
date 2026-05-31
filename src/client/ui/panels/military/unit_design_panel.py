from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class UnitDesignPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT DESIGN", x=650, y=210, w=500, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("unit_designs",))
        imgui.separator()

        designs = self._presenter.designs_for_country(state, country_tag)
        if not designs:
            draw_empty_state("No reusable unit designs are available.")
            return

        for row in designs:
            imgui.text(str(row.get("display_name") or "Design"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("branch") or "").upper())
            imgui.text_disabled(
                f"Quality {float(row.get('quality') or 0.0) * 100:.0f}% | "
                f"Speed {float(row.get('speed') or 0.0) * 100:.0f}% | "
                f"Firepower {float(row.get('firepower') or 0.0) * 100:.0f}%"
            )
            imgui.separator()
