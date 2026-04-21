import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class TradeSystem(ISystem):
    """
    Simulates a Proportional Global Market Clearing cycle.
    100% Vectorized in Polars. 0 Python loops. Zero micro-stutters.
    """

    # Priority Matrix for Budget Allocation (Lower number = Higher priority)
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

        countries_df = state.get_table("countries")
        prod_df = state.get_table("domestic_production")
        
        # 1. Fetch Demand and Stubs
        if "resource_ledger" in state.tables:
            demand_df = state.get_table("resource_ledger").select(pl.col("country_id"), pl.col("game_resource_id"), pl.col("consumption_usd").alias("demand"))
            market_df = prod_df.join(demand_df, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)
        else:
            market_df = prod_df.with_columns((pl.col("domestic_production") * 0.9).alias("demand"))

        market_df = market_df.with_columns([
            pl.lit(False).alias("is_gov_controlled"),
            pl.lit(True).alias("is_legal"),
            pl.lit(0.05).alias("tax_rate")
        ])

        req_cols = {"economic_health": 1.0, "gdp": 1_000_000.0, "population": 1.0}
        for col, default_val in req_cols.items():
            if col not in countries_df.columns:
                countries_df = countries_df.with_columns(pl.lit(default_val).alias(col))

        countries_df = countries_df.with_columns((pl.col("gdp") * 0.5).alias("purchasing_power"))

        # ---------------------------------------------------------
        # 2. Desired Trade & Priority Mapping
        # ---------------------------------------------------------
        market_df = market_df.with_columns([
            pl.when(pl.col("domestic_production") > pl.col("demand")).then(pl.col("domestic_production") - pl.col("demand")).otherwise(0.0).alias("export_desired"),
            pl.when(pl.col("demand") > pl.col("domestic_production")).then(pl.col("demand") - pl.col("domestic_production")).otherwise(0.0).alias("import_desired")
        ])

        # Map priorities for budget allocation
        priority_df = pl.DataFrame([{"game_resource_id": k, "priority": v} for k, v in self.TRADE_PRIORITY_MATRIX.items()])
        market_df = market_df.join(priority_df, on="game_resource_id", how="left").with_columns(pl.col("priority").fill_null(999))

        # ---------------------------------------------------------
        # 3. Budget Allocation (Vectorized Purchasing Power Limits)
        # ---------------------------------------------------------
        # Sort by country and priority, then cumulatively sum the import costs
        market_df = market_df.sort(["country_id", "priority"])
        market_df = market_df.with_columns(
            pl.col("import_desired").cum_sum().over("country_id").alias("cum_import_cost")
        )
        
        # Join Purchasing Power to evaluate what they can afford
        market_df = market_df.join(countries_df.select(["id", "purchasing_power"]), left_on="country_id", right_on="id", how="left")

        # Affordable Import logic: If Gov Controlled, bypass PP limit. Else, cap by PP.
        market_df = market_df.with_columns(
            pl.when(pl.col("is_gov_controlled") | ~pl.col("is_legal"))
            .then(pl.col("import_desired"))
            .when(pl.col("cum_import_cost") <= pl.col("purchasing_power"))
            .then(pl.col("import_desired"))
            .when((pl.col("cum_import_cost") - pl.col("import_desired")) < pl.col("purchasing_power"))
            .then(pl.col("purchasing_power") - (pl.col("cum_import_cost") - pl.col("import_desired")))
            .otherwise(0.0)
            .alias("affordable_import")
        )

        # ---------------------------------------------------------
        # 4. Global Market Clearing (Proportional Fulfillment)
        # ---------------------------------------------------------
        # Aggregate global supply and demand per resource
        world_market = market_df.group_by("game_resource_id").agg(
            pl.col("export_desired").sum().alias("global_supply"),
            pl.col("affordable_import").sum().alias("global_demand")
        )

        market_df = market_df.join(world_market, on="game_resource_id", how="left")

        # Calculate fulfillment ratios: Supply / Demand (Capped at 1.0)
        market_df = market_df.with_columns(
            pl.when(pl.col("global_demand") > 0).then(pl.min_horizontal(1.0, pl.col("global_supply") / pl.col("global_demand"))).otherwise(0.0).alias("imp_ratio"),
            pl.when(pl.col("global_supply") > 0).then(pl.min_horizontal(1.0, pl.col("global_demand") / pl.col("global_supply"))).otherwise(0.0).alias("exp_ratio")
        )

        # Final actual trade volumes
        market_df = market_df.with_columns(
            (pl.col("affordable_import") * pl.col("imp_ratio")).alias("import_actual"),
            (pl.col("export_desired") * pl.col("exp_ratio")).alias("export_actual")
        )

        # ---------------------------------------------------------
        # 5. Financial & Budget Application
        # ---------------------------------------------------------
        global_tax_mod = 0.02
        market_df = market_df.with_columns((pl.col("tax_rate") + global_tax_mod).alias("total_tax"))

        # Calculate Budget Impacts per row
        market_df = market_df.with_columns(
            pl.when(pl.col("is_gov_controlled")).then(pl.col("import_actual") * 1.5).otherwise(0.0).alias("gov_import_expense"),
            
            pl.when(pl.col("is_gov_controlled")).then(pl.col("export_actual") * 1.5)
            .when(pl.col("is_legal")).then((pl.col("import_actual") * pl.col("total_tax")) + (pl.col("export_actual") * pl.col("total_tax")))
            .otherwise(0.0).alias("gov_tax_revenue")
        )

        # Aggregate financial results back to Countries
        budget_updates = market_df.group_by("country_id").agg(
            (pl.col("gov_tax_revenue").sum() * fraction).alias("trade_income"),
            (pl.col("gov_import_expense").sum() * fraction).alias("trade_expense")
        )

        countries_df = countries_df.join(budget_updates, left_on="id", right_on="country_id", how="left").fill_null(0.0)
        countries_df = countries_df.with_columns(
            (pl.col("money_reserves") + pl.col("trade_income") - pl.col("trade_expense")).alias("money_reserves")
        )

        # ---------------------------------------------------------
        # 6. Synthetic Bilateral Trade Network Generation
        # ---------------------------------------------------------
        # To satisfy UI and Economy demands, we cross-join the proportional results to build the network
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

        # ---------------------------------------------------------
        # 7. Inefficiency Penalty
        # ---------------------------------------------------------
        market_df = market_df.with_columns(
            (pl.col("domestic_production") - pl.col("demand") - pl.col("export_actual") + pl.col("import_actual")).alias("unsold_balance")
        )
        
        market_df = market_df.with_columns(
            pl.when(pl.col("unsold_balance") > 0).then(pl.col("domestic_production") - (pl.col("unsold_balance") * 0.8)).otherwise(pl.col("domestic_production")).alias("domestic_production")
        )

        # ---------------------------------------------------------
        # UPDATE STATE (Instant)
        # ---------------------------------------------------------
        state.update_table("trade_network", trade_net)
        state.update_table("domestic_production", market_df.select(["country_id", "game_resource_id", "domestic_production"]))
        
        cols_to_drop = ["purchasing_power", "trade_income", "trade_expense"]
        state.update_table("countries", countries_df.drop([c for c in cols_to_drop if c in countries_df.columns]))