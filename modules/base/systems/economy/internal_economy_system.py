import numpy as np
import polars as pl
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE
from src.shared.state import GameState
from src.shared.numeric import stable_group_sum, stable_group_sums, stable_total
from src.shared.frames import ensure_sorted
from modules.base.systems.world.random_event_effects import aggregate_active_effects
from modules.base.systems.economy.consumption_fast_path import (
    ConsumptionLayoutCache,
    calculate_formulaic_consumption as calculate_formulaic_consumption_fast,
)
from modules.base.systems.economy.input_validation import validate_numeric_columns
from modules.base.systems.economy.aligned_economy_fast_path import (
    AlignedEconomyLayoutCache,
    update_aligned_economy_tables,
)
from modules.base.systems.politics.political_effect_policy import (
    aggregate_political_effects_by_type,
    bounded_modifier,
)
from src.shared.events import EventRealSecond
from src.shared.actions import ActionUpdateResourcePolicy
from src.shared.economy_meta import RESOURCE_MAPPING

_RESOURCE_LEDGER_METADATA = pl.DataFrame(
    [
        {
            "game_resource_id": resource_id,
            "category": values["category"],
            "unit_str": values["unit"],
        }
        for resource_id, values in RESOURCE_MAPPING.items()
    ]
)
_CONSUMPTION_CALC_ORDER = (
    "health_services", "recreational_services", "construction_services",
    "fossil_fuels", "minerals", "precious_stones", "appliances", "vehicles",
    "commodities", "luxury_commodities", "dairy", "meat_and_fish",
    "vegetables_and_fruits", "tobacco", "drugs_and_raw_plants", "business_services",
    "pharmaceuticals", "transport_services", "wood_and_paper", "industrial_services",
    "machinery_and_instruments", "iron_and_steel", "plastics_and_rubber",
    "fabrics_and_leather", "cereals", "chemicals", "electricity",
    "education_services", "government_services", "financial_services",
    "it_and_telecom_services", "tourism_services", "arms_and_ammunition",
    "other_food_and_beverages", "non_ferrous_metals", "construction_materials",
)


class InternalEconomySystem(ISystem):
    """
    Handles internal macroeconomic simulation, including domestic production value 
    generation, base internal taxation, and calculating national demand (consumption).
    Now features Dynamic Wealth Anchoring, Propensity to Consume, and Income Elasticity.
    """

    access = SystemAccess(
        reads=frozenset({'countries', 'domestic_production', 'regions', 'units', 'random_event_effects', 'political_effects'}),
        writes=frozenset({'countries', 'domestic_production', 'resource_ledger'}),
        handles=frozenset({ActionUpdateResourcePolicy}),
        phase=SystemPhase.ECONOMY,
    )
    
    runtime_state_contract = {
        "_missing_columns": SYSTEM_STATE_CACHE,
        "_population_cache_source": SYSTEM_STATE_CACHE,
        "_population_cache_revision": SYSTEM_STATE_CACHE,
        "_population_cache": SYSTEM_STATE_CACHE,
        "_production_layout_cache": SYSTEM_STATE_CACHE,
        "_consumption_layout_cache": SYSTEM_STATE_CACHE,
    }

    def __init__(self):
        self._missing_columns = set()
        self._population_cache_source: pl.DataFrame | None = None
        self._population_cache_revision: int | None = None
        self._population_cache: pl.DataFrame | None = None
        self._production_layout_cache: AlignedEconomyLayoutCache | None = None
        self._consumption_layout_cache = ConsumptionLayoutCache()

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

    # TOTAL BASELINE BASKET = 1,000 POINTS (100%). 10 points = 1% of the consumer's baseline budget.
    # Pattern: C = ((SolventPopulation * solvent_base * (WI^Elasticity)) + Population * general_base) * multiplier + deps
    CONSUMPTION_FORMULAS = {
        # --- FOOD & AGRO (Target: ~120 points / 12% of the economy) ---
        "cereals": {"solvent_base_consumption": 5.0, "general_base_consumption": 15.0, "resource_dependencies": {"dairy": 0.01, "meat_and_fish": 0.05}, "output_multiplier": 0.94, "income_elasticity": 0.2}, # 2% (mostly general)
        "vegetables_and_fruits": {"solvent_base_consumption": 15.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.4}, # 2.5%
        "meat_and_fish": {"solvent_base_consumption": 20.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.6}, # 3%
        "dairy": {"solvent_base_consumption": 15.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.5}, # 2.5%
        "tobacco": {"solvent_base_consumption": 6.0, "general_base_consumption": 4.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.5}, # 1%
        "drugs_and_raw_plants": {"solvent_base_consumption": 3.0, "general_base_consumption": 2.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.5}, # 0.5%
        "other_food_and_beverages": {"solvent_base_consumption": 20.0, "general_base_consumption": 15.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.7}, # 3.5%

        # --- ENERGY (Target: ~80 points / 8% of the economy) ---
        "electricity": {
            "solvent_base_consumption": 20.0, "general_base_consumption": 20.0, "output_multiplier": 0.78, "income_elasticity": 1.0, # 4%
            "resource_dependencies": {
                "wood_and_paper": 0.02, "plastics_and_rubber": 0.04, "fabrics_and_leather": 0.02,
                "chemicals": 0.01, "pharmaceuticals": 0.02, "appliances": 0.04,
                "vehicles": 0.02, "machinery_and_instruments": 0.02, "commodities": 0.01,
                "luxury_commodities": 0.02
            }
        },
        "fossil_fuels": {"solvent_base_consumption": 25.0, "general_base_consumption": 15.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 0.8}, # 4%

        # --- READY-MADE GOODS (Target: ~180 points / 18% of the economy) ---
        "vehicles": {"solvent_base_consumption": 35.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.5}, # 4%
        "commodities": {"solvent_base_consumption": 30.0, "general_base_consumption": 20.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 5% (clothing, household items)
        "appliances": {"solvent_base_consumption": 20.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.2}, # 2.5%
        "pharmaceuticals": {"solvent_base_consumption": 20.0, "general_base_consumption": 10.0, "resource_dependencies": {"health_services": 0.04}, "output_multiplier": 0.96, "income_elasticity": 0.8}, # 3%
        "machinery_and_instruments": {
            "solvent_base_consumption": 15.0, "general_base_consumption": 2.0, "output_multiplier": 0.84, "income_elasticity": 1.2, # 1.7%
            "resource_dependencies": {"construction_services": 0.05, "fossil_fuels": 0.03, "wood_and_paper": 0.02, "minerals": 0.05, "precious_stones": 0.01}
        },
        "luxury_commodities": {"solvent_base_consumption": 15.0, "general_base_consumption": 0.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 2.0}, # 1.5% (only solvent)
        "arms_and_ammunition": {"solvent_base_consumption": 2.0, "general_base_consumption": 1.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 0.3%

        # --- SERVICES (Target: ~600 points / 60% of the economy) ---
        "health_services": {"solvent_base_consumption": 80.0, "general_base_consumption": 40.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.1}, # 12%
        "government_services": {"solvent_base_consumption": 50.0, "general_base_consumption": 50.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 10%
        "construction_services": {"solvent_base_consumption": 60.0, "general_base_consumption": 20.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.1}, # 8%
        "financial_services": {"solvent_base_consumption": 50.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.5}, # 6%
        "education_services": {"solvent_base_consumption": 35.0, "general_base_consumption": 25.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 6%
        "business_services": {"solvent_base_consumption": 40.0, "general_base_consumption": 10.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.2}, # 5%
        "it_and_telecom_services": {"solvent_base_consumption": 35.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.4}, # 4%
        "recreational_services": {"solvent_base_consumption": 25.0, "general_base_consumption": 5.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.8}, # 3%
        "tourism_services": {"solvent_base_consumption": 25.0, "general_base_consumption": 0.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 2.0}, # 2.5%
        "industrial_services": {"solvent_base_consumption": 20.0, "general_base_consumption": 5.0, "resource_dependencies": {"construction_services": 0.02}, "output_multiplier": 0.98, "income_elasticity": 1.0}, # 2.5%
        "transport_services": {"solvent_base_consumption": 5.0, "general_base_consumption": 5.0, "resource_dependencies": {"recreational_services": 0.02}, "output_multiplier": 0.98, "income_elasticity": 1.0}, # 1%

        # --- RAW MATERIALS & MATERIALS (Target: ~20 points / 2% of DIRECT consumption, the rest through factories) ---
        "construction_materials": {"solvent_base_consumption": 8.0, "general_base_consumption": 2.0, "resource_dependencies": {"construction_services": 0.08}, "output_multiplier": 1.0, "income_elasticity": 1.1}, # 1%
        "chemicals": {"solvent_base_consumption": 3.0, "general_base_consumption": 2.0, "resource_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02, "plastics_and_rubber": 0.01, "pharmaceuticals": 0.01}, "output_multiplier": 0.95, "income_elasticity": 1.0}, # 0.5%
        "fabrics_and_leather": {"solvent_base_consumption": 2.0, "general_base_consumption": 1.0, "resource_dependencies": {"commodities": 0.01, "luxury_commodities": 0.05}, "output_multiplier": 0.94, "income_elasticity": 1.0}, # 0.3%
        "iron_and_steel": {"solvent_base_consumption": 1.0, "general_base_consumption": 1.0, "resource_dependencies": {"appliances": 0.04, "vehicles": 0.04, "machinery_and_instruments": 0.04, "construction_services": 0.06}, "output_multiplier": 0.82, "income_elasticity": 1.0}, # 0.2%
        "plastics_and_rubber": {"solvent_base_consumption": 1.0, "general_base_consumption": 1.0, "resource_dependencies": {"luxury_commodities": 0.01, "commodities": 0.02}, "output_multiplier": 0.97, "income_elasticity": 1.0}, # 0.2%
        "wood_and_paper": {"solvent_base_consumption": 1.0, "general_base_consumption": 1.0, "resource_dependencies": {"construction_services": 0.04}, "output_multiplier": 0.96, "income_elasticity": 0.9}, # 0.2%
        "minerals": {"solvent_base_consumption": 1.0, "general_base_consumption": 1.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 0.2%
        "non_ferrous_metals": {"solvent_base_consumption": 1.0, "general_base_consumption": 0.0, "resource_dependencies": {"machinery_and_instruments": 0.02}, "output_multiplier": 1.0, "income_elasticity": 1.0}, # 0.1%
        "precious_stones": {"solvent_base_consumption": 1.0, "general_base_consumption": 0.0, "resource_dependencies": {}, "output_multiplier": 1.0, "income_elasticity": 1.8}, # 0.1%
    }

    def update(self, state: GameState, delta_time: float) -> None:
        # 1. Process Actions
        for action in state.current_actions:
            if isinstance(action, ActionUpdateResourcePolicy):
                self._handle_update_resource_policy(state, action)

        rebuild_ledger = False
        
        if "resource_ledger" not in state.tables and "domestic_production" in state.tables and "trade_network" in state.tables:
            rebuild_ledger = True

        real_sec_events = [e for e in state.events if isinstance(e, EventRealSecond)]
        population = self._get_population(state) if "regions" in state.tables else None
        
        for event in real_sec_events:
            if event.is_paused or event.game_seconds_passed <= 0:
                continue
            
            fraction_of_year = event.game_seconds_passed / (365.25 * 24 * 3600)
            self._process_economy(state, fraction_of_year, population)
            
            if "domestic_production" in state.tables:
                rebuild_ledger = True
                
        if rebuild_ledger:
            self._build_resource_ledger(state, population)

    def _handle_update_resource_policy(self, state: GameState, action: ActionUpdateResourcePolicy) -> None:
        if "domestic_production" not in state.tables:
            return

        df = state.get_table("domestic_production")
        expressions = []
        if "is_gov_controlled" not in df.columns:
            expressions.append(pl.lit(False).alias("is_gov_controlled"))
        if "is_legal" not in df.columns:
            expressions.append(pl.lit(True).alias("is_legal"))
        if "tax_rate" not in df.columns:
            expressions.append(pl.lit(0.0).alias("tax_rate"))
        if expressions:
            df = df.with_columns(expressions)

        tax_rate = max(0.0, min(1.0, float(action.tax_rate)))
        target = (
            (pl.col("country_id") == action.country_tag)
            & (pl.col("game_resource_id") == action.resource_id)
        )

        updated = df.with_columns([
            pl.when(target)
            .then(pl.lit(bool(action.is_gov_controlled)))
            .otherwise(pl.col("is_gov_controlled"))
            .alias("is_gov_controlled"),
            pl.when(target)
            .then(pl.lit(bool(action.is_legal)))
            .otherwise(pl.col("is_legal"))
            .alias("is_legal"),
            pl.when(target)
            .then(pl.lit(tax_rate))
            .otherwise(pl.col("tax_rate"))
            .alias("tax_rate"),
        ])
        state.update_table("domestic_production", updated)

    def _get_population(self, state: GameState) -> pl.DataFrame:
        regions = state.get_table("regions")
        revision = state.table_revisions.get("regions", id(regions))
        if (
            self._population_cache_source is regions
            and self._population_cache_revision == revision
            and self._population_cache is not None
        ):
            return self._population_cache
        
        # Ensure core population columns exist
        required = ["pop_14", "pop_15_64", "pop_65"]
        for col in required:
            if col not in regions.columns:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found in 'regions'. Defaulting to 0.")
                    self._missing_columns.add(col)
                regions = regions.with_columns(pl.lit(0).alias(col))

        population = regions.group_by("owner").agg(
            (pl.col("pop_14").fill_null(0) + pl.col("pop_15_64").fill_null(0) + pl.col("pop_65").fill_null(0)).sum().alias("population")
        ).rename({"owner": "country_id"})
        self._population_cache_source = state.get_table("regions")
        self._population_cache_revision = revision
        self._population_cache = population
        return population

    def _calculate_formulaic_consumption(
        self,
        state: GameState,
        population: pl.DataFrame | None = None,
    ) -> pl.DataFrame:
        """
        Calculates annual consumption (Demand) per country/resource dynamically.
        Uses a Global GDP Anchor, Propensity to Consume logic, and Income Elasticity
        to ensure countries only demand what their economies can realistically afford.
        """
        countries = state.get_table("countries")
        country_columns = set(countries.columns)
        population_data = population if population is not None else self._get_population(state)

        required_metrics = {
            "poverty_rate": 0.0,
            "human_dev": 0.5,
            "gdp_per_capita": 1000.0,
            "real_income_index": 1.0,
            "economic_trade_modifier": 1.0,
        }
        
        default_expressions = []
        for col, default in required_metrics.items():
            if col not in country_columns:
                if col not in self._missing_columns:
                    print(f"[{self.id}] Column '{col}' not found in 'countries'. Defaulting to {default}.")
                self._missing_columns.add(col)
                default_expressions.append(pl.lit(default).alias(col))

        random_event_effects = state.tables.get("random_event_effects")
        if random_event_effects is None or random_event_effects.is_empty():
            # The aligned calculation validates full source columns while extracting its arrays.
            optimized = calculate_formulaic_consumption_fast(
                countries,
                population_data,
                self.CONSUMPTION_FORMULAS,
                _CONSUMPTION_CALC_ORDER,
                self._consumption_layout_cache,
            )
            if optimized is not None:
                return optimized

        # Irregular schemas and effect-aware calculations retain the general validator.
        validate_numeric_columns(
            countries,
            "countries",
            (
                "gdp",
                "gdp_per_capita",
                "poverty_rate",
                "human_dev",
                "real_income_index",
                "economic_trade_modifier",
            ),
            nonnegative=("gdp", "gdp_per_capita"),
        )
        validate_numeric_columns(
            population_data,
            "population",
            ("population",),
            nonnegative=("population",),
        )

        countries_lf = countries.lazy()
        if default_expressions:
            countries_lf = countries_lf.with_columns(default_expressions)
        metric_expressions = [
            pl.col("id").alias("country_id"),
            pl.col("poverty_rate").fill_null(0.0),
            pl.col("human_dev").fill_null(0.5),
            pl.col("gdp_per_capita").fill_null(1000.0),
            pl.col("real_income_index").fill_null(1.0).clip(0.0, 2.0),
            pl.col("economic_trade_modifier").fill_null(1.0).clip(0.5, 1.0),
        ]
        if "gdp" in country_columns:
            metric_expressions.append(pl.col("gdp").cast(pl.Float64, strict=False))
        metrics_lf = countries_lf.select(*metric_expressions)

        data_lf = population_data.lazy().join(metrics_lf, on="country_id", how="inner")

        demand_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            int(state.time.total_minutes),
            categories={"demand"},
            subject_type="country",
        )
        if demand_effects:
            demand_rows = [
                {
                    "country_id": subject_id,
                    "_event_demand_modifier": max(-0.5, min(0.5, magnitude)),
                }
                for (_, subject_id, _), magnitude in demand_effects.items()
            ]
            data_lf = data_lf.join(pl.DataFrame(demand_rows).lazy(), on="country_id", how="left").with_columns(
                pl.col("_event_demand_modifier").fill_null(0.0)
            )
        else:
            data_lf = data_lf.with_columns(pl.lit(0.0).alias("_event_demand_modifier"))
        
        # --- 1. DYNAMIC ANCHOR & CONSUMPTION POOL ---
        # Calculate total GDP to find the global average
        # Keep budgets anchored to authoritative national GDP; legacy states may only carry GDP per capita.
        total_gdp = (
            pl.col("gdp").cast(pl.Float64, strict=False).fill_null(
                pl.col("gdp_per_capita") * pl.col("population")
            )
            if "gdp" in country_columns
            else pl.col("gdp_per_capita") * pl.col("population")
        )
        data = data_lf.with_columns(total_gdp.alias("total_gdp")).collect()

        total_gdp_sum = stable_total(data["total_gdp"]) if not data.is_empty() else 0.0
        total_pop_sum = data["population"].sum() if not data.is_empty() else 1.0

        # The zero-mile marker for global wealth, minimum $100.
        global_avg_gdp_pc = max(total_gdp_sum / max(total_pop_sum, 1.0), 100.0)

        # Reuse the materialized country/population join instead of rerunning it
        # when the complete demand matrix is collected below.
        data_lf = data.lazy()

        # Calculate Wealth Index (WI) and Propensity to Consume.
        data_lf = data_lf.with_columns(
            (pl.col("gdp_per_capita") / global_avg_gdp_pc).clip(0.05, 10.0).alias("wealth_index")
        )
        
        data_lf = data_lf.with_columns(
            (pl.col("population") * (1.0 - pl.col("poverty_rate")) * pl.col("human_dev")).alias("solvent_population"),
            # Propensity formula: Poor countries spend ~90% GDP on consumption, rich ~55%
            (
                pl.col("total_gdp")
                * (0.50 + (0.40 / (1.0 + pl.col("wealth_index"))))
                * pl.col("real_income_index")
                * pl.col("economic_trade_modifier")
                * (1.0 + pl.col("_event_demand_modifier").clip(-0.5, 0.5))
            ).alias("total_consumption_pool")
        )
        
        calc_order = list(_CONSUMPTION_CALC_ORDER)
        
        res_dfs = data_lf
        raw_demand_cols = list(calc_order)

        # --- 2. RAW DEMAND CALCULATION WITH ELASTICITY ---
        pending = list(calc_order)
        computed: set[str] = set()
        initial_columns = (
            set(population_data.columns)
            | set(required_metrics)
            | {
                "country_id",
                "_event_demand_modifier",
                "total_gdp",
                "wealth_index",
                "solvent_population",
                "total_consumption_pool",
            }
        )
        while pending:
            ready = [
                res_id
                for res_id in pending
                if all(
                    dependency in computed
                    or dependency in initial_columns
                    or dependency not in self.CONSUMPTION_FORMULAS
                    for dependency in self.CONSUMPTION_FORMULAS[res_id]
                    .get("resource_dependencies", {})
                )
            ]
            if not ready:
                unresolved = ", ".join(pending)
                raise ValueError(
                    f"Cyclic resource demand dependencies: {unresolved}"
                )

            expressions = []
            for res_id in ready:
                formula = self.CONSUMPTION_FORMULAS[res_id]
                elasticity = formula.get("income_elasticity", 1.0)

                # Elasticity changes only the solvent population's demand.
                expression = (
                    pl.col("solvent_population")
                    * formula["solvent_base_consumption"]
                    * (pl.col("wealth_index") ** elasticity)
                    + pl.col("population") * formula["general_base_consumption"]
                ) * formula["output_multiplier"]

                for dependency, coefficient in formula.get(
                    "resource_dependencies", {}
                ).items():
                    if dependency in computed or dependency in initial_columns:
                        expression = expression + pl.col(dependency) * coefficient
                expressions.append(expression.alias(res_id))

            # The lazy plan keeps dependency stages but materializes the full demand matrix once.
            res_dfs = res_dfs.with_columns(expressions)
            computed.update(ready)
            pending = [res_id for res_id in pending if res_id not in computed]
            
        # --- 3. NORMALIZATION TO FIT THE POOL ---
        # Sum all raw demands to find what the population "wants"
        res_dfs = res_dfs.with_columns(
            pl.sum_horizontal(raw_demand_cols).alias("total_raw_demand")
        )
        
        # Create a compression ratio: what they can afford / what they want
        res_dfs = res_dfs.with_columns(
            pl.when(pl.col("total_raw_demand") > 0)
            .then(pl.col("total_consumption_pool") / pl.col("total_raw_demand"))
            .otherwise(0.0)
            .alias("normalization_factor")
        )
        
        # Compress (or expand) all requests to perfectly match their real economic capacity
        res_dfs = res_dfs.with_columns(
            [
                (pl.col(res_id) * pl.col("normalization_factor")).alias(res_id)
                for res_id in raw_demand_cols
            ]
        )
            
        # Format output
        return res_dfs.select(["country_id"] + raw_demand_cols).unpivot(
            index="country_id",
            on=raw_demand_cols,
            variable_name="game_resource_id",
            value_name="consumption_usd",
        ).collect()

    def _build_resource_ledger(
        self,
        state: GameState,
        population: pl.DataFrame | None = None,
    ):
        """
        Builds a dynamically aggregated resource ledger.
        Now seamlessly integrates outputs from the TradeSystem to reflect global flows.
        """
        prod_table = state.get_table("domestic_production")
        consumption_table = self._calculate_formulaic_consumption(state, population)
        fast_ledger = self._build_resource_ledger_without_trade(
            prod_table,
            state.tables.get("trade_network"),
            consumption_table,
        )
        if fast_ledger is not None:
            state.update_table("resource_ledger", fast_ledger)
            return

        prod_usd = stable_group_sum(
            prod_table,
            ("country_id", "game_resource_id"),
            "domestic_production",
            "production_usd",
        )
        
        # Aggregate real trade flows generated by TradeSystem in the previous phase
        if "trade_network" in state.tables:
            trade_table = state.get_table("trade_network")
            flow_rows = pl.concat(
                [
                    trade_table.select(
                        pl.col("exporter_id").alias("country_id"),
                        "game_resource_id",
                        pl.col("trade_value_usd").alias("export_usd"),
                        pl.lit(None, dtype=pl.Float64).alias("import_usd"),
                    ),
                    trade_table.select(
                        pl.col("importer_id").alias("country_id"),
                        "game_resource_id",
                        pl.lit(None, dtype=pl.Float64).alias("export_usd"),
                        pl.col("trade_value_usd").alias("import_usd"),
                    ),
                ],
                how="vertical",
            )
            net_trade = stable_group_sums(
                flow_rows,
                ("country_id", "game_resource_id"),
                {
                    "export_usd": "export_usd",
                    "import_usd": "import_usd",
                },
            ).with_columns(
                pl.col(["export_usd", "import_usd"]).fill_null(0.0),
                (pl.col("export_usd") - pl.col("import_usd")).alias("trade_usd"),
            )
        else:
            net_trade = pl.DataFrame(
                schema={
                    "country_id": pl.Utf8,
                    "game_resource_id": pl.Utf8,
                    "export_usd": pl.Float64,
                    "import_usd": pl.Float64,
                    "trade_usd": pl.Float64,
                }
            )

        ledger = (
            prod_usd.lazy()
            .join(
                net_trade.lazy(),
                on=["country_id", "game_resource_id"],
                how="full",
                coalesce=True,
            )
            .join(
                consumption_table.lazy(),
                on=["country_id", "game_resource_id"],
                how="full",
                coalesce=True,
            )
            .with_columns(
                pl.col(
                    [
                        "production_usd",
                        "trade_usd",
                        "export_usd",
                        "import_usd",
                        "consumption_usd",
                    ]
                ).fill_null(0.0)
            )
            .with_columns(
                (
                    pl.col("production_usd")
                    + pl.col("import_usd")
                    - pl.col("export_usd")
                    - pl.col("consumption_usd")
                ).alias("balance_usd")
            )
        )

        cols_to_drop = ["avg_price", "base_price", "quality_index", "export_usd", "import_usd"]
        ledger = ledger.drop(cols_to_drop, strict=False)
        
        ledger = (
            ledger.join(_RESOURCE_LEDGER_METADATA.lazy(), on="game_resource_id", how="left")
            .with_columns(
                pl.col("category").fill_null("Unclassified"),
                pl.col("unit_str").fill_null("units"),
            )
        )

        state.update_table(
            "resource_ledger",
            ensure_sorted(ledger.collect(), ("country_id", "game_resource_id")),
        )

    def _build_resource_ledger_without_trade(
        self,
        production: pl.DataFrame,
        trade_network: pl.DataFrame | None,
        consumption: pl.DataFrame,
    ) -> pl.DataFrame | None:
        """Avoid general full joins when the aligned market contains no trade flows."""
        keys = ("country_id", "game_resource_id")
        if (
            (trade_network is not None and not trade_network.is_empty())
            or not set(keys + ("domestic_production",)).issubset(production.columns)
            or not set(keys + ("consumption_usd",)).issubset(consumption.columns)
            or production.height != consumption.height
        ):
            return None

        production_country_ids = production.get_column("country_id")
        production_resource_ids = production.get_column("game_resource_id")
        cache = self._production_layout_cache
        cache_hit = (
            cache is not None
            and cache.production_country_ids.equals(production_country_ids)
            and cache.production_resource_ids.equals(production_resource_ids)
            and cache.production_country_ids.equals(
                consumption.get_column("country_id")
            )
            and cache.production_resource_ids.equals(
                consumption.get_column("game_resource_id")
            )
        )
        if cache_hit:
            production_values = (
                production.get_column("domestic_production")
                .cast(pl.Float64, strict=False)
                .fill_null(0.0)
                .to_numpy()
            )
            consumption_values = (
                consumption.get_column("consumption_usd")
                .cast(pl.Float64, strict=False)
                .fill_null(0.0)
                .to_numpy()
            )
            ledger = cache.ledger_metadata.with_columns(
                pl.Series("production_usd", production_values),
                pl.Series("trade_usd", np.zeros(production.height, dtype=np.float64)),
                pl.Series("consumption_usd", consumption_values),
                pl.Series(
                    "balance_usd",
                    production_values - consumption_values,
                ),
            )
            return ledger.select(
                "country_id",
                "game_resource_id",
                "production_usd",
                "trade_usd",
                "consumption_usd",
                "balance_usd",
                "category",
                "unit_str",
            )

        if (
            not production.select(keys).equals(consumption.select(keys))
            or production.select(pl.struct(keys).is_duplicated().any()).item()
        ):
            return None

        production_values = (
            production.get_column("domestic_production")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
        consumption_values = (
            consumption.get_column("consumption_usd")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
        ledger = pl.DataFrame(
            {
                "country_id": production.get_column("country_id"),
                "game_resource_id": production.get_column("game_resource_id"),
                "production_usd": production_values,
                "trade_usd": pl.Series("trade_usd", [0.0] * production.height),
                "consumption_usd": consumption_values,
                "balance_usd": production_values - consumption_values,
            }
        ).join(_RESOURCE_LEDGER_METADATA, on="game_resource_id", how="left").with_columns(
            pl.col("category").fill_null("Unclassified"),
            pl.col("unit_str").fill_null("units"),
        )
        return ensure_sorted(ledger, keys)

    def _process_economy(
        self,
        state: GameState,
        fraction: float,
        population: pl.DataFrame | None = None,
    ):
        """
        Updates national GDP and Government Budget via Internal Taxation.
        The Private Sector pays for internal consumption dynamically, which TradeSystem handles.
        """
        if "domestic_production" not in state.tables or "countries" not in state.tables:
            return

        if self._try_process_aligned_economy(state, fraction, population):
            return

        prod_table = state.get_table("domestic_production")
        countries = state.get_table("countries")
        country_schema = set(countries.columns)
        countries_lf = countries.lazy()

        # Ensure macro metrics exist for TradeSystem (Economic Health).
        if "economic_health" not in country_schema:
            countries_lf = countries_lf.with_columns(pl.lit(1.0).alias("economic_health"))

        production_basis_lf = prod_table.lazy()
        infrastructure = state.tables.get("regional_infrastructure")
        if infrastructure is not None and not infrastructure.is_empty():
            if "industrial_access_index" in country_schema:
                industrial_access_lf = countries_lf.select(
                    pl.col("id"),
                    pl.col("industrial_access_index").clip(0.0, 1.0).alias("_industrial_access"),
                )
                production_basis_lf = production_basis_lf.join(
                    industrial_access_lf,
                    left_on="country_id",
                    right_on="id",
                    how="left",
                ).with_columns(
                    # Infrastructure limits throughput but does not switch an established economy off.
                    (pl.col("domestic_production") * (0.75 + 0.25 * pl.col("_industrial_access").fill_null(1.0)))
                    .alias("_effective_production")
                )
            else:
                production_basis_lf = production_basis_lf.with_columns(
                    pl.col("domestic_production").alias("_effective_production")
                )
        else:
            production_basis_lf = production_basis_lf.with_columns(
                pl.col("domestic_production").alias("_effective_production")
            )

        political_effects = state.tables.get("political_effects")
        now = int(state.time.total_minutes)
        political_outputs = (
            aggregate_political_effects_by_type(
                political_effects,
                now,
                selectors={
                    ("economy", "production_modifier"),
                    ("labor", "labor_supply_modifier"),
                },
            )
            if political_effects is not None and not political_effects.is_empty()
            else {}
        )
        political_production = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("economy", "production_modifier")
        }
        political_labor = {
            country_id: value
            for (country_id, domain, effect), value in political_outputs.items()
            if (domain, effect) == ("labor", "labor_supply_modifier")
        }
        political_rows = []
        if political_production or political_labor:
            political_rows = [
                {
                    "_modifier_country_id": country_id,
                    "_political_production_modifier": bounded_modifier(
                        political_production.get(country_id, 0.0)
                    ),
                    "_political_labor_modifier": bounded_modifier(
                        political_labor.get(country_id, 0.0)
                    ),
                }
                for country_id in sorted(set(political_production) | set(political_labor))
            ]
        has_country_modifier = "economic_production_modifier" in country_schema
        if has_country_modifier or political_rows:
            production_modifier = (
                pl.col("economic_production_modifier").fill_null(1.0).clip(0.5, 1.0)
                if has_country_modifier
                else pl.lit(1.0)
            )
            production_modifiers_lf = countries_lf.select(
                pl.col("id").alias("_modifier_country_id"),
                production_modifier.alias("_economic_production_modifier"),
            )
            if political_rows:
                production_modifiers_lf = production_modifiers_lf.join(
                    pl.DataFrame(political_rows).lazy(),
                    on="_modifier_country_id",
                    how="left",
                ).with_columns(
                    pl.col("_political_production_modifier").fill_null(1.0),
                    pl.col("_political_labor_modifier").fill_null(1.0),
                )
            else:
                production_modifiers_lf = production_modifiers_lf.with_columns(
                    pl.lit(1.0).alias("_political_production_modifier"),
                    pl.lit(1.0).alias("_political_labor_modifier"),
                )
            production_basis_lf = production_basis_lf.join(
                production_modifiers_lf,
                left_on="country_id",
                right_on="_modifier_country_id",
                how="left",
            ).with_columns(
                (
                    pl.col("_effective_production")
                    * pl.col("_economic_production_modifier").fill_null(1.0)
                    * pl.col("_political_production_modifier").fill_null(1.0)
                    * pl.col("_political_labor_modifier").fill_null(1.0)
                ).alias("_effective_production")
            )

        production_effects = aggregate_active_effects(
            state.tables.get("random_event_effects"),
            int(state.time.total_minutes),
            categories={"production"},
            subject_type="country",
        )
        event_multipliers = {
            subject_id: max(0.5, min(1.5, 1.0 + magnitude))
            for (_, subject_id, _), magnitude in production_effects.items()
        }
        if event_multipliers:
            event_modifier_frame = pl.DataFrame(
                {
                    "_event_country_id": list(event_multipliers),
                    "_event_production_modifier": list(event_multipliers.values()),
                }
            )
            production_basis_lf = production_basis_lf.join(
                event_modifier_frame.lazy(),
                left_on="country_id",
                right_on="_event_country_id",
                how="left",
            ).with_columns(
                (
                    pl.col("_effective_production")
                    * pl.col("_event_production_modifier").fill_null(1.0)
                ).alias("_effective_production")
            )

        production_basis = production_basis_lf.with_columns(
            (pl.col("_effective_production") * fraction).alias("_production_income")
        ).collect()
        prod_val = stable_group_sums(
            production_basis,
            ("country_id",),
            {
                "_production_income": "production_income",
                "_effective_production": "gdp",
            },
        ).rename({"country_id": "id"})

        pop_data = (population if population is not None else self._get_population(state)).rename(
            {"country_id": "id"}
        )
        prod_val_lf = prod_val.lazy().join(pop_data.lazy(), on="id", how="left").with_columns(
            pl.col(["production_income", "gdp", "population"]).fill_null(0)
        )
        prod_val_lf = prod_val_lf.with_columns(
            pl.when(pl.col("population") > 0)
            .then(pl.col("gdp") / pl.col("population"))
            .otherwise(0.0)
            .alias("gdp_per_capita")
        )

        if "internal_tax_rate" not in country_schema:
            if "internal_tax_rate" not in self._missing_columns:
                print(f"[{self.id}] Column 'internal_tax_rate' not found in 'countries'. Defaulting to 0.20.")
                self._missing_columns.add("internal_tax_rate")
            countries_lf = countries_lf.with_columns(pl.lit(0.20).alias("internal_tax_rate"))
        if "industrial_growth_rate" not in country_schema:
            if "industrial_growth_rate" not in self._missing_columns:
                print(f"[{self.id}] Column 'industrial_growth_rate' not found in 'countries'. Defaulting to 0.025.")
                self._missing_columns.add("industrial_growth_rate")
            countries_lf = countries_lf.with_columns(pl.lit(0.025).alias("industrial_growth_rate"))

        updated_countries_lf = countries_lf.drop(["gdp", "gdp_per_capita"], strict=False).join(
            prod_val_lf.select("id", "production_income", "gdp", "gdp_per_capita"),
            on="id",
            how="left",
        ).with_columns(
            pl.col(["production_income", "gdp", "gdp_per_capita"]).fill_null(0)
        )
        updated_countries = updated_countries_lf.with_columns(
            (
                pl.col("money_reserves")
                + pl.col("production_income") * pl.col("internal_tax_rate").fill_null(0.20)
            ).alias("money_reserves")
        ).drop("production_income").sort("id").collect()
        state.update_table("countries", updated_countries)

        # Base organic industrial growth over time.
        prod_table_lf = prod_table.lazy().join(
            updated_countries.lazy().select("id", "industrial_growth_rate"),
            left_on="country_id",
            right_on="id",
            how="left",
        ).with_columns(
            pl.col("industrial_growth_rate").fill_null(0.025)
        )
        prod_table_lf = prod_table_lf.with_columns(
            (pl.col("domestic_production") * (1.0 + (pl.col("industrial_growth_rate") * fraction))).alias("domestic_production")
        )
        state.update_table(
            "domestic_production",
            prod_table_lf.drop("industrial_growth_rate").collect(),
        )

    def _try_process_aligned_economy(
        self,
        state: GameState,
        fraction: float,
        population: pl.DataFrame | None,
    ) -> bool:
        """Keep the common effect-free dense economy tick out of lazy join plans."""
        infrastructure = state.tables.get("regional_infrastructure")
        if infrastructure is not None and not infrastructure.is_empty():
            return False
        for table_name in ("political_effects", "random_event_effects"):
            table = state.tables.get(table_name)
            if table is not None and not table.is_empty():
                return False
        countries = state.get_table("countries")
        if "economic_production_modifier" in countries.columns:
            return False

        population_data = population
        if population_data is None:
            if "regions" not in state.tables:
                return False
            population_data = self._get_population(state)

        for column, default in (
            ("internal_tax_rate", 0.20),
            ("industrial_growth_rate", 0.025),
        ):
            if column not in countries.columns and column not in self._missing_columns:
                print(
                    f"[{self.id}] Column '{column}' not found in 'countries'. "
                    f"Defaulting to {default:.2f}."
                )
                self._missing_columns.add(column)

        result = update_aligned_economy_tables(
            countries,
            state.get_table("domestic_production"),
            population_data,
            fraction,
            self._production_layout_cache,
        )
        if result is None:
            return False

        state.update_table("countries", result.countries)
        state.update_table("domestic_production", result.production)
        self._production_layout_cache = result.layout_cache
        return True
