import polars as pl
from pathlib import Path
from dataclasses import dataclass
import logging
from typing import Dict, List

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("EconomyGenerator")

# --- MACROECONOMIC CONFIGURATION ---

GAME_MAPPING = {
    "cereals": ["10", "11"],
    "vegetables_and_fruits": ["07", "08", "20"],
    "meat_and_fish": ["01", "02", "03", "16"],
    "dairy": ["04"],
    "tobacco": ["24"],
    "drugs_and_raw_plants": ["06", "09", "12", "13", "14"],
    "other_food_and_beverages": ["05", "15", "17", "18", "19", "21", "22", "23"],
    "electricity": ["2716"],
    "fossil_fuels": [f"{str(i).zfill(2)}" for i in range(2701, 2716)], 
    "wood_and_paper": ["44", "45", "46", "47", "48", "49"],
    "minerals": ["25", "26"],
    "iron_and_steel": ["72", "73"],
    "non_ferrous_metals": ["74", "75", "76", "78", "79", "80", "81"],
    "precious_stones": ["71"],
    "fabrics_and_leather": [
        "41", "42", "43", "50", "51", "52", "53", "54", "55", 
        "56", "57", "58", "59", "60"
    ],
    "plastics_and_rubber": ["39", "40"],
    "chemicals": ["28", "29", "31", "32", "33", "34", "35", "36", "38"],
    "pharmaceuticals": ["30"],
    "construction_materials": ["68", "69", "70"],
    "appliances": ["85"],
    "vehicles": ["86", "87", "88", "89"],
    "machinery_and_instruments": ["84", "90"],
    "commodities": [
        "61", "62", "63", "64", "65", "66", "67", 
        "82", "83", "94", "95", "96"
    ],
    "luxury_commodities": ["91", "92", "97"],
    "arms_and_ammunition": ["93"]
}

# Base per capita consumption (in tons/year) for a baseline country.
# Adjusting these values directly impacts global supply/demand balance in the engine.
CONSUMPTION_MATRIX = {
    "cereals": {"base_req": 0.15, "elasticity": 0.1},
    "vegetables_and_fruits": {"base_req": 0.1, "elasticity": 0.2},
    "meat_and_fish": {"base_req": 0.04, "elasticity": 0.6},
    "dairy": {"base_req": 0.05, "elasticity": 0.4},
    "electricity": {"base_req": 1.5, "elasticity": 1.2},
    "fossil_fuels": {"base_req": 0.8, "elasticity": 1.0},
    "wood_and_paper": {"base_req": 0.1, "elasticity": 0.8},
    "iron_and_steel": {"base_req": 0.2, "elasticity": 1.1},
    "appliances": {"base_req": 0.01, "elasticity": 1.5},
    "vehicles": {"base_req": 0.005, "elasticity": 2.0},
    "arms_and_ammunition": {"base_req": 0.001, "elasticity": 0.5},
    # Missing resources will fallback to a hardcoded baseline in ConsumptionModel.
}

@dataclass
class EconomyConfig:
    """Unified configuration for both trade conversion and production estimation."""
    baci_input_path: Path
    country_map_path: Path
    valid_countries_path: Path
    pop_data_path: Path
    eco_data_path: Path
    trade_output_path: Path
    production_output_path: Path
    
    target_year: int = 2001
    min_quantity_tons: float = 1.0
    
    # Outlier clipping
    enable_percentile_clipping: bool = False
    clip_lower_percentile: float = 0.05
    clip_upper_percentile: float = 0.95
    max_fallback_price: float = 5000000.0
    
    # Consumption model baseline
    baseline_gdp_pc: float = 10000.0


# ==============================================================================
# PHASE 1: INTERNATIONAL TRADE PIPELINE
# ==============================================================================

class EconomyMapper:
    """Translates HS product codes into game resource categories."""
    def __init__(self, mapping_dict: Dict[str, List[str]]):
        map_2d, map_4d = {}, {}
        for resource, codes in mapping_dict.items():
            for code in codes:
                if len(code) == 2:
                    map_2d[code] = resource
                elif len(code) == 4:
                    map_4d[code] = resource
                else:
                    # Explaining unidiomatic code: We explicitly crash here instead of logging 
                    # to enforce strict schema adherence during the initial parsing phase.
                    raise ValueError(f"Invalid HS code length in mapping config: {code}")
        
        self.lf_map_2d = pl.DataFrame({"hs2_code": list(map_2d.keys()), "res_2d": list(map_2d.values())}).lazy()
        self.lf_map_4d = pl.DataFrame({"hs4_code": list(map_4d.keys()), "res_4d": list(map_4d.values())}).lazy()

    def map_resources(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        lf = lf.join(self.lf_map_4d, on="hs4_code", how="left")
        lf = lf.join(self.lf_map_2d, on="hs2_code", how="left")
        
        # See: https://docs.pola.rs/user-guide/expressions/null/#coalesce
        return lf.with_columns(
            pl.coalesce("res_4d", "res_2d").fill_null("unclassified").alias("game_resource_id")
        ).drop(["res_4d", "res_2d"])


class BaciLoader:
    """Handles raw data ingestion and UN-to-ISO country code mapping."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_data(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.baci_input_path) if self.cfg.baci_input_path.suffix.lower() == '.csv' else pl.scan_parquet(self.cfg.baci_input_path)
        
        mapping_lf = pl.scan_csv(self.cfg.country_map_path).select([
            pl.col("country_code").cast(pl.Int64), pl.col("iso_3")
        ])

        lf = lf.filter(pl.col("t") == self.cfg.target_year)

        lf = lf.join(mapping_lf, left_on="i", right_on="country_code", how="left").rename({"iso_3": "exporter_id"})
        lf = lf.join(mapping_lf, left_on="j", right_on="country_code", how="left").rename({"iso_3": "importer_id"})
        
        return lf.drop_nulls(subset=["exporter_id", "importer_id"])


class BaciTransformer:
    """Applies economic logic, categorization, and gap-healing."""
    def __init__(self, config: EconomyConfig, mapper: EconomyMapper):
        self.cfg = config
        self.mapper = mapper

    def transform(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        lf = lf.with_columns(
            pl.col("k").cast(pl.Utf8).str.zfill(6).alias("hs6_code")
        ).with_columns(
            pl.col("hs6_code").str.slice(0, 4).alias("hs4_code"),
            pl.col("hs6_code").str.slice(0, 2).alias("hs2_code")
        )

        def calculate_unit_price(level: str) -> pl.Expr:
            return ((pl.col("v").sum().over(level) * 1000) / pl.col("q").sum().over(level))

        # Imputation methodology: https://unstats.un.org/unsd/trade/data/imputation.asp
        lf = lf.with_columns(
            calculate_unit_price("hs6_code").alias("price_hs6"),
            calculate_unit_price("hs4_code").alias("price_hs4"),
            calculate_unit_price("hs2_code").alias("price_hs2"),
            ((pl.col("v").sum() * 1000) / pl.col("q").sum()).alias("price_global")
        )

        lf = lf.with_columns(
            pl.coalesce("price_hs6", "price_hs4", "price_hs2", "price_global").alias("best_estimated_price")
        ).with_columns(
            pl.coalesce(pl.col("q"), (pl.col("v") * 1000) / pl.col("best_estimated_price")).alias("healed_quantity")
        )

        lf = lf.filter(pl.col("healed_quantity") >= self.cfg.min_quantity_tons)
        lf = self.mapper.map_resources(lf)

        lf_agg = lf.group_by(["exporter_id", "importer_id", "game_resource_id"]).agg([
            pl.col("v").sum().alias("total_v"),
            pl.col("healed_quantity").sum().alias("annual_volume_tons")
        ])

        # TODO: Evaluate keeping 0-volume connections as dormant graph edges for dynamic routing.
        lf_agg = lf_agg.filter(
            pl.col("annual_volume_tons").is_not_null() & (pl.col("annual_volume_tons") > 0)
        ).with_columns(
            ((pl.col("total_v") * 1000) / pl.col("annual_volume_tons")).alias("unit_price_usd")
        )
        return lf_agg


class OutlierProcessor:
    """Sanitizes unit prices to handle customs reporting errors."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def process(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if self.cfg.enable_percentile_clipping:
            lower_bound = pl.col("unit_price_usd").quantile(self.cfg.clip_lower_percentile).over("game_resource_id")
            upper_bound = pl.col("unit_price_usd").quantile(self.cfg.clip_upper_percentile).over("game_resource_id")

            lf = lf.with_columns(
                pl.when(pl.col("unit_price_usd") > upper_bound).then(upper_bound)
                .when(pl.col("unit_price_usd") < lower_bound).then(lower_bound)
                .otherwise(pl.col("unit_price_usd"))
                .alias("unit_price_usd")
            )
        else:
            # Hardcap prevents GUI rendering issues and integer overflow in the simulation engine.
            lf = lf.with_columns(
                pl.when(pl.col("unit_price_usd") > self.cfg.max_fallback_price).then(self.cfg.max_fallback_price)
                .otherwise(pl.col("unit_price_usd"))
                .alias("unit_price_usd")
            )
        return lf


class GameDataValidator:
    """Ensures external datasets conform to the active internal map schema."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def validate(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if not self.cfg.valid_countries_path.exists():
            raise FileNotFoundError(f"Missing essential state file: {self.cfg.valid_countries_path}")
            
        valid_countries = pl.scan_csv(self.cfg.valid_countries_path, separator='\t').select(pl.col("id").alias("valid_id"))

        lf = lf.filter(pl.col("game_resource_id") != "unclassified")

        # Inner joins enforce strict filtering of unplayable/non-existent nodes.
        return lf.join(
            valid_countries, left_on="exporter_id", right_on="valid_id", how="inner"
        ).join(
            valid_countries, left_on="importer_id", right_on="valid_id", how="inner"
        )


class TradeConverterPipeline:
    def __init__(self, config: EconomyConfig, mapper: EconomyMapper, validator: GameDataValidator, out_processor: OutlierProcessor):
        self.config = config
        self.loader = BaciLoader(config)
        self.transformer = BaciTransformer(config, mapper)
        self.out_processor = out_processor
        self.validator = validator

    def run(self):
        logger.info("--- Starting International Trade Pipeline ---")
        lf = self.loader.load_data()
        lf = self.transformer.transform(lf)
        lf = self.out_processor.process(lf)
        lf = self.validator.validate(lf) 
        
        target_schema = ["exporter_id", "importer_id", "game_resource_id", "annual_volume_tons", "unit_price_usd"]
        lf.select(target_schema).sink_parquet(self.config.trade_output_path)
        logger.info(f"Trade network saved to {self.config.trade_output_path}")


# ==============================================================================
# PHASE 2: INTERNAL PRODUCTION PIPELINE
# ==============================================================================

class GameStateLoader:
    """Aggregates demographic and economic data from the game's base module."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_population(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.pop_data_path, separator='\t')
        return lf.group_by("_owner").agg(
            (pl.col("pop_14") + pl.col("pop_15_64") + pl.col("pop_65")).sum().alias("total_population")
        ).rename({"_owner": "country_id"})

    def load_economy(self) -> pl.LazyFrame:
        return pl.scan_csv(self.cfg.eco_data_path, separator='\t').select(["id", "gdp_per_capita"]).rename({"id": "country_id"})


class TradeAggregator:
    """Extracts aggregate import/export volumes from the previously generated trade network."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def get_net_trade(self) -> pl.LazyFrame:
        trade_lf = pl.scan_parquet(self.cfg.trade_output_path)
        
        exports = trade_lf.group_by(["exporter_id", "game_resource_id"]).agg(
            pl.col("annual_volume_tons").sum().alias("total_export")
        ).rename({"exporter_id": "country_id"})

        imports = trade_lf.group_by(["importer_id", "game_resource_id"]).agg(
            pl.col("annual_volume_tons").sum().alias("total_import")
        ).rename({"importer_id": "country_id"})

        return exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)


class ConsumptionModel:
    """Estimates theoretical resource demand based on population size and GDP wealth scaling."""
    def __init__(self, config: EconomyConfig, rules: dict):
        self.cfg = config
        self.rules = rules

    def _build_rules_df(self) -> pl.LazyFrame:
        # Fallback values for any unmapped resources to avoid breaking the join
        default_base, default_elasticity = 0.01, 0.5
        
        all_resources = list(GAME_MAPPING.keys())
        bases = [self.rules.get(res, {}).get("base_req", default_base) for res in all_resources]
        elasticities = [self.rules.get(res, {}).get("elasticity", default_elasticity) for res in all_resources]
        
        return pl.DataFrame({
            "game_resource_id": all_resources, "base_req": bases, "elasticity": elasticities
        }).lazy()

    def estimate_consumption(self, dem_eco_lf: pl.LazyFrame) -> pl.LazyFrame:
        rules_lf = self._build_rules_df()
        lf = dem_eco_lf.join(rules_lf, how="cross")
        
        return lf.with_columns(
            (pl.col("gdp_per_capita") / self.cfg.baseline_gdp_pc).clip(0.1, 5.0).alias("wealth_ratio")
        ).with_columns(
            (pl.col("total_population") * pl.col("base_req") * (1.0 + (pl.col("wealth_ratio") - 1.0) * pl.col("elasticity"))).alias("estimated_consumption")
        ).select(["country_id", "game_resource_id", "estimated_consumption"])


class ProductionCalculator:
    """Solves the macroeconomic identity P = max(0, C + E - I) to find domestic production."""
    def calculate(self, consumption_lf: pl.LazyFrame, trade_lf: pl.LazyFrame) -> pl.LazyFrame:
        lf = consumption_lf.join(trade_lf, on=["country_id", "game_resource_id"], how="left").fill_null(0.0)

        # Clamping at 0.0 because negative production implies an inventory depletion state 
        # which is outside the current scope of static generation.
        return lf.with_columns(
            (pl.col("estimated_consumption") + pl.col("total_export") - pl.col("total_import"))
            .clip(lower_bound=0.0)
            .alias("domestic_production_tons")
        ).select(["country_id", "game_resource_id", "domestic_production_tons"])


class InternalProductionPipeline:
    def __init__(self, config: EconomyConfig):
        self.config = config
        self.state_loader = GameStateLoader(config)
        self.trade_aggregator = TradeAggregator(config)
        self.consumption_model = ConsumptionModel(config, CONSUMPTION_MATRIX)
        self.calculator = ProductionCalculator()

    def run(self):
        logger.info("--- Starting Internal Production Estimation ---")
        
        dem_eco_lf = self.state_loader.load_population().join(
            self.state_loader.load_economy(), on="country_id", how="inner"
        )
        trade_lf = self.trade_aggregator.get_net_trade()
        consumption_lf = self.consumption_model.estimate_consumption(dem_eco_lf)
        production_lf = self.calculator.calculate(consumption_lf, trade_lf)

        production_lf.sink_parquet(self.config.production_output_path)
        logger.info(f"Domestic production saved to {self.config.production_output_path}")


# ==============================================================================
# ORCHESTRATION
# ==============================================================================

class WorldEconomyGenerator:
    """Master orchestrator combining both data pipelines in sequence."""
    def __init__(self, config: EconomyConfig):
        self.config = config
        
        # Dependency Injection for Phase 1
        mapper = EconomyMapper(GAME_MAPPING)
        validator = GameDataValidator(config)
        out_processor = OutlierProcessor(config)
        self.trade_pipeline = TradeConverterPipeline(config, mapper, validator, out_processor)
        
        # Dependency Injection for Phase 2
        self.production_pipeline = InternalProductionPipeline(config)

    def generate(self):
        try:
            self.trade_pipeline.run()
            # Production pipeline must run *after* trade, as it relies on the generated trade network
            self.production_pipeline.run()
            logger.info("Global economy generation completed successfully.")
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise

if __name__ == "__main__":
    
    project_root = Path(__file__).resolve().parent.parent.parent
    base_data = project_root / "modules" / "base" / "data"
    
    config = EconomyConfig(
        baci_input_path=Path("BACI_HS92_Y2001_V202401.csv"),
        country_map_path=Path("country_codes.csv"),
        valid_countries_path=base_data / "countries" / "countries.tsv",
        pop_data_path=base_data / "regions" / "regions_pop.tsv",
        eco_data_path=base_data / "countries" / "countries_eco.tsv",
        trade_output_path=base_data / "world" / "trade_network.parquet",
        production_output_path=base_data / "world" / "domestic_production.parquet",
        target_year=2001,
        enable_percentile_clipping=False
    )

    if not config.baci_input_path.exists():
        logger.warning(f"BACI input not found at: {config.baci_input_path}. Please place the dataset.")
    else:
        generator = WorldEconomyGenerator(config)
        generator.generate()