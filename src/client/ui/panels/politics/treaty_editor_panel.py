from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionCreateTreaty


class TreatyEditorPanel:
    TEMPLATE_OPTIONS = (
        ("Military alliance", "military_alliance", "Shared war entry and force coordination."),
        ("Defensive pact", "defensive_pact", "Automatic support when a member is attacked."),
        ("Trade accord", "trade_accord", "Preferential access for resources and transit."),
        ("Research accord", "research_accord", "Cooperative military and civilian development."),
    )

    def __init__(self):
        self._presenter = PoliticsPresenter()
        self._template_idx = 0
        self._partner_idx = 0

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("NEW TREATY", x=360, y=190, w=520, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country, context.net_client)
            return True

    def _render_content(self, state, country_tag: str, is_own_country: bool, net_client) -> None:
        draw_required_tables(state, ("countries_relations", "countries_treaties", "pending_treaties"))
        imgui.separator()

        labels = [label for label, _, _ in self.TEMPLATE_OPTIONS]
        self._template_idx = max(0, min(self._template_idx, len(labels) - 1))
        _, self._template_idx = imgui.combo("TEMPLATE", self._template_idx, labels)
        selected_label, selected_key, selected_description = self.TEMPLATE_OPTIONS[self._template_idx]

        Prims.header("TREATY TEMPLATES", show_bg=False)
        imgui.text(selected_label)
        imgui.push_text_wrap_pos(0.0)
        imgui.text_disabled(selected_description)
        imgui.pop_text_wrap_pos()
        imgui.separator()

        Prims.header("PREFERRED PARTNERS", show_bg=False)
        partners = self._presenter.preferred_treaty_partners(state, country_tag)
        if not partners:
            draw_empty_state("No relation matrix is available to recommend treaty partners.")
            return

        self._partner_idx = max(0, min(self._partner_idx, len(partners) - 1))
        partner_labels = [f"{partner['country_name']} ({partner['country_tag']})" for partner in partners]
        _, self._partner_idx = imgui.combo("PARTNER", self._partner_idx, partner_labels)
        selected_partner = partners[self._partner_idx]

        imgui.dummy((0.0, 8.0))
        imgui.text_disabled("DRAFT TITLE")
        imgui.same_line(140)
        imgui.text(f"{country_tag}-{selected_partner['country_tag']} {selected_label}")
        imgui.text_disabled("RELATION SCORE")
        imgui.same_line(140)
        imgui.text(f"{selected_partner['relation_score']:.0f}")
        imgui.dummy((0.0, 10.0))

        can_submit = bool(is_own_country and net_client is not None)
        if not is_own_country:
            imgui.text_disabled("Only your own country can create treaty proposals.")
        elif net_client is None:
            imgui.text_disabled("Network client is unavailable for diplomacy actions.")

        imgui.begin_disabled(not can_submit)
        if imgui.button("SEND PROPOSAL", (-1, 34)):
            net_client.send_action(
                ActionCreateTreaty(
                    player_id=net_client.player_id,
                    source_country_tag=country_tag,
                    target_country_tag=selected_partner["country_tag"],
                    treaty_type=selected_key,
                    title=f"{country_tag}-{selected_partner['country_tag']} {selected_label}",
                    terms=selected_description,
                )
            )
        imgui.end_disabled()
