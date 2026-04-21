import polars as pl
from dataclasses import dataclass
from typing import Dict, List

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

@dataclass
class FastCountryState:
    """Lightweight Python object to bypass Polars overhead inside the tight O(N*M*K) matching loop."""
    id: str
    rank: int
    pp: float
    rev: float = 0.0
    imp_cost: float = 0.0
    eco_act: float = 0.0
    
    needs: dict = None
    avails: dict = None

class TradeSystem(ISystem):
    """
    Simulates a commodity-oriented global trade cycle.
    Uses Polars for heavy math (Phases 1, 2, 5) and native Python for sequential trading (Phases 3, 4).
    """

    # Priority Matrix: Lower number = Higher priority. 
    # Survival -> Energy -> Materials -> Capital Goods -> Consumer -> Services & Luxury
    TRADE_PRIORITY_MATRIX = {
        # Tier 1: Core Survival & Basic Food
        "cereals": 10,
        "vegetables_and_fruits": 11,
        "meat_and_fish": 12,
        "dairy": 13,
        "pharmaceuticals": 14,
        "health_services": 15,
        
        # Tier 2: Critical Infrastructure & Energy
        "electricity": 20,
        "fossil_fuels": 21,
        "transport_services": 22,
        
        # Tier 3: Heavy Industry & Raw Materials
        "minerals": 30,
        "iron_and_steel": 31,
        "chemicals": 32,
        "wood_and_paper": 33,
        "plastics_and_rubber": 34,
        
        # Tier 4: Manufacturing & Capital Goods
        "machinery_and_instruments": 40,
        "industrial_services": 41,
        "construction_services": 42,
        "construction_materials": 43,
        "vehicles": 44,
        
        # Tier 5: Consumer Goods
        "commodities": 50,
        "fabrics_and_leather": 51,
        "appliances": 52,
        "business_services": 53,
        "it_and_telecom_services": 54,
        
        # Tier 6: Leisure, Luxury & Vices
        "tobacco": 60,
        "drugs_and_raw_plants": 61,
        "recreational_services": 62,
        "tourism_services": 63,
        "luxury_commodities": 64,
        "precious_stones": 65,
        "non_ferrous_metals": 66,
        "arms_and_ammunition": 67,
        "education_services": 68,
        "government_services": 69,
        "financial_services": 70,
        "other_food_and_beverages": 71
    }
    
    @property
    def id(self) -> str:
        return "base.trade"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
                
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._simulate_market_cycle(state, fraction_of_year)

    def _simulate_market_cycle(self, state: GameState, fraction: float):
        if "countries" not in state.tables or "domestic_production" not in state.tables:
            return

        countries_df = state.get_table("countries")
        prod_df = state.get_table("domestic_production")
        
        # Fetch Demand from Ledger
        if "resource_ledger" in state.tables:
            demand_df = state.get_table("resource_ledger").select(
                pl.col("country_id"), 
                pl.col("game_resource_id"), 
                pl.col("consumption_usd").alias("demand")
            )
            market_df = prod_df.join(demand_df, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)
        else:
            market_df = prod_df.with_columns((pl.col("domestic_production") * 0.9).alias("demand"))

        # Stub Policies (To be replaced by joining with 'resource_policies' table later)
        market_df = market_df.with_columns([
            pl.lit(False).alias("is_gov_controlled"),
            pl.lit(True).alias("is_legal"),
            pl.lit(0.05).alias("tax_rate")
        ])

        # Safely ensure required macro metrics exist
        req_cols = {"economic_health": 1.0, "gdp": 1_000_000.0, "population": 1.0}
        for col, default_val in req_cols.items():
            if col not in countries_df.columns:
                countries_df = countries_df.with_columns(pl.lit(default_val).alias(col))

        # Calculate Rank based on GDP per capita
        countries_df = countries_df.with_columns(
            (pl.col("gdp") / pl.when(pl.col("population") > 0).then(pl.col("population")).otherwise(1.0)).alias("gdp_pc")
        ).with_columns(
            pl.col("gdp_pc").rank(method="min", descending=True).cast(pl.Int32).alias("eco_rank")
        )

        # ---------------------------------------------------------
        # PHASE 1: Market Preparation
        # ---------------------------------------------------------
        countries_df = countries_df.with_columns(
            (pl.col("gdp") * 0.5).alias("purchasing_power")
        )

        market_df = market_df.with_columns([
            pl.when(pl.col("domestic_production") > pl.col("demand"))
              .then(pl.col("domestic_production") - pl.col("demand"))
              .otherwise(0.0).alias("export_desired"),
            pl.when(pl.col("demand") > pl.col("domestic_production"))
              .then(pl.col("demand") - pl.col("domestic_production"))
              .otherwise(0.0).alias("import_desired")
        ])

        # ---------------------------------------------------------
        # PHASE 2: Overproduction Penalty
        # ---------------------------------------------------------
        world_totals = market_df.group_by("game_resource_id").agg(
            pl.col("domestic_production").sum().alias("world_prod"),
            pl.col("demand").sum().alias("world_dem")
        )
        
        market_df = market_df.join(world_totals, on="game_resource_id", how="left")
        market_df = market_df.join(countries_df.select(["id", "economic_health"]), left_on="country_id", right_on="id", how="left")
        
        market_df = market_df.with_columns(
            pl.when((pl.col("world_prod") > pl.col("world_dem")) & (pl.col("domestic_production") > pl.col("demand")))
            .then((pl.col("domestic_production") / (pl.col("world_prod") + 1.0)) * pl.col("economic_health"))
            .otherwise(0.0).alias("base_share")
        )
        
        share_denominators = market_df.group_by("game_resource_id").agg(
            pl.col("base_share").sum().alias("share_denominator")
        )
        market_df = market_df.join(share_denominators, on="game_resource_id", how="left")
        
        total_countries = countries_df.height
        market_df = market_df.with_columns(
            pl.when((pl.col("world_prod") > pl.col("world_dem")) & (pl.col("share_denominator") > 0) & (pl.col("domestic_production") > pl.col("demand")))
            .then(
                pl.min_horizontal(
                    ((1.0 - (pl.col("base_share") / pl.col("share_denominator"))) / max(1, total_countries - 1)) * (pl.col("world_prod") - pl.col("world_dem")),
                    pl.col("domestic_production") - pl.col("demand")
                )
            ).otherwise(0.0).alias("absolute_loss")
        )
        
        market_df = market_df.with_columns(
            (pl.col("domestic_production") - pl.col("absolute_loss")).alias("domestic_production")
        )

        # ---------------------------------------------------------
        # PHASE 4: Global Trade (Flat Commodity-First Market)
        # ---------------------------------------------------------
        
        c_dicts = countries_df.select(["id", "eco_rank", "purchasing_power"]).to_dicts()
        m_dicts = market_df.select(["country_id", "game_resource_id", "import_desired", "export_desired", "is_gov_controlled", "is_legal", "tax_rate"]).to_dicts()

        # Build highly optimized in-memory dicts
        fast_states: Dict[str, FastCountryState] = {}
        for c in c_dicts:
            fast_states[c["id"]] = FastCountryState(
                id=c["id"], rank=c["eco_rank"], pp=c["purchasing_power"], needs={}, avails={}
            )

        unique_resources = set()
        res_policies = {} 
        
        for m in m_dicts:
            cid = m["country_id"]
            rid = m["game_resource_id"]
            unique_resources.add(rid)
            
            fast_states[cid].needs[rid] = m["import_desired"]
            fast_states[cid].avails[rid] = m["export_desired"]
            
            res_policies[(cid, rid)] = {
                "gov": m["is_gov_controlled"],
                "leg": m["is_legal"],
                "tax": m["tax_rate"] + 0.02 # Stub: Global Tax Mod is 2%
            }

        # Sort the resources using the Priority Matrix. 
        # Unknown resources default to a weight of 999 (last place).
        ordered_resources = sorted(list(unique_resources), key=lambda r: self.TRADE_PRIORITY_MATRIX.get(r, 999))
        
        sorted_countries = sorted(fast_states.values(), key=lambda x: x.rank)
        
        actual_imports = {(c.id, r): 0.0 for c in sorted_countries for r in unique_resources}
        actual_exports = {(c.id, r): 0.0 for c in sorted_countries for r in unique_resources}
        transactions = []

        # COMMODITY-ORIENTED LOOP
        # Resource traded completely before moving to the next
        for r in ordered_resources:
            
            # Fast-filter: Get only the countries that actually want this specific resource
            active_buyers = [c for c in sorted_countries if c.needs.get(r, 0.0) > 0.0]
            active_sellers = [c for c in sorted_countries if c.avails.get(r, 0.0) > 0.0]
            
            if not active_buyers or not active_sellers:
                continue

            for imp in active_buyers:
                pol = res_policies.get((imp.id, r))
                if not pol: continue
                
                needed = imp.needs[r]
                
                # Check macro PP constraints
                if not pol["gov"] and pol["leg"]:
                    needed = min(needed, imp.pp)
                    
                if needed <= 0:
                    continue

                for exp in active_sellers:
                    if imp.id == exp.id:
                        continue
                        
                    avail = exp.avails[r]
                    if avail <= 0:
                        continue
                        
                    real_import = min(needed, avail)
                    total_tax = pol["tax"]
                    
                    # Log Transcation
                    actual_imports[(imp.id, r)] += (real_import * (1.0 - total_tax))
                    actual_exports[(exp.id, r)] += real_import
                    transactions.append({
                        "exporter_id": exp.id,
                        "importer_id": imp.id,
                        "game_resource_id": r,
                        "trade_value_usd": real_import
                    })
                    
                    # State tracking
                    exp.avails[r] -= real_import 
                    needed -= real_import
                    
                    # Apply Budgets
                    if pol["gov"]:
                        imp.imp_cost += real_import * 1.5
                        exp.rev += real_import * 1.5
                    elif pol["leg"]:
                        imp.pp -= real_import
                        imp.rev += real_import * total_tax
                        imp.eco_act -= real_import
                        
                        exp.pp += real_import
                        exp.rev += real_import * total_tax
                        exp.eco_act += real_import * (1.0 - total_tax)
                    else:
                        # Black market bypass
                        exp.eco_act += real_import
                        
                    if needed <= 0 or (imp.pp <= 0 and not pol["gov"]):
                        break # Buyer fulfilled, move to next buyer

        # Sync Python dicts back to DataFrames
        act_imp_df = pl.DataFrame([{"country_id": k[0], "game_resource_id": k[1], "import_actual": v} for k, v in actual_imports.items()])
        act_exp_df = pl.DataFrame([{"country_id": k[0], "game_resource_id": k[1], "export_actual": v} for k, v in actual_exports.items()])
        
        market_df = market_df.join(act_imp_df, on=["country_id", "game_resource_id"], how="left")
        market_df = market_df.join(act_exp_df, on=["country_id", "game_resource_id"], how="left")

        # ---------------------------------------------------------
        # PHASE 5: Inefficiency Penalty
        # ---------------------------------------------------------
        market_df = market_df.with_columns(
            (pl.col("domestic_production") - pl.col("demand") - pl.col("export_actual") + pl.col("import_actual")).alias("unsold_balance")
        )
        
        market_df = market_df.with_columns(
            pl.when(pl.col("unsold_balance") > 0)
            .then(pl.col("domestic_production") - (pl.col("unsold_balance") * 0.8))
            .otherwise(pl.col("domestic_production")).alias("domestic_production")
        )

        # ---------------------------------------------------------
        # STATE UPDATE
        # ---------------------------------------------------------
        if not transactions:
            trade_net_df = pl.DataFrame(schema={"exporter_id": pl.Utf8, "importer_id": pl.Utf8, "game_resource_id": pl.Utf8, "trade_value_usd": pl.Float64})
        else:
            trade_net_df = pl.DataFrame(transactions)
        state.update_table("trade_network", trade_net_df)

        updated_prod = market_df.select(["country_id", "game_resource_id", "domestic_production"])
        state.update_table("domestic_production", updated_prod)

        budget_updates = pl.DataFrame([
            {"id": c.id, "trade_income": c.rev * fraction, "trade_expense": c.imp_cost * fraction}
            for c in fast_states.values()
        ])
        
        countries_df = countries_df.join(budget_updates, on="id", how="left").fill_null(0.0)
        countries_df = countries_df.with_columns(
            (pl.col("money_reserves") + pl.col("trade_income") - pl.col("trade_expense")).alias("money_reserves")
        )
        
        cols_to_drop = ["purchasing_power", "gdp_pc", "eco_rank", "trade_income", "trade_expense"]
        state.update_table("countries", countries_df.drop([c for c in cols_to_drop if c in countries_df.columns]))