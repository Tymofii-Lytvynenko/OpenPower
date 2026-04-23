import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond

class TradeSystem(ISystem):
    """
    Simulates Global Market Clearing with Physical Constraints.
    Features: Service Evaporation, Asset Depreciation, and Organic Market Pressure.
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

    # Physical properties of resources: Can they be stored? How quickly do they depreciate/spoil per year?
    RESOURCE_PHYSICS = {
        # Services and energy: CANNOT be stored. They are consumed instantly.
        "electricity": {"is_storable": False, "decay_rate": 1.0},
        "construction_services": {"is_storable": False, "decay_rate": 1.0},
        "industrial_services": {"is_storable": False, "decay_rate": 1.0},
        "health_services": {"is_storable": False, "decay_rate": 1.0},
        "recreational_services": {"is_storable": False, "decay_rate": 1.0},
        "business_services": {"is_storable": False, "decay_rate": 1.0},
        "transport_services": {"is_storable": False, "decay_rate": 1.0},
        "education_services": {"is_storable": False, "decay_rate": 1.0},
        "government_services": {"is_storable": False, "decay_rate": 1.0},
        "financial_services": {"is_storable": False, "decay_rate": 1.0},
        "it_and_telecom_services": {"is_storable": False, "decay_rate": 1.0},
        "tourism_services": {"is_storable": False, "decay_rate": 1.0},

        # Fast depreciation (Finished goods, 20-25% per year due to aging/fashion)
        "appliances": {"is_storable": True, "decay_rate": 0.20},
        "vehicles": {"is_storable": True, "decay_rate": 0.25},
        "machinery_and_instruments": {"is_storable": True, "decay_rate": 0.20},
        "commodities": {"is_storable": True, "decay_rate": 0.25},
        "luxury_commodities": {"is_storable": True, "decay_rate": 0.20},
        "pharmaceuticals": {"is_storable": True, "decay_rate": 0.15}, # Expiry date / Shelf life
        "arms_and_ammunition": {"is_storable": True, "decay_rate": 0.10}, 

        # Medium spoilage (Food and Agro, 10-15% annual losses)
        "cereals": {"is_storable": True, "decay_rate": 0.10},
        "vegetables_and_fruits": {"is_storable": True, "decay_rate": 0.15},
        "meat_and_fish": {"is_storable": True, "decay_rate": 0.15},
        "dairy": {"is_storable": True, "decay_rate": 0.15},
        "tobacco": {"is_storable": True, "decay_rate": 0.10},
        "drugs_and_raw_plants": {"is_storable": True, "decay_rate": 0.10},
        "other_food_and_beverages": {"is_storable": True, "decay_rate": 0.10},

        # Slow spoilage (Raw materials and Materials, 2-5% per year)
        "fossil_fuels": {"is_storable": True, "decay_rate": 0.05}, # Evaporation, leakage
        "wood_and_paper": {"is_storable": True, "decay_rate": 0.05},
        "minerals": {"is_storable": True, "decay_rate": 0.02},
        "iron_and_steel": {"is_storable": True, "decay_rate": 0.03}, # Rust
        "precious_stones": {"is_storable": True, "decay_rate": 0.00}, # Eternal
        "non_ferrous_metals": {"is_storable": True, "decay_rate": 0.02},
        "fabrics_and_leather": {"is_storable": True, "decay_rate": 0.05},
        "plastics_and_rubber": {"is_storable": True, "decay_rate": 0.05},
        "chemicals": {"is_storable": True, "decay_rate": 0.08},
        "construction_materials": {"is_storable": True, "decay_rate": 0.05},
    }

    def __init__(self):
        self._missing_columns = set()

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

        countries_lf = state.get_table("countries").lazy()
        prod_lf = state.get_table("domestic_production").lazy()
        
        if "resource_ledger" in state.tables:
            demand_lf = state.get_table("resource_ledger").lazy().select(
                pl.col("country_id"), pl.col("game_resource_id"), pl.col("consumption_usd").alias("demand")
            )
        else:
            demand_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("demand"))

        if "stockpiles" in state.tables:
            stock_lf = state.get_table("stockpiles").lazy()
        else:
            stock_lf = prod_lf.select(["country_id", "game_resource_id"]).with_columns(pl.lit(0.0).alias("stock_amount"))

        market_lf = prod_lf.join(demand_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)
        market_lf = market_lf.join(stock_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)

        # Ensure Meta columns exist
        market_cols = market_lf.collect_schema().names()
        if "is_gov_controlled" not in market_cols:
            if "is_gov_controlled" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_gov_controlled' not found in 'domestic_production'. Defaulting to False.")
                self._missing_columns.add("is_gov_controlled")
            market_lf = market_lf.with_columns(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in market_cols:
            if "is_legal" not in self._missing_columns:
                print(f"[{self.id}] Column 'is_legal' not found in 'domestic_production'. Defaulting to True.")
                self._missing_columns.add("is_legal")
            market_lf = market_lf.with_columns(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in market_cols:
            if "tax_rate" not in self._missing_columns:
                print(f"[{self.id}] Column 'tax_rate' not found in 'domestic_production'. Defaulting to 0.05.")
                self._missing_columns.add("tax_rate")
            market_lf = market_lf.with_columns(pl.lit(0.05).alias("tax_rate"))

        # Add Physical Properties
        physics_df = pl.DataFrame([
            {"game_resource_id": k, "is_storable": v["is_storable"], "decay_rate": v["decay_rate"]}
            for k, v in self.RESOURCE_PHYSICS.items()
        ])
        market_lf = market_lf.join(physics_df.lazy(), on="game_resource_id", how="left").with_columns([
            pl.col("is_storable").fill_null(True),
            pl.col("decay_rate").fill_null(0.10)
        ])

        # ---------------------------------------------------------
        # Local Supply & Trade Desires
        # ---------------------------------------------------------
        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") + pl.col("stock_amount")).alias("local_supply")
        )

        market_lf = market_lf.with_columns([
            pl.when(pl.col("local_supply") >= pl.col("demand")).then(pl.col("local_supply") - pl.col("demand")).otherwise(0.0).alias("export_desired"),
            pl.when(pl.col("demand") > pl.col("local_supply")).then(pl.col("demand") - pl.col("local_supply")).otherwise(0.0).alias("import_desired")
        ])

        market_lf = market_lf.with_columns(pl.col("import_desired").alias("affordable_import"))

        # ---------------------------------------------------------
        # Global Market Clearing
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
        # The Core Fix: Stockpile Decay & Dynamic Penalties
        # ---------------------------------------------------------
        # 1. How much is left over after trading?
        market_lf = market_lf.with_columns(
            (pl.col("export_desired") - pl.col("export_actual")).alias("unsold_amount")
        )

        # 2. Update Stockpiles (with Decay) for Storable Goods
        market_lf = market_lf.with_columns(
            pl.when(pl.col("is_storable"))
            .then(pl.col("unsold_amount") * (1.0 - (pl.col("decay_rate") * fraction)))
            .otherwise(0.0)
            .alias("new_stock_amount")
        )

        # 3. Apply Asymmetric Penalties (Organic Bankruptcy vs Service Layoffs)
        market_lf = market_lf.with_columns(
            # If it's services (NOT storable): Penalty is harsh and immediate. 
            # If 20% of services are unwanted, lay off staff (minus 10% capacity per year)
            pl.when(~pl.col("is_storable"))
            .then((pl.col("unsold_amount") / pl.max_horizontal(pl.col("domestic_production"), 1.0)) * 0.5 * fraction)
            
            # If it's goods (Storable): Soft penalty.
            # We only punish when warehouses swell to more than 50% of annual production. Maximum 10% reduction per year.
            .when(pl.col("is_storable") & ((pl.col("new_stock_amount") / pl.max_horizontal(pl.col("domestic_production"), 1.0)) > 0.5))
            .then(pl.min_horizontal((pl.col("new_stock_amount") / pl.max_horizontal(pl.col("domestic_production"), 1.0)) * 0.05, 0.10) * fraction)
            
            .otherwise(0.0).alias("production_penalty_pct")
        )

        market_lf = market_lf.with_columns(
            (pl.col("domestic_production") * (1.0 - pl.col("production_penalty_pct"))).alias("domestic_production")
        )

        # ---------------------------------------------------------
        # Financial Execution & Output
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
            pl.col("gov_tax_revenue").sum().alias("trade_income"),
            pl.col("gov_import_expense").sum().alias("trade_expense")
        )

        # Drop old trade columns before join to avoid _right suffix clashes
        countries_lf = countries_lf.drop(["trade_income", "trade_expense"], strict=False)
        countries_lf = countries_lf.join(budget_updates_lf, left_on="id", right_on="country_id", how="left").fill_null(0.0)
        
        # We NO LONGER update money_reserves here. 
        # BudgetSystem handles the annual rates we just stored in countries_lf.

        # EXECUTE
        market_df = market_lf.collect()
        countries_df = countries_lf.collect()

        # Update State
        state.update_table("stockpiles", market_df.select(["country_id", "game_resource_id", pl.col("new_stock_amount").alias("stock_amount")]))
        
        # Create trade_network table for EconomySystem ledger
        # In a global pool model, we represent this as flows between countries and the "WORLD"
        exports_df = market_df.filter(pl.col("export_actual") > 0).select([
            pl.col("country_id").alias("exporter_id"),
            pl.lit("WORLD").alias("importer_id"),
            pl.col("game_resource_id"),
            pl.col("export_actual").alias("trade_value_usd")
        ])
        imports_df = market_df.filter(pl.col("import_actual") > 0).select([
            pl.lit("WORLD").alias("exporter_id"),
            pl.col("country_id").alias("importer_id"),
            pl.col("game_resource_id"),
            pl.col("import_actual").alias("trade_value_usd")
        ])
        state.update_table("trade_network", pl.concat([exports_df, imports_df]))

        final_prod_cols = [c for c in market_df.columns if c not in [
            "demand", "stock_amount", "local_supply", "export_desired", "import_desired", "priority", 
            "affordable_import", "global_supply", "global_demand", "imp_ratio", "exp_ratio", 
            "import_actual", "export_actual", "unsold_amount", "new_stock_amount", "stock_to_prod_ratio", 
            "production_penalty_pct", "total_tax", "gov_import_expense", "gov_tax_revenue", "is_storable", "decay_rate"
        ]]
        state.update_table("domestic_production", market_df.select(final_prod_cols))
        state.update_table("countries", countries_df)