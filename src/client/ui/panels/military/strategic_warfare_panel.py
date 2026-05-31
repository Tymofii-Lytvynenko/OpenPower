from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class StrategicWarfarePanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("STRATEGIC WARFARE", x=840, y=180, w=500, h=360) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("strategic_weapons",))
        imgui.separator()

        rows = self._presenter.strategic_inventory_for_country(state, country_tag)
        if not rows:
            draw_empty_state("No strategic inventory is available for the selected country.")
            return

        for row in rows:
            ready = int(row.get("ready") or 0)
            total = int(row.get("quantity") or 0)
            defense = float(row.get("defense_rating") or 0.0) * 100.0
            imgui.text(str(row.get("weapon_type") or "Strategic system"))
            imgui.same_line()
            Prims.right_align_text(f"{ready}/{total} ready")
            imgui.text_disabled(f"Defense rating {defense:.0f}%")
