import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext


class TradePanel:
    """Detailed trade view backed by the live trade_network table."""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("TRADE MENU", x=720, y=120, w=760, h=620) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag)
            return True

    def _render_content(self, state, target_tag):
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (8, 6))

        trade = state.get_table("trade_network") if "trade_network" in state.tables else None
        if trade is None or trade.is_empty():
            imgui.text_disabled("Trade data has not been generated yet.")
            imgui.pop_style_var()
            return

        try:
            exports = trade.filter(pl.col("exporter_id") == target_tag).group_by("game_resource_id").agg(
                pl.col("trade_value_usd").sum().alias("exports")
            )
            imports = trade.filter(pl.col("importer_id") == target_tag).group_by("game_resource_id").agg(
                pl.col("trade_value_usd").sum().alias("imports")
            )
            flows = exports.join(imports, on="game_resource_id", how="full", coalesce=True).with_columns([
                pl.col("exports").fill_null(0.0),
                pl.col("imports").fill_null(0.0),
            ]).with_columns(
                (pl.col("exports") - pl.col("imports")).alias("net")
            )
        except Exception:
            imgui.text_disabled("Unable to read trade flow table.")
            imgui.pop_style_var()
            return

        total_exports = float(flows["exports"].sum() or 0.0) if not flows.is_empty() else 0.0
        total_imports = float(flows["imports"].sum() or 0.0) if not flows.is_empty() else 0.0
        net_trade = total_exports - total_imports

        Prims.header("TRADE BALANCE", show_bg=False)
        self._draw_summary_row("EXPORTS", total_exports, GAMETHEME.colors.positive)
        self._draw_summary_row("IMPORTS", total_imports, GAMETHEME.colors.negative)
        self._draw_summary_row("NET", net_trade, GAMETHEME.colors.positive if net_trade >= 0 else GAMETHEME.colors.negative)
        imgui.dummy((0, 8))

        Prims.header("RESOURCE FLOWS", show_bg=False)
        table_flags = imgui.TableFlags_.row_bg | imgui.TableFlags_.borders | imgui.TableFlags_.scroll_y | imgui.TableFlags_.resizable
        if imgui.begin_table("TradeFlows", 4, table_flags, (0, 360)):
            imgui.table_setup_scroll_freeze(0, 1)
            imgui.table_setup_column("RESOURCE", imgui.TableColumnFlags_.width_stretch)
            imgui.table_setup_column("EXPORT", imgui.TableColumnFlags_.width_fixed, 140)
            imgui.table_setup_column("IMPORT", imgui.TableColumnFlags_.width_fixed, 140)
            imgui.table_setup_column("NET", imgui.TableColumnFlags_.width_fixed, 140)
            imgui.table_headers_row()

            for row in flows.sort("net", descending=True).iter_rows(named=True):
                net = float(row.get("net") or 0.0)
                color = GAMETHEME.colors.positive if net >= 0 else GAMETHEME.colors.negative
                imgui.table_next_row()
                imgui.table_next_column(); imgui.text(str(row.get("game_resource_id") or "Unknown").replace("_", " ").title())
                imgui.table_next_column(); Prims.right_align_text(self._fmt_money(row.get("exports") or 0.0))
                imgui.table_next_column(); Prims.right_align_text(self._fmt_money(row.get("imports") or 0.0))
                imgui.table_next_column(); Prims.right_align_text(self._fmt_money(net), color)

            imgui.end_table()

        imgui.dummy((0, 8))
        self._render_budget_trade_impact(state, target_tag)
        imgui.pop_style_var()

    def _render_budget_trade_impact(self, state, target_tag):
        if "countries" not in state.tables:
            return

        try:
            row = state.get_table("countries").filter(pl.col("id") == target_tag)
            if row.is_empty():
                return

            trade_income = self._read_float(row, "trade_income")
            trade_expense = self._read_float(row, "trade_expense")
            tourism_income = self._read_float(row, "tourism_income")

            Prims.header("BUDGET IMPACT", show_bg=False)
            self._draw_summary_row("TRADE TAX / STATE EXPORTS", trade_income, GAMETHEME.colors.positive)
            self._draw_summary_row("STATE IMPORT EXPENSE", trade_expense, GAMETHEME.colors.negative)
            self._draw_summary_row("TOURISM LEVY", tourism_income, GAMETHEME.colors.positive)
        except Exception:
            imgui.text_disabled("Budget impact unavailable.")

    def _read_float(self, row, column: str) -> float:
        if column not in row.columns:
            return 0.0
        value = row[column][0]
        return float(value) if value is not None else 0.0

    def _draw_summary_row(self, label: str, value: float, color: tuple):
        imgui.text(label)
        imgui.same_line(240)
        Prims.right_align_text(self._fmt_money(value), color)

    def _fmt_money(self, val: float) -> str:
        sign = "- " if val < 0 else ""
        return f"$ {sign}{abs(float(val)):,.0f}".replace(",", " ")
