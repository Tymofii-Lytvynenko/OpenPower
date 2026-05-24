import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims


class TradePanel:
    """Negotiation UI for diplomatic territory and technology deals."""

    DEAL_TYPES = ["Territory Transfer", "Technology Transfer"]

    def __init__(self):
        self.deal_type_idx = 0
        self.partner_idx = 0
        self.offer_region_idx = 0
        self.request_region_idx = 0
        self.offer_tech_idx = 0
        self.request_tech_idx = 0

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("DIPLOMATIC TRADE", x=720, y=120, w=760, h=620) as is_open:
            if not is_open:
                return False
            self._render_content(
                state=state,
                target_tag=context.target_tag,
                selected_region_id=context.selected_region_id,
                is_own=context.is_own_country,
            )
            return True

    def _render_content(self, state, target_tag: str, selected_region_id, is_own: bool):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        Prims.header("TRADE SCOPE", show_bg=False)
        imgui.text_wrapped(
            "This panel is for negotiated diplomatic deals: technology transfer "
            "and territory transfer. Resource imports and exports are shown in "
            "the Resources panel and are not part of this interface."
        )
        imgui.dummy((0, 8))

        partners = self._country_options(state, exclude_tag=target_tag)
        if not partners:
            imgui.text_disabled("No trade partners are available in the countries table.")
            imgui.pop_style_var()
            return

        self.partner_idx = max(0, min(self.partner_idx, len(partners) - 1))
        partner_tag, _ = partners[self.partner_idx]

        imgui.text_disabled("PARTNER")
        imgui.same_line(140)
        imgui.set_next_item_width(280)
        changed, self.partner_idx = imgui.combo(
            "##trade_partner",
            self.partner_idx,
            [label for _, label in partners],
        )
        if changed:
            partner_tag, _ = partners[self.partner_idx]
            self.offer_region_idx = 0
            self.request_region_idx = 0
            self.offer_tech_idx = 0
            self.request_tech_idx = 0

        imgui.text_disabled("DEAL TYPE")
        imgui.same_line(140)
        imgui.set_next_item_width(280)
        _, self.deal_type_idx = imgui.combo("##trade_deal_type", self.deal_type_idx, self.DEAL_TYPES)
        imgui.dummy((0, 8))

        self._render_context_summary(state, target_tag, partner_tag, selected_region_id)
        imgui.dummy((0, 8))

        if self.deal_type_idx == 0:
            self._render_territory_trade(state, target_tag, partner_tag)
        else:
            self._render_technology_trade(state, target_tag, partner_tag)

        imgui.dummy((0, 12))
        self._render_submit_area(is_own)
        imgui.pop_style_var()

    def _country_options(self, state, exclude_tag: str) -> list[tuple[str, str]]:
        if "countries" not in state.tables:
            return []

        try:
            countries = state.get_table("countries")
            if "id" not in countries.columns:
                return []

            labels = []
            for row in countries.iter_rows(named=True):
                tag = str(row.get("id") or "")
                if not tag or tag == exclude_tag:
                    continue
                name = row.get("name") or row.get("display_name") or row.get("country_name") or tag
                labels.append((tag, f"{name} ({tag})"))
            return sorted(labels, key=lambda item: item[1])
        except Exception:
            return []

    def _render_context_summary(self, state, target_tag: str, partner_tag: str, selected_region_id):
        Prims.header("NEGOTIATION CONTEXT", show_bg=False)
        self._draw_text_row("Your country", target_tag)
        self._draw_text_row("Counterparty", partner_tag)

        selected_label = "No region selected"
        if selected_region_id is not None and "regions" in state.tables:
            try:
                row = state.get_table("regions").filter(pl.col("id") == selected_region_id)
                if not row.is_empty():
                    owner = row["owner"][0] if "owner" in row.columns else "Unknown"
                    name = self._region_name(row.to_dicts()[0])
                    selected_label = f"{name} / owner: {owner}"
            except Exception:
                selected_label = "Unable to read selected region"

        self._draw_text_row("Selected region", selected_label)

    def _render_territory_trade(self, state, target_tag: str, partner_tag: str):
        Prims.header("TERRITORY TRANSFER", show_bg=False)

        own_regions = self._regions_for_owner(state, target_tag)
        partner_regions = self._regions_for_owner(state, partner_tag)

        imgui.text_disabled("OFFER TERRITORY")
        imgui.same_line(180)
        imgui.set_next_item_width(-1)
        if own_regions:
            self.offer_region_idx = max(0, min(self.offer_region_idx, len(own_regions) - 1))
            _, self.offer_region_idx = imgui.combo(
                "##offer_region",
                self.offer_region_idx,
                [label for _, label in own_regions],
            )
        else:
            imgui.text_disabled("No owned regions available")

        imgui.text_disabled("REQUEST TERRITORY")
        imgui.same_line(180)
        imgui.set_next_item_width(-1)
        if partner_regions:
            self.request_region_idx = max(0, min(self.request_region_idx, len(partner_regions) - 1))
            _, self.request_region_idx = imgui.combo(
                "##request_region",
                self.request_region_idx,
                [label for _, label in partner_regions],
            )
        else:
            imgui.text_disabled("Partner has no listed regions")

        imgui.dummy((0, 8))
        imgui.text_wrapped(
            "This is a proposal builder only. It intentionally does not call "
            "ActionAnnexRegion or ActionOccupyRegion, because those are direct "
            "state-change actions, not negotiated diplomatic trade."
        )

    def _render_technology_trade(self, state, target_tag: str, partner_tag: str):
        Prims.header("TECHNOLOGY TRANSFER", show_bg=False)

        tech_tables = self._technology_tables(state)
        if not tech_tables:
            imgui.text_disabled("No technology or research table is loaded in the current ruleset.")
            imgui.text_wrapped(
                "The panel is reserved for technology deals, but it cannot show "
                "available technologies until the simulation exposes a technology "
                "inventory or research table and a diplomacy proposal action."
            )
            return

        imgui.text_disabled("AVAILABLE DATA")
        for table_name in tech_tables:
            imgui.bullet_text(table_name)

        imgui.dummy((0, 8))
        imgui.text_wrapped(
            f"Technology deal UI is scoped to {target_tag} <-> {partner_tag}. "
            "Mapping concrete technologies requires the schema of the detected "
            "technology tables."
        )

    def _render_submit_area(self, is_own: bool):
        Prims.header("PROPOSAL", show_bg=False)

        can_submit = False
        if not is_own:
            imgui.text_disabled("Only your own country can initiate diplomatic trade proposals.")
        else:
            imgui.text_disabled("Diplomatic proposal action is not implemented in the current ruleset.")

        imgui.begin_disabled(not can_submit)
        imgui.button("SEND PROPOSAL", (-1, 32))
        imgui.end_disabled()

    def _regions_for_owner(self, state, owner_tag: str) -> list[tuple[int, str]]:
        if "regions" not in state.tables:
            return []

        try:
            regions = state.get_table("regions")
            if "owner" not in regions.columns or "id" not in regions.columns:
                return []

            result = []
            for row in regions.filter(pl.col("owner") == owner_tag).iter_rows(named=True):
                region_id = int(row.get("id"))
                result.append((region_id, self._region_name(row)))
            return sorted(result, key=lambda item: item[1])
        except Exception:
            return []

    def _region_name(self, row: dict) -> str:
        for key in ("name", "region_name", "display_name", "province", "city"):
            value = row.get(key)
            if value:
                return f"{value} ({row.get('id')})"
        return f"Region {row.get('id')}"

    def _technology_tables(self, state) -> list[str]:
        return sorted(
            name for name in state.tables.keys() if "tech" in name.lower() or "research" in name.lower()
        )

    def _draw_text_row(self, label: str, value: str):
        imgui.text_disabled(label)
        imgui.same_line(140)
        imgui.text(str(value))
