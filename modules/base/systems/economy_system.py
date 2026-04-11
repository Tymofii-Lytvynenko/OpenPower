import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class EconomySystem(ISystem):
    """
    Handles internal macroeconomic simulation, including domestic production value 
    generation and wealth accumulation.
    """
    
    @property
    def id(self) -> str:
        return "base.economy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.trade"] # Run after trade to have final money state

    # Manufactured goods/services where Quality Index (1-100) scales the price.
    # Raw materials default to 1% quality and ignore the scaling.
    QUALITY_SENSITIVE_GOODS = [
        "appliances", "vehicles", "machinery_and_instruments", "arms_and_ammunition", 
        "pharmaceuticals", "luxury_commodities", "transport_services", "tourism_services",
        "construction_services", "financial_services", "it_and_telecom_services",
        "business_services", "recreational_services", "health_services", 
        "education_services", "government_services", "industrial_services"
    ]

    def update(self, state: GameState, delta_time: float) -> None:
        rebuild_ledger = False
        if "resource_ledger" not in state.tables and "domestic_production" in state.tables and "trade_network" in state.tables:
            rebuild_ledger = True

        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
                
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_economy(state, fraction_of_year)
            # Rebuild ledger periodically when simulation advances 
            if "domestic_production" in state.tables and "trade_network" in state.tables:
                rebuild_ledger = True
                
        if rebuild_ledger:
            self._build_resource_ledger(state)

    def _build_resource_ledger(self, state: GameState):
        """
        Builds a dynamically aggregated resource ledger linking Demographics, Production, and Trade.
        """
        prod_table = state.get_table("domestic_production")
        trade_table = state.get_table("trade_network")
        regions = state.get_table("regions")

        from src.shared.economy_meta import RESOURCE_MAPPING

        # 1. Prepare Tables
        # Baseline quality is approx 25
        prod_usd = prod_table.rename({"domestic_production": "production_usd"})
        if "quality_index" in prod_usd.columns:
            prod_usd = prod_usd.with_columns(pl.col("quality_index").fill_null(25.0))
        else:
            prod_usd = prod_usd.with_columns(pl.lit(25.0).alias("quality_index"))

        
        # 3. Trade (Already in USD Value)
        exports = trade_table.group_by(["exporter_id", "game_resource_id"]).agg(
            pl.col("trade_value_usd").sum().alias("export_usd")
        ).rename({"exporter_id": "country_id"})
        
        imports = trade_table.group_by(["importer_id", "game_resource_id"]).agg(
            pl.col("trade_value_usd").sum().alias("import_usd")
        ).rename({"importer_id": "country_id"})
        
        net_trade = exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)
        net_trade = net_trade.with_columns(
            (pl.col("export_usd") - pl.col("import_usd")).alias("trade_usd")
        )
        
        # 4. Master Ledger
        ledger = prod_usd.join(net_trade, on=["country_id", "game_resource_id"], how="full", coalesce=True)
        # Fill production/trade holes with 0
        ledger = ledger.with_columns(
            pl.col(["production_usd", "trade_usd"]).fill_null(0.0)
        )

        # In MONETARY MODE, production_usd is taken directly from the source table.
        # We don't multiply volume by price.



        # 5. Dynamic Consumption based on Population
        if "pop_14" in regions.columns:
            country_pop = regions.group_by("owner").agg(
                (pl.col("pop_14") + pl.col("pop_15_64") + pl.col("pop_65")).sum().alias("total_pop")
            ).rename({"owner": "country_id"})
        else:
            country_pop = regions.group_by("owner").agg(pl.count().alias("total_pop")).rename({"owner": "country_id"})
            
        ledger = ledger.join(country_pop, on="country_id", how="left").with_columns(pl.col("total_pop").fill_null(0.0))
        
        rates_data = [
            {"game_resource_id": "cereals", "per_capita": 160.0},
            {"game_resource_id": "vegetables_and_fruits", "per_capita": 200.0},
            {"game_resource_id": "meat_and_fish", "per_capita": 525.0},
            {"game_resource_id": "electricity", "per_capita": 400.0},
            {"game_resource_id": "fossil_fuels", "per_capita": 375.0},
            {"game_resource_id": "pharmaceuticals", "per_capita": 1250.0},
        ]
        consumption_rates = pl.DataFrame(rates_data, schema={"game_resource_id": pl.String, "per_capita": pl.Float64})
        
        ledger = ledger.join(consumption_rates, on="game_resource_id", how="left").with_columns(
            pl.col("per_capita").fill_null(50.0) # Default fallback USD demand
        )
        
        # Calculate real dynamic consumption (USD Demand)
        ledger = ledger.with_columns(
            (pl.col("total_pop") * pl.col("per_capita")).alias("consumption_usd")
        )

        
        # 6. Real Balances
        ledger = ledger.with_columns(
            (pl.col("production_usd") - pl.col("consumption_usd") - pl.col("trade_usd")).alias("balance_usd")
        )
        
        # Only drop columns that are actually present to avoid errors
        cols_to_drop = ["total_pop", "per_capita", "avg_price", "base_price", "quality_index"]
        ledger = ledger.drop([c for c in cols_to_drop if c in ledger.columns])
        
        cat_df = pl.DataFrame([
            {"game_resource_id": k, "category": v["category"], "unit_str": v["unit"]}
            for k, v in RESOURCE_MAPPING.items()
        ])
        
        ledger = ledger.join(cat_df, on="game_resource_id", how="left").with_columns(
            pl.col("category").fill_null("Unclassified"),
            pl.col("unit_str").fill_null("units")
        )
        
        state.update_table("resource_ledger", ledger)

    def _process_economy(self, state: GameState, fraction: float):
        """
        Calculates domestic production value and updates country wealth.
        """
        if "domestic_production" not in state.tables or "trade_network" not in state.tables:
            return

        prod_table = state.get_table("domestic_production")
        trade_table = state.get_table("trade_network")
        countries = state.get_table("countries")

        # 3. Calculate value generated per country 
        # In MONETARY MODE, domestic_production is already USD. 
        # Quality is already baked in by the generator.
        prod_val = prod_table.with_columns(
            (pl.col("domestic_production") * fraction).alias("generated_value")
        )



        country_income = prod_val.group_by("country_id").agg(
            pl.col("generated_value").sum().alias("production_income")
        ).rename({"country_id": "id"})

        # Update money reserves (Production income + taxes etc)
        updated_countries = countries.join(country_income, on="id", how="left").fill_null(0)
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + pl.col("production_income")).alias("money_reserves")
        )

        state.update_table("countries", updated_countries.drop("production_income"))

        # 5. Dynamically Grow Domestic Production (Industrial Growth)
        prod_table = prod_table.with_columns(
            (pl.col("domestic_production") * (1.0 + (0.025 * fraction))).alias("domestic_production")
        )
        state.update_table("domestic_production", prod_table)
