from __future__ import annotations

import json
import math
from typing import Any

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels import trade_options
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    draw_gml_separator,
    get_gml_layout,
    resume_gml_layout,
    suspend_gml_layout,
)
from src.shared.actions import (
    ActionCounterTradeDeal,
    ActionCreateTradeDeal,
    ActionRespondTradeDeal,
    ActionWithdrawTradeDeal,
)


class TradePanel:
    """Builds bilateral offers and presents the complete response lifecycle."""

    _ASSET_CATEGORIES = (
        ("cash", "Cash"),
        ("region", "Regions"),
        ("technology", "Technology"),
    )

    def __init__(self):
        self.partner_tag = ""
        self.counter_to_deal_id = ""
        self.offered_assets: list[dict[str, Any]] = []
        self.requested_assets: list[dict[str, Any]] = []
        self.offer_cash = 0.0
        self.request_cash = 0.0
        self.offer_region_idx = 0
        self.request_region_idx = 0
        self.offer_technology_idx = 0
        self.request_technology_idx = 0
        self.offer_technology_level = 0
        self.request_technology_level = 0
        self.expiry_days = 30.0
        self.active_page = "proposal"
        self.asset_category = "cash"
        self._selected_asset_index = {"offer": 0, "request": 0}
        self._draft_country = ""
        self._requested_deal_id = ""
        self._selected_deal_id = ""

    def request_deal(self, deal_id: str) -> None:
        self._requested_deal_id = str(deal_id)
        self._selected_deal_id = self._requested_deal_id
        self.active_page = "deal"

    def render(self, state, context: PanelRenderContext) -> bool:
        template = "Trade_Window" if self.active_page == "offers" else "Trade_Detailed_Window"
        layout = get_gml_layout(template)
        viewport = imgui.get_main_viewport().size
        x = max(0.0, (float(viewport.x) - layout.width) / 2.0)
        y = max(0.0, (float(viewport.y) - layout.height) / 2.0)
        with WindowManager.window(
            "BILATERAL TRADE", x=x, y=y, w=layout.width, h=layout.height,
            test_id="trade.panel", gml_template=template,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        country = self._tag(context.target_tag)
        if self._draft_country != country:
            # Draft assets belong to the selected country and must not leak across selection changes.
            self._reset_package()
            self._draft_country = country
        template = "Trade_Window" if self.active_page == "offers" else "Trade_Detailed_Window"
        title_ui = GMLWidgets(f"{template}/frmTitle")
        if self.active_page == "proposal":
            if title_ui.button(
                "btnApply", "", "trade.page.offers",
                tooltip="Show current and resolved trade offers",
            ):
                self.active_page = "offers"
                return
        elif self.active_page == "offers":
            if title_ui.button(
                "btnApply", "", "trade.page.proposal",
                tooltip="Return to the trade proposal",
            ):
                self.active_page = "proposal"
                return
        elif title_ui.button(
            "btnApply", "", "trade.page.offers",
            tooltip="Return to the offer list",
        ):
            self.active_page = "offers"
            return
        self._draw_title_action_icon(
            title_ui,
            "btnApply",
            "offers" if self.active_page == "proposal" else "proposal",
        )

        if self.active_page == "offers":
            self._render_trade_offer_list(state, country)
            return
        if self.active_page == "deal":
            self._render_trade_deal_detail(state, context, country)
            return

        self._render_country_header(state, country, context)
        draw_gml_separator("Trade_Detailed_Window/frmInner/picSep", color=GAMETHEME.colors.text_dim)
        draw_gml_separator("Trade_Detailed_Window/frmInner/picSep1", color=GAMETHEME.colors.text_dim)
        partners = self._country_options(state, country)
        if partners and not any(tag == self.partner_tag for tag, _ in partners):
            self.partner_tag = partners[0][0]
        partner_index = next((i for i, item in enumerate(partners) if item[0] == self.partner_tag), 0)
        partner_path = "Trade_Detailed_Window/frmInner/frmSideB/cboCountry"
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 0.0))
        imgui.begin_disabled(bool(self.counter_to_deal_id) or not partners)
        try:
            changed, partner_index = imgui.combo(
                "##trade_partner",
                partner_index,
                [label for _, label in partners] or ["No trade partners"],
                test_id="trade.partner",
                gml_id=partner_path,
            )
        finally:
            imgui.end_disabled()
            imgui.pop_style_var()
        if changed and partners:
            self.partner_tag = partners[partner_index][0]
            self._reset_package()

        if self.counter_to_deal_id:
            original = next((row for row in self._rows(state, "diplomatic_trade_deals")
                             if str(row.get("id")) == self.counter_to_deal_id), None)
            if original is None or original.get("status") != "pending" or self._integer(original.get("expires_at_minute")) <= self._integer(state.time.total_minutes):
                # Server updates can resolve an offer while its local draft is still being edited.
                self._reset_package()
                self.active_page = "offers"
                self._render_balance(state, "The original offer is no longer pending.", context)
                return

        if not partners:
            self._render_balance(state, "No trade partners are available.", context)
        elif not context.is_own_country or context.net_client is None:
            self._render_balance(state, "Control your own country to negotiate or respond to offers.", context)
        elif not self._country_at_war(state, country, self.partner_tag):
            self._render_package_editor(state, context, country, self.partner_tag)
        else:
            self._render_balance(state, "Countries at war must use the peace-deal editor.", context)

    def _render_country_header(self, state, country: str, context: PanelRenderContext) -> None:
        layout = active_gml_layout()
        if layout is None:
            return
        left = GMLWidgets("Trade_Detailed_Window/frmInner/frmSideA")
        heading = "OPEN OFFERS" if self.active_page == "offers" else f"YOU GIVE · {country or 'COUNTRY'}"
        left.text("txtCountry", heading, test_id="trade.offer.country")
        if self.active_page != "proposal":
            return
        rect = left.rect("txtCountry")
        if rect is not None:
            imgui.set_cursor_screen_pos((
                layout.window_position[0] + rect.x + 150.0,
                layout.window_position[1] + rect.y,
            ))
            imgui.set_next_item_width(max(80.0, rect.width - 150.0))
            category_values = [value for value, _ in self._ASSET_CATEGORIES]
            if self.asset_category not in category_values:
                self.asset_category = category_values[0]
            category_index = category_values.index(self.asset_category)
            changed, category_index = imgui.combo(
                "##trade_asset_category",
                category_index,
                [label for _, label in self._ASSET_CATEGORIES],
                test_id="trade.asset_category",
            )
            if changed:
                self.asset_category = category_values[category_index]

    def _render_package_editor(self, state, context, country: str, partner: str) -> None:
        self._render_asset_side(state, self.offered_assets, country, partner, "offer")
        self._render_asset_side(state, self.requested_assets, partner, country, "request")

        self._render_balance(state, context=context)
        layout = active_gml_layout()
        if layout is not None:
            rect = GMLWidgets("Trade_Detailed_Window/frmInner/frmBalance").rect("frmOverviewMeter")
            if rect is not None:
                window_x, window_y = layout.window_position
                imgui.set_cursor_screen_pos((window_x + rect.x - 73.0, window_y + rect.y - 17.0))
                imgui.text_disabled("DAYS")
                imgui.set_cursor_screen_pos((window_x + rect.x - 39.0, window_y + rect.y - 17.0))
                imgui.set_next_item_width(60.0)
                changed, days = imgui.input_int(
                    "##trade_expiry_days", int(self.expiry_days), 0, 0,
                    test_id="trade.expiry_days",
                )
                if changed:
                    self.expiry_days = float(days)
        self.expiry_days = min(365.0, max(1.0, self.expiry_days))
        can_submit = bool(self.offered_assets or self.requested_assets)
        inner_ui = GMLWidgets("Trade_Detailed_Window/frmInner")
        if inner_ui.button(
            "btnPropose", "SEND", "trade.send", enabled=can_submit,
            tooltip="Send the current bilateral proposal",
        ):
            self._send_proposal(context, country, partner)
        if inner_ui.button(
            "btnCancel", "CLEAR", "trade.cancel",
            tooltip="Clear all assets from this proposal",
        ):
            self._reset_package()

    @staticmethod
    def _draw_title_action_icon(ui: GMLWidgets, slot: str, action: str) -> None:
        layout = active_gml_layout()
        rect = ui.rect(slot)
        if layout is None or rect is None:
            return
        x = layout.window_position[0] + rect.x
        y = layout.window_position[1] + rect.y
        draw = imgui.get_window_draw_list()
        color = imgui.get_color_u32(GAMETHEME.colors.text_main)
        if action == "offers":
            for offset in (5.0, 8.0, 11.0):
                draw.add_line((x + 5.0, y + offset), (x + 12.0, y + offset), color, 1.0)
        else:
            draw.add_line((x + 5.0, y + 8.0), (x + 12.0, y + 8.0), color, 1.0)
            draw.add_line((x + 5.0, y + 8.0), (x + 9.0, y + 5.0), color, 1.0)
            draw.add_line((x + 5.0, y + 8.0), (x + 9.0, y + 11.0), color, 1.0)

    def _render_balance(self, state, message: str = "", context: PanelRenderContext | None = None) -> None:
        ui = GMLWidgets("Trade_Detailed_Window/frmInner/frmBalance")
        offered = sum(
            self._number(asset.get("amount"))
            for asset in self.offered_assets
            if str(asset.get("type") or "") == "cash"
        )
        requested = sum(
            self._number(asset.get("amount"))
            for asset in self.requested_assets
            if str(asset.get("type") or "") == "cash"
        )
        result = self._latest_action_result(state, context)
        label = message or (
            f"Last action: {result.get('status')}" if result is not None
            else "CASH BALANCE ONLY"
        )
        tooltip = (
            str(result.get("reason") or "") if result is not None
            else "Territory and technology values are not estimated by OpenPower."
        )
        ui.text("lblBalance", label, test_id="trade.balance", tooltip=tooltip)
        ui.text("txtPriceA", f"−${offered:,.0f}", test_id="trade.balance.offered")
        ui.text("txtPriceB", f"+${requested:,.0f}", right=True, test_id="trade.balance.requested")
        ratio = offered / (offered + requested) if offered + requested > 0 else 0.0
        ui.meter("frmOverviewMeter", ratio, GAMETHEME.colors.accent)

    def _latest_action_result(self, state, context: PanelRenderContext | None) -> dict[str, Any] | None:
        journal = getattr(state, "journal", None)
        results = getattr(journal, "command_results", [])
        action_names = {
            "ActionCreateTradeDeal",
            "ActionCounterTradeDeal",
            "ActionRespondTradeDeal",
            "ActionWithdrawTradeDeal",
        }
        player_id = str(context.net_client.player_id) if context and context.net_client is not None else ""
        return next(
            (
                row for row in reversed(results)
                if str(row.get("player_id") or "") == player_id
                and str(row.get("action_type") or "") in action_names
            ),
            None,
        )

    def _render_asset_side(
        self,
        state,
        assets: list[dict[str, Any]],
        giver: str,
        receiver: str,
        prefix: str,
    ) -> None:
        side = "frmSideA" if prefix == "offer" else "frmSideB"
        root = f"Trade_Detailed_Window/frmInner/{side}"

        if self.asset_category == "cash":
            amount_attr = "offer_cash" if prefix == "offer" else "request_cash"
            amount = max(0.0, float(getattr(self, amount_attr)))
            amount_path = f"{root}/tabGroups/Tab3/frmMoney/edtText"
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 0.0))
            try:
                changed, amount = imgui.input_float(
                f"##{prefix}_cash", amount, 0.0, 0.0, "%.0f",
                test_id=f"trade.{prefix}.cash",
                    gml_id=amount_path,
                )
            finally:
                imgui.pop_style_var()
            _, amount = self._render_numeric_stepper(
                f"{root}/tabGroups/Tab3/frmMoney/btnDown",
                f"trade.{prefix}.cash.down", -1, amount,
            )
            _, amount = self._render_numeric_stepper(
                f"{root}/tabGroups/Tab3/frmMoney/btnUp",
                f"trade.{prefix}.cash.up", 1, amount,
            )
            setattr(self, amount_attr, max(0.0, amount))
            amount_ui = GMLWidgets(f"{root}/tabGroups/Tab3")
            amount_ui.text(
                "txtPrice", f"{amount:,.0f}", test_id=f"trade.{prefix}.cash_amount",
                tooltip="Cash amount to add to this side of the proposal.",
            )
            if amount_ui.button("btnAdd", "ADD", f"trade.{prefix}.add_cash", enabled=amount > 0.0):
                assets.append({"type": "cash", "amount": round(amount, 2)})
                setattr(self, amount_attr, 0.0)

        elif self.asset_category == "region":
            regions = self._regions_for_owner(state, giver)
            attr = "offer_region_idx" if prefix == "offer" else "request_region_idx"
            index = max(0, min(int(getattr(self, attr)), max(0, len(regions) - 1)))
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 0.0))
            imgui.begin_disabled(not regions)
            try:
                _, index = imgui.combo(
                    f"##{prefix}_region", index,
                    [label for _, label in regions] or ["No eligible region"],
                    test_id=f"trade.{prefix}.region",
                    gml_id=f"{root}/tabGroups/Tab1/cboRegion",
                )
            finally:
                imgui.end_disabled()
                imgui.pop_style_var()
            if regions:
                setattr(self, attr, index)
                if GMLWidgets(f"{root}/tabGroups/Tab1").button(
                    "btnAdd", "ADD", f"trade.{prefix}.add_region",
                ):
                    self._append_unique(assets, {"type": "territory", "region_id": regions[index][0]})
            GMLWidgets(f"{root}/tabGroups/Tab1").text(
                "txtPrice", "UNPRICED", test_id=f"trade.{prefix}.region_value",
                tooltip="OpenPower does not estimate territory value.",
            )

        elif self.asset_category == "technology":
            technologies = self._technology_options(state, giver, receiver)
            category_ui = GMLWidgets(f"{root}/tabGroups/Tab2")
            imgui.begin_disabled()
            try:
                imgui.combo(
                    f"##{prefix}_technology_type", 0, ["Research"],
                    test_id=f"trade.{prefix}.technology_type",
                    gml_id=category_ui.path("cboType"),
                )
            finally:
                imgui.end_disabled()
            branch_attr = "offer_technology_idx" if prefix == "offer" else "request_technology_idx"
            level_attr = "offer_technology_level" if prefix == "offer" else "request_technology_level"
            branch_index = max(0, min(int(getattr(self, branch_attr)), max(0, len(technologies) - 1)))
            branches = [branch for branch, _, _ in technologies]
            imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 0.0))
            imgui.begin_disabled(not technologies)
            try:
                _, branch_index = imgui.combo(
                    f"##{prefix}_technology", branch_index,
                    branches or ["No transferable technology"],
                    test_id=f"trade.{prefix}.technology",
                    gml_id=category_ui.path("cboTechnology"),
                )
            finally:
                imgui.end_disabled()

            levels: list[int] = []
            if technologies:
                setattr(self, branch_attr, branch_index)
                _, maximum_level, receiver_level = technologies[branch_index]
                levels = list(range(receiver_level + 1, maximum_level + 1))
            saved_level = int(getattr(self, level_attr))
            if levels and saved_level not in levels:
                saved_level = levels[-1]
                setattr(self, level_attr, saved_level)
            level_index = levels.index(saved_level) if levels else 0
            imgui.begin_disabled(not levels)
            try:
                _, level_index = imgui.combo(
                    f"##{prefix}_technology_level", level_index,
                    [str(level) for level in levels] or ["—"],
                    test_id=f"trade.{prefix}.technology_level",
                    gml_id=category_ui.path("cboLevel"),
                )
            finally:
                imgui.end_disabled()
                imgui.pop_style_var()
            if levels:
                selected_level = levels[level_index]
                setattr(self, level_attr, selected_level)
                category_ui.text("txtPrice", f"LEVEL {selected_level}", test_id=f"trade.{prefix}.technology_value")
            else:
                selected_level = 0
                category_ui.text(
                    "txtPrice", "UNAVAILABLE", test_id=f"trade.{prefix}.technology_value",
                    tooltip="The giver has no research level above the recipient.",
                )
            if category_ui.button(
                "btnAdd", "ADD", f"trade.{prefix}.add_technology", enabled=bool(levels),
            ) and levels:
                self._append_unique(assets, {
                    "type": "technology",
                    "branch": technologies[branch_index][0],
                    "level": selected_level,
                })

        self._render_asset_list(state, assets, prefix, root)

    @staticmethod
    def _render_numeric_stepper(
        path: str,
        test_id: str,
        direction: int,
        value: float,
        *,
        enabled: bool = True,
    ) -> tuple[bool, float]:
        layout = active_gml_layout()
        if layout is None or layout.layout.component(path) is None:
            return False, value
        imgui.begin_disabled(not enabled)
        try:
            changed = imgui.invisible_button(
                f"##{test_id}", test_id=test_id, gml_id=path,
            )
        finally:
            imgui.end_disabled()
        if changed and enabled:
            value = max(0.0, value + direction)
        rect = layout.rect_for(path)
        x = layout.window_position[0] + rect.x
        y = layout.window_position[1] + rect.y
        center_x, center_y = x + rect.width / 2.0, y + rect.height / 2.0
        color = imgui.get_color_u32(GAMETHEME.colors.text_main if enabled else GAMETHEME.colors.text_dim)
        draw = imgui.get_window_draw_list()
        if direction < 0:
            draw.add_line((center_x - 2.0, center_y - 1.0), (center_x, center_y + 1.0), color, 1.0)
            draw.add_line((center_x, center_y + 1.0), (center_x + 2.0, center_y - 1.0), color, 1.0)
        else:
            draw.add_line((center_x - 2.0, center_y + 1.0), (center_x, center_y - 1.0), color, 1.0)
            draw.add_line((center_x, center_y - 1.0), (center_x + 2.0, center_y + 1.0), color, 1.0)
        return changed, value

    def _render_asset_list(
        self,
        state,
        assets: list[dict[str, Any]],
        prefix: str,
        root: str,
    ) -> None:
        list_path = f"{root}/frmItems/lstItems"
        child_visible = imgui.begin_child(
            f"##{prefix}_assets",
            (0.0, 0.0),
            True,
            test_id=f"trade.{prefix}.asset_list",
            gml_id=list_path,
        )
        rows = self._asset_rows(assets)
        if child_visible:
            for index, asset in enumerate(rows):
                selected = index == self._selected_asset_index[prefix]
                if imgui.selectable(
                    self._asset_label(state, asset),
                    selected,
                    test_id=f"trade.{prefix}.asset.{index}",
                )[0]:
                    self._selected_asset_index[prefix] = index
        imgui.end_child()

        imgui.begin_disabled(not rows)
        if imgui.button(
            "REMOVE",
            test_id=f"trade.{prefix}.remove_selected",
            gml_id=f"{root}/frmItems/btnRemoveSelected",
        ):
            index = self._selected_asset_index[prefix]
            if 0 <= index < len(assets):
                assets.pop(index)
                self._selected_asset_index[prefix] = min(index, max(0, len(assets) - 1))
        if imgui.button(
            "CLEAR",
            test_id=f"trade.{prefix}.remove_all",
            gml_id=f"{root}/frmItems/btnRemoveAll",
        ):
            assets.clear()
            self._selected_asset_index[prefix] = 0
        imgui.end_disabled()

    def _render_trade_offer_list(self, state, country: str) -> None:
        root = "Trade_Window/frmInner/frmList"
        ui = GMLWidgets(root)
        ui.text("lblProposer", "PROPOSER")
        ui.text("lblRecipient", "RECIPIENT")
        ui.text("lblStatus", "STATUS")
        deals = self._country_deals(state, country)
        selected = next(
            (row for row in deals if str(row.get("id") or "") == self._selected_deal_id),
            None,
        )
        if selected is None:
            selected = next(
                (row for row in deals if str(row.get("status") or "") == "pending"),
                deals[0] if deals else None,
            )
            self._selected_deal_id = str(selected.get("id") or "") if selected else ""

        session = active_gml_layout()
        list_path = f"{root}/lstTrade"
        rect = session.rect_for(list_path) if session else None
        column_offsets = []
        if session is not None and rect is not None:
            for header in ("lblProposer", "lblRecipient", "lblStatus"):
                header_rect = session.rect_for(f"{root}/{header}")
                column_offsets.append(header_rect.x - rect.x)
        if session is not None and rect is not None:
            previous = imgui.get_cursor_screen_pos()
            token = suspend_gml_layout()
            try:
                imgui.set_cursor_screen_pos((
                    session.window_position[0] + rect.x,
                    session.window_position[1] + rect.y,
                ))
                if imgui.begin_child(
                    "##trade_offers",
                    (rect.width, rect.height),
                    True,
                    gml_id=list_path,
                ):
                    if not deals:
                        imgui.text_disabled("No bilateral trade offers yet.")
                    for row in deals:
                        deal_id = str(row.get("id") or "")
                        values = (
                            self._tag(row.get("source_country_id")),
                            self._tag(row.get("target_country_id")),
                            str(row.get("status") or "unknown").upper(),
                        )
                        clicked = imgui.selectable(
                            f"##trade_offer_{deal_id}",
                            deal_id == self._selected_deal_id,
                            size=(rect.width - 28.0, 15.0),
                            test_id=f"trade.deal.{deal_id}.row",
                        )[0]
                        row_origin = imgui.get_item_rect_min()
                        next_row = imgui.get_cursor_screen_pos()
                        for offset, value in zip(column_offsets, values):
                            imgui.set_cursor_screen_pos((row_origin.x + offset, row_origin.y + 1.0))
                            imgui.text(value)
                        imgui.set_cursor_screen_pos(next_row)
                        imgui.dummy((1.0, 1.0))
                        if clicked:
                            self._selected_deal_id = deal_id
                            selected = row
                imgui.end_child()
            finally:
                imgui.set_cursor_screen_pos(previous)
                resume_gml_layout(token)

        if ui.button(
            "btnViewTrade",
            "VIEW",
            "trade.deal.view",
            enabled=selected is not None,
            tooltip="View the selected offer and its available actions",
        ):
            self._requested_deal_id = str(selected.get("id") or "") if selected else ""
            self.active_page = "deal"

    def _render_trade_deal_detail(self, state, context, country: str) -> None:
        row = next(
            (
                deal for deal in self._country_deals(state, country)
                if str(deal.get("id") or "") == self._requested_deal_id
            ),
            None,
        )
        actions = GMLWidgets("Trade_Detailed_Window/frmInner")
        if row is None:
            imgui.text_wrapped("The selected offer is unavailable.", test_id="trade.selected_deal.unavailable")
            return

        source = self._tag(row.get("source_country_id"))
        target = self._tag(row.get("target_country_id"))
        incoming = target == country
        counterpart = source if incoming else target
        GMLWidgets("Trade_Detailed_Window/frmInner/frmSideA").text(
            "txtCountry", f"PROPOSER · {source}", test_id="trade.detail.proposer",
        )
        GMLWidgets("Trade_Detailed_Window/frmInner/frmSideB").text_at(
            "cboCountry", f"RECIPIENT · {target}", test_id="trade.detail.recipient",
        )
        self._render_deal_asset_slot(
            state,
            self._decode_assets(row.get("offered_assets_json")),
            "frmSideA",
            "OFFERED ASSETS",
            "trade.detail.offered",
        )
        self._render_deal_asset_slot(
            state,
            self._decode_assets(row.get("requested_assets_json")),
            "frmSideB",
            "REQUESTED ASSETS",
            "trade.detail.requested",
        )
        status = str(row.get("status") or "unknown").upper()
        GMLWidgets("Trade_Detailed_Window/frmInner/frmBalance").text(
            "lblBalance", f"{status} · {counterpart}", test_id="trade.detail.status",
        )

        pending = str(row.get("status") or "") == "pending"
        can_act = pending and context.is_own_country and context.net_client is not None
        deal_id = str(row.get("id") or "")
        if incoming:
            if actions.button("btnAccept", "ACCEPT", f"trade.deal.{deal_id}.accept", enabled=can_act):
                context.net_client.send_action(
                    ActionRespondTradeDeal(context.net_client.player_id, deal_id, country, True)
                )
                self.active_page = "offers"
                return
            if actions.button("btnCounterOffer1", "REJECT", f"trade.deal.{deal_id}.reject", enabled=can_act):
                context.net_client.send_action(
                    ActionRespondTradeDeal(context.net_client.player_id, deal_id, country, False)
                )
                self.active_page = "offers"
                return
            if actions.button("btnCounterOffer", "COUNTER", f"trade.deal.{deal_id}.counter", enabled=can_act):
                self._begin_counteroffer(row)
                return
        elif actions.button("btnAccept", "WITHDRAW", f"trade.deal.{deal_id}.withdraw", enabled=can_act):
            context.net_client.send_action(
                ActionWithdrawTradeDeal(context.net_client.player_id, deal_id, country)
            )
            self.active_page = "offers"
            return
        # GML reuses overlapping footer slots for state-specific actions; Back stays in the title bar.

    def _render_deal_asset_slot(
        self,
        state,
        assets: list[dict[str, Any]],
        side: str,
        heading: str,
        test_id: str,
    ) -> None:
        session = active_gml_layout()
        path = f"Trade_Detailed_Window/frmInner/{side}/frmItems/lstItems"
        component = session.layout.component(path) if session else None
        rect = session.rect_for(component) if session and component else None
        if session is None or rect is None:
            return

        previous = imgui.get_cursor_screen_pos()
        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((
                session.window_position[0] + rect.x,
                session.window_position[1] + rect.y,
            ))
            if imgui.begin_child(f"##{test_id}", (rect.width, rect.height), True, gml_id=path):
                imgui.text_disabled(heading)
                if assets:
                    for index, asset in enumerate(assets):
                        imgui.text_wrapped(
                            self._asset_label(state, asset),
                            test_id=f"{test_id}.{index}",
                        )
                else:
                    imgui.text_disabled("None")
            imgui.end_child()
        finally:
            imgui.set_cursor_screen_pos(previous)
            resume_gml_layout(token)

    def _country_deals(self, state, country: str) -> list[dict[str, Any]]:
        deals = [
            row for row in self._rows(state, "diplomatic_trade_deals")
            if country in {
                self._tag(row.get("source_country_id")),
                self._tag(row.get("target_country_id")),
            }
        ]
        return sorted(
            deals,
            key=lambda row: (
                str(row.get("status") or "") != "pending",
                -self._integer(row.get("created_at_minute")),
                str(row.get("id") or ""),
            ),
        )

    def _send_proposal(self, context, country: str, partner: str) -> None:
        if self.counter_to_deal_id:
            action = ActionCounterTradeDeal(
                context.net_client.player_id,
                self.counter_to_deal_id,
                country,
                list(self.offered_assets),
                list(self.requested_assets),
                int(self.expiry_days),
            )
        else:
            action = ActionCreateTradeDeal(
                context.net_client.player_id,
                country,
                partner,
                list(self.offered_assets),
                list(self.requested_assets),
                int(self.expiry_days),
            )
        context.net_client.send_action(action)
        self._reset_package()
        self.active_page = "offers"

    def _begin_counteroffer(self, row):
        self._reset_package()
        self.partner_tag = self._tag(row.get("source_country_id"))
        self.counter_to_deal_id = str(row.get("id") or "")
        # Incoming packages use the proposer's perspective; counteroffers reverse that perspective.
        self.offered_assets = [dict(asset) for asset in self._decode_assets(row.get("requested_assets_json"))]
        self.requested_assets = [dict(asset) for asset in self._decode_assets(row.get("offered_assets_json"))]
        self.active_page = "proposal"

    _country_options = staticmethod(trade_options.country_options)
    _regions_for_owner = staticmethod(trade_options.regions_for_owner)
    _technology_options = staticmethod(trade_options.technology_options)

    def _asset_label(self, state, asset: dict[str, Any]) -> str:
        asset_type = str(asset.get("type") or "")
        if asset_type == "cash":
            return f"Cash {self._number(asset.get('amount')):,.0f}"
        if asset_type == "technology":
            return f"Technology: {str(asset.get('branch') or '').replace('_', ' ').title()} to level {self._integer(asset.get('level'))}"
        if asset_type == "territory":
            region_id = self._integer(asset.get("region_id"))
            regions = state.tables.get("regions")
            if regions is not None:
                match = next((row for row in regions.iter_rows(named=True) if self._integer(row.get("id")) == region_id), None)
                if match:
                    name = match.get("name") or match.get("region_name") or match.get("display_name") or match.get("province")
                    if name:
                        return f"Region: {name} ({region_id})"
            return f"Region {region_id}"
        return str(asset)

    def _asset_rows(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(assets)

    @staticmethod
    def _append_unique(assets: list[dict[str, Any]], asset: dict[str, Any]) -> None:
        identity = (asset.get("type"), asset.get("region_id", asset.get("branch")))
        if any((row.get("type"), row.get("region_id", row.get("branch"))) == identity for row in assets):
            return
        assets.append(asset)

    def _reset_package(self, keep_counter: bool = False) -> None:
        self.offered_assets.clear()
        self.requested_assets.clear()
        self.offer_cash = 0.0
        self.request_cash = 0.0
        self.offer_region_idx = 0
        self.request_region_idx = 0
        self.offer_technology_idx = 0
        self.request_technology_idx = 0
        self.offer_technology_level = 0
        self.request_technology_level = 0
        if not keep_counter:
            self.counter_to_deal_id = ""

    def _country_at_war(self, state, left: str, right: str) -> bool:
        for war in self._rows(state, "countries_wars"):
            if str(war.get("status") or "active").casefold() != "active":
                continue
            side_a = {self._tag(value) for value in war.get("side_a", [])}
            side_b = {self._tag(value) for value in war.get("side_b", [])}
            if (left in side_a and right in side_b) or (left in side_b and right in side_a):
                return True
        return False

    @staticmethod
    def _decode_assets(raw: Any) -> list[dict[str, Any]]:
        try:
            value = json.loads(str(raw or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []

    _rows = staticmethod(trade_options.table_rows)
    _tag = staticmethod(trade_options.country_tag)
    _integer = staticmethod(trade_options.nonnegative_integer)

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0
