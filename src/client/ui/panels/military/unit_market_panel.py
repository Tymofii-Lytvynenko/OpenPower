from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class UnitMarketPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT MARKET", x=690, y=150, w=500, h=360) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, country_tag: str) -> None:
        draw_required_tables(state, ("unit_market_listings", "unit_designs"))
        imgui.separator()

        listings = self._presenter.market_listings_for_country(state, country_tag)
        if not listings:
            draw_empty_state("No unit market listings are available in the current dataset.")
            return

        for row in listings:
            imgui.text(str(row.get("design_name") or "Listing"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("seller_country_id") or ""))
            imgui.text(
                f"Qty {int(row.get('quantity') or 0)} | Price ${float(row.get('price') or 0.0):,.0f}".replace(",", " ")
            )
            imgui.separator()
