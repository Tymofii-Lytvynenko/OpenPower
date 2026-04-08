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

    def update(self, state: GameState, delta_time: float) -> None:
        if "resource_ledger" not in state.tables and "domestic_production" in state.tables and "trade_network" in state.tables:
            self._build_resource_ledger(state)

        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
                
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_economy(state, fraction_of_year)

    def _build_resource_ledger(self, state: GameState):
        """
        Builds a statically aggregated resource ledger for UI presentation.
        Re-run this if production or trade volumes ever become dynamic.
        """
        prod_table = state.get_table("domestic_production")
        trade_table = state.get_table("trade_network")

        prices = trade_table.group_by("game_resource_id").agg(
            pl.col("unit_price_usd").median().alias("avg_price")
        )

        prod_val = prod_table.join(prices, on="game_resource_id", how="left").fill_null(1.0)
        
        prod_val = prod_val.with_columns(
            (pl.col("domestic_production") * pl.col("avg_price")).alias("production_usd")
        ).rename({"domestic_production": "production_vol"})
        
        exports = trade_table.group_by(["exporter_id", "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("export_vol"),
            (pl.col("annual_volume") * pl.col("unit_price_usd")).sum().alias("export_usd")
        ).rename({"exporter_id": "country_id"})
        
        imports = trade_table.group_by(["importer_id", "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("import_vol"),
            (pl.col("annual_volume") * pl.col("unit_price_usd")).sum().alias("import_usd")
        ).rename({"importer_id": "country_id"})
        
        net_trade = exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)
        net_trade = net_trade.with_columns(
            (pl.col("export_vol") - pl.col("import_vol")).alias("trade_vol"),
            (pl.col("export_usd") - pl.col("import_usd")).alias("trade_usd")
        )
        
        ledger = prod_val.join(net_trade, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)
        
        ledger = ledger.with_columns(
            (pl.col("production_vol") - pl.col("trade_vol")).clip(lower_bound=0.0).alias("consumption_vol"),
            (pl.col("production_usd") - pl.col("trade_usd")).clip(lower_bound=0.0).alias("consumption_usd")
        )
        
        ledger = ledger.with_columns(
            (pl.col("production_vol") - pl.col("consumption_vol") - pl.col("trade_vol")).alias("balance_vol"),
            (pl.col("production_usd") - pl.col("consumption_usd") - pl.col("trade_usd")).alias("balance_usd")
        )
        
        from src.shared.economy_meta import RESOURCE_MAPPING
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

        # 1. Calculate Global Price Index for each resource
        # (This is a simplified approach using median trade prices)
        prices = trade_table.group_by("game_resource_id").agg(
            pl.col("unit_price_usd").median().alias("avg_price")
        )

        # 2. Join production with prices
        prod_val = prod_table.join(prices, on="game_resource_id", how="left").fill_null(1.0) # Fallback to $1/ton

        # 3. Calculate value generated per country
        # Value = production * avg_price * quality_index/100 * fraction_of_year
        # Note: quality_index is 1..100
        prod_val = prod_val.with_columns(
            (pl.col("domestic_production") * pl.col("avg_price") * (pl.col("quality_index") / 100.0) * fraction).alias("generated_value")
        )

        country_income = prod_val.group_by("country_id").agg(
            pl.col("generated_value").sum().alias("production_income")
        ).rename({"country_id": "id"})

        # 4. Update money reserves (Production income + taxes etc)
        # For now, let's just add production income minus a base consumption cost (simulated)
        updated_countries = countries.join(country_income, on="id", how="left").fill_null(0)
        
        # Simple Logic: countries gain money relative to production, but spend it elsewhere 
        # (Simplified: Gain 100% of generated value as reserves/GDP-like growth)
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + pl.col("production_income")).alias("money_reserves")
        )

        state.update_table("countries", updated_countries.drop("production_income"))
