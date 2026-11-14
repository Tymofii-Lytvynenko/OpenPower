import math
from collections.abc import Mapping

import polars as pl

from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.client.ui.components.shared.gml_value_repeat import GMLValueRepeatPair
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.formatting import format_signed_currency
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_close_intent import PanelCloseIntent
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    resume_gml_layout,
    suspend_gml_layout,
)
from src.client.ui.panels.economy_presenter import EconomyPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
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
        self._policy_baseline: dict[str, float] = {}
        self._population_cursor_values: dict[str, tuple[float, float]] = {}
        self._rate_repeat = {
            name: GMLValueRepeatPair()
            for name in ("interest_rate", "personal_income_tax_rate")
        }
        self._creditor_country_id = ""
        self._loan_principal = 1_000_000.0
        self._loan_interest_rate = 0.05
        self._active_page = "source"
        self._close_intent = PanelCloseIntent()
        self.request_close = self._close_intent.request
        self._close_confirmation = DirtyCloseConfirmation(
            "economic_health.close",
            "Apply your economic policy changes before closing?",
        )
        self._local_save_confirmation_preferences = SaveConfirmationPreferences()

    def render(self, state, context: PanelRenderContext) -> bool:
        navigation_close = self._close_intent.consume()
        if self._active_page == "source":
            keep_open = self._render_source_window(state, context, navigation_close)
            if not keep_open:
                self._population_cursor_values.clear()
            return keep_open
        return self._render_extended_window(state, context, navigation_close)

    def _render_source_window(self, state, context: PanelRenderContext, navigation_close: bool) -> bool:
        country_row = self._get_country_row(state, context.target_tag)
        view = self._presenter.present(state, context.target_tag)
        if country_row is not None and view is not None:
            self._initialize_policy_draft(country_row, view, context.target_tag)

        preferences = context.save_confirmation_preferences or self._local_save_confirmation_preferences
        can_apply = bool(
            context.is_own_country
            and context.net_client is not None
            and self._draft_country_id == context.target_tag
        )
        keep_open = True
        with WindowManager.window(
            "ECONOMIC HEALTH",
            x=930,
            y=86,
            w=264,
            h=333,
            test_id="economic_health.panel",
            gml_template="Economic_Health_Window",
            avoid_overlaps=True,
            bottom_clearance=104.0,
        ) as is_open:
            close_decision = None
            if not is_open or navigation_close:
                if self._has_policy_changes():
                    close_decision = self._close_confirmation.request_close(
                        preferences,
                        can_apply=can_apply,
                    )
                else:
                    keep_open = False

            if is_open and not navigation_close:
                self._render_source_content(state, context, country_row, view)

            if close_decision is not None:
                self._finish_close(close_decision, context)
                keep_open = False
            elif keep_open:
                close_decision = self._close_confirmation.render(
                    preferences,
                    can_apply=can_apply,
                )
                if close_decision is not None:
                    self._finish_close(close_decision, context)
                    keep_open = False

        return keep_open

    def _render_extended_window(self, state, context: PanelRenderContext, navigation_close: bool) -> bool:
        preferences = context.save_confirmation_preferences or self._local_save_confirmation_preferences
        can_apply = bool(
            context.is_own_country
            and context.net_client is not None
            and self._draft_country_id == context.target_tag
        )
        keep_open = True
        with WindowManager.window(
            "ECONOMIC HEALTH DETAILS",
            x=920,
            y=76,
            w=560,
            h=680,
            test_id="economic_health.extended",
            avoid_overlaps=True,
            bottom_clearance=104.0,
        ) as is_open:
            close_decision = None
            if not is_open or navigation_close:
                if self._has_policy_changes():
                    close_decision = self._close_confirmation.request_close(
                        preferences,
                        can_apply=can_apply,
                    )
                else:
                    self._active_page = "source"
                    keep_open = True

            if is_open and not navigation_close:
                self._render_content(state, context)

            if close_decision is not None:
                self._finish_close(close_decision, context)
                self._active_page = "source"
                keep_open = False
            elif keep_open:
                close_decision = self._close_confirmation.render(
                    preferences,
                    can_apply=can_apply,
                )
                if close_decision is not None:
                    self._finish_close(close_decision, context)
                    self._active_page = "source"
                    keep_open = False

        return keep_open

    def _render_source_content(self, state, context: PanelRenderContext, country_row, view) -> None:
        ui = GMLWidgets("Economic_Health_Window")
        ui.frame("frmInner/frmGdp")
        ui.frame("frmInner/frmPopulation")
        ui.frame("frmInner/frmInflation")

        if country_row is None or view is None:
            draw_empty_state("No economic profile is available for this country.")
            return

        gdp = self._read_float(country_row, "gdp", 0.0)
        population = self._country_population(state, context.target_tag)
        per_capita = gdp / population if population is not None and population > 0 else None
        unemployment = self._finite_rate(view.unemployment_rate)
        poverty = self._finite_rate(view.poverty_rate)
        inflation = self._finite_rate(view.inflation_rate)

        ui.text("frmInner/frmGdp/lblTitle", "GDP", test_id="economic_health.label.gdp")
        ui.text("frmInner/frmGdp/lblTotal", "TOTAL", test_id="economic_health.label.total")
        ui.text("frmInner/frmGdp/lblCapita", "PER CAPITA", test_id="economic_health.label.per_capita", font_size=8.5)
        ui.text("frmInner/frmGdp/lblTax", "PERSONAL INCOME TAX", test_id="economic_health.label.tax", font_size=8.5)
        ui.text("frmInner/frmGdp/txtTotal", self._fmt_money(gdp), test_id="economic_health.gdp")
        ui.text(
            "frmInner/frmGdp/txtCapita",
            self._fmt_money(per_capita) if per_capita is not None else "N/A",
            tooltip="GDP divided by the selected country's population across its owned regions.",
            test_id="economic_health.gdp_per_capita",
            font_size=9.0,
        )
        ui.rule("frmInner/frmGdp/picSep")

        ui.text("frmInner/frmPopulation/lblTitle", "POPULATION", test_id="economic_health.label.population")
        ui.text("frmInner/frmPopulation/lblUnemployment", "UNEMPLOYMENT RATE", test_id="economic_health.label.unemployment", font_size=8.5)
        ui.text("frmInner/frmPopulation/lblPoverty", "POVERTY RATE", test_id="economic_health.label.poverty", font_size=8.5)
        ui.text("frmInner/frmPopulation/txtUnemployment", f"{unemployment * 100:.1f}%", test_id="economic_health.unemployment", font_size=9.0)
        ui.text("frmInner/frmPopulation/txtPoverty", f"{poverty * 100:.1f}%", test_id="economic_health.poverty", font_size=9.0)
        self._draw_population_meter(
            ui, "frmInner/frmPopulation/frmUnemployment", unemployment, "unemployment"
        )
        self._draw_population_meter(
            ui, "frmInner/frmPopulation/frmPoverty", poverty, "poverty"
        )

        ui.text("frmInner/frmInflation/lblTitle", "INFLATION", test_id="economic_health.label.inflation")
        ui.text("frmInner/frmInflation/lblInterest", "INTEREST RATE", test_id="economic_health.label.interest", font_size=8.5)
        ui.text("frmInner/frmInflation/txtInflation", f"{inflation * 100:.1f}%", test_id="economic_health.inflation", font_size=9.0)
        ui.text("frmInner/frmInflation/txtTransparentLabel3", "−12%", test_id="economic_health.inflation.low", font_size=8.5)
        ui.text("frmInner/frmInflation/txtTransparentLabel1", "3%", test_id="economic_health.inflation.mid", font_size=8.5)
        ui.text("frmInner/frmInflation/txtTransparentLabel2", "+18%", test_id="economic_health.inflation.high", font_size=8.5)
        self._draw_inflation_meter(ui, inflation)

        self._render_source_rate_control(
            ui,
            state,
            context,
            value_name="interest_rate",
            label="Interest rate",
            test_prefix="economic_health.interest",
            value_path="frmInner/frmInflation/frmInterest",
        )
        changed, value = ui.input_float(
            "frmInner/frmInflation/frmInterest/edtText",
            "##economic-health-interest",
            self._draft_interest_rate * 100.0,
            "economic_health.interest.value",
            format="%.1f%%",
            # The source GML already places dedicated +/- buttons beside this edit field.
            # Keeping imgui's optional step buttons would consume most of its inherited width.
            font_size=9.0,
            enabled=bool(context.is_own_country and context.net_client is not None),
        )
        if changed:
            self._reset_rate_repeat("interest_rate")
            self._draft_interest_rate = self._clamp_policy_rate(state, "interest_rate", value / 100.0)

        changed, value = ui.input_float(
            "frmInner/frmGdp/frmTax/edtText",
            "##economic-health-tax",
            self._draft_tax_rate * 100.0,
            "economic_health.tax.value",
            format="%.1f%%",
            font_size=9.0,
            enabled=bool(context.is_own_country and context.net_client is not None),
        )
        if changed:
            self._reset_rate_repeat("personal_income_tax_rate")
            self._draft_tax_rate = self._clamp_policy_rate(state, "personal_income_tax_rate", value / 100.0)

        self._render_source_rate_control(
            ui,
            state,
            context,
            value_name="personal_income_tax_rate",
            label="Personal income tax",
            value_path="frmInner/frmGdp/frmTax",
            test_prefix="economic_health.tax",
        )

        apply_enabled = bool(context.is_own_country and context.net_client is not None)
        if ui.button(
            "frmTitle/btnApply",
            "✓",
            "economic_health.apply",
            enabled=apply_enabled,
            tooltip="Apply the staged interest-rate and income-tax changes.",
        ) and apply_enabled:
            self._apply_policy_changes(context)

        if ui.button_at(
            "frmTitle/lblTitle",
            "+",
            "economic_health.more",
            offset=(170.0, 4.0),
            size=(17.0, 17.0),
            tooltip="Open the extended economic overview, policy controls, and debt management.",
            padding=(1.0, 0.0),
        ):
            imgui.open_popup("EconomicHealthDetailsMenu")
        if imgui.begin_popup("EconomicHealthDetailsMenu", test_id="economic_health.more.menu"):
            if imgui.menu_item("Extended overview", "", False, True, test_id="economic_health.more.overview")[0]:
                self._active_page = "overview"
                imgui.close_current_popup()
            if imgui.menu_item("Policy controls", "", False, True, test_id="economic_health.more.policy")[0]:
                self._active_page = "policy"
                imgui.close_current_popup()
            if imgui.menu_item("Debt management", "", False, True, test_id="economic_health.more.debt")[0]:
                self._active_page = "debt"
                imgui.close_current_popup()
            imgui.end_popup()

    def _render_source_rate_control(
        self, ui: GMLWidgets, state, context: PanelRenderContext, *, value_name: str,
        label: str, test_prefix: str, value_path: str,
    ) -> None:
        value = getattr(self, "_draft_interest_rate" if value_name == "interest_rate" else "_draft_tax_rate")
        cap = self._clamp_policy_rate(state, value_name, value)
        if value_name == "interest_rate":
            self._draft_interest_rate = cap
        else:
            self._draft_tax_rate = cap
        enabled = bool(context.is_own_country and context.net_client is not None)
        lower, upper = self._policy_rate_bounds(state, value_name)
        for direction, amount in (("down", -1), ("up", 1)):
            clicked, active = ui.arrow_button_state(
                f"{value_path}/btn{direction.title()}",
                direction,
                f"{test_prefix}.{direction}",
                enabled=enabled,
                tooltip=(
                    f"Change {label.lower()} by 0.1 percentage points; "
                    "hold to repeat with increasing steps."
                ),
            )
            current = round(value * 1000.0)
            updated, changed = self._rate_repeat[value_name][direction].advance(
                current,
                active=active,
                clicked=clicked,
                direction=amount,
                now=float(imgui.get_time()),
                minimum=round(lower * 1000.0),
                maximum=round(upper * 1000.0),
                step_tiers=((10, 10),),
            )
            if changed:
                value = updated / 1000.0
                if value_name == "interest_rate":
                    self._draft_interest_rate = value
                else:
                    self._draft_tax_rate = value

    def _draw_population_meter(
        self, ui: GMLWidgets, path: str, value: float, metric: str,
    ) -> None:
        session = active_gml_layout()
        track = ui.rect(f"{path}/btnUnfilled")
        if session is None or track is None:
            return
        x = session.window_position[0] + track.x - imgui.get_scroll_x()
        y = session.window_position[1] + track.y - imgui.get_scroll_y()
        value = max(0.0, min(1.0, value))
        saved = self._population_cursor_values.get(metric)
        cursor = value if saved is None or abs(saved[0] - value) > 1e-9 else saved[1]
        _, active = ui.hitbox_state(
            f"{path}/btnUnfilled",
            f"economic_health.{metric}.cursor",
            tooltip="Drag the source meter cursor; the percentage remains the reported country value.",
        )
        if active:
            mouse_x = float(imgui.get_mouse_pos().x)
            cursor = max(0.0, min(1.0, (mouse_x - x) / max(1.0, track.width - 8.0)))
            self._population_cursor_values[metric] = (value, cursor)

        handle_width = 8.0
        handle_x = x + (track.width - handle_width) * cursor
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(
            (x, y),
            (x + track.width, y + track.height),
            imgui.get_color_u32((0.18, 0.055, 0.055, 1.0)),
        )
        draw.add_rect_filled(
            (handle_x, y),
            (handle_x + handle_width, y + track.height),
            imgui.get_color_u32((0.86, 0.24, 0.19, 1.0)),
        )

    def _draw_inflation_meter(self, ui: GMLWidgets, inflation: float) -> None:
        session = active_gml_layout()
        track = ui.rect("frmInner/frmInflation/frmInflation/picGradient")
        marker_path = "frmInner/frmInflation/picDelimiter"
        marker = ui.rect(marker_path)
        section = ui.rect("frmInner/frmInflation")
        if session is None or track is None or marker is None or section is None:
            return

        x = session.window_position[0] + track.x - imgui.get_scroll_x()
        y = session.window_position[1] + track.y - imgui.get_scroll_y()
        draw = imgui.get_window_draw_list()
        stops = (
            (0.0, (0.28, 0.51, 0.70, 1.0)),
            (0.4, (0.57, 0.68, 0.34, 1.0)),
            (0.6, (0.73, 0.68, 0.28, 1.0)),
            (1.0, (0.76, 0.28, 0.24, 1.0)),
        )
        for index in range(12):
            start = index / 12.0
            end = (index + 1) / 12.0
            color = self._gradient_color((start + end) / 2.0, stops)
            draw.add_rect_filled(
                (x + track.width * start, y),
                (x + track.width * end, y + track.height),
                imgui.get_color_u32(color),
            )

        fraction = max(0.0, min(1.0, (inflation + 0.12) / 0.30))
        source_marker_left = 58.0 + (201.0 - marker.width - 58.0) * fraction
        desired_x = section.x + source_marker_left
        session.move_component(marker_path, x=desired_x - marker.x)
        marker = ui.rect(marker_path)
        marker_x = session.window_position[0] + marker.x - imgui.get_scroll_x()
        marker_y = session.window_position[1] + marker.y - imgui.get_scroll_y()
        draw.add_rect_filled(
            (marker_x, marker_y),
            (marker_x + marker.width, marker_y + marker.height),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
        )

    @staticmethod
    def _gradient_color(position: float, stops) -> tuple[float, float, float, float]:
        for (left_pos, left), (right_pos, right) in zip(stops, stops[1:], strict=False):
            if position <= right_pos:
                fraction = (position - left_pos) / max(1e-9, right_pos - left_pos)
                return tuple(a + (b - a) * fraction for a, b in zip(left, right, strict=True))
        return stops[-1][1]

    def _initialize_policy_draft(self, country_row, view, country_tag: str) -> None:
        if self._draft_country_id == country_tag:
            return
        self._draft_country_id = country_tag
        self._draft_minimum_wage = view.minimum_wage
        self._draft_interest_rate = view.interest_rate
        self._draft_tax_rate = self._read_float(country_row, "personal_income_tax_rate", 0.2)
        self._draft_health_spending = self._read_float(country_row, "budget_health_ratio", 0.5)
        self._policy_baseline = self._current_policy_values()

    def _reset_rate_repeat(self, value_name: str) -> None:
        self._rate_repeat[value_name].reset()

    def _policy_rate_bounds(self, state, value_name: str) -> tuple[float, float]:
        terms = getattr(state, "globals", {}).get("economic_health_terms", {})
        terms = terms if isinstance(terms, Mapping) else {}
        try:
            lower = float(terms.get(f"min_{value_name}", 0.0))
            upper = float(terms.get(f"max_{value_name}", 0.5))
        except (TypeError, ValueError, OverflowError):
            return 0.0, 0.5
        if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
            return 0.0, 0.5
        return lower, upper

    def _clamp_policy_rate(self, state, value_name: str, value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        lower, upper = self._policy_rate_bounds(state, value_name)
        return max(lower, min(upper, value))

    def _apply_policy_changes(self, context: PanelRenderContext) -> None:
        if context.net_client is None:
            return
        current = self._current_policy_values()
        for policy_name, value in current.items():
            baseline = self._policy_baseline.get(policy_name)
            if baseline is None or abs(value - baseline) <= 1e-9:
                continue
            self._dispatch_policy_value(context.net_client, context.target_tag, policy_name, value)

    def _render_content(self, state, context: PanelRenderContext):
        target_tag = context.target_tag
        country_row = self._get_country_row(state, target_tag)
        view = self._presenter.present(state, target_tag)
        if country_row is None or view is None:
            draw_empty_state("No economic profile is available for this country.")
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
        if self._render_page_navigation():
            imgui.pop_style_var()
            return
        imgui.push_text_wrap_pos(0.0)

        if self._active_page == "debt":
            self._render_debt_controls(state, context, view)
            imgui.pop_text_wrap_pos()
            imgui.pop_style_var()
            return
        if self._active_page == "policy":
            self._render_policy_controls(state, context, view, country_row)
            imgui.pop_text_wrap_pos()
            imgui.pop_style_var()
            return

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

        imgui.pop_text_wrap_pos()
        imgui.pop_style_var()

    def _render_page_navigation(self) -> bool:
        window_position = imgui.get_window_pos()
        layout = active_gml_layout()
        x = layout.window_position[0] + 20.0 if layout else float(window_position.x) + 20.0
        y = layout.window_position[1] + 32.0 if layout else float(window_position.y) + 32.0
        token = suspend_gml_layout()
        try:
            for index, (page_id, label) in enumerate((
                ("overview", "OVERVIEW"),
                ("policy", "POLICY"),
                ("debt", "DEBT"),
                ("source", "REFERENCE"),
            )):
                imgui.set_cursor_screen_pos((x + index * 74.0, y))
                if imgui.button(
                    label,
                    (68.0, 17.0),
                    test_id=f"economic_health.page.{page_id}",
                ):
                    self._active_page = page_id
                    if page_id == "source":
                        self._population_cursor_values.clear()
                        return True
        finally:
            resume_gml_layout(token)
        return False

    def _render_policy_controls(self, state, context: PanelRenderContext, view, country_row) -> None:
        client = context.net_client
        terms = getattr(state, "globals", {}).get("economic_health_terms", {})
        terms = terms if isinstance(terms, Mapping) else {}
        self._initialize_policy_draft(country_row, view, context.target_tag)
        imgui.dummy((0, 8))
        Prims.header("SCHEDULE ECONOMIC POLICY", show_bg=False)
        max_wage = max(1.0, float(terms.get("max_minimum_wage", 1_000_000.0)))
        imgui.text_disabled("Minimum wage")
        imgui.set_next_item_width(216.0)
        _, self._draft_minimum_wage = imgui.slider_float(
            "##minimum-wage", self._draft_minimum_wage, 0.0, max_wage, "%.0f",
            test_id="economic_health.minimum_wage",
        )
        imgui.text_disabled("Policy interest rate")
        imgui.set_next_item_width(216.0)
        _, interest_percent = imgui.slider_float(
            "##interest-rate", self._draft_interest_rate * 100.0, 0.0, 50.0, "%.1f%%",
            test_id="economic_health.interest_rate",
        )
        self._draft_interest_rate = interest_percent / 100.0
        imgui.text_disabled("Personal income tax")
        imgui.set_next_item_width(216.0)
        _, tax_percent = imgui.slider_float(
            "##tax-rate", self._draft_tax_rate * 100.0, 0.0, 50.0, "%.1f%%",
            test_id="economic_health.tax_rate",
        )
        self._draft_tax_rate = tax_percent / 100.0
        imgui.text_disabled("Public health spending")
        imgui.set_next_item_width(216.0)
        _, health_spending_percent = imgui.slider_float(
            "##health-spending", self._draft_health_spending * 100.0, 0.0, 100.0, "%.1f%%",
            test_id="economic_health.health_spending",
        )
        self._draft_health_spending = health_spending_percent / 100.0
        can_change = bool(context.is_own_country and client is not None)
        imgui.begin_disabled(not can_change)
        if imgui.button("Wage", (102.0, 18.0), test_id="economic_health.schedule_wage") and can_change:
            self._dispatch_policy_value(client, context.target_tag, "minimum_wage", self._draft_minimum_wage)
        imgui.same_line(spacing=8.0)
        if imgui.button("Interest", (102.0, 18.0), test_id="economic_health.schedule_interest") and can_change:
            self._dispatch_policy_value(client, context.target_tag, "interest_rate", self._draft_interest_rate)
        if imgui.button("Income tax", (102.0, 18.0), test_id="economic_health.schedule_tax") and can_change:
            self._dispatch_policy_value(client, context.target_tag, "personal_income_tax_rate", self._draft_tax_rate)
        imgui.same_line(spacing=8.0)
        if imgui.button("Health budget", (102.0, 18.0), test_id="economic_health.schedule_health") and can_change:
            self._dispatch_policy_value(client, context.target_tag, "budget_health_ratio", self._draft_health_spending)
        imgui.end_disabled()
        if view.active_policies:
            for policy in view.active_policies[:3]:
                imgui.text_wrapped(
                    f"{policy.policy_name} → {policy.target_value:.3f}; "
                    f"cost $ {policy.transition_cost:,.0f}; effective {policy.effective_date}"
                )

    def _current_policy_values(self) -> dict[str, float]:
        return {
            "minimum_wage": float(self._draft_minimum_wage),
            "interest_rate": float(self._draft_interest_rate),
            "personal_income_tax_rate": float(self._draft_tax_rate),
            "budget_health_ratio": float(self._draft_health_spending),
        }

    def _has_policy_changes(self) -> bool:
        current = self._current_policy_values()
        return any(
            abs(current[key] - baseline) > 1e-9
            for key, baseline in self._policy_baseline.items()
        )

    def _dispatch_policy_value(self, client, country_tag: str, policy_name: str, value: float) -> None:
        if policy_name == "personal_income_tax_rate":
            client.send_action(ActionSetTax(client.player_id, country_tag, value))
        else:
            client.send_action(ActionChangeEconomicPolicy(
                client.player_id, country_tag, policy_name, value
            ))
        self._policy_baseline[policy_name] = float(value)

    def _finish_close(self, decision: CloseDecision, context: PanelRenderContext) -> None:
        if decision is CloseDecision.APPLY and context.net_client is not None:
            self._apply_policy_changes(context)
        else:
            values = self._policy_baseline or self._current_policy_values()
            self._draft_minimum_wage = values["minimum_wage"]
            self._draft_interest_rate = values["interest_rate"]
            self._draft_tax_rate = values["personal_income_tax_rate"]
            self._draft_health_spending = values["budget_health_ratio"]

    def _render_debt_controls(self, state, context: PanelRenderContext, view) -> None:
        client = context.net_client
        countries = state.tables.get("countries")
        country_ids = [] if countries is None or "id" not in countries.columns else sorted(
            str(value) for value in countries.get_column("id").to_list() if str(value) != context.target_tag
        )
        if self._creditor_country_id not in country_ids:
            self._creditor_country_id = country_ids[0] if country_ids else ""
        preview = self._creditor_country_id or "No eligible creditor"
        window_position = imgui.get_window_pos()
        window_size = imgui.get_window_size()

        def inline_width(label: str, maximum: float = 140.0) -> float:
            left = float(window_position.x) + 28.0
            right = float(window_position.x + window_size.x) - 12.0
            label_width = imgui.calc_text_size(label).x
            return max(0.0, min(maximum, right - left - label_width - 8.0))

        token = suspend_gml_layout()
        try:
            imgui.set_cursor_screen_pos((float(window_position.x) + 28.0, float(window_position.y) + 68.0))
            imgui.set_next_item_width(inline_width("Creditor"))
            if imgui.begin_combo("Creditor", preview, test_id="economic_health.creditor"):
                for country_id in country_ids:
                    selected = country_id == self._creditor_country_id
                    if imgui.selectable(country_id, selected)[0]:
                        self._creditor_country_id = country_id
                imgui.end_combo()

            imgui.set_cursor_screen_pos((float(window_position.x) + 28.0, float(window_position.y) + 104.0))
            imgui.set_next_item_width(inline_width("Principal"))
            _, self._loan_principal = imgui.input_float(
                "Principal", self._loan_principal, 0.0, 0.0, "%.0f",
                test_id="economic_health.principal",
            )
            imgui.set_cursor_screen_pos((float(window_position.x) + 28.0, float(window_position.y) + 140.0))
            imgui.set_next_item_width(inline_width("Annual interest"))
            _, self._loan_interest_rate = imgui.slider_float(
                "Annual interest", self._loan_interest_rate, 0.0, 0.5, "%.3f",
                test_id="economic_health.loan_interest",
            )
            can_request = bool(context.is_own_country and client is not None and self._creditor_country_id)
            imgui.begin_disabled(not can_request)
            imgui.set_cursor_screen_pos((float(window_position.x) + 28.0, float(window_position.y) + 179.0))
            if imgui.button(
                "REQUEST FINANCING",
                test_id="economic_health.request_financing",
            ) and can_request:
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
        finally:
            resume_gml_layout(token)
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

    def _country_population(self, state, target_tag: str) -> float | None:
        regions = getattr(state, "tables", {}).get("regions")
        columns = ("pop_14", "pop_15_64", "pop_65")
        if regions is None or "owner" not in regions.columns or not set(columns).issubset(regions.columns):
            return None
        try:
            totals = regions.filter(pl.col("owner") == str(target_tag)).select(
                [pl.col(column).fill_null(0).sum().alias(column) for column in columns]
            ).row(0)
            population = sum(float(value or 0.0) for value in totals)
        except Exception:
            return None
        return population if math.isfinite(population) and population > 0.0 else None

    @staticmethod
    def _finite_rate(value: float) -> float:
        try:
            rate = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return rate if math.isfinite(rate) else 0.0

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
        return format_signed_currency(float(value))
