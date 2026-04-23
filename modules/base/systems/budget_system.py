import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class BudgetSystem(ISystem):
    """
    Handles national budget calculations including revenues, expenses, debt interest, 
    and tax fairness.
    """

    # Constant used to balance the personal income tax formula against GDP
    # TODO: Adjust this constant based on OpenPower's global GDP scale during balancing.
    PERSONAL_INCOME_TAX_CONSTANT = 3.0 
    
    DEBT_INTEREST_RATE = 0.05

    @property
    def id(self) -> str:
        return "base.budget"

    @property
    def dependencies(self) -> list[str]:
        # Budget must run after Economy (GDP calculation) and Trade (Imports/Exports revenue)
        return ["base.time", "base.economy", "base.trade"]

    def update(self, state: GameState, delta_time: float) -> None:
        # We process financial ticks continuously based on real seconds to keep the UI smooth
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            
            # Convert game seconds to a fraction of an in-game year
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_budget(state, fraction_of_year)

    def _process_budget(self, state: GameState, fraction: float) -> None:
        if "countries" not in state.tables:
            return

        # Initialize lazy evaluation to optimize the query graph before execution
        lf = state.get_table("countries").lazy()

        # 1. Ensure essential columns exist to prevent runtime crashes for incomplete save states
        required_cols = {
            "gdp": 0.0, "human_dev": 0.5, "personal_income_tax_rate": 0.2, 
            "tourism_income": 0.0, "imf_revenue": 0.0, "trade_income": 0.0, "trade_expense": 0.0,
            "budget_edu_ratio": 0.05, "budget_health_ratio": 0.05, "budget_env_ratio": 0.02, 
            "budget_infra_ratio": 0.05, "budget_telecom_ratio": 0.02, "budget_gov_ratio": 0.05,
            "budget_propaganda_ratio": 0.01, "budget_tourism_promo_ratio": 0.01,
            "security_upkeep": 0.0, "diplomacy_upkeep": 0.0, "research_expense": 0.0,
            "corruption_index": 0.1, "military_count": 0, "money_reserves": 0.0
        }

        existing_cols = lf.collect_schema().names()
        for col, default_val in required_cols.items():
            if col not in existing_cols:
                lf = lf.with_columns(pl.lit(default_val).alias(col))

        # 2. Revenue Calculations
        # Formula: (GDP * HumanDev * IncomeTaxRate) / Constant
        lf = lf.with_columns(
            (
                (pl.col("gdp") * pl.col("human_dev") * pl.col("personal_income_tax_rate")) 
                / self.PERSONAL_INCOME_TAX_CONSTANT
            ).alias("revenue_tax")
        )

        lf = lf.with_columns(
            (
                pl.col("revenue_tax") + 
                pl.col("trade_income") + 
                pl.col("tourism_income") + 
                pl.col("imf_revenue")
            ).alias("total_annual_revenue")
        )

        # 3. Expense Calculations
        # Ratio-based expenses are calculated as a percentage of GDP for stability, 
        # as relying on tax revenue can cause death spirals if taxes are lowered.
        lf = lf.with_columns(
            (
                pl.col("gdp") * (
                    pl.col("budget_edu_ratio") +
                    pl.col("budget_health_ratio") +
                    pl.col("budget_env_ratio") +
                    pl.col("budget_infra_ratio") +
                    pl.col("budget_telecom_ratio") +
                    pl.col("budget_gov_ratio") +
                    pl.col("budget_propaganda_ratio") +
                    pl.col("budget_tourism_promo_ratio")
                )
            ).alias("expense_social_and_infra")
        )

        # Calculate corruption loss based on government spending size
        lf = lf.with_columns(
            (pl.col("gdp") * pl.col("budget_gov_ratio") * pl.col("corruption_index")).alias("expense_corruption")
        )

        # Calculate military upkeep
        # FIXME: MVP implementation. Replace with actual unit aggregation from a separate 'units' table 
        # when the ECS supports entity-component relationships for military divisions.
        # Assuming a flat base cost per military_count for now.
        BASE_UNIT_COST = 500_000.0
        lf = lf.with_columns(
            (pl.col("military_count") * BASE_UNIT_COST * pl.col("human_dev")).alias("expense_military_upkeep")
        )

        # Calculate Debt Interest
        lf = lf.with_columns(
            pl.when(pl.col("money_reserves") < 0)
            .then(pl.col("money_reserves").abs() * self.DEBT_INTEREST_RATE)
            .otherwise(0.0)
            .alias("expense_debt_interest")
        )

        # Aggregate Total Expenses
        lf = lf.with_columns(
            (
                pl.col("expense_social_and_infra") +
                pl.col("expense_corruption") +
                pl.col("expense_military_upkeep") +
                pl.col("expense_debt_interest") +
                pl.col("security_upkeep") +
                pl.col("diplomacy_upkeep") +
                pl.col("research_expense") +
                pl.col("trade_expense")
            ).alias("total_annual_expense")
        )

        # 4. Tax Fairness Factor (For the Politics System to read)
        # Mechanic: People expect social spending to roughly match (2 * tax_rate - 0.2).
        # We expose this metric so politics_system.py can adjust stability/approval.
        lf = lf.with_columns(
            (
                (pl.col("budget_edu_ratio") + pl.col("budget_env_ratio") + 
                 pl.col("budget_health_ratio") + pl.col("budget_telecom_ratio") + 
                 pl.col("budget_infra_ratio")) / 5.0
            ).alias("_avg_social_spending")
        )

        lf = lf.with_columns(
            pl.max_horizontal(0.0, (2.0 * pl.col("personal_income_tax_rate")) - 0.2).alias("_expected_spending")
        )

        lf = lf.with_columns(
            pl.when(pl.col("_expected_spending") == 0.0)
            .then(1.0)
            .otherwise(
                pl.min_horizontal(1.0, pl.col("_avg_social_spending") / pl.col("_expected_spending"))
            ).alias("tax_fairness_factor")
        )

        # 5. Apply the delta to Monetary Supply (Money Reserves) based on time passed
        lf = lf.with_columns(
            (
                pl.col("money_reserves") + 
                ((pl.col("total_annual_revenue") - pl.col("total_annual_expense")) * fraction)
            ).alias("money_reserves")
        )

        # Clean up temporary calculation columns to keep the DataFrame lightweight
        lf = lf.drop(["_avg_social_spending", "_expected_spending", "revenue_tax", 
                      "expense_social_and_infra", "expense_corruption", "expense_military_upkeep", 
                      "expense_debt_interest"])

        # Execute the optimized query graph and update the state
        state.update_table("countries", lf.collect())