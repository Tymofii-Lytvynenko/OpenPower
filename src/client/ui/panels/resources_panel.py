import math
from dataclasses import dataclass

import numpy as np
import polars as pl

from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.components.shared.increase_production_dialog import (
    IncreaseProductionDialog,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.instrumented_implot import implot
from src.client.ui.core.panel_close_intent import PanelCloseIntent
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import draw_gml_separator
from src.client.ui.panels.resource_flows import (
    RESOURCE_LEDGER_COLUMNS,
    TRADE_NETWORK_COLUMNS,
    build_resource_flows,
    validate_resource_ledger,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import (
    ActionIncreaseResourceProduction,
    ActionUpdateResourcePolicy,
)


@dataclass
class ResourcePolicyDraft:
    baseline_management: int
    baseline_status: int
    baseline_tax: int
    management: int
    status: int
    tax: int

    @property
    def values(self) -> tuple[int, int, int]:
        return self.management, self.status, self.tax

    @property
    def baseline(self) -> tuple[int, int, int]:
        return self.baseline_management, self.baseline_status, self.baseline_tax

    @property
    def is_dirty(self) -> bool:
        return self.values != self.baseline

    def rebase(self, values: tuple[int, int, int]) -> None:
        self.baseline_management, self.baseline_status, self.baseline_tax = values
        self.management, self.status, self.tax = values


@dataclass(frozen=True)
class PendingResourcePolicy:
    values: tuple[int, int, int]
    player_id: str
    result_cursor: int


@dataclass(frozen=True)
class PendingProductionIncrease:
    player_id: str
    result_cursor: int


class ResourcesPanel:
    """Resources directory backed by live data and policy actions."""

    RESOURCE_LEDGER_COLUMNS = RESOURCE_LEDGER_COLUMNS
    TRADE_NETWORK_COLUMNS = TRADE_NETWORK_COLUMNS

    def __init__(self):
        self._close_intent = PanelCloseIntent()
        self.request_close = self._close_intent.request
        self.selected_resource = None
        self.has_unsaved_changes = False
        self.close_confirmation = DirtyCloseConfirmation(
            "resources.close",
            "Apply your resource policy changes before closing?",
        )
        self._local_save_confirmation_preferences = SaveConfirmationPreferences()
        self._increase_production_dialog = IncreaseProductionDialog()

        self.opts_man = ["Private Market", "State Monopoly"]
        self.opts_sta = ["Legalized", "Banned"]

        self.draft_management = 0
        self.draft_status = 0
        self.draft_tax = 0
        self.current_policy_key = None
        # The source keeps dirty policy values per resource while the selection changes.
        self._policy_drafts: dict[tuple[str, str], ResourcePolicyDraft] = {}
        self._pending_policy_updates: dict[tuple[str, str], PendingResourcePolicy] = {}
        self._pending_production_increases: dict[tuple[str, str], PendingProductionIncrease] = {}
        self._flow_cache_ledger: pl.DataFrame | None = None
        self._flow_cache_trade: pl.DataFrame | None = None
        self._flow_cache_country: str | None = None
        self._flow_cache_frame: pl.DataFrame | None = None
        self._panel_diagnostic: str | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        navigation_close = self._close_intent.consume()
        target_tag = context.target_tag
        is_own = context.is_own_country
        net_client = context.net_client
        self._resolve_pending_production_increases(state)
        preferences = (
            context.save_confirmation_preferences
            or self._local_save_confirmation_preferences
        )
        can_apply = bool(
            is_own
            and net_client
            and any(
                country == str(target_tag or "").strip().upper()
                and draft.is_dirty
                and (country, resource) not in self._pending_policy_updates
                for (country, resource), draft in self._policy_drafts.items()
            )
        )
        keep_open = True
        with WindowManager.window(
            "RESOURCES MENU",
            x=400,
            y=100,
            w=850,
            h=710,
            test_id="resources.panel",
        ) as is_open:
            close_decision = None
            if not is_open or navigation_close:
                if self.has_unsaved_changes:
                    close_decision = self.close_confirmation.request_close(
                        preferences,
                        can_apply=can_apply,
                    )
                else:
                    keep_open = False

            if is_open and not navigation_close:
                imgui.begin_disabled(not can_apply)
                imgui.push_style_color(
                    imgui.Col_.button,
                    GAMETHEME.colors.interaction_active if can_apply else (0, 0, 0, 0),
                )
                if Prims.button(
                    "✓",
                    test_id="resources.apply",
                    size=(17.0, 17.0),
                    enabled=can_apply,
                ) and can_apply:
                    self._dispatch_policy_updates(net_client, target_tag, state)
                imgui.pop_style_color()
                imgui.end_disabled()

                self._render_content(state, target_tag, is_own)

            if close_decision is not None:
                self._finish_close(close_decision, state, target_tag, net_client)
                keep_open = False
            elif keep_open:
                close_decision = self.close_confirmation.render(
                    preferences,
                    can_apply=can_apply,
                )
                if close_decision is not None:
                    self._finish_close(close_decision, state, target_tag, net_client)
                    keep_open = False

        if self._increase_production_dialog.is_open:
            increase_percent = self._increase_production_dialog.render(
                state,
                can_apply=bool(
                    is_own
                    and net_client
                    and not self._pending_production_increases
                ),
            )
            if increase_percent is not None:
                self._dispatch_production_increase(
                    net_client,
                    self._increase_production_dialog.country_tag,
                    self._increase_production_dialog.resource_id,
                    increase_percent,
                    state,
                )
        return keep_open

    def _resolve_pending_production_increases(self, state) -> None:
        results = getattr(getattr(state, "journal", None), "command_results", [])
        for key, pending in tuple(self._pending_production_increases.items()):
            for result in results[pending.result_cursor:]:
                if result.get("action_type") != "ActionIncreaseResourceProduction":
                    continue
                actor = str(result.get("actor_id") or result.get("player_id") or "")
                if actor != pending.player_id:
                    continue
                result_country = str(result.get("country_id") or key[0]).strip().upper()
                result_resource = str(result.get("resource_id") or key[1]).strip().lower()
                if (result_country, result_resource) == key:
                    self._pending_production_increases.pop(key, None)
                    break

    def _dispatch_production_increase(
        self,
        net_client,
        country_tag: str,
        resource_id: str,
        increase_percent: int,
        state,
    ) -> None:
        country = str(country_tag or "").strip().upper()
        resource = str(resource_id or "").strip().lower()
        key = (country, resource)
        if not net_client or key in self._pending_production_increases:
            return
        player_id = str(net_client.player_id or "")
        results = getattr(getattr(state, "journal", None), "command_results", [])
        self._pending_production_increases[key] = PendingProductionIncrease(
            player_id,
            len(results),
        )
        net_client.send_action(
            ActionIncreaseResourceProduction(
                player_id=player_id,
                country_tag=country,
                resource_id=resource,
                increase_percent=increase_percent,
            )
        )

    def _dispatch_policy_updates(self, net_client, target_tag, state) -> None:
        country = str(target_tag or "").strip().upper()
        player_id = str(net_client.player_id or "")
        result_cursor = len(getattr(getattr(state, "journal", None), "command_results", []))
        for (draft_country, resource), draft in sorted(self._policy_drafts.items()):
            key = (draft_country, resource)
            if (
                draft_country != country
                or not draft.is_dirty
                or key in self._pending_policy_updates
            ):
                continue
            management, status, tax = draft.values
            self._pending_policy_updates[key] = PendingResourcePolicy(
                draft.values,
                player_id,
                result_cursor,
            )
            net_client.send_action(
                ActionUpdateResourcePolicy(
                    player_id=player_id,
                    country_tag=country,
                    resource_id=resource,
                    is_gov_controlled=management == 1,
                    is_legal=status == 0,
                    tax_rate=tax / 100.0,
                )
            )
        self._refresh_dirty_state()

    def _finish_close(self, decision, state, target_tag, net_client) -> None:
        if decision is CloseDecision.APPLY and net_client:
            self._dispatch_policy_updates(net_client, target_tag, state)
            return
        self._discard_unsubmitted_drafts()
        self._sync_policy_from_state(state, target_tag)

    def _render_content(self, state, target_tag, is_own):
        abbreviate = state.globals.get("abbreviate_numbers", False)

        imgui.push_style_color(imgui.Col_.child_bg, (0.05, 0.05, 0.05, 1.0))
        imgui.begin_child(
            "table_view",
            (0, 157),
            child_flags=imgui.ChildFlags_.borders,
            gml_id="Resources_Window/frmInner/frmResources/frmResources",
        )
        flags = (
            imgui.TableFlags_.scroll_y
            | imgui.TableFlags_.borders
            | imgui.TableFlags_.row_bg
            | imgui.TableFlags_.resizable
        )

        imgui.push_style_var(imgui.StyleVar_.item_spacing, (4.0, 0.0))
        if imgui.begin_table("ResourcesTable", 5, flags):
            try:
                imgui.table_setup_scroll_freeze(0, 1)
                imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_fixed, 110)
                imgui.table_setup_column("PRODUCTION", imgui.TableColumnFlags_.width_fixed, 90)
                imgui.table_setup_column("CONSUMPTION", imgui.TableColumnFlags_.width_fixed, 90)
                imgui.table_setup_column("MARKET FLOW", imgui.TableColumnFlags_.width_fixed, 90)
                imgui.table_setup_column("BALANCE", imgui.TableColumnFlags_.width_fixed, 80)
                imgui.table_headers_row()

                if "resource_ledger" in state.tables:
                    ledger_full = state.tables["resource_ledger"]
                    ledger_country = ledger_full.filter(pl.col("country_id") == target_tag) if target_tag else ledger_full

                    if not ledger_country.is_empty():
                        categories = ledger_country.select("category").unique().to_series().to_list()
                        categories.sort()

                        for cat in categories:
                            cat_df = ledger_country.filter(pl.col("category") == cat)

                            cat_prod_usd = cat_df["production_usd"].sum()
                            cat_cons_usd = cat_df["consumption_usd"].sum()
                            cat_trade_usd = cat_df["trade_usd"].sum()
                            cat_bal_usd = cat_df["balance_usd"].sum()

                            imgui.table_next_row()
                            imgui.table_next_column()
                            safe_cat = str(cat) if cat is not None else "Unclassified"
                            tree_open = imgui.tree_node_ex(
                                safe_cat,
                                imgui.TreeNodeFlags_.default_open if safe_cat == "Services" else 0,
                                test_id=f"resources.category.{safe_cat.lower().replace(' ', '_')}",
                            )

                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_prod_usd, abbreviate))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_cons_usd, abbreviate))
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_trade_usd, abbreviate))

                            color = (
                                GAMETHEME.colors.negative
                                if cat_bal_usd is not None and cat_bal_usd < 0
                                else GAMETHEME.colors.positive
                            )
                            imgui.table_next_column(); Prims.right_align_text(self._fmt_money(cat_bal_usd, abbreviate), color)

                            if tree_open:
                                res_df = cat_df.sort("game_resource_id")
                                for row in res_df.iter_rows(named=True):
                                    g_id = row.get("game_resource_id")
                                    res_name = str(g_id).replace("_", " ").title() if g_id else "Unknown"

                                    self._draw_leaf_row(
                                        g_id,
                                        res_name,
                                        row["production_usd"],
                                        row["consumption_usd"],
                                        row["trade_usd"],
                                        row["balance_usd"],
                                        abbreviate,
                                        state,
                                        target_tag,
                                    )
                                imgui.tree_pop()
                    else:
                        imgui.table_next_row()
                        imgui.table_next_column()
                        draw_empty_state("No resource data available.")
            except (pl.exceptions.PolarsError, KeyError, TypeError, ValueError) as exc:
                imgui.text_disabled(f"Resource ledger data is invalid: {exc}")

            imgui.end_table()
        imgui.pop_style_var()
        imgui.end_child()
        imgui.pop_style_color()

        self._render_controls(state, target_tag, is_own)
        self._render_market_flow_summary(
            state,
            target_tag,
            is_own=is_own,
            gml_id="Resources_Window/frmInner/frmResources/frmStockMarket",
        )

    def _fmt_money(self, val, abbreviate=False) -> str:
        if val is None:
            return "$ 0 M" if abbreviate else "$ 0"
        if abbreviate:
            # Live national totals exceed billions; rendering them in millions
            # overran adjacent metric cards even though small fixture values fit.
            for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
                if abs(val) >= scale:
                    return f"$ {val / scale:.1f} {suffix}"
            return f"$ {val:.0f}"
        return f"$ {val:,.0f}".replace(",", " ")

    def _draw_leaf_row(self, resource_id, name, p_usd, c_usd, t_usd, b_usd, abbreviate=False,
                       state=None, target_tag=None):
        imgui.table_next_row()
        imgui.table_next_column()
        imgui.dummy((7, 0))
        imgui.same_line()

        is_selected = self.selected_resource == resource_id
        if imgui.selectable(
            name,
            is_selected,
            imgui.SelectableFlags_.span_all_columns,
            test_id=f"resources.resource.{resource_id}",
        )[0]:
            self._refresh_current_draft()
            self.selected_resource = resource_id
            self.current_policy_key = None
            if state is not None:
                self._sync_policy_from_state(state, target_tag)

        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(p_usd, abbreviate))
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(c_usd, abbreviate))
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(t_usd, abbreviate))

        color_usd = GAMETHEME.colors.negative if b_usd and b_usd < 0 else GAMETHEME.colors.positive
        imgui.table_next_column(); Prims.right_align_text(self._fmt_money(b_usd, abbreviate), color_usd)

    def _render_controls(self, state, target_tag, is_own):
        self._sync_policy_from_state(state, target_tag)
        country = str(target_tag or "").strip().upper()
        resource = str(self.selected_resource or "").strip().lower()
        increase_pending = bool(self._pending_production_increases)
        controls_disabled = bool(
            not is_own
            or not self.selected_resource
            or self.current_policy_key in self._pending_policy_updates
            or increase_pending
        )
        ledger = state.tables.get("resource_ledger")
        ledger_required = {"country_id", "game_resource_id", "production_usd", "balance_usd"}
        if self.selected_resource and ledger is not None:
            missing = ledger_required.difference(ledger.columns)
            if missing:
                self._panel_diagnostic = (
                    "Resource ledger is missing columns: " + ", ".join(sorted(missing))
                )

        imgui.push_style_var(imgui.StyleVar_.frame_padding, (8.0, 0.5))
        imgui.push_style_color(imgui.Col_.frame_bg, GAMETHEME.colors.bg_input)
        if controls_disabled:
            imgui.begin_disabled()

        # A missing ledger value must not look like a zero balance or available stock.
        pct_gdp_str, mkt_share_str, avail_str = "-- %", "-- %", "Unavailable"
        actual_trade_str = "Unavailable"
        res_name = "Select a Resource"

        if self._panel_diagnostic:
            imgui.text_disabled(self._panel_diagnostic)

        if self.selected_resource and ledger is not None and "countries" in state.tables and not self._panel_diagnostic:
            res_name = self.selected_resource.replace("_", " ").upper()
            countries = state.tables["countries"]

            c_row = ledger.filter(
                (pl.col("country_id") == target_tag)
                & (pl.col("game_resource_id") == self.selected_resource)
            )
            if not c_row.is_empty():
                c_prod = c_row["production_usd"].sum()
                c_bal = c_row["balance_usd"].sum()
                avail_str = self._fmt_money(c_bal, abbreviate=True).replace("$ ", "")
                raw_trade = c_row["trade_usd"].sum()
                if raw_trade is not None and math.isfinite(float(raw_trade)):
                    actual_trade_str = self._fmt_money(float(raw_trade), abbreviate=True)

                country_data = countries.filter(pl.col("id") == target_tag)
                if not country_data.is_empty() and "gdp" in country_data.columns and country_data["gdp"][0]:
                    pct_gdp_str = f"{(c_prod / country_data['gdp'][0]) * 100:.2f} %"

                w_row = ledger.filter(pl.col("game_resource_id") == self.selected_resource)
                world_prod = w_row["production_usd"].sum()
                if world_prod:
                    mkt_share_str = f"{(c_prod / world_prod) * 100:.2f} %"

        imgui.text_colored(
            GAMETHEME.colors.accent,
            res_name,
            gml_id="Resources_Window/frmInner/frmResources/lblResource",
        )
        draw_gml_separator(
            "Resources_Window/frmInner/frmResources/picSep",
            color=(0.6, 0.6, 0.6, 0.2),
        )

        imgui.text_disabled(
            "MANAGEMENT",
            gml_id="Resources_Window/frmInner/frmResources/lblManagement",
        )
        changed, self.draft_management = imgui.combo(
            "##resources.policy.management",
            self.draft_management,
            self.opts_man,
            test_id="resources.policy.management",
            gml_id="Resources_Window/frmInner/frmResources/cboManagement",
        )
        if changed:
            self._set_current_draft_value("management", self.draft_management)

        imgui.text_disabled(
            "LEGAL STATUS",
            gml_id="Resources_Window/frmInner/frmResources/lblStatus",
        )
        changed, self.draft_status = imgui.combo(
            "##resources.policy.status",
            self.draft_status,
            self.opts_sta,
            test_id="resources.policy.status",
            gml_id="Resources_Window/frmInner/frmResources/cboStatus",
        )
        if changed:
            self._set_current_draft_value("status", self.draft_status)

        imgui.text_disabled(
            "RESOURCE TAX",
            gml_id="Resources_Window/frmInner/frmResources/lblSectorTax",
        )
        self._render_tax_control()

        imgui.text_disabled("SHARE OF GDP", gml_id="Resources_Window/frmInner/frmResources/lblGdp")
        imgui.text(pct_gdp_str, gml_id="Resources_Window/frmInner/frmResources/txtGdp")
        imgui.text_disabled("MKT SHARE", gml_id="Resources_Window/frmInner/frmResources/lblMarketShare")
        imgui.text(mkt_share_str, gml_id="Resources_Window/frmInner/frmResources/txtMarketShare")

        imgui.text_disabled("NET BALANCE", gml_id="Resources_Window/frmInner/frmResources/lblMarketAvailability")
        imgui.text(
            avail_str,
            gml_id="Resources_Window/frmInner/frmResources/txtAvailability",
        )

        imgui.text_disabled(
            "GLOBAL TAX",
            gml_id="Resources_Window/frmInner/frmResources/lblGlobalTaxMod",
        )
        self._render_unavailable_resource_value(
            "global_tax_modifier",
            "frmGlobalTaxMod",
            "OpenPower has no global resource-tax modifier field.",
        )

        imgui.text_disabled("TRADE", gml_id="Resources_Window/frmInner/frmResources/lblTrade2")
        trade_tooltip = "OpenPower has no per-resource import/export target action."
        imgui.begin_disabled()
        imgui.combo(
            "##resources.trade",
            0,
            ("Unavailable",),
            test_id="resources.policy.trade",
            gml_id="Resources_Window/frmInner/frmResources/cboTrade",
            gml_enabled=False,
        )
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(trade_tooltip)
        imgui.end_disabled()
        imgui.text_disabled("ACTUAL", gml_id="Resources_Window/frmInner/frmResources/lblActual")
        imgui.text(
            actual_trade_str,
            test_id="resources.actual_trade",
            gml_id="Resources_Window/frmInner/frmResources/txtActual",
        )
        if imgui.is_item_hovered() and actual_trade_str != "Unavailable":
            imgui.set_tooltip("Net recorded trade value (exports minus imports), in USD.")

        imgui.text_disabled("DESIRED", gml_id="Resources_Window/frmInner/frmResources/lblDesired")
        self._render_unavailable_resource_value(
            "desired_trade",
            "frmDesired",
            trade_tooltip,
        )

        imgui.begin_disabled()
        imgui.checkbox(
            "##resources.policy.meet_consumption",
            False,
            test_id="resources.policy.meet_consumption",
            gml_id="Resources_Window/frmInner/frmResources/togMeetConsumption",
            gml_enabled=False,
        )
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip("OpenPower has no per-resource meet-consumption policy field.")
        imgui.end_disabled()
        imgui.text_disabled(
            "Meet consumption",
            gml_id="Resources_Window/frmInner/frmResources/lblMeetConsumption",
        )

        if imgui.button(
            "INCREASE PRODUCTION",
            (170.0, 18.0),
            test_id="resources.increase_production",
            gml_id="Resources_Window/frmInner/frmResources/btnIncreaseProduction",
        ):
            self._increase_production_dialog.open(target_tag, self.selected_resource)
        if increase_pending and imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip("Production increase request is awaiting an authoritative result.")

        if controls_disabled:
            imgui.end_disabled()
        imgui.pop_style_color()
        imgui.pop_style_var()

    def _render_unavailable_resource_value(
        self,
        key: str,
        gml_stepper: str,
        tooltip: str,
    ) -> None:
        widgets = GMLWidgets("Resources_Window/frmInner/frmResources")
        field_gml_id = widgets.path(f"{gml_stepper}/edtText")
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 1.0))
        imgui.begin_disabled()
        try:
            unavailable_text = "N/A" if key == "desired_trade" else "Unavailable"
            widgets.arrow_button(
                f"{gml_stepper}/btnDown",
                "down",
                f"resources.policy.{key}.decrement",
                enabled=False,
                tooltip=tooltip,
                gml_id=widgets.path(f"{gml_stepper}/btnDown"),
            )
            imgui.input_text(
                f"##resources.policy.{key}",
                unavailable_text,
                flags=imgui.InputTextFlags_.read_only,
                test_id=f"resources.policy.{key}",
                gml_id=field_gml_id,
                gml_enabled=False,
            )
            if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
                imgui.set_tooltip(tooltip)
            widgets.arrow_button(
                f"{gml_stepper}/btnUp",
                "up",
                f"resources.policy.{key}.increment",
                enabled=False,
                tooltip=tooltip,
                gml_id=widgets.path(f"{gml_stepper}/btnUp"),
            )
        finally:
            imgui.end_disabled()
            imgui.pop_style_var()

    def _render_tax_control(self) -> None:
        widgets = GMLWidgets("Resources_Window/frmInner/frmResources")
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
        try:
            changed, value = imgui.input_int(
                "##resources.policy.tax",
                self.draft_tax,
                0,
                0,
                test_id="resources.policy.tax",
                # frmUpdatableValue is composite; the numeric edit is its edtText child.
                gml_id=widgets.path("frmSectorTax/edtText"),
            )
        finally:
            imgui.pop_style_var()
        if changed:
            self._set_draft_tax(value)

        if widgets.arrow_button(
            "frmSectorTax/btnDown",
            "down",
            "resources.policy.tax.decrement",
            enabled=self.draft_tax > 0,
            tooltip="Decrease resource tax by 1 percentage point",
            gml_id=widgets.path("frmSectorTax/btnDown"),
        ):
            self._set_draft_tax(self.draft_tax - 1)

    def _set_draft_tax(self, value: int) -> None:
        tax = max(0, min(100, int(value)))
        if tax != self.draft_tax:
            self.draft_tax = tax
            self._set_current_draft_value("tax", tax)

    def _sync_policy_from_state(self, state, target_tag):
        self._panel_diagnostic = None
        if not self.selected_resource:
            self._refresh_dirty_state()
            return

        country = str(target_tag or "").strip().upper()
        key = (country, str(self.selected_resource or "").strip().lower())
        values = self._read_policy_values(state, key)
        draft = self._policy_drafts.get(key)
        pending = self._pending_policy_updates.get(key)

        if pending is not None:
            rejection = self._find_policy_rejection(state, key, pending)
            if values == pending.values:
                self._pending_policy_updates.pop(key, None)
                draft = self._policy_drafts[key]
                draft.rebase(values)
            elif rejection is not None:
                self._pending_policy_updates.pop(key, None)
                draft = self._policy_drafts[key]
                draft.baseline_management, draft.baseline_status, draft.baseline_tax = values
                draft.management, draft.status, draft.tax = pending.values
            elif draft is None:
                draft = ResourcePolicyDraft(*values, *pending.values)
                self._policy_drafts[key] = draft
        elif draft is None:
            draft = ResourcePolicyDraft(*values, *values)
            self._policy_drafts[key] = draft
        elif not draft.is_dirty:
            draft.rebase(values)

        if draft is not None:
            self.draft_management, self.draft_status, self.draft_tax = draft.values
        self.current_policy_key = key
        self._refresh_dirty_state()

    def _read_policy_values(self, state, key: tuple[str, str]) -> tuple[int, int, int]:
        country, resource = key
        production = state.tables.get("domestic_production")
        if production is None:
            self._panel_diagnostic = "Domestic production data is unavailable."
            return 0, 0, 0
        required = {"country_id", "game_resource_id"}
        if not required.issubset(production.columns):
            missing = ", ".join(sorted(required.difference(production.columns)))
            self._panel_diagnostic = f"Domestic production is missing columns: {missing}."
            return 0, 0, 0

        row = production.filter(
            (pl.col("country_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase() == country)
            & (pl.col("game_resource_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_lowercase() == resource)
        )
        if row.height != 1:
            return 0, 0, 0

        controlled = bool(row["is_gov_controlled"][0]) if "is_gov_controlled" in row.columns else False
        legal = bool(row["is_legal"][0]) if "is_legal" in row.columns else True
        tax_rate = 0.0
        if "tax_rate" in row.columns:
            try:
                raw_tax = row["tax_rate"][0]
                tax_rate = float(raw_tax) if raw_tax is not None else 0.0
                if not math.isfinite(tax_rate):
                    raise ValueError("tax_rate must be finite")
            except (TypeError, ValueError, OverflowError) as exc:
                self._panel_diagnostic = f"Domestic production tax rate is invalid: {exc}"
                tax_rate = 0.0
        return 1 if controlled else 0, 0 if legal else 1, max(0, min(100, int(round(tax_rate * 100.0))))

    def _find_policy_rejection(self, state, key, pending) -> dict | None:
        results = getattr(getattr(state, "journal", None), "command_results", [])
        country, resource = key
        for result in results[pending.result_cursor:]:
            if str(result.get("action_type") or "") != "ActionUpdateResourcePolicy":
                continue
            if str(result.get("player_id") or result.get("actor_id") or "") != pending.player_id:
                continue
            if str(result.get("status") or "").casefold() not in {"rejected", "failed"}:
                continue
            result_country = str(result.get("country_id") or result.get("country_tag") or "").strip().upper()
            result_resource = str(result.get("resource_id") or "").strip().lower()
            if result_country and result_country != country:
                continue
            if result_resource and result_resource != resource:
                continue
            return result
        return None

    def _set_current_draft_value(self, field: str, value: int) -> None:
        key = self.current_policy_key
        draft = self._policy_drafts.get(key)
        if draft is None:
            return
        setattr(draft, field, int(value))
        self._refresh_dirty_state()

    def _refresh_current_draft(self) -> None:
        key = self.current_policy_key
        draft = self._policy_drafts.get(key)
        if draft is None or key in self._pending_policy_updates:
            return
        draft.management = self.draft_management
        draft.status = self.draft_status
        draft.tax = self.draft_tax
        self._refresh_dirty_state()

    def _refresh_dirty_state(self) -> None:
        self.has_unsaved_changes = any(
            draft.is_dirty and key not in self._pending_policy_updates
            for key, draft in self._policy_drafts.items()
        )

    def _discard_unsubmitted_drafts(self) -> None:
        self._policy_drafts = {
            key: draft
            for key, draft in self._policy_drafts.items()
            if key in self._pending_policy_updates
        }
        self.current_policy_key = None
        self._refresh_dirty_state()

    def _render_market_flow_summary(self, state, target_tag, *, is_own: bool = True, gml_id=None):
        w, h = imgui.get_content_region_avail().x, imgui.get_content_region_avail().y
        imgui.push_style_color(imgui.Col_.child_bg, (0.035, 0.045, 0.06, 0.88))
        imgui.begin_child(
            "MarketFlowSummary",
            (w, h),
            child_flags=imgui.ChildFlags_.borders,
            gml_id=gml_id,
        )
        try:
            child_position = imgui.get_window_pos()
            imgui.text_colored(GAMETHEME.colors.accent, "RESOURCE MARKET FLOW")
            imgui.separator()
            imgui.set_cursor_screen_pos((child_position.x + 22.0, child_position.y + 44.0))
            imgui.text_wrapped(
                "Production, consumption, imports, exports, and balance by resource. "
                "Trade flows are not the diplomatic TRADE panel."
            )
            # The GML tax arrow overlaps this supplemental child, so render its hitbox here where it can receive input.
            if GMLWidgets("Resources_Window/frmInner/frmResources").arrow_button_at(
                (child_position.x + 11.0, child_position.y + 67.0),
                (9.0, 8.0),
                "up",
                "resources.policy.tax.increment",
                enabled=(
                    is_own
                    and bool(self.selected_resource)
                    and self.current_policy_key not in self._pending_policy_updates
                    and self.draft_tax < 100
                ),
                tooltip="Increase resource tax by 1 percentage point",
                gml_id="Resources_Window/frmInner/frmResources/frmSectorTax/btnUp",
            ):
                self._set_draft_tax(self.draft_tax + 1)
            imgui.dummy((0, 6))

            try:
                flows = self._resource_flow_frame(state, target_tag)
            except ValueError:
                # Long schema diagnostics were clipped by the narrow source panel.
                imgui.text_wrapped("Resource market data is unavailable.",
                                   test_id="resources.market.unavailable")
                return

            self._render_flow_metric_cards(flows)
            imgui.dummy((0, 4))
            self._render_market_balance_plot(flows)
            self._render_market_flow_table(flows)
        finally:
            imgui.end_child()
            imgui.pop_style_color()

    def _resource_flow_frame(self, state, target_tag: str) -> pl.DataFrame:
        ledger = state.tables.get("resource_ledger")
        validate_resource_ledger(ledger)

        trade = state.tables.get("trade_network")
        if (
            ledger is self._flow_cache_ledger
            and trade is self._flow_cache_trade
            and target_tag == self._flow_cache_country
            and self._flow_cache_frame is not None
        ):
            return self._flow_cache_frame

        flows = build_resource_flows(ledger, trade, target_tag)

        self._flow_cache_ledger = ledger
        self._flow_cache_trade = trade
        self._flow_cache_country = target_tag
        self._flow_cache_frame = flows
        return flows

    def _render_flow_metric_cards(self, flows: pl.DataFrame) -> None:
        values = [
            ("PRODUCTION", "production_usd", GAMETHEME.colors.positive),
            ("CONSUMPTION", "consumption_usd", GAMETHEME.colors.warning),
            ("IMPORTS", "imports", GAMETHEME.colors.info),
            ("EXPORTS", "exports", GAMETHEME.colors.accent),
            ("BALANCE", "balance_usd", GAMETHEME.colors.positive),
        ]
        labels = {
            "PRODUCTION": "PROD",
            "CONSUMPTION": "CONS",
            "IMPORTS": "IN",
            "EXPORTS": "OUT",
            "BALANCE": "NET",
        }
        if not imgui.begin_table(
            "ResourceMetrics",
            len(values),
            imgui.TableFlags_.sizing_stretch_prop,
        ):
            return

        try:
            for label, _, _ in values:
                imgui.table_setup_column(labels[label], imgui.TableColumnFlags_.width_stretch)
            imgui.table_next_row()
            for label, _, _ in values:
                imgui.table_next_column()
                imgui.text_disabled(labels[label])
            imgui.table_next_row()
            for _, column, color in values:
                imgui.table_next_column()
                total = flows.get_column(column).sum() if column in flows.columns else 0.0
                amount = float(total) if total is not None else 0.0
                # Keep the unit visible even in the five-column summary's narrow cells.
                compact = self._fmt_money(amount, abbreviate=True).replace(" ", "")
                Prims.right_align_text(compact, color)
                if imgui.is_item_hovered():
                    imgui.set_tooltip(self._fmt_money(amount))
        finally:
            imgui.end_table()

    def _render_market_balance_plot(self, flows: pl.DataFrame) -> None:
        if flows.is_empty():
            draw_empty_state("No resource ledger or market-flow rows are available.")
            return

        visible = flows.head(8)
        resource_names = [
            str(value or "Unknown").replace("_", " ").title()
            for value in visible.get_column("game_resource_id").to_list()
        ]
        x_values = np.arange(len(resource_names), dtype=np.float64)
        series = (
            ("Production", "production_usd", -0.32),
            ("Consumption", "consumption_usd", -0.16),
            ("Imports", "imports", 0.0),
            ("Exports", "exports", 0.16),
            ("Balance", "balance_usd", 0.32),
        )
        if not implot.begin_plot("Resource balances##ResourcePanel", imgui.ImVec2(-1.0, 210.0)):
            return

        try:
            implot.setup_axes("Resource", "USD")
            implot.setup_axis_ticks(implot.ImAxis_.x1, x_values.tolist(), resource_names)
            for label, column, shift in series:
                y_values = np.asarray(visible.get_column(column).to_list(), dtype=np.float64)
                implot.plot_bars(label, x_values + shift, y_values, 0.14)
        finally:
            implot.end_plot()

    def _render_market_flow_table(self, flows: pl.DataFrame) -> None:
        if flows.is_empty():
            return
        if not imgui.begin_table(
            "MarketFlowSummaryTable",
            4,
            imgui.TableFlags_.row_bg | imgui.TableFlags_.borders_inner_h,
        ):
            return

        imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_stretch)
        imgui.table_setup_column("EXPORT", imgui.TableColumnFlags_.width_fixed, 90)
        imgui.table_setup_column("IMPORT", imgui.TableColumnFlags_.width_fixed, 90)
        imgui.table_setup_column("NET", imgui.TableColumnFlags_.width_fixed, 90)
        imgui.table_headers_row()
        for row in flows.head(8).iter_rows(named=True):
            net = float(row.get("net_trade_usd") or 0.0)
            color = GAMETHEME.colors.positive if net >= 0 else GAMETHEME.colors.negative
            imgui.table_next_row()
            imgui.table_next_column()
            imgui.text(str(row.get("game_resource_id") or "Unknown").replace("_", " ").title())
            imgui.table_next_column()
            Prims.right_align_text(self._fmt_money(row.get("exports") or 0.0, True))
            imgui.table_next_column()
            Prims.right_align_text(self._fmt_money(row.get("imports") or 0.0, True))
            imgui.table_next_column()
            Prims.right_align_text(self._fmt_money(net, True), color)
        imgui.end_table()
