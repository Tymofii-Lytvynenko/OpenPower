from src.client.ui.core.panel_close_intent import PanelCloseIntent
from src.client.ui.core.formatting import format_signed_currency

import polars as pl
from imgui_bundle import icons_fontawesome_6
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.theme import GAMETHEME
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)
from src.shared.actions import ActionUpdateBudget
from src.shared.budget_policy import BUDGET_DEMAND_MULTIPLIER, BUDGET_SECTOR_WEIGHTS
from src.client.ui.panels.budget_allocations import (
    country_budget_allocations,
    default_budget_allocations,
    normalize_budget_ratio,
)


class BudgetPanel:
    """
    Detailed National Budget Menu.
    Uses real data from the simulation and allows interaction for the player's country.
    """
    ROW_DETAILS = {
        "income-tax": (
            "Annual income-tax revenue, calculated from GDP, human development, "
            "and the effective personal tax rate."
        ),
        "income-trade": "Annual public revenue recorded by the global trade market.",
        "fixed-security": "Recurring security-services expenditure recorded for this country.",
        "fixed-diplomacy": "Diplomatic aid and treaty-maintenance expenditure recorded for this country.",
        "fixed-trade": "Government trade-import and trade-agreement expenditure recorded for this country.",
        "fixed-military-upkeep": (
            "Annual military operating costs based on force size, readiness, "
            "and active design maintenance."
        ),
    }
    PERSONAL_INCOME_TAX_KEY = "personal_income_tax_rate"

    def __init__(
        self,
        open_economic_health_cb=None,
        open_resources_cb=None,
        open_treaties_cb=None,
        open_covert_ops_cb=None,
        open_unit_list_cb=None,
    ):
        self._close_intent = PanelCloseIntent()
        self.request_close = self._close_intent.request
        self._navigation_callbacks = {
            "income-tax": open_economic_health_cb,
            "income-trade": open_resources_cb,
            "fixed-security": open_covert_ops_cb,
            "fixed-diplomacy": open_treaties_cb,
            "fixed-trade": open_resources_cb,
            "fixed-military-upkeep": open_unit_list_cb,
        }
        self.K_BUDGET = BUDGET_DEMAND_MULTIPLIER
        self.PERSONAL_INCOME_TAX_CONSTANT = 3.0
        
        # Mapping of column names to UI labels
        self.M_SECTOR_LABELS = {
            "budget_health_ratio": "HEALTH CARE",
            "budget_edu_ratio": "EDUCATION",
            "budget_social_ratio": "SOCIAL SUPPORT",
            "budget_gov_ratio": "GOVERNMENT",
            "budget_env_ratio": "ENVIRONMENT",
            "budget_research_ratio": "RESEARCH",
            "budget_infra_ratio": "INFRASTRUCTURE",
            "budget_telecom_ratio": "TELECOM",
            "budget_imf_ratio": "FOREIGN AID (IMF)",
            "budget_propaganda_ratio": "PROPAGANDA",
            "budget_tourism_promo_ratio": "TOURISM"
        }
        
        # Sector multipliers from BudgetSystem
        self.M_SECTOR_WEIGHTS = dict(BUDGET_SECTOR_WEIGHTS)
        
        self.allocations = default_budget_allocations(
            self.M_SECTOR_LABELS, self.PERSONAL_INCOME_TAX_KEY
        )
        self.draft_allocations = self.allocations.copy()
        
        self.REQUIREMENT_THRESHOLD = 0.50
        self.close_confirmation = DirtyCloseConfirmation(
            "budget.close",
            "Apply your budget changes before closing?",
        )
        self._local_save_confirmation_preferences = SaveConfirmationPreferences()
        self.current_tag = ""
        self._needs_state_sync = True

    def render(self, state, context: PanelRenderContext) -> bool:
        navigation_close = self._close_intent.consume()
        target_tag = context.target_tag
        is_own = context.is_own_country
        net_client = context.net_client
        preferences = (
            context.save_confirmation_preferences
            or self._local_save_confirmation_preferences
        )
        can_apply = bool(net_client and is_own)

        self._sync_target_allocations(state, target_tag)

        with WindowManager.window(
            "BUDGET MENU",
            x=300,
            y=100,
            w=480,
            h=780,
            test_id="budget.panel",
        ) as is_open:
            has_changes = self.draft_allocations != self.allocations
            close_decision = None

            if not is_open or navigation_close:
                if has_changes:
                    close_decision = self.close_confirmation.request_close(
                        preferences,
                        can_apply=can_apply,
                    )
                else:
                    return False

            apply_enabled = has_changes and is_own and net_client is not None
            imgui.begin_disabled(not apply_enabled)
            imgui.push_style_color(
                imgui.Col_.button,
                GAMETHEME.colors.interaction_active if apply_enabled else (0, 0, 0, 0),
            )
            if Prims.button(
                "✓",
                test_id="budget.apply",
                size=(17.0, 17.0),
                enabled=apply_enabled,
            ) and apply_enabled:
                self._dispatch_budget_update(net_client, target_tag)
            imgui.pop_style_color()
            imgui.end_disabled()

            self._render_content(state, target_tag, is_own)

            if close_decision is not None:
                self._finish_close(close_decision, net_client, target_tag)
                return False

            close_decision = self.close_confirmation.render(
                preferences,
                can_apply=can_apply,
            )
            if close_decision is not None:
                self._finish_close(close_decision, net_client, target_tag)
                return False

            return True

    def _sync_target_allocations(self, state, target_tag) -> None:
        if target_tag != self.current_tag:
            self.current_tag = target_tag
            self.allocations = default_budget_allocations(
                self.M_SECTOR_LABELS, self.PERSONAL_INCOME_TAX_KEY
            )
            self.draft_allocations = self.allocations.copy()
            self._needs_state_sync = True

        if self._needs_state_sync:
            # Retry when snapshots arrive before the selected country row.
            # Defaults prevent showing allocations from the previously selected country.
            self._needs_state_sync = not self._sync_with_state(state, target_tag)

    def _sync_with_state(self, state, target_tag) -> bool:
        if "countries" not in state.tables:
            return False
        df = state.get_table("countries").filter(pl.col("id") == target_tag)
        if df.is_empty():
            return False

        allocations = country_budget_allocations(
            df.to_dicts()[0], self.M_SECTOR_LABELS, self.PERSONAL_INCOME_TAX_KEY
        )
        if allocations is None:
            return False

        self.allocations = allocations
        self.draft_allocations = self.allocations.copy()
        return True

    def _finish_close(self, decision, net_client, target_tag) -> None:
        if decision is CloseDecision.APPLY and net_client:
            self._dispatch_budget_update(net_client, target_tag)
        else:
            self.draft_allocations = self.allocations.copy()

    def _get_player_total_demand(self, state, target_tag) -> float:
        if "resource_ledger" not in state.tables: return 0.0
        country_ledger = state.get_table("resource_ledger").filter(pl.col("country_id") == target_tag)
        if country_ledger.is_empty(): return 0.0
        return country_ledger["consumption_usd"].sum()

    def _render_content(self, state, target_tag, is_own):
        total_demand = self._get_player_total_demand(state, target_tag)

        # Get country data for income and fixed expenses
        country_row = {}
        if "countries" in state.tables:
            df = state.get_table("countries").filter(pl.col("id") == target_tag)
            if not df.is_empty():
                country_row = df.to_dicts()[0]

        # 1. INCOME
        revenue_tax = country_row.get("revenue_tax", 0.0)
        trade_income = country_row.get("trade_income", 0.0)
        tourism_income = country_row.get("tourism_income", 0.0)
        budget_imf_ratio = country_row.get("budget_imf_ratio", 0.0)
        total_income = country_row.get("total_annual_revenue", revenue_tax + trade_income + tourism_income + budget_imf_ratio)

        self._draw_gml_text("frmIncome", "lblTitle", "INCOME", color=GAMETHEME.colors.text_main)
        self._draw_gml_text("frmIncome", "txtLabel", "TOTAL")
        self._draw_gml_text(
            "frmIncome", "txtTotal", self._fmt_money(total_income),
            color=GAMETHEME.colors.positive, align="right",
        )
        self._draw_gml_text("frmIncome", "txtLabel2", "PERSONAL INCOME TAX")
        self._draw_gml_text(
            "frmIncome", "txtPersonnalIncomeTax", self._fmt_money(revenue_tax),
            align="right",
        )
        self._draw_more_button("income-tax", "frmIncome", "btnPersonalIncomeTax", revenue_tax)
        self._draw_income_tax_slider(is_own)
        self._draw_gml_text("frmIncome", "txtLabel3", "TRADE")
        self._draw_gml_text("frmIncome", "txtTrade", self._fmt_money(trade_income), align="right")
        self._draw_more_button("income-trade", "frmIncome", "btnTrade", trade_income)
        self._draw_gml_text("frmIncome", "txtLabel4", "TOURISM")
        self._draw_gml_text("frmIncome", "txtTourism", self._fmt_money(tourism_income), align="right")
        self._draw_gml_text("frmIncome", "txtLabel5", "IMF AID")
        self._draw_gml_text("frmIncome", "txtImf", self._fmt_money(budget_imf_ratio), align="right")

        # 2. SECTOR EXPENSES (Dynamic Preview)
        total_expense_dynamic = sum(
            total_demand * self.K_BUDGET * self.M_SECTOR_WEIGHTS[col] * self.draft_allocations[col]
            for col in self.M_SECTOR_LABELS.keys()
        )
        
        self._draw_gml_text("frmExpenses", "lblTitle", "EXPENSES", color=GAMETHEME.colors.text_main)
        self._draw_gml_text("frmExpenses", "lblTotal", "TOTAL")
        self._draw_gml_text(
            "frmExpenses", "txtTotal", self._fmt_money(total_expense_dynamic),
            color=GAMETHEME.colors.negative, align="right",
        )
        
        # Define UI order
        ui_order = [
            "budget_infra_ratio", "budget_propaganda_ratio", "budget_env_ratio", "budget_health_ratio", 
            "budget_edu_ratio", "budget_telecom_ratio", "budget_gov_ratio", "budget_imf_ratio", 
            "budget_research_ratio", "budget_tourism_promo_ratio", "budget_social_ratio"
        ]
                    
        gml_expense_components = {
            "budget_infra_ratio": ("lblInfrastructure", "frmMeterInfrastructure", "txtInfrastructure"),
            "budget_propaganda_ratio": ("lblPropaganda", "frmMeterPropaganda", "txtPropaganda"),
            "budget_env_ratio": ("lblEnvironment", "frmMeterEnvironment", "txtEnvironment"),
            "budget_health_ratio": ("lblHealthCare", "frmMeterHealthCare", "txtHealthCare"),
            "budget_edu_ratio": ("lblEducation", "frmMeterEducation", "txtEducation"),
            "budget_telecom_ratio": ("lblTelecom", "frmMeterTelecom", "txtTelecom"),
            "budget_gov_ratio": ("lblGovernment", "frmMeterGovernment", "txtGovernment"),
            "budget_imf_ratio": ("lblImf", "frmMeterImf", "txtImf"),
            "budget_research_ratio": ("lblResearch", "frmMeterResearch", "txtResearch"),
            "budget_tourism_promo_ratio": ("lblTourism", "frmMeterTourism", "txtTourism"),
        }
        for col in ui_order:
            label = self.M_SECTOR_LABELS[col]
            preview_cost = total_demand * self.K_BUDGET * self.M_SECTOR_WEIGHTS[col] * self.draft_allocations[col]
            components = gml_expense_components.get(col)
            if components is not None:
                self._draw_gml_expense_slider(col, label, preview_cost, is_own, *components)

        # 3. FIXED EXPENSES
        expense_corruption = country_row.get("expense_corruption", 0.0)
        security_upkeep = country_row.get("security_upkeep", 0.0)
        diplomacy_upkeep = country_row.get("diplomacy_upkeep", 0.0)
        trade_expense = country_row.get("trade_expense", 0.0)
        military_upkeep = country_row.get("expense_military_upkeep", 0.0)
        debt_interest = country_row.get("expense_debt_interest", 0.0)
        
        total_fixed = (expense_corruption + security_upkeep + diplomacy_upkeep + 
                       trade_expense + military_upkeep + debt_interest)

        self._draw_gml_text("frmFixedExpenses", "lblTitle", "FIXED EXPENSES", color=GAMETHEME.colors.text_main)
        self._draw_gml_text("frmFixedExpenses", "txtLabel", "TOTAL")
        self._draw_gml_text(
            "frmFixedExpenses", "txtTotal", self._fmt_money(total_fixed),
            color=GAMETHEME.colors.negative, align="right",
        )
        fixed_rows = (
            ("SECURITY", security_upkeep, "txtLabel1", "txtSecurity", "btnSecurity", "fixed-security"),
            ("DIPLOMACY", diplomacy_upkeep, "txtLabel2", "txtDiplomacy", "btnDiplomacy", "fixed-diplomacy"),
            ("TRADE", trade_expense, "txtLabel3", "txtTrade", "btnTrade", "fixed-trade"),
            ("MILITARY UPKEEP", military_upkeep, "txtLabel5", "txtUnitsUpkeep", "btnUnitUpkeep", "fixed-military-upkeep"),
            ("DEBT INTEREST", debt_interest, "txtLabel4", "txtDebt", None, None),
            ("CORRUPTION", expense_corruption, "txtLabel6", "txtCorruption", None, None),
        )
        for label, amount, label_id, value_id, button_id, detail_key in fixed_rows:
            self._draw_gml_text("frmFixedExpenses", label_id, label)
            self._draw_gml_text(
                "frmFixedExpenses", value_id, self._fmt_money(amount), align="right"
            )
            if button_id and detail_key:
                self._draw_more_button(detail_key, "frmFixedExpenses", button_id, amount)

        # 4. SUMMARY
        total_expenses = total_expense_dynamic + total_fixed
        surplus = total_income - total_expenses
        money_reserves = country_row.get("money_reserves", 0.0)

        self._draw_gml_text("frmBalance", "lblTitle", "SURPLUS / DEFICIT", color=GAMETHEME.colors.text_main)
        self._draw_gml_text(
            "frmBalance", "txtAmount", self._fmt_money(surplus),
            color=GAMETHEME.colors.positive if surplus >= 0 else GAMETHEME.colors.negative,
            align="right",
        )
        self._draw_gml_text("frmAvailable", "lblTitle", "AVAILABLE FUNDS", color=GAMETHEME.colors.text_main)
        self._draw_gml_text(
            "frmAvailable", "txtAmount", self._fmt_money(money_reserves),
            color=GAMETHEME.colors.positive if money_reserves >= 0 else GAMETHEME.colors.negative,
            align="right",
        )

    @staticmethod
    def _gml_component_path(section: str, component_id: str) -> str:
        return f"Budget_Window/frmInner/{section}/{component_id}"

    def _draw_gml_text(self, section, component_id, text, *, color=None, align=None):
        component_path = self._gml_component_path(section, component_id)
        if color is None:
            imgui.text(str(text), gml_id=component_path, gml_align=align)
        else:
            imgui.text_colored(color, str(text), gml_id=component_path, gml_align=align)

    def _draw_more_button(self, detail_key, section, component_id, amount):
        callback = self._navigation_callbacks.get(detail_key)
        if callback is None:
            return
        clicked = Prims.button(
            "more",
            test_id=f"budget.navigate.{detail_key}",
            size=(37.0, 12.0),
            gml_id=self._gml_component_path(section, component_id),
        )
        if clicked:
            callback()
        if imgui.is_item_hovered():
            imgui.set_tooltip(self._standard_row_details(detail_key, amount))

    def _draw_gml_expense_slider(
        self, col, label, value, is_own, label_id, meter_id, value_id
    ):
        section = "frmExpenses"
        self._draw_gml_text(section, label_id, label)

        alloc_pct = self.draft_allocations.get(col, 0.5)
        if not is_own:
            imgui.begin_disabled()
        Prims.invisible_button(
            (162.0, 16.0),
            test_id=f"budget.allocation.{col}",
            label=f"{label} allocation slider",
            enabled=is_own,
            gml_id=self._gml_component_path(section, meter_id),
        )
        if not is_own:
            imgui.end_disabled()

        p = imgui.get_item_rect_min()
        max_p = imgui.get_item_rect_max()
        slider_w = float(max_p.x - p.x)
        slider_h = float(max_p.y - p.y)
        if imgui.is_item_active():
            mouse_x = imgui.get_io().mouse_pos.x
            new_pct = max(0.0, min((mouse_x - p.x) / max(1.0, slider_w), 1.0))
            if 0.48 <= new_pct <= 0.52:
                new_pct = self.REQUIREMENT_THRESHOLD
            self.draft_allocations[col] = new_pct
            alloc_pct = new_pct

        draw_list = imgui.get_window_draw_list()
        mid_x = p.x + slider_w * self.REQUIREMENT_THRESHOLD
        alloc_x = p.x + slider_w * alloc_pct
        draw_list.add_rect_filled(p, (mid_x, p.y + slider_h), imgui.get_color_u32((0.2, 0.05, 0.05, 1.0)))
        draw_list.add_rect_filled((mid_x, p.y), (p.x + slider_w, p.y + slider_h), imgui.get_color_u32((0.05, 0.15, 0.05, 1.0)))
        if alloc_pct < self.REQUIREMENT_THRESHOLD:
            draw_list.add_rect_filled((alloc_x, p.y), (mid_x, p.y + slider_h), imgui.get_color_u32((0.8, 0.15, 0.15, 1.0)))
        elif alloc_pct > self.REQUIREMENT_THRESHOLD:
            draw_list.add_rect_filled((mid_x, p.y), (alloc_x, p.y + slider_h), imgui.get_color_u32((0.2, 0.7, 0.2, 1.0)))
        draw_list.add_line((mid_x, p.y - 3), (mid_x, p.y + slider_h + 3), imgui.get_color_u32((0.4, 0.4, 0.4, 1.0)), 2.0)
        draw_list.add_rect(p, (p.x + slider_w, p.y + slider_h), imgui.get_color_u32((0.0, 0.0, 0.0, 1.0)))
        draw_list.add_rect_filled((alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), imgui.get_color_u32((0.9, 0.9, 0.9, 1.0)))
        draw_list.add_rect((alloc_x - 2, p.y - 2), (alloc_x + 2, p.y + slider_h + 2), imgui.get_color_u32((0.0, 0.0, 0.0, 1.0)))
        self._draw_gml_text(section, value_id, self._fmt_short_money(value), align="right")

    def _draw_income_tax_slider(self, is_own: bool) -> None:
        session = active_gml_layout()
        if session is not None:
            amount = session.layout.component(
                self._gml_component_path("frmIncome", "txtPersonnalIncomeTax")
            )
            if amount is not None:
                amount_rect = session.rect_for(amount)
                imgui.set_cursor_screen_pos((
                    session.window_position[0] + amount_rect.x + 49,
                    session.window_position[1] + amount_rect.y,
                ))
        current = self.draft_allocations[self.PERSONAL_INCOME_TAX_KEY]
        imgui.set_next_item_width(88.0)
        if not is_own:
            imgui.begin_disabled()
        changed, percentage = Prims.slider_float(
            "##income-tax-rate",
            current * 100.0,
            0.0,
            100.0,
            "%.0f%%",
            test_id="budget.income_tax_rate",
            enabled=is_own,
        )
        if not is_own:
            imgui.end_disabled()
        if changed:
            self.draft_allocations[self.PERSONAL_INCOME_TAX_KEY] = self._bounded_ratio(
                percentage / 100.0, current
            )

    # Helpers
    def _fmt_money(self, val: float) -> str:
        return format_signed_currency(val)

    def _fmt_short_money(self, val: float) -> str:
        abs_val = abs(val)
        if abs_val >= 1_000_000_000: return f"$ {abs_val / 1_000_000_000:,.1f} B".replace(",", " ")
        elif abs_val >= 1_000_000: return f"$ {abs_val / 1_000_000:,.1f} M".replace(",", " ")
        return self._fmt_money(val)

    def _standard_row_details(self, detail_key: str, value: float) -> str:
        description = self.ROW_DETAILS.get(detail_key)
        if description is None:
            description = "Additional information is not available for this budget row."
        return f"{description}\nCurrent recorded amount: {self._fmt_money(value)}"

    def _dispatch_budget_update(self, net_client, country_tag: str) -> None:
        action = ActionUpdateBudget(
            player_id=net_client.player_id,
            country_tag=country_tag,
            allocations={
                key: self._bounded_ratio(value, self.allocations.get(key, 0.0))
                for key, value in self.draft_allocations.items()
            },
        )
        net_client.send_action(action)
        self.allocations = action.allocations.copy()
        self.draft_allocations = self.allocations.copy()

    @staticmethod
    def _bounded_ratio(value, fallback: float) -> float:
        return normalize_budget_ratio(value, fallback)
