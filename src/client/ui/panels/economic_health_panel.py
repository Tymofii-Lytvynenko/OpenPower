import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME


class EconomicHealthPanel:
    """Detailed economy diagnostics based on live country and resource tables."""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("ECONOMIC HEALTH", x=1260, y=120, w=330, h=430) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, target_tag):
        country_row = self._get_country_row(state, target_tag)
        economic_health = self._read_float(country_row, "economic_health", 0.0)
        tax_fairness = self._read_float(country_row, "tax_fairness_factor", 1.0)
        revenue = self._read_float(country_row, "total_annual_revenue", 0.0)
        expenses = self._read_float(country_row, "total_annual_expense", 0.0)
        reserves = self._read_float(country_row, "money_reserves", 0.0)
        gdp = self._read_float(country_row, "gdp", 0.0)
        resource_coverage = self._resource_coverage(state, target_tag)
        reserve_coverage = self._reserve_coverage(reserves, expenses)
        budget_balance = revenue - expenses

        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        Prims.header("SUMMARY", show_bg=False)
        self._draw_meter("Economic health", economic_health, self._health_color(economic_health))
        self._draw_meter("Resource coverage", resource_coverage, self._health_color(resource_coverage))
        self._draw_meter("Tax fairness", tax_fairness, self._health_color(tax_fairness))
        self._draw_meter("Reserve coverage", reserve_coverage, self._health_color(reserve_coverage))

        imgui.dummy((0, 8))
        Prims.header("ANNUAL FLOW", show_bg=False)
        self._draw_money_row("Revenue", revenue, GAMETHEME.colors.positive)
        self._draw_money_row("Expenses", expenses, GAMETHEME.colors.negative)
        self._draw_money_row(
            "Balance",
            budget_balance,
            GAMETHEME.colors.positive if budget_balance >= 0 else GAMETHEME.colors.negative,
        )
        self._draw_money_row(
            "Reserves",
            reserves,
            GAMETHEME.colors.positive if reserves >= 0 else GAMETHEME.colors.negative,
        )

        imgui.dummy((0, 8))
        Prims.header("SCALE", show_bg=False)
        self._draw_money_row("GDP", gdp, GAMETHEME.colors.text_main)

        imgui.pop_style_var()

    def _get_country_row(self, state, target_tag):
        if "countries" not in state.tables:
            return None

        try:
            row = state.get_table("countries").filter(pl.col("id") == target_tag)
            return row if not row.is_empty() else None
        except Exception:
            return None

    def _read_float(self, row, column: str, default: float) -> float:
        if row is None or column not in row.columns:
            return default
        value = row[column][0]
        return float(value) if value is not None else default

    def _resource_coverage(self, state, target_tag) -> float:
        if "resource_ledger" not in state.tables:
            return 0.0

        try:
            ledger = state.get_table("resource_ledger")
            country_ledger = ledger.filter(pl.col("country_id") == target_tag)
            if country_ledger.is_empty() or "consumption_usd" not in country_ledger.columns:
                return 0.0

            total_consumption = float(country_ledger["consumption_usd"].sum() or 0.0)
            if total_consumption <= 0.0:
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
            return max(0.0, min(1.0, 1.0 - shortage / total_consumption))
        except Exception:
            return 0.0

    def _reserve_coverage(self, reserves: float, annual_expenses: float) -> float:
        if annual_expenses <= 0.0:
            return 1.0 if reserves >= 0 else 0.0
        return max(0.0, min(1.0, reserves / annual_expenses))

    def _health_color(self, value: float) -> tuple:
        if value >= 0.75:
            return GAMETHEME.colors.positive
        if value >= 0.45:
            return GAMETHEME.colors.warning
        return GAMETHEME.colors.negative

    def _draw_meter(self, label: str, value: float, color: tuple):
        value = max(0.0, min(float(value), 1.0))
        imgui.text(label)
        imgui.same_line(180)
        imgui.text_colored(color, f"{value * 100:.1f} %")
        Prims.meter("", value * 100.0, color)

    def _draw_money_row(self, label: str, value: float, color: tuple):
        imgui.text(label)
        imgui.same_line(120)
        Prims.right_align_text(self._fmt_money(value), color)

    def _fmt_money(self, value: float) -> str:
        sign = "- " if value < 0 else ""
        return f"$ {sign}{abs(float(value)):,.0f}".replace(",", " ")
