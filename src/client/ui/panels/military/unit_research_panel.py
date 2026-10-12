from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionUpdateResearchFunding


class UnitResearchPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT RESEARCH", x=600, y=180, w=520, h=390) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_required_tables(state, ("research_tracks",))
        imgui.separator()

        country_tag = str(context.target_tag or "").strip().upper()
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
            client = context.net_client
            if not context.is_own_country or client is None:
                continue
            branch = str(row.get("branch") or "").strip().lower()
            if not branch:
                continue
            branch_id = str(row.get("id") or branch)
            if imgui.small_button(f"−##research-{branch_id}"):
                self._set_funding(client, country_tag, row, max(0.0, float(row.get("funding_ratio") or 0.0) - 0.05))
            imgui.same_line()
            imgui.text(f"{funding:.1f}% allocated")
            imgui.same_line()
            if imgui.small_button(f"+##research-{branch_id}"):
                self._set_funding(client, country_tag, row, min(1.0, float(row.get("funding_ratio") or 0.0) + 0.05))

    def _set_funding(self, client, country_tag: str, row: dict, ratio: float) -> None:
        client.send_action(ActionUpdateResearchFunding(
            client.player_id,
            country_tag,
            str(row.get("branch") or "").strip().lower(),
            ratio,
            max(1, int(row.get("priority") or 1)),
        ))
