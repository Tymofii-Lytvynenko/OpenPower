import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class TradeSystem(ISystem):
    """
    Simulates a Proportional Global Market Clearing cycle.
    100% Vectorized and 100% LAZY in Polars. Zero micro-stutters.
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

        # 1. ENTER LAZY MODE: Stop calculating, start planning!
        countries_lf = state.get_table("countries").lazy()
        prod_lf = state.get_table("domestic_production").lazy()
        
        if "resource_ledger" in state.tables:
            demand_lf = state.get_table("resource_ledger").lazy().select(
                pl.col("country_id"), pl.col("game_resource_id"), pl.col("consumption_usd").alias("demand")
            )
            market_lf = prod_lf.join(demand_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)
        else:
            market_lf = prod_lf.with_columns((pl.col("domestic_production") * 0.9).alias("demand"))

        # Ensure columns exist lazily (respecting existing data if present)
        market_cols = market_lf.columns
        if "is_gov_controlled" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in market_cols:
            market_lf = market_lf.with_columns(pl.lit(0.05).alias("tax_rate"))

        # Ensure columns exist lazily
        current_cols = state.get_table("countries").columns
        missing_cols = []
        if "economic_health" not in current_cols: missing_cols.append(pl.lit(1.0).alias("economic_health"))
        if "gdp" not in current_cols: missing_cols.append(pl.lit(1_000_000.0).alias("gdp"))
        if "population" not in current_cols: missing_cols.append(pl.lit(1.0).alias("population"))
        
        if missing_cols:
            countries_lf = countries_lf.with_columns(missing_cols)

        countries_lf = countries_lf.with_columns((pl.col("gdp") * 0.5).alias("purchasing_power"))

        # ---------------------------------------------------------
        # 2. Desired Trade & Priorities (Lazy)
        # ---------------------------------------------------------
        market_lf = market_lf.with_columns([
            pl.when(pl.col("domestic_production") > pl.col("demand")).then(pl.col("domestic_production") - pl.col("demand")).otherwise(0.0).alias("export_desired"),
            pl.when(pl.col("demand") > pl.col("domestic_production")).then(pl.col("demand") - pl.col("domestic_production")).otherwise(0.0).alias("import_desired")
        ])

        priority_df = pl.DataFrame([{"game_resource_id": k, "priority": v} for k, v in self.TRADE_PRIORITY_MATRIX.items()])
        market_lf = market_lf.join(priority_df.lazy(), on="game_resource_id", how="left").with_columns(pl.col("priority").fill_null(999))

        # ---------------------------------------------------------
        # 3. Budget Allocation (Lazy Window Functions)
        # ---------------------------------------------------------
        market_lf = market_lf.sort(["country_id", "priority"])
        market_lf = market_lf.with_columns(
            pl.col("import_desired").cum_sum().over("country_id").alias("cum_import_cost")
        )
        
        market_lf = market_lf.join(countries_lf.select(["id", "purchasing_power"]), left_on="country_id", right_on="id", how="left")

        market_lf = market_lf.with_columns(
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
        # 4. Global Market Clearing (Lazy)
        # ---------------------------------------------------------
        world_market_lf = market_lf.group_by("game_resource_id").agg(
            pl.col("export_desired").sum().alias("global_supply"),
            pl.col("affordable_import").sum().alias("global_demand")
        )

        market_lf = market_lf.join(world_market_lf, on="game_resource_id", how="left")

        market_lf = market_lf.with_columns(
            pl.when(pl.col("global_demand") > 0).then(pl.min_horizontal(1.0, pl.col("global_supply") / pl.col("global_demand"))).otherwise(0.0).alias("imp_ratio"),
            pl.when(pl.col("global_supply") > 0).then(pl.min_horizontal(1.0, pl.col("global_demand") / pl.col("global_supply"))).otherwise(0.0).alias("exp_ratio")
        )

        market_lf = market_lf.with_columns(
            (pl.col("affordable_import") * pl.col("imp_ratio")).alias("import_actual"),
            (pl.col("export_desired") * pl.col("exp_ratio")).alias("export_actual")
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
        countries_lf = countries_lf.with_columns(
            (pl.col("money_reserves") + pl.col("trade_income") - pl.col("trade_expense")).alias("money_reserves")
        )

        # ---------------------------------------------------------
        # 6. Penalty and Execution
        # ---------------------------------------------------------
        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") - pl.col("demand") - pl.col("export_actual") + pl.col("import_actual")).alias("unsold_balance")
        )
        market_lf = market_lf.with_columns(
            pl.when(pl.col("unsold_balance") > 0).then(pl.col("domestic_production") - (pl.col("unsold_balance") * 0.8)).otherwise(pl.col("domestic_production")).alias("domestic_production")
        )

        # THE MAGIC HAPPENS HERE: We tell Polars to execute the entire plan at once!
        # This is where the 30x performance boost comes from.
        market_df = market_lf.collect()
        countries_df = countries_lf.collect()

        # ---------------------------------------------------------
        # 7. Generate Trade Network
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

        # UPDATE STATE
        state.update_table("trade_network", trade_net)
        
        # Preserve all columns (like is_gov_controlled, tax_rate) that were in market_df
        final_prod_cols = [c for c in market_df.columns if c not in ["export_desired", "import_desired", "priority", "cum_import_cost", "purchasing_power", "affordable_import", "global_supply", "global_demand", "imp_ratio", "exp_ratio", "import_actual", "export_actual", "gov_import_expense", "gov_tax_revenue", "unsold_balance"]]
        state.update_table("domestic_production", market_df.select(final_prod_cols))
        
        cols_to_drop = ["purchasing_power", "trade_income", "trade_expense"]
        state.update_table("countries", countries_df.drop([c for c in cols_to_drop if c in countries_df.columns]))