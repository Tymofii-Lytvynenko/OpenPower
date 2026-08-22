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
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_required_tables(state, ("battles",))
        imgui.separator()

        battles = self._presenter.battles_for_country(state, context.target_tag)
        if not battles:
            draw_empty_state("No active battles are tracked in the current state.")
            return

        for row in battles:
            battle_id = str(row.get("id") or "Battle")
            model = self._presenter.battle_status(state, battle_id)
            region_name = resolve_region_name(state, int(row.get("region_id") or 0))
            balance = (model.balance if model else float(row.get("balance") or 0.0)) * 100.0
            imgui.text(battle_id)
            imgui.same_line()
            imgui.text_disabled(region_name)
            mode = (model.mode if model else str(row.get("mode") or "positional")).title()
            status = model.status if model else str(row.get("status") or "inactive")
            round_number = model.round if model else int(row.get("round") or 0)
            imgui.text(f"{mode} | Round {round_number} | Balance {balance:.0f}% | Status {status}")
            side_a = model.side_a_strength if model else float(row.get("side_a_strength") or 0.0)
            side_b = model.side_b_strength if model else float(row.get("side_b_strength") or 0.0)
            imgui.text(f"Forces {side_a:.0f} : {side_b:.0f}")
            if context.on_focus_request is not None and imgui.button(f"Focus##{battle_id}"):
                context.on_focus_request(int(row.get("region_id") or 0))
            if model:
                imgui.text(f"Losses {model.side_a_losses} : {model.side_b_losses}")
                distribution = model.readiness_distribution
                imgui.text(
                    "Readiness "
                    f"parked {distribution.get('parked', 0)} | "
                    f"ready {distribution.get('ready', 0)} | "
                    f"fortified {distribution.get('fortified', 0)}"
                )
                imgui.text(f"A: {', '.join(model.side_a_countries) or '—'}")
                imgui.text(f"B: {', '.join(model.side_b_countries) or '—'}")
                for participant in model.participants:
                    imgui.text_disabled(
                        f"{participant.country_id} [{participant.role}] {participant.weighted_strength:.0f}"
                    )
                if model.occupation:
                    imgui.text_disabled(
                        f"Occupation: {model.occupation.get('controller_country_id', '')} "
                        f"garrison {model.occupation.get('garrison_strength', 0)} "
                        f"resistance {float(model.occupation.get('resistance', 0.0) or 0.0):.1f} "
                        f"status {model.occupation.get('occupation_status', 'active')}"
                    )
            if hasattr(imgui, "progress_bar"):
                imgui.progress_bar(max(0.0, min(1.0, balance / 100.0)), (0.0, 12.0), "")
            imgui.separator()
