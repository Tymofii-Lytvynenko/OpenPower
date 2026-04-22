import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.events import EventRealSecond
from src.shared.economy_meta import RESOURCE_MAPPING

class EconomySystem(ISystem):
    """
    Handles internal macroeconomic simulation, including domestic production value 
    generation, base internal taxation, and calculating national demand (consumption).
    """
    
    @property
    def id(self) -> str:
        return "base.economy"

    @property
    def dependencies(self) -> list[str]:
        # Economy runs after Trade to finalize the ledger and apply internal GDP growth
        # based on the post-trade, penalized state of production.
        return ["base.time", "base.trade"]

    QUALITY_SENSITIVE_GOODS = [
        "appliances", "vehicles", "machinery_and_instruments",
        "pharmaceuticals", "luxury_commodities", "transport_services", 
        "construction_services", "business_services", "recreational_services", 
        "health_services", "industrial_services"
    ]

    # Pattern: C = ((SolventPopulation * solvent_base_consumption + Population * general_base_consumption) * multiplier) + dependencies
    CONSUMPTION_FORMULAS = {
        # Food and agriculture
        "cereals": {"solvent_base_consumption": 592.46, "general_base_consumption": 75.0, "resource_dependencies": {"dairy": 0.01, "meat_and_fish": 0.05}, "output_multiplier": 0.94},
        "vegetables_and_fruits": {"solvent_base_consumption": 764.3, "general_base_consumption": 40.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "meat_and_fish": {"solvent_base_consumption": 498.2, "general_base_consumption": 30.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "dairy": {"solvent_base_consumption": 830.9, "general_base_consumption": 25.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "tobacco": {"solvent_base_consumption": 143.49, "general_base_consumption": 4.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "drugs_and_raw_plants": {"solvent_base_consumption": 95.18, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0},

        # Energy
        "electricity": {
            "solvent_base_consumption": 1401.75, "general_base_consumption": 35.0, "output_multiplier": 0.78,
            "resource_dependencies": {
                "wood_and_paper": 0.02, "plastics_and_rubber": 0.04, "fabrics_and_leather": 0.02,
                "chemicals": 0.01, "pharmaceuticals": 0.02, "appliances": 0.04,
                "vehicles": 0.02, "machinery_and_instruments": 0.02, "commodities": 0.01,
                "luxury_commodities": 0.02
            }
        },
        "fossil_fuels": {"solvent_base_consumption": 1142.7, "general_base_consumption": 40.0, "resource_dependencies": {}, "output_multiplier": 1.0},

        # Raw materials
        "wood_and_paper": {"solvent_base_consumption": 183.88, "general_base_consumption": 10.0, "resource_dependencies": {"construction_services": 0.04}, "output_multiplier": 0.96},
        "minerals": {"solvent_base_consumption": 567.25, "general_base_consumption": 30.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "iron_and_steel": {
            "solvent_base_consumption": 1078.88, "general_base_consumption": 50.0, "output_multiplier": 0.82,
            "resource_dependencies": {"appliances": 0.04, "vehicles": 0.04, "machinery_and_instruments": 0.04, "construction_services": 0.06}
        },
        "precious_stones": {"solvent_base_consumption": 35.2, "general_base_consumption": 0.8, "resource_dependencies": {}, "output_multiplier": 1.0},

        # Industrial materials
        "fabrics_and_leather": {"solvent_base_consumption": 1338.8, "general_base_consumption": 75.0, "resource_dependencies": {"commodities": 0.01, "luxury_commodities": 0.05}, "output_multiplier": 0.94},
        "plastics_and_rubber": {"solvent_base_consumption": 615.9, "general_base_consumption": 10.0, "resource_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02}, "output_multiplier": 0.97},
        "chemicals": {
            "solvent_base_consumption": 1517.0, "general_base_consumption": 40.0, "output_multiplier": 0.95,
            "resource_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02, "plastics_and_rubber": 0.01, "pharmaceuticals": 0.01}
        },

        # Finished goods
        "pharmaceuticals": {"solvent_base_consumption": 128.97, "general_base_consumption": 5.0, "resource_dependencies": {"health_services": 0.04}, "output_multiplier": 0.96},
        "appliances": {"solvent_base_consumption": 685.05, "general_base_consumption": 7.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "vehicles": {"solvent_base_consumption": 826.15, "general_base_consumption": 15.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "machinery_and_instruments": {
            "solvent_base_consumption": 413.81, "general_base_consumption": 12.0, "output_multiplier": 0.84,
            "resource_dependencies": {"construction_services": 0.05, "fossil_fuels": 0.03, "wood_and_paper": 0.02, "minerals": 0.05, "precious_stones": 0.01}
        },
        "commodities": {"solvent_base_consumption": 1198.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "luxury_commodities": {"solvent_base_consumption": 247.4, "general_base_consumption": 0.8, "resource_dependencies": {}, "output_multiplier": 1.0},

        # Services
        "construction_services": {"solvent_base_consumption": 1800.0, "general_base_consumption": 40.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "industrial_services": {"solvent_base_consumption": 800.0, "general_base_consumption": 5.0, "resource_dependencies": {"construction_services": 0.02}, "output_multiplier": 0.98},
        "health_services": {"solvent_base_consumption": 3200.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "recreational_services": {"solvent_base_consumption": 400.0, "general_base_consumption": 70.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "business_services": {"solvent_base_consumption": 800.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "transport_services": {"solvent_base_consumption": 400.0, "general_base_consumption": 2.0, "resource_dependencies": {"recreational_services": 0.02}, "output_multiplier": 0.98},
        "education_services": {"solvent_base_consumption": 1200.0, "general_base_consumption": 40.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "government_services": {"solvent_base_consumption": 2200.0, "general_base_consumption": 120.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "financial_services": {"solvent_base_consumption": 1800.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "it_and_telecom_services": {"solvent_base_consumption": 900.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0},
        "tourism_services": {"solvent_base_consumption": 600.0, "general_base_consumption": 15.0, "resource_dependencies": {}, "output_multiplier": 1.0},    }

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
            
            if "domestic_production" in state.tables:
                rebuild_ledger = True
                
        if rebuild_ledger:
            self._build_resource_ledger(state)

    def _get_population(self, state: GameState) -> pl.DataFrame:
        regions = state.get_table("regions")
        return regions.group_by("owner").agg(
            (pl.col("pop_14").fill_null(0) + pl.col("pop_15_64").fill_null(0) + pl.col("pop_65").fill_null(0)).sum().alias("population")
        ).rename({"owner": "country_id"})

    def _calculate_formulaic_consumption(self, state: GameState) -> pl.DataFrame:
        """
        Calculates annual consumption (Demand) per country/resource.
        Provides the baseline demand values that the TradeSystem relies on.
        """
        countries = state.get_table("countries")
        data = self._get_population(state)
        
        metrics_data = countries.select(
            pl.col("id").alias("country_id"),
            pl.col("poverty_rate"),
            pl.col("human_dev")
        )

        data = data.join(metrics_data, on="country_id", how="inner")
        
        data = data.with_columns(
            (pl.col("population") * (1.0 - pl.col("poverty_rate")) * pl.col("human_dev")).alias("solvent_population")
        )
        
        calc_order = [
            "health_services", "recreational_services", "construction_services", 
            "fossil_fuels", "minerals", "precious_stones", "appliances", "vehicles", 
            "commodities", "luxury_commodities", "dairy", "meat_and_fish", 
            "vegetables_and_fruits", "tobacco", "drugs_and_raw_plants", "business_services",
            "pharmaceuticals", "transport_services", "wood_and_paper", "industrial_services",
            "machinery_and_instruments", "iron_and_steel", "plastics_and_rubber", 
            "fabrics_and_leather", "cereals", "chemicals", "electricity",
            # Newly added
            "education_services", "government_services", "financial_services",
            "it_and_telecom_services", "tourism_services", "arms_and_ammunition",
            "other_food_and_beverages", "non_ferrous_metals", "construction_materials"
        ]
        
        res_dfs = data.clone()
        for res_id in calc_order:
            formula = self.CONSUMPTION_FORMULAS[res_id]
            
            expr = (pl.col("solvent_population") * formula["solvent_base_consumption"] + 
                    pl.col("population") * formula["general_base_consumption"]) * formula["output_multiplier"]
            
            for req_id, req_coeff in formula["resource_dependencies"].items():
                if req_id in res_dfs.columns:
                    expr = expr + (pl.col(req_id) * req_coeff)
            
            res_dfs = res_dfs.with_columns(expr.alias(res_id))
            
        output_res = list(self.CONSUMPTION_FORMULAS.keys())
        
        long_consumption = res_dfs.select(["country_id"] + output_res).melt(
            id_vars="country_id",
            value_vars=output_res,
            variable_name="game_resource_id",
            value_name="consumption_usd"
        )
        
        return long_consumption

    def _build_resource_ledger(self, state: GameState):
        """
        Builds a dynamically aggregated resource ledger.
        Now seamlessly integrates outputs from the TradeSystem to reflect global flows.
        """
        prod_table = state.get_table("domestic_production")
        trade_table = state.get_table("trade_network")

        prod_usd = prod_table.group_by(["country_id", "game_resource_id"]).agg(
            pl.col("domestic_production").sum().alias("production_usd")
        )
        
        # Aggregate real trade flows generated by TradeSystem in the previous phase
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

        consumption_table = self._calculate_formulaic_consumption(state)
        
        ledger = prod_usd.join(net_trade, on=["country_id", "game_resource_id"], how="full", coalesce=True)
        ledger = ledger.join(consumption_table, on=["country_id", "game_resource_id"], how="full", coalesce=True)

        ledger = ledger.with_columns(
            pl.col(["production_usd", "trade_usd", "export_usd", "import_usd", "consumption_usd"]).fill_null(0.0)
        )

        # Balance reflects supply vs demand after all market actions
        ledger = ledger.with_columns(
            (pl.col("production_usd") + pl.col("import_usd") - pl.col("export_usd") - pl.col("consumption_usd")).alias("balance_usd")
        )

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
        Updates national GDP and Government Budget via Internal Taxation.
        The Private Sector pays for internal consumption dynamically, which TradeSystem handles.
        """
        if "domestic_production" not in state.tables or "countries" not in state.tables:
            return

        prod_table = state.get_table("domestic_production")
        countries = state.get_table("countries")
        
        # Ensure macro metrics exist for TradeSystem (Economic Health)
        if "economic_health" not in countries.columns:
            countries = countries.with_columns(pl.lit(1.0).alias("economic_health"))

        prod_val = prod_table.group_by("country_id").agg(
            (pl.col("domestic_production") * fraction).sum().alias("production_income"),
            pl.col("domestic_production").sum().alias("gdp") 
        ).rename({"country_id": "id"})

        pop_data = self._get_population(state).rename({"country_id": "id"})
        prod_val = prod_val.join(pop_data, on="id", how="left").fill_null(0)
        prod_val = prod_val.with_columns(
            pl.when(pl.col("population") > 0)
            .then(pl.col("gdp") / pl.col("population"))
            .otherwise(0.0)
            .alias("gdp_per_capita")
        )

        cols_to_drop = [c for c in ["gdp", "gdp_per_capita"] if c in countries.columns]
        if cols_to_drop:
            countries = countries.drop(cols_to_drop)

        updated_countries = countries.join(prod_val.select(["id", "production_income", "gdp", "gdp_per_capita"]), on="id", how="left").fill_null(0)
        
        # Internal Taxation mechanic: The government budget collects a flat % of generated GDP.
        # Private consumption costs are NO LONGER drained directly from the state budget.
        internal_tax_rate = 0.20 # 20% flat baseline tax for state budget
        updated_countries = updated_countries.with_columns(
            (pl.col("money_reserves") + (pl.col("production_income") * internal_tax_rate)).alias("money_reserves")
        )

        state.update_table("countries", updated_countries.drop(["production_income"]))

        # Base organic industrial growth over time
        prod_table = prod_table.with_columns(
            (pl.col("domestic_production") * (1.0 + (0.025 * fraction))).alias("domestic_production")
        )
        state.update_table("domestic_production", prod_table)