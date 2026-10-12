import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.economy_presenter import EconomyPresenter
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
    ActionSetTax,
)


class EconomicHealthPanel:
    """Economic overview and controls backed by authoritative snapshot data."""

    def __init__(self) -> None:
        self._presenter = EconomyPresenter()
        self._draft_country_id = ""
        self._draft_minimum_wage = 0.0
        self._draft_interest_rate = 0.05
        self._draft_tax_rate = 0.2
        self._draft_health_spending = 0.5
        self._creditor_country_id = ""
        self._loan_principal = 1_000_000.0
        self._loan_interest_rate = 0.05

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("ECONOMIC HEALTH", x=1060, y=80, w=560, h=680) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext):
        target_tag = context.target_tag
        country_row = self._get_country_row(state, target_tag)
        view = self._presenter.present(state, target_tag)
        if country_row is None or view is None:
            imgui.text_disabled("No economic profile is available for this country.")
            return
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

        imgui.dummy((0, 8))
        Prims.header("LABOR AND PRICES", show_bg=False)
        imgui.text(f"Minimum wage: $ {view.minimum_wage:,.2f}")
        imgui.text(f"Interest rate: {view.interest_rate * 100:.2f}%")
        imgui.text(f"Inflation: {view.inflation_rate * 100:.2f}%")
        imgui.text(f"Employment / unemployment: {view.employment_rate * 100:.1f}% / {view.unemployment_rate * 100:.1f}%")
        imgui.text(f"Underemployment: {view.underemployment_rate * 100:.1f}%")
        imgui.text(f"Poverty: {view.poverty_rate * 100:.1f}%")
        imgui.text(f"Labor / employed / underemployed: {view.labor_supply:,.0f} / {view.employed_population:,.0f} / {view.underemployed_population:,.0f}")
        imgui.text(f"Nominal / real income index: {view.nominal_income_index:.3f} / {view.real_income_index:.3f}")
        imgui.text(f"Migration pressure signal: {view.migration_pressure * 100:.1f}%")
        trend_by_name = {trend.indicator: trend for trend in view.indicator_trends}
        for indicator in ("economic_health", "inflation_rate", "employment_rate", "unemployment_rate", "poverty_rate", "real_income_index"):
            trend = trend_by_name.get(indicator)
            if trend is not None:
                imgui.text_disabled(
                    f"{indicator.replace('_', ' ').title()} trend: {trend.direction} ({trend.delta:+.3f})"
                )

        imgui.dummy((0, 8))
        Prims.header("DEBT AND DISTRESS", show_bg=False)
        imgui.text(f"Domestic overdraft: $ {view.domestic_debt:,.0f}")
        imgui.text(f"Foreign debt: $ {view.foreign_debt:,.0f}")
        imgui.text(f"Annual debt service: $ {view.annual_debt_service:,.0f}")
        imgui.text(f"Arrears / status: $ {view.arrears:,.0f} / {view.distress_status}")
        imgui.text(f"Recovery: {view.recovery_condition}")
        imgui.text(f"Annual fiscal balance: $ {view.fiscal_balance:,.0f}")
        for threshold_name, threshold_value in view.risk_thresholds:
            imgui.text_disabled(f"{threshold_name.replace('_', ' ').title()} threshold: {threshold_value * 100:.1f}%")
        for obligation in view.obligations[:4]:
            imgui.text(
                f"{obligation.contract_id} → {obligation.creditor_country_id}: "
                f"$ {obligation.principal_remaining:,.0f}, next {obligation.next_payment_date}, "
                f"maturity {obligation.maturity_date}, {obligation.annual_interest_rate * 100:.2f}% interest, "
                f"arrears $ {obligation.arrears_amount:,.0f} ({obligation.status})"
            )

        imgui.dummy((0, 8))
        Prims.header("RECENT CAUSES", show_bg=False)
        if view.top_causes:
            for cause in view.top_causes:
                imgui.text(f"{cause.indicator}: {cause.delta:+.4f} — {cause.reason}")
        else:
            imgui.text_disabled("No recorded economic changes yet.")

        self._render_policy_controls(state, context, view, country_row)
        self._render_debt_controls(state, context, view)

        imgui.pop_style_var()

    def _render_policy_controls(self, state, context: PanelRenderContext, view, country_row) -> None:
        client = context.net_client
        terms = getattr(state, "globals", {}).get("economic_health_terms", {})
        terms = terms if isinstance(terms, dict) else {}
        if self._draft_country_id != context.target_tag:
            self._draft_country_id = context.target_tag
            self._draft_minimum_wage = view.minimum_wage
            self._draft_interest_rate = view.interest_rate
            self._draft_tax_rate = self._read_float(country_row, "personal_income_tax_rate", 0.2)
            self._draft_health_spending = self._read_float(country_row, "budget_health_ratio", 0.5)
        imgui.dummy((0, 8))
        Prims.header("SCHEDULE ECONOMIC POLICY", show_bg=False)
        max_wage = max(1.0, float(terms.get("max_minimum_wage", 1_000_000.0)))
        _, self._draft_minimum_wage = imgui.slider_float(
            "Minimum wage", self._draft_minimum_wage, 0.0, max_wage, "%.2f"
        )
        _, self._draft_interest_rate = imgui.slider_float(
            "Policy interest", self._draft_interest_rate, 0.0, 0.5, "%.3f"
        )
        _, self._draft_tax_rate = imgui.slider_float(
            "Income tax", self._draft_tax_rate, 0.0, 0.5, "%.3f"
        )
        _, self._draft_health_spending = imgui.slider_float(
            "Public health spending", self._draft_health_spending, 0.0, 1.0, "%.3f"
        )
        can_change = bool(context.is_own_country and client is not None)
        imgui.begin_disabled(not can_change)
        if imgui.button("Schedule wage change") and can_change:
            client.send_action(ActionChangeEconomicPolicy(
                client.player_id, context.target_tag, "minimum_wage", self._draft_minimum_wage
            ))
        imgui.same_line()
        if imgui.button("Schedule interest change") and can_change:
            client.send_action(ActionChangeEconomicPolicy(
                client.player_id, context.target_tag, "interest_rate", self._draft_interest_rate
            ))
        imgui.same_line()
        if imgui.button("Schedule tax change") and can_change:
            client.send_action(ActionSetTax(
                client.player_id, context.target_tag, self._draft_tax_rate
            ))
        if imgui.button("Schedule health-spending change") and can_change:
            client.send_action(ActionChangeEconomicPolicy(
                client.player_id, context.target_tag, "budget_health_ratio", self._draft_health_spending
            ))
        imgui.end_disabled()
        if view.active_policies:
            for policy in view.active_policies[:3]:
                imgui.text_disabled(
                    f"{policy.policy_name} → {policy.target_value:.3f}; "
                    f"cost $ {policy.transition_cost:,.0f}; effective {policy.effective_date}"
                )

    def _render_debt_controls(self, state, context: PanelRenderContext, view) -> None:
        client = context.net_client
        countries = state.tables.get("countries")
        country_ids = [] if countries is None or "id" not in countries.columns else sorted(
            str(value) for value in countries.get_column("id").to_list() if str(value) != context.target_tag
        )
        imgui.dummy((0, 8))
        Prims.header("FOREIGN FINANCING", show_bg=False)
        if self._creditor_country_id not in country_ids:
            self._creditor_country_id = country_ids[0] if country_ids else ""
        preview = self._creditor_country_id or "No eligible creditor"
        if imgui.begin_combo("Creditor", preview):
            for country_id in country_ids:
                selected = country_id == self._creditor_country_id
                if imgui.selectable(country_id, selected)[0]:
                    self._creditor_country_id = country_id
            imgui.end_combo()
        _, self._loan_principal = imgui.input_float("Principal", self._loan_principal, 100_000.0, 1_000_000.0, "%.0f")
        _, self._loan_interest_rate = imgui.slider_float("Annual interest", self._loan_interest_rate, 0.0, 0.5, "%.3f")
        can_request = bool(context.is_own_country and client is not None and self._creditor_country_id)
        imgui.begin_disabled(not can_request)
        if imgui.button("Request 12-monthly-payment financing") and can_request:
            client.send_action(ActionRequestDebtContract(
                client.player_id,
                context.target_tag,
                self._creditor_country_id,
                max(1.0, self._loan_principal),
                self._loan_interest_rate,
                1,
                max(1.0, self._loan_principal / 12.0),
                12,
                "USD",
                "Requested through the economic overview.",
            ))
        imgui.end_disabled()
        for obligation in view.obligations[:3]:
            if obligation.status in {"arrears", "restructured"} and context.is_own_country and client is not None:
                if imgui.small_button(f"Request restructure##{obligation.contract_id}"):
                    client.send_action(ActionRequestDebtRestructuring(
                        client.player_id,
                        context.target_tag,
                        obligation.contract_id,
                        min(0.5, obligation.annual_interest_rate),
                        1,
                        max(1.0, obligation.principal_remaining / 24.0),
                        24,
                    ))
        if countries is None or not context.is_own_country or client is None:
            return
        pending = state.tables.get("debt_contracts")
        if pending is None or pending.is_empty():
            return
        creditor_requests = pending.filter(
            (pl.col("creditor_country_id") == context.target_tag) & (pl.col("status") == "pending")
        )
        for request in creditor_requests.iter_rows(named=True):
            imgui.text(f"Financing request from {request['debtor_country_id']}: $ {request['principal_original']:,.0f}")
            if imgui.small_button(f"Approve##{request['id']}"):
                client.send_action(ActionResolveDebtContract(client.player_id, str(request["id"]), True))
            imgui.same_line()
            if imgui.small_button(f"Reject##{request['id']}"):
                client.send_action(ActionResolveDebtContract(client.player_id, str(request["id"]), False))

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
