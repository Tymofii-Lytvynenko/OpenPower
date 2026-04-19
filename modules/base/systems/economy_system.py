import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond
from src.shared.economy_meta import RESOURCE_MAPPING

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

    # Formulaic consumption constants per resource.
    # Pattern: C = ((Pop * pop_coeff + Stab * stab_coeff) * base_mult) + dep_coeff_1 * C_dep_1 + ...
    CONSUMPTION_FORMULAS = {
        # Food and agriculture
        "cereals": {"pop_weight": 592.46, "stability_weight": 75.0, "inter_dependencies": {"dairy": 0.01, "meat_and_fish": 0.05}, "output_multiplier": 0.94},
        "vegetables_and_fruits": {"pop_weight": 764.3, "stability_weight": 40.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "meat_and_fish": {"pop_weight": 498.2, "stability_weight": 30.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "dairy": {"pop_weight": 830.9, "stability_weight": 25.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "tobacco": {"pop_weight": 143.49, "stability_weight": 4.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "drugs_and_raw_plants": {"pop_weight": 95.18, "stability_weight": 5.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "other_food_and_beverages": {"pop_weight": 600.0, "stability_weight": 40.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 

        # Energy
        "electricity": {
            "pop_weight": 1401.75, "stability_weight": 35.0, "output_multiplier": 0.78,
            "inter_dependencies": {
                "wood_and_paper": 0.02, "plastics_and_rubber": 0.04, "fabrics_and_leather": 0.02,
                "chemicals": 0.01, "pharmaceuticals": 0.02, "appliances": 0.04,
                "vehicles": 0.02, "machinery_and_instruments": 0.02, "commodities": 0.01,
                "luxury_commodities": 0.02
            }
        },
        "fossil_fuels": {"pop_weight": 1142.7, "stability_weight": 40.0, "inter_dependencies": {}, "output_multiplier": 1.0},

        # Raw materials
        "wood_and_paper": {"pop_weight": 183.88, "stability_weight": 10.0, "inter_dependencies": {"construction_services": 0.04}, "output_multiplier": 0.96},
        "minerals": {"pop_weight": 567.25, "stability_weight": 30.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "iron_and_steel": {
            "pop_weight": 1078.88, "stability_weight": 50.0, "output_multiplier": 0.82,
            "inter_dependencies": {"appliances": 0.04, "vehicles": 0.02, "machinery_and_instruments": 0.02, "construction_services": 0.06}
        },
        "precious_stones": {"pop_weight": 35.2, "stability_weight": 0.8, "inter_dependencies": {}, "output_multiplier": 1.0},
        "non_ferrous_metals": {"pop_weight": 400.0, "stability_weight": 20.0, "inter_dependencies": {"vehicles": 0.05, "appliances": 0.05}, "output_multiplier": 1.0},

        # Industrial materials
        "fabrics_and_leather": {"pop_weight": 1338.8, "stability_weight": 75.0, "inter_dependencies": {"commodities": 0.01, "luxury_commodities": 0.05}, "output_multiplier": 0.94},
        "plastics_and_rubber": {"pop_weight": 615.9, "stability_weight": 10.0, "inter_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02}, "output_multiplier": 0.97},
        "chemicals": {
            "pop_weight": 1517.0, "stability_weight": 40.0, "output_multiplier": 0.95,
            "inter_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02, "plastics_and_rubber": 0.01, "pharmaceuticals": 0.01}
        },
        "construction_materials": {"pop_weight": 2000.0, "stability_weight": 50.0, "inter_dependencies": {"construction_services": 0.1}, "output_multiplier": 1.0},

        # Finished goods
        "pharmaceuticals": {"pop_weight": 128.97, "stability_weight": 5.0, "inter_dependencies": {"health_services": 0.04}, "output_multiplier": 0.96},
        "appliances": {"pop_weight": 685.0, "stability_weight": 7.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "vehicles": {"pop_weight": 826.0, "stability_weight": 15.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "machinery_and_instruments": {
            "pop_weight": 414.0, "stability_weight": 12.0, "output_multiplier": 0.84,
            "inter_dependencies": {"construction_services": 0.05, "fossil_fuels": 0.03, "wood_and_paper": 0.02, "minerals": 0.05, "precious_stones": 0.01}
        },
        "commodities": {"pop_weight": 1200.0, "stability_weight": 10.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "luxury_commodities": {"pop_weight": 250.0, "stability_weight": 0.8, "inter_dependencies": {}, "output_multiplier": 1.0},
        "arms_and_ammunition": {"pop_weight": 50.0, "stability_weight": 100.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 

        # Services
        "construction_services": {"pop_weight": 6473.0, "stability_weight": 130.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "industrial_services": {"pop_weight": 2687.0, "stability_weight": 20.0, "inter_dependencies": {"construction_services": 0.02}, "output_multiplier": 0.98},
        "health_services": {"pop_weight": 11158.0, "stability_weight": 30.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "recreational_services": {"pop_weight": 1456.0, "stability_weight": 260.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "business_services": {"pop_weight": 2740.0, "stability_weight": 25.0, "inter_dependencies": {}, "output_multiplier": 1.0},
        "transport_services": {"pop_weight": 1350.0, "stability_weight": 8.0, "inter_dependencies": {"recreational_services": 0.02}, "output_multiplier": 0.98},
        "it_and_telecom_services": {"pop_weight": 3000.0, "stability_weight": 10.0, "inter_dependencies": {"business_services": 0.05}, "output_multiplier": 1.0},
        "financial_services": {"pop_weight": 4000.0, "stability_weight": 200.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 
        "tourism_services": {"pop_weight": 1000.0, "stability_weight": 500.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 
        "government_services": {"pop_weight": 8000.0, "stability_weight": 50.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 
        "education_services": {"pop_weight": 5000.0, "stability_weight": 20.0, "inter_dependencies": {}, "output_multiplier": 1.0}, 
    }

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

    def _get_population(self, state: GameState) -> pl.DataFrame:
        """Helper to compute total population per country from regions."""
        regions = state.get_table("regions")
        return regions.group_by("owner").agg(
            (pl.col("pop_14").fill_null(0) + pl.col("pop_15_64").fill_null(0) + pl.col("pop_65").fill_null(0)).sum().alias("population")
        ).rename({"owner": "country_id"})

    def _calculate_formulaic_consumption(self, state: GameState) -> pl.DataFrame:
        """
        Calculates annual consumption per country/resource based on population and stability.
        Consumption is calculated in USD using formulaic derivations.
        """
        countries = state.get_table("countries")
        
        # 1. Total Population per country
        pop_data = self._get_population(state)
        
        # 2. Stability index per country 
        # Scaled to 0.0-1.0 range for the internal formula logic
        stab_col = "gvt_stability" if "gvt_stability" in countries.columns else None
        if stab_col:
            stab_data = countries.select(["id", stab_col]).rename({"id": "country_id", stab_col: "stability_index"})
        else:
            stab_data = countries.select(pl.col("id").alias("country_id"), pl.lit(50.0).alias("stability_index"))

        data = pop_data.join(stab_data, on="country_id", how="inner")
        
        # Prepare inputs: total_population_mil, gov_stability_factor (0-1)
        data = data.with_columns(
            (pl.col("population") / 1_000_000.0).alias("total_population_mil"),
            (pl.col("stability_index") / 100.0).alias("gov_stability_factor")
        )
        
        # 3. Calculate in topological order to satisfy resource dependencies
        calc_order = [
            "dairy", "meat_and_fish", "cereals", "vegetables_and_fruits", "tobacco", 
            "drugs_and_raw_plants", "other_food_and_beverages", "fossil_fuels", 
            "minerals", "precious_stones", "construction_services", "recreational_services",
            "health_services", "education_services", "government_services", 
            "financial_services", "tourism_services", "arms_and_ammunition", "business_services",
            "wood_and_paper", "industrial_services", "transport_services", "it_and_telecom_services",
            "pharmaceuticals", "appliances", "vehicles", "commodities", "luxury_commodities", 
            "non_ferrous_metals", "construction_materials", "machinery_and_instruments",
            "iron_and_steel", "plastics_and_rubber", "fabrics_and_leather", "chemicals", 
            "electricity"
        ]
        
        res_dfs = data.clone()
        for res_id in calc_order:
            formula = self.CONSUMPTION_FORMULAS[res_id]
            # Core demand: ((PopMil * weight + StabilityFactor * weight) * multiplier)
            expr = (pl.col("total_population_mil") * formula["pop_weight"] + 
                    pl.col("gov_stability_factor") * formula["stability_weight"]) * formula["output_multiplier"]
            
            # Add inter-resource requirements
            for req_id, req_coeff in formula["inter_dependencies"].items():
                if req_id in res_dfs.columns:
                    expr = expr + (pl.col(req_id) * req_coeff)
            
            res_dfs = res_dfs.with_columns(expr.alias(res_id))
            
        # 4. Final translation to absolute USD
        output_res = list(self.CONSUMPTION_FORMULAS.keys())
        res_dfs = res_dfs.with_columns([
            (pl.col(c) * 1_000_000.0).alias(c) for c in output_res
        ])
        
        # Melt to long format for ledger joining
        long_consumption = res_dfs.select(["country_id"] + output_res).melt(
            id_vars="country_id",
            value_vars=output_res,
            variable_name="game_resource_id",
            value_name="consumption_usd"
        )
        
        return long_consumption

    def _build_resource_ledger(self, state: GameState):
        """
        Builds a dynamically aggregated resource ledger using formulaic consumption.
        """
        prod_table = state.get_table("domestic_production")
        trade_table = state.get_table("trade_network")
        from src.shared.economy_meta import RESOURCE_MAPPING

        # 1. Prepare Production (Annual rate)
        # Group by first to ensure any duplicate rows from data generation are consolidated.
        prod_usd = prod_table.group_by(["country_id", "game_resource_id"]).agg(
            pl.col("domestic_production").sum().alias("production_usd")
        )

        # 2. Prepare Trade (Annual rates)
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
        
        # 3. Calculate Formulaic Consumption
        consumption_table = self._calculate_formulaic_consumption(state)
        
        # 4. Master Ledger Compilation
        ledger = prod_usd.join(net_trade, on=["country_id", "game_resource_id"], how="full", coalesce=True)
        ledger = ledger.join(consumption_table, on=["country_id", "game_resource_id"], how="full", coalesce=True)
        
        ledger = ledger.with_columns(
            pl.col(["production_usd", "trade_usd", "export_usd", "import_usd", "consumption_usd"]).fill_null(0.0)
        )

        # 5. Economic Balance (Supply vs Demand)
        # Balance = Production + Imports - Exports - Consumption
        ledger = ledger.with_columns(
            (pl.col("production_usd") + pl.col("import_usd") - pl.col("export_usd") - pl.col("consumption_usd")).alias("balance_usd")
        )

        # 6. Metadata and Formatting
        cols_to_drop = ["avg_price", "base_price", "quality_index", "export_usd", "import_usd"]
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
        Calculates domestic production value and consumption costs, then updates country wealth.
        Also computes dynamic GDP and GDP per capita.
        """
        if "domestic_production" not in state.tables or "countries" not in state.tables:
            return

        prod_table = state.get_table("domestic_production")
        countries = state.get_table("countries")

        # 1. Calculate Production Income and GDP (Annual Rate)
        prod_val = prod_table.group_by("country_id").agg(
            (pl.col("domestic_production") * fraction).sum().alias("production_income"),
            pl.col("domestic_production").sum().alias("gdp") # Total generated value per year
        ).rename({"country_id": "id"})

        # 2. Calculate GDP Per Capita
        pop_data = self._get_population(state).rename({"country_id": "id"})
        prod_val = prod_val.join(pop_data, on="id", how="left").fill_null(0)
        prod_val = prod_val.with_columns(
            pl.when(pl.col("population") > 0)
            .then(pl.col("gdp") / pl.col("population"))
            .otherwise(0.0)
            .alias("gdp_per_capita")
        )

        # 3. Calculate Consumption Expenses (scaled by time fraction)
        consumption_long = self._calculate_formulaic_consumption(state)
        consumption_expenses = consumption_long.group_by("country_id").agg(
            (pl.col("consumption_usd") * fraction).sum().alias("consumption_cost")
        ).rename({"country_id": "id"})

        # 4. Update Countries Table (Money Reserves, GDP)
        cols_to_drop = [c for c in ["gdp", "gdp_per_capita"] if c in countries.columns]
        if cols_to_drop:
            countries = countries.drop(cols_to_drop)

        updated_countries = countries.join(prod_val.select(["id", "production_income", "gdp", "gdp_per_capita"]), on="id", how="left").join(consumption_expenses, on="id", how="left").fill_null(0)
        
        # Reserves += Production - Consumption
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + pl.col("production_income") - pl.col("consumption_cost")).alias("money_reserves")
        )

        state.update_table("countries", updated_countries.drop(["production_income", "consumption_cost"]))

        # 5. Dynamically Grow Domestic Production (Industrial Growth)
        prod_table = prod_table.with_columns(
            (pl.col("domestic_production") * (1.0 + (0.025 * fraction))).alias("domestic_production")
        )
        state.update_table("domestic_production", prod_table)
