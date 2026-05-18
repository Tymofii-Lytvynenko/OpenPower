import polars as pl
import numpy as np
from typing import List

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionBuildUnit, ActionUpdateBudget, GameAction

# =========================================================================
# 📊 FIRST-PRINCIPLES SCORERS (Utility evaluation based on real economic metrics)
# All computations utilize absolute physical/financial metrics (currency, time, probabilities).
# =========================================================================

def audit_financial_survival(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    LEVEL 1: SURVIVAL.
    Calculates the financial runway (how many months a country can operate before default).
    """
    return lf.with_columns(
        # Net annual income or budget deficit
        annual_net_income = pl.col("total_annual_revenue") - pl.col("total_annual_expense")
    ).with_columns(
        # Remaining months before bankruptcy if net income is negative; otherwise infinity (999.0)
        months_to_bankruptcy = pl.when(pl.col("annual_net_income") < 0)
                                 .then((pl.col("money_reserves") / pl.col("annual_net_income").abs()) * 12)
                                 .otherwise(999.0)
    ).with_columns(
        # Survival utility: as months to default drops below 12, utility scales up rapidly toward 1.0
        utility_survival_taxes = pl.when(pl.col("months_to_bankruptcy") < 12.0)
                                   .then((1.0 - (pl.col("months_to_bankruptcy") / 12.0)).clip(0.0, 1.0))
                                   .otherwise(0.0)
    )

def calculate_military_roi(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    LEVEL 2: DEVELOPMENT (Security Investments).
    Calculates the Total Cost of Ownership (TCO) of the military alongside its insurance value for GDP.
    """
    # Business assumptions (5-year planning horizon)
    PLANNING_HORIZON_YEARS = 5.0
    UNIT_BUILD_COST = 1_000_000.0
    UNIT_ANNUAL_UPKEEP_BASE = 500_000.0
    # One military unit is estimated to protect 1% of GDP from damage or hostile actions
    GDP_PROTECTED_PER_UNIT = 0.01 

    return lf.with_columns(
        # Total cost: Build cost plus upkeep over the 5-year planning horizon
        unit_5y_cost = UNIT_BUILD_COST + (UNIT_ANNUAL_UPKEEP_BASE * pl.col("human_dev") * PLANNING_HORIZON_YEARS)
    ).with_columns(
        # Expected benefit: The portion of GDP preserved by the unit in absolute monetary terms.
        # PSYCHOLOGY: A paranoid leader (trait > 1.0) perceives threat levels as higher, inflating perceived utility.
        unit_5y_benefit = (pl.col("gdp") * GDP_PROTECTED_PER_UNIT) * pl.col("trait_threat_perception")
    ).with_columns(
        # Net financial ROI (Return on Investment) of military deployment
        military_roi = (pl.col("unit_5y_benefit") - pl.col("unit_5y_cost")) / pl.col("unit_5y_cost")
    ).with_columns(
        # Military buildup utility: Only triggered if ROI is positive, reserves exceed cost, and budget is not in deficit
        utility_build_army = pl.when(
                                (pl.col("military_roi") > 0.0) & 
                                (pl.col("money_reserves") > pl.col("unit_5y_cost")) &
                                (pl.col("annual_net_income") > 0.0)
                             )
                             .then(pl.col("military_roi").clip(0.0, 1.0))
                             .otherwise(0.0)
    )

# =========================================================================
# ⚙️ AI SYSTEM (Framework Orchestrator)
# =========================================================================

class AISystem(ISystem):
    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.ai"

    @property
    def dependencies(self) -> list[str]:
        # AI execution should start immediately after the time/tick progression system
        return ["base.time"]

    def _ensure_columns(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Validates and initializes missing columns, including psychological state indicators."""
        schema = lf.collect_schema().names()
        
        defaults = {
            "total_annual_revenue": 0.0,
            "total_annual_expense": 0.0,
            "money_reserves": 0.0,
            "gdp": 10_000_000.0,
            "human_dev": 0.5,
            "personal_income_tax_rate": 0.20,
            # Psychological profile: 1.0 = baseline government. >1.0 = paranoid, <1.0 = pacifist/risk-averse
            "trait_threat_perception": 1.0 
        }

        for col, default_val in defaults.items():
            if col not in schema:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found. Defaulting to {default_val}.")
                    self._missing_columns.add(col)
                lf = lf.with_columns(pl.lit(default_val).alias(col))
                
        return lf

    def update(self, state: GameState, delta_time: float) -> None:
        tick = state.globals.get("tick", 0)
        # AI decision-making throttled to monthly intervals (every 30 ticks)
        if tick % 30 != 0:
            return

        if "countries" not in state.tables:
            return

        # 1. DATA PREPARATION
        countries_lf = state.get_table("countries").lazy()
        countries_lf = self._ensure_columns(countries_lf)

        # 2. VECTOR UTILITY EVALUATION (First-Principles Pipeline)
        decision_df = (
            countries_lf
            .pipe(audit_financial_survival)
            .pipe(calculate_military_roi)
            .select([
                "id", 
                "personal_income_tax_rate", 
                "utility_survival_taxes", 
                "utility_build_army",
                "months_to_bankruptcy",
                "military_roi"
            ])
            .collect()
        )

        # 3. ACTION RESOLUTION (Hierarchical Decision Tree)
        generated_actions: List[GameAction] = []

        for row in decision_df.iter_rows(named=True):
            country_id = row["id"]
            
            # National Maslow's hierarchy of needs: prioritizes survival before development/expansion
            
            # LEVEL 1: Default Threat Mitigation (Highest priority)
            if row["utility_survival_taxes"] > 0.0:
                current_tax = row["personal_income_tax_rate"]
                # Adjust taxes conservatively (+2% increments) to prevent sudden economic collapse
                new_tax = min(0.50, current_tax + 0.02)
                
                generated_actions.append(ActionUpdateBudget(
                    player_id="ai_system",
                    country_tag=country_id,
                    allocations={"personal_income_tax_rate": new_tax}
                ))
                continue # Economic rescue takes absolute precedence; defer expansion plans for the next tick.

            # LEVEL 2: Financial Surplus & Security Reinvestment
            if row["utility_build_army"] > 0.0:
                generated_actions.append(ActionBuildUnit(
                    player_id="ai_system",
                    country_tag=country_id,
                    unit_type="army",
                    count=1
                ))
                # Divergent behavior emerges naturally from underlying GDP variances and psychological traits

        # 4. ACTION INJECTION
        state.current_actions.extend(generated_actions)

        # (Optional) Developer Telemetry / Debug logging
        # print(f"[{self.id}] AI Actions Generated: {len(generated_actions)}")