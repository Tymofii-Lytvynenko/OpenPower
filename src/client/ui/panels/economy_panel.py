import polars as pl

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.formatting import format_currency
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
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
        revenue = None
        expenses = None
        reserves = None
        eco_health = None
        resources_health = self._get_resource_health(state, target_tag)
        market_model_val = self._get_market_model_value(state, target_tag)

        if "countries" in state.tables:
            try:
                df = state.tables["countries"]
                row = df.filter(pl.col("id") == target_tag)
                if row.height == 1:
                    revenue = self._number_from_row(row, "total_annual_revenue")
                    expenses = self._number_from_row(row, "total_annual_expense")
                    reserves = self._number_from_row(row, "money_reserves")
                    health = self._number_from_row(row, "economic_health")
                    if health is not None and 0.0 <= health <= 1.0:
                        eco_health = health
            except Exception:
                pass

        balance = revenue - expenses if revenue is not None and expenses is not None else None

        ui = GMLWidgets("Economic_Window/frmInner")
        ui.text("frmEconomicModel/lblTitle", "ECONOMIC MODEL")
        ui.meter("frmEconomicModel/frmModelCursor", market_model_val or 0.0,
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
            ui.text(f"{section}/txtValue", "--" if value is None else f"{value * 100:.0f}%")
            ui.meter(
                f"{section}/frmGradient",
                value if value is not None else 0.0,
                GAMETHEME.colors.positive,
            )
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
            ui.text(
                f"frmBudget/{value_id}",
                "--" if value is None else self._fmt_money(value),
                right=True,
                color=(
                    GAMETHEME.colors.negative
                    if value is not None and value < 0
                    else GAMETHEME.colors.text_main
                ),
            )
        if ui.button("btnTrade", "TRADE", "economy.trade_btn", enabled=self.toggle_trade_cb is not None):
            self.toggle_trade_cb()

    def _get_market_model_value(self, state, target_tag) -> float | None:
        """Return the free-market share when the required production data is valid."""
        if "domestic_production" not in state.tables:
            return None

        try:
            df = state.get_table("domestic_production")
            if "country_id" not in df.columns or "domestic_production" not in df.columns:
                return None

            target_df = df.filter(pl.col("country_id") == target_tag)
            if target_df.is_empty():
                return None

            production = [self._finite_number(value) for value in target_df["domestic_production"].to_list()]
            if not production or any(value is None or value < 0.0 for value in production):
                return None
            total = sum(production)
            if total <= 0.0:
                return None

            if "is_gov_controlled" not in target_df.columns:
                return None

            control_flags = target_df["is_gov_controlled"].to_list()
            if len(control_flags) != len(production) or any(
                not isinstance(controlled, bool) for controlled in control_flags
            ):
                return None
            gov_total = sum(
                amount
                for amount, controlled in zip(production, control_flags, strict=True)
                if controlled
            )
            return max(0.0, min(1.0, 1.0 - (gov_total / total)))
        except Exception:
            return None

    def _get_resource_health(self, state, target_tag) -> float | None:
        """Estimate demand coverage when the country resource ledger is complete."""
        if "resource_ledger" not in state.tables:
            return None

        try:
            ledger = state.get_table("resource_ledger")
            if not {"country_id", "consumption_usd", "balance_usd"}.issubset(ledger.columns):
                return None

            country_ledger = ledger.filter(pl.col("country_id") == target_tag)
            if country_ledger.is_empty():
                return None

            consumption_values = [
                self._finite_number(value)
                for value in country_ledger["consumption_usd"].to_list()
            ]
            balances = [
                self._finite_number(value)
                for value in country_ledger["balance_usd"].to_list()
            ]
            if (
                not consumption_values
                or len(consumption_values) != len(balances)
                or any(value is None or value < 0.0 for value in consumption_values)
                or any(value is None for value in balances)
            ):
                return None

            consumption = sum(consumption_values)
            if consumption <= 0.0:
                return 1.0

            shortage = abs(sum(balance for balance in balances if balance < 0.0))
            return max(0.0, min(1.0, 1.0 - (shortage / consumption)))
        except Exception:
            return None

    @staticmethod
    def _number_from_row(row, column: str) -> float | None:
        if column not in row.columns or row.height != 1:
            return None
        return EconomyPanel._finite_number(row[column][0])

    @staticmethod
    def _finite_number(value) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number

    @staticmethod
    def _fmt_money(value: float) -> str:
        return format_currency(value)
