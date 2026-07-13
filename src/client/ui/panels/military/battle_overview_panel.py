from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_data import resolve_region_name
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class BattleOverviewPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("BATTLE OVERVIEW", x=800, y=250, w=500, h=340) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("battles",))
        imgui.separator()

        battles = self._presenter.battles_for_country(state, country_tag)
        if not battles:
            draw_empty_state("No active battles are tracked in the current state.")
            return

        for row in battles:
            region_name = resolve_region_name(state, int(row.get("region_id") or 0))
            balance = float(row.get("balance") or 0.0) * 100.0
            imgui.text(str(row.get("id") or "Battle"))
            imgui.same_line()
            imgui.text_disabled(region_name)
            mode = str(row.get("mode") or "positional").title()
            imgui.text(f"{mode} | Balance {balance:.0f}% | Status {str(row.get('status') or 'inactive')}")
            imgui.separator()
