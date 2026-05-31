from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class UnitProductionPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT PRODUCTION", x=560, y=140, w=560, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("unit_designs", "production_orders"))
        imgui.separator()

        designs = self._presenter.designs_for_country(state, country_tag)
        orders = self._presenter.production_orders_for_country(state, country_tag)
        posture = self._presenter.force_posture_text(state, country_tag)
        imgui.text_disabled(posture)
        imgui.dummy((0.0, 6.0))

        Prims.header("AVAILABLE DESIGNS", show_bg=False)
        if not designs:
            draw_empty_state("No design catalog is available for production.")
        else:
            for row in designs[:6]:
                imgui.text(str(row.get("display_name") or "Design"))
                imgui.same_line()
                Prims.right_align_text(
                    f"${float(row.get('cost') or 0.0):,.0f}".replace(",", " ")
                )

        imgui.dummy((0.0, 12.0))
        Prims.header("QUEUE", show_bg=False)
        if not orders:
            draw_empty_state("No production orders are queued.")
            return

        for row in orders:
            progress = max(0.0, min(100.0, float(row.get("progress") or 0.0) * 100.0))
            imgui.text(str(row.get("design_id") or "Design"))
            imgui.same_line()
            Prims.right_align_text(f"x{int(row.get('quantity') or 0)}")
            Prims.meter("", progress, (0.35, 0.65, 0.35, 1.0))
