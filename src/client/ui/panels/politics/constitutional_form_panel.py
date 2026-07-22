from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_widgets import draw_key_value_rows


class ConstitutionalFormPanel:
    def __init__(self):
        self._presenter = PoliticsPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("CONSTITUTIONAL FORM", x=260, y=120, w=360, h=300) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        summary = self._presenter.build_summary(state, country_tag)
        draw_key_value_rows(
            (
                ("Government Type", summary.government_type),
                ("Capital", summary.capital_name),
                ("Next Election", summary.next_election),
                ("Martial Law", "Active" if summary.martial_law else "Inactive"),
                ("Election Risk", f"{summary.election_risk_pct:.1f}%"),
                ("Ideology Balance", f"{summary.ideology_balance * 100:.1f}% free-market"),
                ("Active Treaties", str(summary.active_treaties)),
                ("Pending Treaties", str(summary.pending_treaties)),
            ),
            dim_labels=False,
        )
