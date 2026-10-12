from __future__ import annotations

import json
import math
from typing import Any

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.shared.actions import (
    ActionCounterTradeDeal,
    ActionCreateTradeDeal,
    ActionRespondTradeDeal,
    ActionWithdrawTradeDeal,
)


class TradePanel:
    """Builds bilateral offers and presents the complete response lifecycle."""

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
        self.expiry_days = 30.0
        self.active_page = "proposal"
        self._draft_country = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("DIPLOMATIC TRADE", x=900, y=60, w=760, h=640) as is_open:
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
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))
        Prims.header("BILATERAL NEGOTIATION", show_bg=False)
        imgui.text_wrapped(
            "Package cash, regions, and researched technologies on both sides. "
            "The other country can accept, reject, or counter; accepted assets are checked again before transfer."
        )
        imgui.text_wrapped("Resource imports and exports are managed in Resources.")
        imgui.dummy((0, 6))

        partners = self._country_options(state, country)
        if not partners:
            imgui.text_disabled("No trade partners are available in the countries table.")
            imgui.pop_style_var()
            return
        if not any(tag == self.partner_tag for tag, _ in partners):
            self.partner_tag = partners[0][0]
        partner_index = next(i for i, item in enumerate(partners) if item[0] == self.partner_tag)
        imgui.text_disabled("COUNTERPARTY")
        imgui.same_line(140)
        imgui.set_next_item_width(320)
        imgui.begin_disabled(bool(self.counter_to_deal_id))
        changed, partner_index = imgui.combo(
            "##trade_partner",
            partner_index,
            [label for _, label in partners],
            test_id="trade.partner",
        )
        imgui.end_disabled()
        if changed:
            self.partner_tag = partners[partner_index][0]
            self._reset_package()

        if self.counter_to_deal_id:
            original = next((row for row in self._rows(state, "diplomatic_trade_deals")
                             if str(row.get("id")) == self.counter_to_deal_id), None)
            if original is None or original.get("status") != "pending" or self._integer(original.get("expires_at_minute")) <= self._integer(state.time.total_minutes):
                # Server updates can resolve an offer while its local draft is still being edited.
                self._reset_package()
                self.active_page = "offers"
                imgui.text_wrapped("The original offer is no longer pending. Review the latest offers below.")

        if imgui.button("Build proposal", test_id="trade.page.proposal"):
            self.active_page = "proposal"
        imgui.same_line()
        if imgui.button("Offers and history", test_id="trade.page.offers"):
            self.active_page = "offers"
        if self.active_page == "offers":
            self._render_pending_deals(state, context, country)
        elif not context.is_own_country or context.net_client is None:
            imgui.text_disabled("Control your own country to negotiate or respond to offers.")
        elif not self._country_at_war(state, country, self.partner_tag):
            self._render_package_editor(state, context, country, self.partner_tag)
        else:
            imgui.text_wrapped("These countries are at war. Use the peace-deal editor to negotiate terms.")

        self._render_action_feedback(state, context)
        imgui.pop_style_var()

    def _render_package_editor(self, state, context, country: str, partner: str) -> None:
        Prims.header("COUNTEROFFER" if self.counter_to_deal_id else "PROPOSAL BUILDER", show_bg=False)
        if self.counter_to_deal_id:
            imgui.text_wrapped(f"Responding to offer {self.counter_to_deal_id}. Edit the terms below.")
            if imgui.small_button("Cancel counteroffer", test_id="trade.cancel_counter"):
                self._reset_package()
        self._render_package_summary(state, country, partner)
        if imgui.get_content_region_avail().x >= 640 and imgui.begin_table("trade_package_sides", 2):
            imgui.table_next_column()
            self._render_asset_side(state, "YOU GIVE", self.offered_assets, country, partner, "offer")
            imgui.table_next_column()
            self._render_asset_side(state, "YOU REQUEST", self.requested_assets, partner, country, "request")
            imgui.end_table()
        else:
            self._render_asset_side(state, "YOU GIVE", self.offered_assets, country, partner, "offer")
            self._render_asset_side(state, "YOU REQUEST", self.requested_assets, partner, country, "request")
        imgui.dummy((0, 8))
        imgui.text_disabled("Offer expires after days")
        imgui.set_next_item_width(170)
        _, self.expiry_days = imgui.input_float("##trade_expiry_days", self.expiry_days, 1.0, 7.0, "%.0f", test_id="trade.expiry_days")
        self.expiry_days = min(365.0, max(1.0, self.expiry_days))
        can_submit = bool(self.offered_assets or self.requested_assets)
        imgui.begin_disabled(not can_submit)
        if imgui.button("Send counteroffer" if self.counter_to_deal_id else "Send proposal", (-1, 32), test_id="trade.send"):
            self._send_proposal(context, country, partner)
        imgui.end_disabled()
        if not can_submit:
            imgui.text_disabled("Add at least one asset to either side of the package.")

    def _render_package_summary(self, state, country, partner):
        imgui.text_wrapped(f"Proposed agreement: {country} / {partner} · {int(self.expiry_days)} days")
        for title, assets in ((f"{country} gives", self.offered_assets), (f"{partner} gives", self.requested_assets)):
            imgui.text_wrapped(f"{title}: {', '.join(self._asset_label(state, asset) for asset in assets) or 'Nothing selected'}")
        offered_cash = sum(self._number(asset.get("amount")) for asset in self.offered_assets if asset.get("type") == "cash")
        requested_cash = sum(self._number(asset.get("amount")) for asset in self.requested_assets if asset.get("type") == "cash")
        imgui.text(f"Your net cash transfer: {requested_cash - offered_cash:+,.0f}")
        imgui.separator()

    def _render_asset_side(self, state, title: str, assets: list[dict[str, Any]], giver: str, receiver: str, prefix: str) -> None:
        Prims.header(title, show_bg=False)
        rows = self._asset_rows(assets)
        if rows:
            child_visible = imgui.begin_child(f"##{prefix}_assets", (0.0, 74.0), True)
            if child_visible:
                for index, asset in enumerate(rows):
                    imgui.text_wrapped(self._asset_label(state, asset))
                    if imgui.small_button(f"Remove##{prefix}_{index}", test_id=f"trade.{prefix}.remove.{index}"):
                        assets.remove(asset)
                        break
            imgui.end_child()

        imgui.text_disabled("CASH")
        amount_attr = "offer_cash" if prefix == "offer" else "request_cash"
        amount = max(0.0, float(getattr(self, amount_attr)))
        imgui.set_next_item_width(max(90, imgui.get_content_region_avail().x - 90))
        _, amount = imgui.input_float(f"##{prefix}_cash", amount, 0.0, 0.0, "%.0f", test_id=f"trade.{prefix}.cash")
        setattr(self, amount_attr, max(0.0, amount))
        imgui.same_line()
        if imgui.small_button(f"Add cash##{prefix}", test_id=f"trade.{prefix}.add_cash") and amount > 0.0:
            assets.append({"type": "cash", "amount": round(amount, 2)})
            setattr(self, amount_attr, 0.0)
        balance = next(
            (
                self._number(row.get("money_reserves"))
                for row in self._rows(state, "countries")
                if self._tag(row.get("id")) == giver
            ),
            0.0,
        )
        imgui.text_disabled(f"{giver} available cash: {balance:,.0f}")

        regions = self._regions_for_owner(state, giver)
        if regions:
            attr = "offer_region_idx" if prefix == "offer" else "request_region_idx"
            index = max(0, min(int(getattr(self, attr)), len(regions) - 1))
            imgui.set_next_item_width(max(90, imgui.get_content_region_avail().x - 100))
            _, index = imgui.combo(f"##{prefix}_region", index, [label for _, label in regions], test_id=f"trade.{prefix}.region")
            setattr(self, attr, index)
            imgui.same_line()
            region_id = regions[index][0]
            if imgui.small_button(f"Add region##{prefix}", test_id=f"trade.{prefix}.add_region"):
                self._append_unique(assets, {"type": "territory", "region_id": region_id})

        technologies = self._technology_options(state, giver, receiver)
        if technologies:
            attr = "offer_technology_idx" if prefix == "offer" else "request_technology_idx"
            index = max(0, min(int(getattr(self, attr)), len(technologies) - 1))
            imgui.set_next_item_width(max(90, imgui.get_content_region_avail().x - 125))
            _, index = imgui.combo(f"##{prefix}_technology", index, [label for _, label in technologies], test_id=f"trade.{prefix}.technology")
            setattr(self, attr, index)
            imgui.same_line()
            asset = technologies[index][0]
            if imgui.small_button(f"Add technology##{prefix}", test_id=f"trade.{prefix}.add_technology"):
                self._append_unique(assets, dict(asset))
        else:
            imgui.text_wrapped("No technology is available that improves the recipient's research.")
        imgui.text_wrapped(f"Assets supplied by {giver}. Technology is copied; the giver keeps its research.")

    def _render_pending_deals(self, state, context, country: str) -> None:
        Prims.header("OPEN OFFERS AND HISTORY", show_bg=False)
        deals = self._rows(state, "diplomatic_trade_deals")
        if not deals:
            imgui.text_disabled("No bilateral trade offers yet.")
            return
        child_visible = imgui.begin_child("##trade_deals", (0.0, 250.0), True)
        if not child_visible:
            imgui.end_child()
            return
        pending = [row for row in deals if str(row.get("status") or "") == "pending"]
        history = [row for row in deals if str(row.get("status") or "") != "pending"]
        for row in pending:
            source = self._tag(row.get("source_country_id"))
            target = self._tag(row.get("target_country_id"))
            incoming = target == country
            if not incoming and source != country:
                continue
            other = source if incoming else target
            imgui.separator()
            imgui.text(f"{'INCOMING' if incoming else 'OUTGOING'} · {other} · {row.get('id', '')}")
            self._render_deal_assets(state, row)
            remaining = max(0, self._integer(row.get("expires_at_minute")) - self._integer(state.time.total_minutes))
            imgui.text(f"Expires in {math.ceil(remaining / 1440)} days")
            imgui.text_wrapped(str(row.get("reason") or ""))
            if not context.is_own_country or context.net_client is None:
                continue
            if incoming:
                if imgui.small_button(f"Accept##{row.get('id')}", test_id=f"trade.deal.{row.get('id')}.accept"):
                    context.net_client.send_action(
                        ActionRespondTradeDeal(context.net_client.player_id, str(row.get("id") or ""), country, True)
                    )
                imgui.same_line()
                if imgui.small_button(f"Reject##{row.get('id')}", test_id=f"trade.deal.{row.get('id')}.reject"):
                    context.net_client.send_action(
                        ActionRespondTradeDeal(context.net_client.player_id, str(row.get("id") or ""), country, False)
                    )
                imgui.same_line()
                if imgui.small_button(f"Counter##{row.get('id')}", test_id=f"trade.deal.{row.get('id')}.counter"):
                    self._begin_counteroffer(row)
            elif imgui.small_button(f"Withdraw##{row.get('id')}", test_id=f"trade.deal.{row.get('id')}.withdraw"):
                context.net_client.send_action(
                    ActionWithdrawTradeDeal(context.net_client.player_id, str(row.get("id") or ""), country)
                )
        if history:
            imgui.separator()
            imgui.text_disabled("RECENT RESOLVED OFFERS")
            relevant_history = [row for row in history if country in {self._tag(row.get("source_country_id")), self._tag(row.get("target_country_id"))}]
            for row in relevant_history[-12:][::-1]:
                source = self._tag(row.get("source_country_id"))
                target = self._tag(row.get("target_country_id"))
                if country not in {source, target}:
                    continue
                imgui.text_wrapped(
                    f"{source} / {target} · {row.get('status')} · {row.get('reason', '')}"
                )
        imgui.end_child()

    def _render_deal_assets(self, state, row: dict[str, Any]) -> None:
        offered = self._decode_assets(row.get("offered_assets_json"))
        requested = self._decode_assets(row.get("requested_assets_json"))
        imgui.text_wrapped(f"Gives: {', '.join(self._asset_label(state, asset) for asset in offered) or 'nothing'}")
        imgui.text_wrapped(f"Requests: {', '.join(self._asset_label(state, asset) for asset in requested) or 'nothing'}")
        counter_to = str(row.get("counter_to_deal_id") or "")
        if counter_to:
            imgui.text_disabled(f"Counteroffer to {counter_to}")

    def _render_action_feedback(self, state, context: PanelRenderContext) -> None:
        journal = getattr(state, "journal", None)
        results = getattr(journal, "command_results", [])
        if not results:
            return
        action_names = {
            "ActionCreateTradeDeal",
            "ActionCounterTradeDeal",
            "ActionRespondTradeDeal",
            "ActionWithdrawTradeDeal",
        }
        player_id = str(context.net_client.player_id) if context.net_client is not None else ""
        result = next(
            (
                row for row in reversed(results)
                if str(row.get("player_id") or "") == player_id
                and str(row.get("action_type") or "") in action_names
            ),
            None,
        )
        if result is not None:
            imgui.text_wrapped(f"Last trade action · {result.get('status')}: {result.get('reason', '')}")

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

    def _country_options(self, state, exclude_tag: str) -> list[tuple[str, str]]:
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return []
        result = []
        for row in countries.iter_rows(named=True):
            tag = self._tag(row.get("id"))
            if not tag or tag == exclude_tag:
                continue
            label = row.get("name") or row.get("display_name") or row.get("country_name") or tag
            result.append((tag, f"{label} ({tag})"))
        return sorted(result, key=lambda item: item[1])

    def _regions_for_owner(self, state, owner_tag: str) -> list[tuple[int, str]]:
        regions = state.tables.get("regions")
        if regions is None or not {"id", "owner"}.issubset(regions.columns):
            return []
        government = next(
            (row for row in self._rows(state, "country_governments") if self._tag(row.get("country_id")) == owner_tag),
            {},
        )
        capital_id = self._integer(government.get("capital_region_id"))
        owned_count = sum(
            1 for row in regions.iter_rows(named=True) if self._tag(row.get("owner")) == owner_tag
        )
        owned = []
        for row in regions.iter_rows(named=True):
            region_id = self._integer(row.get("id"))
            if self._tag(row.get("owner")) != owner_tag:
                continue
            if region_id == capital_id and owned_count <= 1:
                continue
            name = row.get("name") or row.get("region_name") or row.get("display_name") or row.get("province") or "Region"
            owned.append((region_id, f"{name} ({region_id})"))
        return sorted(owned, key=lambda item: item[1])

    def _technology_options(self, state, giver: str, receiver: str) -> list[tuple[dict[str, Any], str]]:
        tracks = self._rows(state, "research_tracks")
        levels = {
            (self._tag(row.get("country_id")), str(row.get("branch") or "").casefold()): self._integer(row.get("research_level"))
            for row in tracks
        }
        options = []
        for (country, branch), level in levels.items():
            if country != giver or level <= levels.get((receiver, branch), 0):
                continue
            asset = {"type": "technology", "branch": branch, "level": level}
            options.append((asset, f"{branch.replace('_', ' ').title()} (level {level})"))
        return sorted(options, key=lambda item: item[1])

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

    @staticmethod
    def _rows(state, table: str) -> list[dict[str, Any]]:
        frame = state.tables.get(table)
        return [] if frame is None else frame.to_dicts()

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0
