from __future__ import annotations

from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables
from src.shared.actions import ActionBuyMarketUnit, ActionListUsedUnit, ActionWithdrawUsedUnitListing


class UnitMarketPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT MARKET", x=690, y=150, w=500, h=360) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country_tag = str(context.target_tag or "").upper()
        draw_required_tables(state, ("unit_market_listings", "unit_designs"))
        imgui.separator()

        listings = self._presenter.market_listings_for_country(state, country_tag)
        if not listings:
            draw_empty_state("No eligible used-unit listings are currently available.")
        own_listings = [row for row in listings if str(row.get("seller_country_id") or "").strip().upper() == country_tag]
        buy_listings = [row for row in listings if str(row.get("seller_country_id") or "").strip().upper() != country_tag]
        for row in buy_listings:
            imgui.text(str(row.get("design_name") or "Listing"))
            imgui.same_line()
            imgui.text_disabled(str(row.get("seller_name") or row.get("seller_country_id") or ""))
            imgui.text(
                f"Qty {int(row.get('quantity') or 0)} | Price ${float(row.get('price') or 0.0):,.0f}".replace(",", " ")
            )
            if context.is_own_country and context.net_client is not None and imgui.button(f"BUY ONE##{row.get('id') or ''}"):
                context.net_client.send_action(ActionBuyMarketUnit(
                    context.net_client.player_id, str(row.get("id") or ""), country_tag, 1,
                ))
            imgui.separator()

        imgui.text("YOUR LISTINGS")
        for row in own_listings:
            imgui.text(f"{row.get('design_name') or 'Unit'} · Qty {int(row.get('quantity') or 0)} · ${float(row.get('price') or 0.0):,.0f}")
            if context.is_own_country and context.net_client is not None and imgui.small_button(f"WITHDRAW##{row.get('id') or ''}"):
                context.net_client.send_action(ActionWithdrawUsedUnitListing(
                    context.net_client.player_id, country_tag, str(row.get("id") or ""),
                ))

        imgui.text("ELIGIBLE UNITS TO LIST")
        marketable = self._presenter.marketable_units_for_country(state, country_tag)
        if not marketable:
            imgui.text_disabled("No deployed, unengaged units are eligible to list.")
        for unit in marketable[:12]:
            imgui.text(f"{unit.get('design_name') or 'Unit'} · {unit.get('id')} · Qty {int(unit.get('strength') or 0)}")
            if context.is_own_country and context.net_client is not None and imgui.small_button(f"LIST AT 75%##{unit.get('id') or ''}"):
                context.net_client.send_action(ActionListUsedUnit(
                    context.net_client.player_id, country_tag, str(unit.get("id") or ""),
                ))
