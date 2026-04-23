import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionUpdateBudget
from src.shared.events import EventRealSecond

class BudgetSystem(ISystem):
    """
    Handles national budget calculations including revenues, dynamic sector expenses, 
    debt interest, and tax fairness.
    
    This system treats tourism income as a specific 20% levy on foreign currency 
    inflows (exports of tourism services), providing additional revenue beyond 
    standard internal taxation.
    """

    # Constants for revenue and interest
    PERSONAL_INCOME_TAX_CONSTANT = 3.0 
    DEBT_INTEREST_RATE = 0.05
    # The percentage of foreign tourism spending that goes directly to the state budget
    TOURISM_FOREIGN_LEVY_RATE = 0.20 
    
    # Base budget multiplier for social/infra demand
    K_BUDGET = 0.15
    
    # Sector expense ratios (multipliers for total demand)
    M_SECTOR = {
        "budget_health_ratio": 0.25,
        "budget_edu_ratio": 0.23,
        "budget_social_ratio": 0.15,
        "budget_gov_ratio": 0.14,
        "budget_env_ratio": 0.10,
        "budget_research_ratio": 0.09,
        "budget_infra_ratio": 0.07,
        "budget_telecom_ratio": 0.04,
        "budget_imf_ratio": 0.04,
        "budget_propaganda_ratio": 0.03,
        "budget_tourism_promo_ratio": 0.01
    }

    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.budget"

    @property
    def dependencies(self) -> list[str]:
        # Depends on Trade to ensure 'trade_network' (exports) is calculated first
        return ["base.time", "base.economy", "base.trade"]

    def update(self, state: GameState, delta_time: float) -> None:
        # 1. Handle Incoming Actions (e.g., player changing budget sliders)
        for action in state.current_actions:
            if isinstance(action, ActionUpdateBudget):
                self._handle_update_budget(state, action)

        # 2. Process Periodic Simulation via Real Second Heartbeat
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            
            # Convert game time passed into a fraction of a year for annual rates
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_budget(state, fraction_of_year)

    def _calculate_tourism_revenue(self, state: GameState) -> pl.LazyFrame:
        """
        Calculates revenue from foreign tourists based on tourism service exports.
        Logic: 20% of all tourism services 'sold' to the world (foreign currency).
        """
        if "trade_network" not in state.tables:
            return pl.DataFrame(schema={"id": pl.Utf8, "tourism_income": pl.Float64}).lazy()

        # Isolate international tourism receipts from the trade network
        return (
            state.get_table("trade_network")
            .lazy()
            .filter(
                (pl.col("game_resource_id") == "tourism_services") & 
                (pl.col("exporter_id") != "WORLD")
            )
            .group_by("exporter_id")
            .agg(
                (pl.col("trade_value_usd").sum() * self.TOURISM_FOREIGN_LEVY_RATE)
                .alias("tourism_income")
            )
            .rename({"exporter_id": "id"})
        )

    def _process_budget(self, state: GameState, fraction: float) -> None:
        if "countries" not in state.tables:
            return

        # Prepare Total Demand per country from resource ledger
        if "resource_ledger" in state.tables:
            ledger_lf = state.get_table("resource_ledger").lazy()
            demand_lf = ledger_lf.group_by("country_id").agg(
                pl.col("consumption_usd").sum().alias("total_demand")
            )
        else:
            demand_lf = pl.DataFrame(schema={"country_id": pl.Utf8, "total_demand": pl.Float64}).lazy()

        # Get Dynamic Tourism Revenue
        tourism_rev_lf = self._calculate_tourism_revenue(state)

        # Start building the main processing LazyFrame
        lf = state.get_table("countries").lazy()
        lf = lf.drop(["total_demand", "tourism_income"], strict=False) # Clean up to avoid join collisions
        
        # Joins
        lf = lf.join(demand_lf, left_on="id", right_on="country_id", how="left").with_columns(
            pl.col("total_demand").fill_null(0.0)
        )
        lf = lf.join(tourism_rev_lf, on="id", how="left").with_columns(
            pl.col("tourism_income").fill_null(0.0)
        )

        # Ensure required columns for calculations exist with defaults
        required_cols = {
            "gdp": 0.0, "human_dev": 0.5, "personal_income_tax_rate": 0.2, 
            "budget_imf_ratio": 0.0, "trade_income": 0.0, "trade_expense": 0.0,
            "budget_edu_ratio": 0.5, "budget_health_ratio": 0.5, "budget_social_ratio": 0.5, "budget_env_ratio": 0.5, 
            "budget_infra_ratio": 0.5, "budget_telecom_ratio": 0.5, "budget_gov_ratio": 0.5,
            "budget_propaganda_ratio": 0.5, "budget_tourism_promo_ratio": 0.5,
            "budget_research_ratio": 0.5, "budget_imf_ratio": 0.0,
            "security_upkeep": 0.0, "diplomacy_upkeep": 0.0,
            "corruption_index": 0.1, "military_count": 0, "money_reserves": 0.0
        }

        existing_cols = lf.collect_schema().names()
        for col, default_val in required_cols.items():
            if col not in existing_cols:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found. Defaulting to {default_val}.")
                    self._missing_columns.add(col)
                lf = lf.with_columns(pl.lit(default_val).alias(col))

        # --- REVENUE CALCULATION ---
        
        # 1. Personal Income Tax
        lf = lf.with_columns(
            ((pl.col("gdp") * pl.col("human_dev") * pl.col("personal_income_tax_rate")) 
             / self.PERSONAL_INCOME_TAX_CONSTANT).alias("revenue_tax")
        )

        # 2. Total Revenue (includes our dynamic tourism_income)
        lf = lf.with_columns(
            (
                pl.col("revenue_tax") + 
                pl.col("trade_income") + 
                pl.col("tourism_income") + 
                pl.col("budget_imf_ratio")
            ).alias("total_annual_revenue")
        )

        # --- EXPENSE CALCULATION ---

        # 1. Social and Infrastructure Sectors
        expense_components = [
            (pl.col("total_demand") * self.K_BUDGET * multiplier * pl.col(col_name))
            for col_name, multiplier in self.M_SECTOR.items()
        ]
        lf = lf.with_columns(pl.sum_horizontal(expense_components).alias("expense_social_and_infra"))

        # 2. Governance / Corruption loss
        lf = lf.with_columns((pl.col("gdp") * pl.col("budget_gov_ratio") * pl.col("corruption_index")).alias("expense_corruption"))

        # 3. Military Upkeep
        BASE_UNIT_COST = 500_000.0
        lf = lf.with_columns((pl.col("military_count") * BASE_UNIT_COST * pl.col("human_dev")).alias("expense_military_upkeep"))

        # 4. Debt Interest
        lf = lf.with_columns(
            pl.when(pl.col("money_reserves") < 0)
            .then(pl.col("money_reserves").abs() * self.DEBT_INTEREST_RATE)
            .otherwise(0.0)
            .alias("expense_debt_interest")
        )

        # 5. Total Annual Expense
        lf = lf.with_columns(
            (
                pl.col("expense_social_and_infra") +
                pl.col("expense_corruption") +
                pl.col("expense_military_upkeep") +
                pl.col("expense_debt_interest") +
                pl.col("security_upkeep") +
                pl.col("diplomacy_upkeep") +
                pl.col("trade_expense")
            ).alias("total_annual_expense")
        )

        # --- TAX FAIRNESS FACTOR ---
        
        lf = lf.with_columns(
            ((pl.col("budget_edu_ratio") + pl.col("budget_env_ratio") + 
              pl.col("budget_health_ratio") + pl.col("budget_telecom_ratio") + 
              pl.col("budget_infra_ratio") + pl.col("budget_social_ratio")) / 6.0).alias("_avg_social_spending")
        )

        lf = lf.with_columns(pl.max_horizontal(0.0, (2.0 * pl.col("personal_income_tax_rate")) - 0.2).alias("_expected_spending"))

        lf = lf.with_columns(
            pl.when(pl.col("_expected_spending") == 0.0).then(1.0)
            .otherwise(pl.min_horizontal(1.0, pl.col("_avg_social_spending") / pl.col("_expected_spending")))
            .alias("tax_fairness_factor")
        )

        # --- FINAL STATE UPDATE ---
        
        lf = lf.with_columns(
            (pl.col("money_reserves") + ((pl.col("total_annual_revenue") - pl.col("total_annual_expense")) * fraction))
            .alias("money_reserves")
        )

        # Cleanup internal calculation columns
        lf = lf.drop(["_avg_social_spending", "_expected_spending"])

        state.update_table("countries", lf.collect())

    def _handle_update_budget(self, state: GameState, action: ActionUpdateBudget) -> None:
        if "countries" not in state.tables:
            return
        
        df = state.get_table("countries")
        updates = []
        for col, val in action.allocations.items():
            if col in self.M_SECTOR or col == "personal_income_tax_rate":
                clamped_val = max(0.0, min(1.0, float(val)))
                updates.append(
                    pl.when(pl.col("id") == action.country_tag)
                    .then(pl.lit(clamped_val))
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        
        if updates:
            state.update_table("countries", df.with_columns(updates))