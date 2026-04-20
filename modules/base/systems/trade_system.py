import polars as pl
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

# --- Composition Objects ---
# We extract trade entities into dedicated dataclasses to manage transient state.

@dataclass
class ResourceProfile:
    """Stub definition for resource legal/gov properties."""
    is_gov_controlled: bool = False
    is_legal: bool = True
    tax_rate: float = 0.05

@dataclass
class CountryTradeState:
    """Holds the transient economic state of a country during a trade cycle."""
    country_id: str
    gdp_base: float
    eco_health: float
    eco_rank: int
    purchasing_power: float = 0.0
    eco_activity: float = 0.0
    
    budget_imports: float = 0.0
    budget_revenue: float = 0.0
    
    # Resource metrics mapped by resource_id
    production: Dict[str, float] = field(default_factory=dict)
    demand: Dict[str, float] = field(default_factory=dict)
    import_desired: Dict[str, float] = field(default_factory=dict)
    export_desired: Dict[str, float] = field(default_factory=dict)
    import_actual: Dict[str, float] = field(default_factory=dict)
    export_actual: Dict[str, float] = field(default_factory=dict)


class GlobalMarketAlgorithm:
    """
    Executes the 5-phase macroeconomic global market cycle.
    Separated from the main System class to ensure Single Responsibility.
    """
    
    def __init__(self, states: Dict[str, CountryTradeState], resources: List[str], res_profiles: Dict[str, ResourceProfile]):
        self.states = states
        self.resources = resources
        self.profiles = res_profiles
        self.global_tax_mod = 0.02 # Stub: Global tax modifier
        self.transactions: List[Dict] = []
        
        # Stub: Diplomacy and treaties
        self.treaty_groups: List[List[str]] = [] # e.g., [["FRA", "DEU"], ["USA", "CAN"]]
        self.hostile_pairs: set[tuple[str, str]] = set()

    def execute_cycle(self):
        self._phase_1_initialization()
        self._phase_2_overproduction_penalty()
        self._phase_3_regional_trade()
        self._phase_4_global_trade()
        self._phase_5_inefficiency_penalty()

    def _phase_1_initialization(self):
        """Phase 1: Market Preparation & Purchasing Power Initialization."""
        for state in self.states.values():
            state.purchasing_power = state.gdp_base * 0.5
            state.eco_activity = 0.0
            
            for r in self.resources:
                # Reset accumulators
                state.import_actual[r] = 0.0
                state.export_actual[r] = 0.0
                
                # Determine market desires
                prod = state.production.get(r, 0.0)
                dem = state.demand.get(r, 0.0)
                if prod > dem:
                    state.export_desired[r] = prod - dem
                    state.import_desired[r] = 0.0
                else:
                    state.export_desired[r] = 0.0
                    state.import_desired[r] = dem - prod

    def _phase_2_overproduction_penalty(self):
        """Phase 2: Global Surplus Correction."""
        total_countries = len(self.states)
        if total_countries <= 1:
            return

        for r in self.resources:
            world_prod = sum(c.production.get(r, 0.0) for c in self.states.values())
            world_dem = sum(c.demand.get(r, 0.0) for c in self.states.values())
            
            if world_prod <= world_dem:
                continue
                
            global_surplus = world_prod - world_dem
            share_denominator = 0.0
            
            # Calculate Share Denominator
            for c in self.states.values():
                prod = c.production.get(r, 0.0)
                dem = c.demand.get(r, 0.0)
                if prod > dem:
                    share_denominator += (prod / (world_prod + 1.0)) * c.eco_health
                    
            # Apply absolute loss
            if share_denominator <= 0:
                continue
                
            for c in self.states.values():
                prod = c.production.get(r, 0.0)
                dem = c.demand.get(r, 0.0)
                if prod > dem:
                    base_share = (prod / (world_prod + 1.0)) * c.eco_health
                    loss_pct = (1.0 - (base_share / share_denominator)) / (total_countries - 1)
                    absolute_loss = min(max(0.0, loss_pct * global_surplus), prod - dem)
                    c.production[r] -= absolute_loss

    def _phase_3_regional_trade(self):
        """Phase 3: Common Market Treaties."""
        for group in self.treaty_groups:
            members = [self.states[cid] for cid in group if cid in self.states]
            self._execute_matching_loop(members, members)

    def _phase_4_global_trade(self):
        """Phase 4: Global Trade."""
        all_countries = list(self.states.values())
        self._execute_matching_loop(all_countries, all_countries)

    def _phase_5_inefficiency_penalty(self):
        """Phase 5: Unused Goods Decay."""
        for c in self.states.values():
            for r in self.resources:
                prod = c.production.get(r, 0.0)
                dem = c.demand.get(r, 0.0)
                exp = c.export_actual.get(r, 0.0)
                imp = c.import_actual.get(r, 0.0)
                
                balance = prod - dem - exp + imp
                if balance > 0:
                    # Remove 80% of unused capacity
                    c.production[r] -= (balance * 0.8)

    def _execute_matching_loop(self, importers_pool: List[CountryTradeState], exporters_pool: List[CountryTradeState]):
        """
        Sub-Routine: Trade Matching Algorithm.
        Pairs Importers with Exporters. Order matters heavily based on EconomicRank.
        """
        # Sort by economic rank (1 is highest/richest)
        importers = sorted(importers_pool, key=lambda x: x.eco_rank)
        exporters = sorted(exporters_pool, key=lambda x: x.eco_rank)
        
        for imp in importers:
            if imp.purchasing_power <= 0:
                continue
                
            for r in self.resources:
                needed = imp.import_desired.get(r, 0.0) - imp.import_actual.get(r, 0.0)
                if needed <= 0:
                    continue
                    
                profile = self.profiles.get(r, ResourceProfile())
                total_tax = profile.tax_rate + self.global_tax_mod
                
                # Check purchasing power limits for private/legal goods
                if not profile.is_gov_controlled and profile.is_legal:
                    needed = min(needed, imp.purchasing_power)
                    
                if needed <= 0:
                    continue

                for exp in exporters:
                    if imp.country_id == exp.country_id:
                        continue
                        
                    # Diplomacy check stub
                    if (imp.country_id, exp.country_id) in self.hostile_pairs or (exp.country_id, imp.country_id) in self.hostile_pairs:
                        continue
                        
                    available = exp.export_desired.get(r, 0.0) - exp.export_actual.get(r, 0.0)
                    real_import = min(needed, available)
                    
                    if real_import <= 0:
                        continue
                        
                    # Execute transaction
                    imp.import_actual[r] += (real_import * (1.0 - total_tax))
                    exp.export_actual[r] += real_import
                    
                    self.transactions.append({
                        "importer_id": imp.country_id,
                        "exporter_id": exp.country_id,
                        "game_resource_id": r,
                        "trade_value_usd": real_import
                    })
                    
                    # Monetary / Budget Application
                    if profile.is_gov_controlled:
                        imp.budget_imports += real_import * 1.5
                        exp.budget_revenue += real_import * 1.5
                    elif profile.is_legal:
                        imp.purchasing_power -= real_import
                        imp.budget_revenue += real_import * total_tax
                        imp.eco_activity -= real_import
                        
                        exp.purchasing_power += real_import # Adding to PP honors the Phase 1 export summation logic dynamically
                        exp.budget_revenue += real_import * total_tax
                        exp.eco_activity += real_import * (1.0 - total_tax)
                    else:
                        # Illegal goods bypass limits and generate no taxes
                        exp.eco_activity += real_import
                        
                    # Update loop conditions
                    needed -= real_import
                    if needed <= 0 or imp.purchasing_power <= 0:
                        break # Move to next resource


class TradeSystem(ISystem):
    """
    Simulates global trade of resources, calculates supply/demand economics, 
    executes bilateral trades, and manages dynamic trade networks.
    """
    
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
        """
        Prepares data, runs the GlobalMarketAlgorithm, and writes results back to the GameState.
        """
        if "countries" not in state.tables or "domestic_production" not in state.tables:
            return

        countries_df = state.get_table("countries")
        production_df = state.get_table("domestic_production")
        
        # We must deviate from standard Polars vectorized operations here. 
        # The trade matching algorithm requires sequential mutation of state (e.g., purchasing power limits) 
        # where the outcome of one row directly restricts the next. Vectorizing this in pure Polars 
        # is mathematically unfeasible, so we extract to native Python structures for the O(N^3) loop.
        
        trade_states: Dict[str, CountryTradeState] = {}
        all_resources: set[str] = set()
        
        # 1. Initialize states
        # Stub: Providing fallback logic for missing GDP or health metrics
        country_dicts = countries_df.to_dicts()
        for row in country_dicts:
            cid = row["id"]
            gdp = row.get("gdp", 1_000_000.0)
            pop = row.get("population", 1.0)
            eco_rank = 1 # Assigned later
            eco_health = row.get("economic_health", 1.0)
            
            trade_states[cid] = CountryTradeState(
                country_id=cid,
                gdp_base=gdp,
                eco_health=eco_health,
                eco_rank=eco_rank
            )
            
        # Assign basic eco_rank sorted by GDP per capita 
        ranked_countries = sorted(trade_states.values(), key=lambda x: x.gdp_base / max(1.0, pop), reverse=True)
        for rank, cs in enumerate(ranked_countries, start=1):
            cs.eco_rank = rank

        # 2. Extract Production and Demand
        # Stub: If 'resource_ledger' exists, we use it to find realistic 'Demand'.
        # Otherwise, demand defaults to 90% of production to prevent extreme zero-demand collapses.
        demand_map = {}
        if "resource_ledger" in state.tables:
            ledger = state.get_table("resource_ledger").to_dicts()
            for row in ledger:
                demand_map[(row["country_id"], row["game_resource_id"])] = row.get("consumption_usd", 0.0)

        for row in production_df.to_dicts():
            cid = row["country_id"]
            rid = row["game_resource_id"]
            prod_val = row["domestic_production"]
            
            if cid in trade_states:
                all_resources.add(rid)
                trade_states[cid].production[rid] = prod_val
                # Inject demand from map or use a default stub
                trade_states[cid].demand[rid] = demand_map.get((cid, rid), prod_val * 0.9)

        # 3. Execute the Algorithm
        res_profiles = {r: ResourceProfile() for r in all_resources} # Stubs for now
        algorithm = GlobalMarketAlgorithm(trade_states, list(all_resources), res_profiles)
        algorithm.execute_cycle()

        # 4. Write back the generated Trade Network
        if not algorithm.transactions:
            trade_net_df = pl.DataFrame(schema={"exporter_id": pl.Utf8, "importer_id": pl.Utf8, "game_resource_id": pl.Utf8, "trade_value_usd": pl.Float64})
        else:
            trade_net_df = pl.DataFrame(algorithm.transactions)
        
        state.update_table("trade_network", trade_net_df)

        # 5. Apply Financial Flow and Production Penalties
        self._apply_results_to_state(state, trade_states, fraction)

    def _apply_results_to_state(self, state: GameState, trade_states: Dict[str, CountryTradeState], fraction: float):
        """Translates algorithm mutations back to Polars DataFrames."""
        countries_df = state.get_table("countries")
        prod_df = state.get_table("domestic_production")
        
        # Build update lists
        budget_updates = []
        for c in trade_states.values():
            budget_updates.append({
                "id": c.country_id,
                "trade_income": c.budget_revenue * fraction,
                "trade_expense": c.budget_imports * fraction
            })
            
        update_df = pl.DataFrame(budget_updates)
        
        updated_countries = countries_df.join(update_df, on="id", how="left").fill_null(0.0)
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + pl.col("trade_income") - pl.col("trade_expense")).alias("money_reserves")
        )
        state.update_table("countries", updated_countries.drop(["trade_income", "trade_expense"]))

        # Re-build production table from penalized stats
        new_prod_rows = []
        for c in trade_states.values():
            for r, val in c.production.items():
                new_prod_rows.append({
                    "country_id": c.country_id,
                    "game_resource_id": r,
                    "domestic_production": max(0.0, val)
                })
                
        if new_prod_rows:
            new_prod_df = pl.DataFrame(new_prod_rows)
            # Retain other specific columns from domestic_production if they existed
            updated_prod = prod_df.select(["country_id", "game_resource_id"]).join(new_prod_df, on=["country_id", "game_resource_id"], how="inner")
            state.update_table("domestic_production", updated_prod)