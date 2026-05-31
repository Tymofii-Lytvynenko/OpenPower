from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class CovertOpsPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("COVERT OPS", x=720, y=190, w=460, h=350) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("covert_cells",))
        imgui.separator()

        cells = self._presenter.covert_cells_for_country(state, country_tag)
        if not cells:
            draw_empty_state("No covert cells are registered for the selected country.")
            return

        for row in cells:
            imgui.text(str(row.get("cell_name") or "Cell"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("target_country_id") or ""))
            imgui.text(
                f"Readiness {float(row.get('readiness') or 0.0) * 100:.0f}% | "
                f"Mission {str(row.get('mission_type') or 'idle')}"
            )
            imgui.separator()
