import polars as pl
from typing import List

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionBuildUnit, ActionUpdateBudget, GameAction

# =========================================================================
# 🧠 AI SCORERS (Vector utility scoring functions)
# High-performance Polars vectorized scoring. Avoid Python for-loops to ensure scalability.
# Each scorer returns a value between 0.0 and 1.0.
# =========================================================================

def score_military_buildup(lf: pl.LazyFrame) -> pl.LazyFrame:
    """ 
    Evaluates a country's utility score for building new military units.
    MVP Logic: Boosts utility if cash reserves exceed 500 million.
    """
    return lf.with_columns(
        pl.when(pl.col("money_reserves") > 500_000_000)
        .then((pl.col("money_reserves") / 2_000_000_000).clip(0.0, 1.0))
        .otherwise(0.0)
        .alias("score_build_military")
    )

def score_economic_panic(lf: pl.LazyFrame) -> pl.LazyFrame:
    """ 
    Evaluates a country's utility score for raising taxes due to a budget deficit.
    MVP Logic: Maximizes panic (1.0) if financial reserves fall below zero.
    """
    return lf.with_columns(
        pl.when(pl.col("money_reserves") < 0)
        .then(1.0)
        .otherwise(0.0)
        .alias("score_raise_taxes")
    )

# =========================================================================
# ⚙️ AI SYSTEM (Framework Orchestrator)
# =========================================================================

class AISystem(ISystem):
    """
    Declarative Utility AI framework powered by Polars.
    """
    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.ai"

    @property
    def dependencies(self) -> list[str]:
        # The AI system must run immediately after the time system, allowing it 
        # to queue actions before they are processed by the Military and Budget systems.
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Throttle AI execution to once per month (every 30 ticks) to optimize performance
        # and prevent daily computational overhead.
        tick = state.globals.get("tick", 0)
        if tick % 30 != 0:
            return

        if "countries" not in state.tables:
            return

        # 1. DATA PREPARATION (Sanity Check)
        countries_lf = state.get_table("countries").lazy()
        
        # Ensure fallback defaults exist for required columns if they are missing from the schema
        if "personal_income_tax_rate" not in state.get_table("countries").columns:
            countries_lf = countries_lf.with_columns(pl.lit(0.20).alias("personal_income_tax_rate"))
        if "money_reserves" not in state.get_table("countries").columns:
            countries_lf = countries_lf.with_columns(pl.lit(0.0).alias("money_reserves"))

        # 2. VECTOR UTILITY EVALUATION (AI Pipeline)
        # Process data through the composition of utility scoring functions
        scored_lf = (
            countries_lf
            .pipe(score_military_buildup)
            .pipe(score_economic_panic)
        )

        # Extract only the columns required for final decision-making to optimize memory footprint
        decision_df = scored_lf.select([
            "id", 
            "personal_income_tax_rate", 
            "score_build_military", 
            "score_raise_taxes"
        ]).collect()

        # 3. ACTION RESOLUTION (Decision Making)
        # Since heavy calculations are offloaded to Polars vectorization, iterating 
        # over the collected rows to generate Python GameAction objects is highly efficient (<1ms).
        generated_actions: List[GameAction] = []

        for row in decision_df.iter_rows(named=True):
            country_id = row["id"]
            
            # Select the action with the highest utility score
            scores = {
                "build_military": row["score_build_military"],
                "raise_taxes": row["score_raise_taxes"]
            }
            
            best_action = max(scores, key=scores.get)
            best_score = scores[best_action]

            # Skip decision-making if the highest action utility score is below the activation threshold
            if best_score < 0.5:
                continue

            # Map the selected intent to a game action command
            if best_action == "build_military":
                generated_actions.append(ActionBuildUnit(
                    player_id="ai_system",
                    country_tag=country_id,
                    unit_type="army",
                    count=1
                ))
            
            elif best_action == "raise_taxes":
                current_tax = row["personal_income_tax_rate"]
                # Increase tax rate incrementally, capping at 50%
                new_tax = min(0.50, current_tax + 0.05)
                
                generated_actions.append(ActionUpdateBudget(
                    player_id="ai_system",
                    country_tag=country_id,
                    allocations={"personal_income_tax_rate": new_tax}
                ))

        # 4. ACTION INJECTION
        # Inject the generated actions into the current tick's action queue.
        # Subsequent systems (e.g., Economy, Military) will process them seamlessly alongside player actions.
        state.current_actions.extend(generated_actions)