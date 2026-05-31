from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class TreatyEditorPanel:
    def __init__(self):
        self._presenter = PoliticsPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("NEW TREATY", x=360, y=190, w=520, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("countries_relations", "countries_treaties", "pending_treaties"))
        imgui.separator()

        Prims.header("TREATY TEMPLATES", show_bg=False)
        templates = (
            ("Military alliance", "Shared war entry and force coordination."),
            ("Defensive pact", "Automatic support when a member is attacked."),
            ("Trade accord", "Preferential access for resources and transit."),
            ("Research accord", "Cooperative military and civilian development."),
        )
        for title, description in templates:
            imgui.text(title)
            imgui.push_text_wrap_pos(0.0)
            imgui.text_disabled(description)
            imgui.pop_text_wrap_pos()
            imgui.separator()

        Prims.header("PREFERRED PARTNERS", show_bg=False)
        partners = self._presenter.preferred_treaty_partners(state, country_tag)
        if not partners:
            draw_empty_state("No relation matrix is available to recommend treaty partners.")
            return

        for partner in partners:
            imgui.text(str(partner["country_name"]))
            imgui.same_line()
            Prims.right_align_text(f"{partner['relation_score']:.0f}")
