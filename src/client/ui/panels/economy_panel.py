import polars as pl
from src.client.ui.core.formatting import format_currency
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.layouts.main_pillar_positions import main_pillar_position


class EconomyPanel:
    def __init__(
        self,
        toggle_resources_cb=None,
        toggle_budget_cb=None,
        toggle_health_cb=None,
        toggle_trade_cb=None,
    ):
        self.toggle_resources_cb = toggle_resources_cb
        self.toggle_budget_cb = toggle_budget_cb
        self.toggle_health_cb = toggle_health_cb
        self.toggle_trade_cb = toggle_trade_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        x, y = main_pillar_position("economy")
        with WindowManager.window(
            "ECONOMY", x=x, y=y, w=280, h=480, test_id="economy.panel",
            horizontal_anchor="right", horizontal_margin=19.0,
            flags=imgui.WindowFlags_.no_resize | imgui.WindowFlags_.no_scrollbar | imgui.WindowFlags_.no_scroll_with_mouse,
        ) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, target_tag, is_own):
        # --- 1. Fetch Economy Data ---
        revenue = 0.0
        expenses = 0.0
        reserves = 0.0
        eco_health = 0.0
        resources_health = self._get_resource_health(state, target_tag)
        market_model_val = self._get_market_model_value(state, target_tag)
        
        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if not row.is_empty():
                    # Budget details
                    if "total_annual_revenue" in row.columns:
                        val_rev = row["total_annual_revenue"][0]
                        revenue = float(val_rev) if val_rev is not None else 0.0
                        
                    if "total_annual_expense" in row.columns:
                        val_exp = row["total_annual_expense"][0]
                        expenses = float(val_exp) if val_exp is not None else 0.0
                        
                    if "money_reserves" in row.columns:
                        val_res = row["money_reserves"][0]
                        reserves = float(val_res) if val_res is not None else 0.0
                        
                    if "economic_health" in row.columns:
                        val_eh = row["economic_health"][0]
                        eco_health = float(val_eh) if val_eh is not None else 0.836
            except Exception:
                pass

        balance = revenue - expenses

        ui = GMLWidgets("Economic_Window/frmInner")
        ui.text("frmEconomicModel/lblTitle", "ECONOMIC MODEL")
        ui.meter("frmEconomicModel/frmModelCursor", market_model_val,
                 GAMETHEME.colors.positive, cursor=True)
        ui.text("frmEconomicModel/lblStateControlled", "State",
                color=GAMETHEME.colors.text_dim)
        if imgui.is_item_hovered():
            imgui.set_tooltip("State-controlled model")
        ui.text("frmEconomicModel/lblFreeMarket", "Market",
                color=GAMETHEME.colors.text_dim, right=True)
        if imgui.is_item_hovered():
            imgui.set_tooltip("Free-market model")
        for section, label, button, test_id, callback in (
            ("frmEconomicHealth", "ECONOMIC HEALTH", "btnMoreEconomicHealth", "economy.health_btn", self.toggle_health_cb),
            ("frmBudget", "BUDGET", "btnMoreBudget", "economy.budget_btn", self.toggle_budget_cb),
            ("frmResources", "RESOURCES", "btnMoreResources", "economy.resources_btn", self.toggle_resources_cb),
        ):
            ui.text(f"{section}/lblTitle", label)
            if ui.button(f"{section}/{button}", "more", test_id, enabled=callback is not None):
                callback()
        for section, value in (("frmEconomicHealth", eco_health), ("frmResources", resources_health)):
            ui.text(f"{section}/txtValue", f"{value * 100:.0f}%")
            ui.meter(f"{section}/frmGradient", value, GAMETHEME.colors.positive)
        for label_id, value_id, label, value in (
            ("lblIncome", "txtIncome", "INCOME", revenue),
            ("lblExpenses", "txtExpenses", "EXPENSES", expenses),
            ("lblBalance", "txtBalance", "BALANCE", balance),
            ("lblAvailable", "txtDebt", "AVAILABLE", reserves),
        ):
            # The source GML slot clips "AVAILABLE" at the configured UI font size.
            display_label = "FUNDS" if label_id == "lblAvailable" else label
            ui.text(f"frmBudget/{label_id}", display_label)
            if label_id == "lblAvailable" and imgui.is_item_hovered():
                imgui.set_tooltip("Available country reserves")
            ui.text(f"frmBudget/{value_id}", self._fmt_money(value), right=True,
                    color=GAMETHEME.colors.negative if value < 0 else GAMETHEME.colors.text_main)
        if ui.button("btnTrade", "TRADE", "economy.trade_btn", enabled=self.toggle_trade_cb is not None):
            self.toggle_trade_cb()

    def _get_market_model_value(self, state, target_tag) -> float:
        """Returns the free-market share of domestic production from live policy data."""
        if "domestic_production" not in state.tables:
            return 0.0

        try:
            df = state.get_table("domestic_production")
            if "country_id" not in df.columns or "domestic_production" not in df.columns:
                return 0.0

            target_df = df.filter(pl.col("country_id") == target_tag)
            if target_df.is_empty():
                return 0.0

            total = float(target_df["domestic_production"].sum() or 0.0)
            if total <= 0.0:
                return 0.0

            if "is_gov_controlled" not in target_df.columns:
                return 1.0

            gov_total = float(
                target_df
                .filter(pl.col("is_gov_controlled") == True)
                .select(pl.col("domestic_production").sum())
                .item()
                or 0.0
            )
            return max(0.0, min(1.0, 1.0 - (gov_total / total)))
        except Exception:
            return 0.0

    def _get_resource_health(self, state, target_tag) -> float:
        """Estimates demand coverage from the country resource ledger."""
        if "resource_ledger" not in state.tables:
            return 0.0

        try:
            ledger = state.get_table("resource_ledger")
            if "country_id" not in ledger.columns:
                return 0.0

            country_ledger = ledger.filter(pl.col("country_id") == target_tag)
            if country_ledger.is_empty() or "consumption_usd" not in country_ledger.columns:
                return 0.0

            consumption = float(country_ledger["consumption_usd"].sum() or 0.0)
            if consumption <= 0.0:
                return 1.0

            if "balance_usd" not in country_ledger.columns:
                return 1.0

            shortage = abs(
                float(
                    country_ledger
                    .filter(pl.col("balance_usd") < 0)
                    .select(pl.col("balance_usd").sum())
                    .item()
                    or 0.0
                )
            )
            return max(0.0, min(1.0, 1.0 - (shortage / consumption)))
        except Exception:
            return 0.0

    @staticmethod
    def _fmt_money(value: float) -> str:
        return format_currency(value)
