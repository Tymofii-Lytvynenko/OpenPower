import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class TradeSystem(ISystem):
    """
    Simulates a Proportional Global Market Clearing cycle with National Stockpiles.
    Vectorized and LAZY in Polars.
    """

    TRADE_PRIORITY_MATRIX = {
        "cereals": 10, "vegetables_and_fruits": 11, "meat_and_fish": 12, "dairy": 13, 
        "pharmaceuticals": 14, "health_services": 15, "electricity": 20, "fossil_fuels": 21, 
        "transport_services": 22, "minerals": 30, "iron_and_steel": 31, "chemicals": 32, 
        "wood_and_paper": 33, "plastics_and_rubber": 34, "machinery_and_instruments": 40, 
        "industrial_services": 41, "construction_services": 42, "construction_materials": 43, 
        "vehicles": 44, "commodities": 50, "fabrics_and_leather": 51, "appliances": 52, 
        "business_services": 53, "it_and_telecom_services": 54, "tobacco": 60, 
        "drugs_and_raw_plants": 61, "recreational_services": 62, "tourism_services": 63, 
        "luxury_commodities": 64, "precious_stones": 65, "non_ferrous_metals": 66, 
        "arms_and_ammunition": 67, "education_services": 68, "government_services": 69, 
        "financial_services": 70, "other_food_and_beverages": 71
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
            if event.is_paused or event.game_seconds_passed <= 0: continue
            fraction = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._simulate_market_cycle(state, fraction)

    def _simulate_market_cycle(self, state: GameState, fraction: float):
        if "countries" not in state.tables or "domestic_production" not in state.tables: return

        # 1. ENTER LAZY MODE
        countries_lf = state.get_table("countries").lazy()
        prod_lf = state.get_table("domestic_production").lazy()
        
        # Load normalized Demand from EconomySystem
        if "resource_ledger" in state.tables:
            demand_lf = state.get_table("resource_ledger").lazy().select(
                pl.col("country_id"), pl.col("game_resource_id"), pl.col("consumption_usd").alias("demand")
            )
        else:
            demand_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("demand"))

        # Load or Initialize National Stockpiles (Reserves)
        if "stockpiles" in state.tables:
            stock_lf = state.get_table("stockpiles").lazy()
        else:
            stock_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("stock_amount"))

        # Join Market Data
        market_lf = prod_lf.join(demand_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)
        market_lf = market_lf.join(stock_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)

        # Ensure Meta columns exist
        market_cols = market_lf.columns
        if "is_gov_controlled" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(0.05).alias("tax_rate"))

        # ---------------------------------------------------------
        # 2. Local Supply & Desired Trade
        # ---------------------------------------------------------
        # Local Supply is what we just produced PLUS what was sitting in the stockpile
        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") + pl.col("stock_amount")).alias("local_supply")
        )

        market_lf = market_lf.with_columns([
            # If we have more than we need, we want to export the surplus
            pl.when(pl.col("local_supply") >= pl.col("demand"))
            .then(pl.col("local_supply") - pl.col("demand"))
            .otherwise(0.0).alias("export_desired"),
            
            # If our production + stockpile isn't enough, we must import
            pl.when(pl.col("demand") > pl.col("local_supply"))
            .then(pl.col("demand") - pl.col("local_supply"))
            .otherwise(0.0).alias("import_desired")
        ])

        # Priority mapping
        priority_df = pl.DataFrame([{"game_resource_id": k, "priority": v} for k, v in self.TRADE_PRIORITY_MATRIX.items()])
        market_lf = market_lf.join(priority_df.lazy(), on="game_resource_id", how="left").with_columns(pl.col("priority").fill_null(999))

        # Because EconomySystem already applied the Wealth/GDP Normalization constraint,
        # we completely trust that the requested demand is affordable. No more artificial 50% GDP caps!
        market_lf = market_lf.with_columns(
            pl.when(pl.col("is_gov_controlled") | ~pl.col("is_legal"))
            .then(pl.col("import_desired"))
            .otherwise(pl.col("import_desired")) # Trusted demand
            .alias("affordable_import")
        )

        # ---------------------------------------------------------
        # 3. Global Market Clearing (Lazy)
        # ---------------------------------------------------------
        world_market_lf = market_lf.group_by("game_resource_id").agg(
            pl.col("export_desired").sum().alias("global_supply"),
            pl.col("affordable_import").sum().alias("global_demand")
        )

        market_lf = market_lf.join(world_market_lf, on="game_resource_id", how="left")

        # Calculate clearing ratios to satisfy supply/demand proportionally
        market_lf = market_lf.with_columns(
            pl.when(pl.col("global_demand") > 0).then(pl.min_horizontal(1.0, pl.col("global_supply") / pl.col("global_demand"))).otherwise(0.0).alias("imp_ratio"),
            pl.when(pl.col("global_supply") > 0).then(pl.min_horizontal(1.0, pl.col("global_demand") / pl.col("global_supply"))).otherwise(0.0).alias("exp_ratio")
        )

        market_lf = market_lf.with_columns(
            (pl.col("affordable_import") * pl.col("imp_ratio")).alias("import_actual"),
            (pl.col("export_desired") * pl.col("exp_ratio")).alias("export_actual")
        )

        # ---------------------------------------------------------
        # 4. Update Stockpiles & Apply Organic Market Pressure
        # ---------------------------------------------------------
        # Whatever we put up for export but couldn't sell goes back to the stockpile
        market_lf = market_lf.with_columns(
            (pl.col("export_desired") - pl.col("export_actual")).alias("new_stock_amount")
        )

        # Calculate how big the stockpile is relative to what we produce in a year.
        market_lf = market_lf.with_columns(
            (pl.col("new_stock_amount") / pl.max_horizontal(pl.col("domestic_production"), 1.0)).alias("stock_to_prod_ratio")
        )

        # Organic Penalty (Law of Supply): 
        # If stockpiles exceed 50% of annual production, start scaling back factories.
        # Max penalty is 10% reduction per year (realistic recession), NOT an instant 80% nuke.
        market_lf = market_lf.with_columns(
            pl.when(pl.col("stock_to_prod_ratio") > 0.5)
            .then(pl.min_horizontal(pl.col("stock_to_prod_ratio") * 0.05, 0.10) * fraction)
            .otherwise(0.0).alias("production_penalty_pct")
        )

        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") * (1.0 - pl.col("production_penalty_pct"))).alias("domestic_production")
        )

        # ---------------------------------------------------------
        # 5. Financial & Budget Application (Lazy)
        # ---------------------------------------------------------
        global_tax_mod = 0.02
        market_lf = market_lf.with_columns((pl.col("tax_rate") + global_tax_mod).alias("total_tax"))

        market_lf = market_lf.with_columns(
            pl.when(pl.col("is_gov_controlled")).then(pl.col("import_actual") * 1.5).otherwise(0.0).alias("gov_import_expense"),
            pl.when(pl.col("is_gov_controlled")).then(pl.col("export_actual") * 1.5)
            .when(pl.col("is_legal")).then((pl.col("import_actual") * pl.col("total_tax")) + (pl.col("export_actual") * pl.col("total_tax")))
            .otherwise(0.0).alias("gov_tax_revenue")
        )

        budget_updates_lf = market_lf.group_by("country_id").agg(
            (pl.col("gov_tax_revenue").sum() * fraction).alias("trade_income"),
            (pl.col("gov_import_expense").sum() * fraction).alias("trade_expense")
        )

        countries_lf = countries_lf.join(budget_updates_lf, left_on="id", right_on="country_id", how="left").fill_null(0.0)
        
        # Ensure 'money_reserves' column exists
        if "money_reserves" not in countries_lf.columns:
            countries_lf = countries_lf.with_columns(pl.lit(0.0).alias("money_reserves"))
            
        countries_lf = countries_lf.with_columns(
            (pl.col("money_reserves") + pl.col("trade_income") - pl.col("trade_expense")).alias("money_reserves")
        )

        # ---------------------------------------------------------
        # 6. EXECUTE GRAPH (POLARS MAGIC)
        # ---------------------------------------------------------
        market_df = market_lf.collect()
        countries_df = countries_lf.collect()

        # ---------------------------------------------------------
        # 7. Generate Trade Network & Update State
        # ---------------------------------------------------------
        exporters = market_df.filter(pl.col("export_actual") > 0).select(["country_id", "game_resource_id", "export_actual", "global_supply"])
        importers = market_df.filter(pl.col("import_actual") > 0).select(["country_id", "game_resource_id", "import_actual"])
        
        trade_net = exporters.join(importers, on="game_resource_id", suffix="_imp")
        trade_net = trade_net.with_columns(
            (pl.col("import_actual") * (pl.col("export_actual") / pl.col("global_supply"))).alias("trade_value_usd")
        ).select([
            pl.col("country_id").alias("exporter_id"),
            pl.col("country_id_imp").alias("importer_id"),
            "game_resource_id", "trade_value_usd"
        ])

        # STATE UPDATES
        state.update_table("trade_network", trade_net)
        
        # Update Stockpiles
        state.update_table("stockpiles", market_df.select(["country_id", "game_resource_id", pl.col("new_stock_amount").alias("stock_amount")]))
        
        # Preserve core production columns
        final_prod_cols = [c for c in market_df.columns if c not in [
            "demand", "stock_amount", "local_supply", "export_desired", "import_desired", "priority", 
            "affordable_import", "global_supply", "global_demand", "imp_ratio", "exp_ratio", 
            "import_actual", "export_actual", "new_stock_amount", "stock_to_prod_ratio", 
            "production_penalty_pct", "total_tax", "gov_import_expense", "gov_tax_revenue"
        ]]
        state.update_table("domestic_production", market_df.select(final_prod_cols))
        
        cols_to_drop = ["trade_income", "trade_expense"]
        state.update_table("countries", countries_df.drop([c for c in cols_to_drop if c in countries_df.columns]))