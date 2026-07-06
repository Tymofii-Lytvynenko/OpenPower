from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionDeclareWar, ActionOfferPeace


class WarListPanel:
    CASUS_BELLI_OPTIONS = (
        "Border dispute",
        "Treaty violation",
        "Resource embargo",
        "Regional security",
    )

    def __init__(self):
        self._presenter = MilitaryPresenter()
        self._target_idx = 0
        self._casus_belli_idx = 0

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("WAR LIST", x=760, y=220, w=520, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country, context.net_client)
            return True

    def _render_content(self, state, country_tag: str, is_own_country: bool, net_client) -> None:
        draw_required_tables(state, ("countries_wars", "countries_relations"))
        imgui.separator()

        if is_own_country and net_client is not None:
            self._render_declare_war_section(state, country_tag, net_client)
            imgui.dummy((0.0, 10.0))

        wars = self._presenter.wars_for_country(state, country_tag)
        if not wars:
            draw_empty_state("No active wars are associated with the selected country.")
            return

        for row in wars:
            imgui.text(str(row.get("front") or "Active front"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("status") or "ACTIVE").upper())
            if is_own_country and net_client is not None:
                if imgui.button(f"OFFER PEACE##{row.get('id')}", (120.0, 0.0)):
                    net_client.send_action(
                        ActionOfferPeace(
                            player_id=net_client.player_id,
                            war_id=str(row.get("id") or ""),
                            source_country_tag=country_tag,
                            terms="Immediate ceasefire",
                        )
                    )
            imgui.separator()

    def _render_declare_war_section(self, state, country_tag: str, net_client) -> None:
        imgui.text_disabled("DECLARE WAR")
        targets = self._presenter.preferred_war_targets(state, country_tag)
        if not targets:
            imgui.text_disabled("No valid war targets are available for the current diplomatic state.")
            return

        self._target_idx = max(0, min(self._target_idx, len(targets) - 1))
        self._casus_belli_idx = max(0, min(self._casus_belli_idx, len(self.CASUS_BELLI_OPTIONS) - 1))

        target_labels = [
            f"{target['country_name']} ({target['country_tag']}) | relation {target['relation_score']:.0f}"
            for target in targets
        ]
        imgui.set_next_item_width(-1)
        _, self._target_idx = imgui.combo("##war_target", self._target_idx, target_labels)
        imgui.set_next_item_width(-1)
        _, self._casus_belli_idx = imgui.combo("##casus_belli", self._casus_belli_idx, list(self.CASUS_BELLI_OPTIONS))

        selected_target = targets[self._target_idx]
        if imgui.button("DECLARE WAR", (-1, 32)):
            net_client.send_action(
                ActionDeclareWar(
                    player_id=net_client.player_id,
                    source_country_tag=country_tag,
                    target_country_tag=selected_target["country_tag"],
                    casus_belli=self.CASUS_BELLI_OPTIONS[self._casus_belli_idx],
                )
            )
