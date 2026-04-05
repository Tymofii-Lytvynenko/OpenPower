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

# Target categories where quality actually matters. 
# Raw materials like 'minerals' or 'cereals' are excluded and will default to a quality of 1.
QUALITY_SENSITIVE_GOODS = [
    "appliances", 
    "vehicles", 
    "machinery_and_instruments", 
    "arms_and_ammunition", 
    "pharmaceuticals",
    "luxury_commodities",
    # Service categories added to quality calculation
    "transport_services",
    "tourism_services",
    "construction_services",
    "financial_services",
    "it_and_telecom_services",
    "business_services",
    "recreational_services",
    "health_services",
    "education_services",
    "government_services",
    "industrial_services",
]

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

# ITPD-E industry sector descriptions mapped to OpenPower service resources
SERVICES_MAPPING = {
    "transport_services": ["Transport"],
    "tourism_services": ["Travel"],
    "construction_services": ["Construction"],
    "financial_services": ["Insurance and pension services", "Financial services"],
    "it_and_telecom_services": ["Telecom, computer, information services"],
    "business_services": ["Other business services", "Trade-related services", "Charges for use of intellectual property"],
    "recreational_services": ["Heritage and recreational services", "Other personal services"],
    "health_services": ["Health services"],
    "education_services": ["Education services"],
    "government_services": ["Government goods and services n.i.e."],
    "industrial_services": ["Manufacturing services on physical inputs", "Maintenance and repair services n.i.e."]
    # "Services not allocated" is intentionally omitted to fall back to "unclassified"
}

# Base per capita consumption
# Note: Physical goods are typically measured in tons/year. 
# Exception: 'electricity' (HS 2716) is implicitly measured in MWh due to UN Comtrade reporting standards.
# Services are measured in man-hours/year.
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
    
    # Service requirements (man-hours scaling)
    # The base_req defines the man-hours demanded per capita at the baseline GDP ($10k).
    # Values are scaled down so that the total sum of man-hours demanded by an advanced 
    # economy (after elasticity multipliers) does not exceed the physical limits of 
    # the active labor force (approx. 700-1000 available service man-hours per capita).
    "transport_services": {"base_req": 10.0, "elasticity": 1.2},
    "tourism_services": {"base_req": 5.0, "elasticity": 2.5},
    "construction_services": {"base_req": 8.0, "elasticity": 1.4},
    "financial_services": {"base_req": 4.0, "elasticity": 1.5},
    "it_and_telecom_services": {"base_req": 15.0, "elasticity": 1.5},
    "business_services": {"base_req": 8.0, "elasticity": 1.3},
    "recreational_services": {"base_req": 3.0, "elasticity": 2.0},
    
    # Explaining unidiomatic code: We split the generic 'social_services' into 
    # health and education to strictly match the keys generated by SERVICES_MAPPING.
    # Failing to match keys causes the ConsumptionModel to fallback to a 0.01 baseline.
    "health_services": {"base_req": 7.0, "elasticity": 0.8},
    "education_services": {"base_req": 8.0, "elasticity": 0.8}, 
    
    "government_services": {"base_req": 18.0, "elasticity": 0.5},
    "industrial_services": {"base_req": 5.0, "elasticity": 1.1},
}

@dataclass
class EconomyConfig:
    """Unified configuration for trade conversion, services, and production estimation."""
    baci_input_path: Path
    itpd_input_path: Path
    country_map_path: Path
    valid_countries_path: Path
    pop_data_path: Path
    eco_data_path: Path
    trade_output_path: Path
    production_output_path: Path
    
    target_year: int = 2001
    min_quantity_tons: float = 1.0
    working_hours_per_year: float = 2000.0
    
    enable_percentile_clipping: bool = False
    clip_lower_percentile: float = 0.05
    clip_upper_percentile: float = 0.95
    max_fallback_price: float = 5000000.0
    
    baseline_gdp_pc: float = 10000.0


# ==============================================================================
# DATA LOADERS & STATE ACCESS
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


class GameDataValidator:
    """Ensures external datasets conform to the active internal map schema."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def validate(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if not self.cfg.valid_countries_path.exists():
            raise FileNotFoundError(f"Missing essential state file: {self.cfg.valid_countries_path}")
            
        valid_countries = pl.scan_csv(self.cfg.valid_countries_path, separator='\t').select(pl.col("id").alias("valid_id"))

        lf = lf.filter(pl.col("game_resource_id") != "unclassified")

        return lf.join(
            valid_countries, left_on="exporter_id", right_on="valid_id", how="inner"
        ).join(
            valid_countries, left_on="importer_id", right_on="valid_id", how="inner"
        )


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
                    # to enforce strict schema adherence during the initial config parsing.
                    raise ValueError(f"Invalid HS code length in mapping config: {code}")
        
        self.lf_map_2d = pl.DataFrame({"hs2_code": list(map_2d.keys()), "res_2d": list(map_2d.values())}).lazy()
        self.lf_map_4d = pl.DataFrame({"hs4_code": list(map_4d.keys()), "res_4d": list(map_4d.values())}).lazy()

    def map_resources(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        lf = lf.join(self.lf_map_4d, on="hs4_code", how="left")
        lf = lf.join(self.lf_map_2d, on="hs2_code", how="left")
        
        # Coalesce selects the first non-null value, prioritizing 4-digit precision.
        return lf.with_columns(
            pl.coalesce("res_4d", "res_2d").fill_null("unclassified").alias("game_resource_id")
        ).drop(["res_4d", "res_2d"])


class ServiceMapper:
    """Translates ITPD-E industry descriptions into game service categories."""
    def __init__(self, mapping_dict: Dict[str, List[str]]):
        flat_map = {}
        for resource, sectors in mapping_dict.items():
            for sector in sectors:
                flat_map[sector] = resource
                
        self.lf_map = pl.DataFrame({
            "industry_descr": list(flat_map.keys()), 
            "game_resource_id": list(flat_map.values())
        }).lazy()

    def map_services(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.join(self.lf_map, on="industry_descr", how="left").with_columns(
            pl.col("game_resource_id").fill_null("unclassified")
        )


class BaciLoader:
    """Handles raw physical goods data ingestion and UN-to-ISO country code mapping."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_data(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.baci_input_path) if self.cfg.baci_input_path.suffix.lower() == '.csv' else pl.scan_parquet(self.cfg.baci_input_path)
        
        mapping_lf = pl.scan_csv(self.cfg.country_map_path).select([
            pl.col("country_code").cast(pl.Int64), pl.col("country_iso3")
        ])

        lf = lf.filter(pl.col("t") == self.cfg.target_year)

        lf = lf.join(mapping_lf, left_on="i", right_on="country_code", how="left").rename({"country_iso3": "exporter_id"})
        lf = lf.join(mapping_lf, left_on="j", right_on="country_code", how="left").rename({"country_iso3": "importer_id"})
        
        return lf.drop_nulls(subset=["exporter_id", "importer_id"])


class BaciTransformer:
    """Applies economic logic, categorization, and gap-healing for physical goods."""
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
            pl.col("healed_quantity").sum().alias("annual_volume")
        ])

        # TODO: Evaluate keeping 0-volume connections as dormant graph edges for dynamic routing.
        lf_agg = lf_agg.filter(
            pl.col("annual_volume").is_not_null() & (pl.col("annual_volume") > 0)
        ).with_columns(
            ((pl.col("total_v") * 1000) / pl.col("annual_volume")).alias("unit_price_usd")
        )
        return lf_agg


class ItpdServicesLoader:
    """Extracts intangible trade flows from the ITPD-E dataset."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_data(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.itpd_input_path)

        return lf.filter(
            (pl.col("year") == self.cfg.target_year) & 
            (pl.col("broad_sector") == "Services") &
            (pl.col("exporter_iso3") != pl.col("importer_iso3"))
        ).rename({
            "exporter_iso3": "exporter_id",
            "importer_iso3": "importer_id"
        }).select(["exporter_id", "importer_id", "industry_descr", "trade"])


class ServicesManHourConverter:
    """Translates monetary service value into labor time (man-hours) and applies category mapping."""
    def __init__(self, config: EconomyConfig, state_loader: GameStateLoader, mapper: ServiceMapper):
        self.cfg = config
        self.state_loader = state_loader
        self.mapper = mapper

    def convert(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        eco_lf = self.state_loader.load_economy()

        # Join with exporter's economy data to estimate their average wage
        lf = lf.join(eco_lf, left_on="exporter_id", right_on="country_id", how="left")
        lf = lf.with_columns(
            pl.col("gdp_per_capita").fill_null(self.cfg.baseline_gdp_pc)
        )

        lf = self.mapper.map_services(lf)

        # Calculate volume in man-hours rather than tons
        lf = lf.with_columns(
            (pl.col("gdp_per_capita") / self.cfg.working_hours_per_year).alias("hourly_wage")
        ).with_columns(
            ((pl.col("trade") * 1_000_000) / pl.col("hourly_wage")).alias("annual_volume"),
            pl.col("hourly_wage").alias("unit_price_usd")
        )

        return lf.select([
            "exporter_id", "importer_id", "game_resource_id", 
            "annual_volume", "unit_price_usd"
        ])


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
            lf = lf.with_columns(
                pl.when(pl.col("unit_price_usd") > self.cfg.max_fallback_price).then(self.cfg.max_fallback_price)
                .otherwise(pl.col("unit_price_usd"))
                .alias("unit_price_usd")
            )
        return lf


class TradeConverterPipeline:
    def __init__(
        self, 
        config: EconomyConfig, 
        mapper: EconomyMapper, 
        service_mapper: ServiceMapper,
        validator: GameDataValidator, 
        out_processor: OutlierProcessor,
        state_loader: GameStateLoader
    ):
        self.config = config
        self.validator = validator
        
        self.baci_loader = BaciLoader(config)
        self.baci_transformer = BaciTransformer(config, mapper)
        self.out_processor = out_processor
        
        self.itpd_loader = ItpdServicesLoader(config)
        self.services_converter = ServicesManHourConverter(config, state_loader, service_mapper)

    def run(self):
        logger.info("--- Starting International Trade Pipeline ---")
        
        goods_lf = self.baci_loader.load_data()
        goods_lf = self.baci_transformer.transform(goods_lf)
        goods_lf = self.out_processor.process(goods_lf)
        
        services_lf = self.itpd_loader.load_data()
        services_lf = self.services_converter.convert(services_lf)
        
        combined_lf = pl.concat([goods_lf.drop("total_v"), services_lf])
        combined_lf = self.validator.validate(combined_lf) 
        
        target_schema = ["exporter_id", "importer_id", "game_resource_id", "annual_volume", "unit_price_usd"]
        combined_lf.select(target_schema).sink_parquet(self.config.trade_output_path)
        logger.info(f"Trade network saved to {self.config.trade_output_path}")


# ==============================================================================
# PHASE 2: INTERNAL PRODUCTION PIPELINE
# ==============================================================================

class QualityEstimator:
    """Calculates a Quality Index (1-100) for complex manufactured goods and services."""
    def __init__(self, baseline_gdp_pc: float = 10000.0, price_weight: float = 0.4, tech_weight: float = 0.6):
        self.baseline_gdp = baseline_gdp_pc
        self.w_price = price_weight
        self.w_tech = tech_weight

    def calculate(self, trade_lf: pl.LazyFrame, eco_lf: pl.LazyFrame, production_lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Calculating Quality Index for manufactured goods and services...")

        global_prices = trade_lf.group_by("game_resource_id").agg(
            pl.col("unit_price_usd").median().alias("global_median_price")
        )

        local_prices = trade_lf.group_by(["exporter_id", "game_resource_id"]).agg(
            pl.col("unit_price_usd").median().alias("local_price")
        ).rename({"exporter_id": "country_id"})

        eval_lf = production_lf.join(
            local_prices, on=["country_id", "game_resource_id"], how="left"
        ).join(
            eco_lf, on="country_id", how="left"
        ).join(
            global_prices, on="game_resource_id", how="left"
        )

        eval_lf = eval_lf.with_columns(
            pl.col("local_price").fill_null(pl.col("global_median_price"))
        )

        eval_lf = eval_lf.with_columns(
            (pl.col("local_price") / pl.col("global_median_price")).clip(0.5, 3.0).alias("price_ratio"),
            (pl.col("gdp_per_capita") / self.baseline_gdp).clip(0.1, 5.0).alias("tech_ratio")
        ).with_columns(
            ((pl.col("price_ratio") ** self.w_price) * (pl.col("tech_ratio") ** self.w_tech)).alias("raw_quality")
        )

        max_theoretical_quality = (3.0 ** self.w_price) * (5.0 ** self.w_tech)
        
        eval_lf = eval_lf.with_columns(
            pl.when(pl.col("game_resource_id").is_in(QUALITY_SENSITIVE_GOODS))
            .then(
                ((pl.col("raw_quality") / max_theoretical_quality) * 100).round(0).clip(1.0, 100.0)
            )
            .otherwise(1.0)
            .cast(pl.Int32)
            .alias("quality_index")
        )

        return eval_lf.select([
            "country_id", 
            "game_resource_id", 
            "domestic_production", 
            "quality_index"
        ])


class TradeAggregator:
    """Extracts aggregate import/export volumes from the previously generated trade network."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def get_net_trade(self) -> pl.LazyFrame:
        trade_lf = pl.scan_parquet(self.cfg.trade_output_path)
        
        exports = trade_lf.group_by(["exporter_id", "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("total_export")
        ).rename({"exporter_id": "country_id"})

        imports = trade_lf.group_by(["importer_id", "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("total_import")
        ).rename({"importer_id": "country_id"})

        return exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)


class ConsumptionModel:
    """Estimates theoretical resource demand based on population size and GDP wealth scaling."""
    def __init__(self, config: EconomyConfig, rules: dict):
        self.cfg = config
        self.rules = rules

    def _build_rules_df(self) -> pl.LazyFrame:
        default_base, default_elasticity = 0.01, 0.5
        
        all_resources = list(GAME_MAPPING.keys()) + list(SERVICES_MAPPING.keys())
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

        # Clamping at 0.0 prevents inventory depletion states which fall outside the scope of static generation.
        return lf.with_columns(
            (pl.col("estimated_consumption") + pl.col("total_export") - pl.col("total_import"))
            .clip(lower_bound=0.0)
            .alias("domestic_production")
        ).select(["country_id", "game_resource_id", "domestic_production"])


class InternalProductionPipeline:
    def __init__(self, config: EconomyConfig, quality_estimator: QualityEstimator, state_loader: GameStateLoader):
        self.config = config
        self.state_loader = state_loader
        self.trade_aggregator = TradeAggregator(config)
        self.consumption_model = ConsumptionModel(config, CONSUMPTION_MATRIX)
        self.calculator = ProductionCalculator()
        self.quality_estimator = quality_estimator

    def run(self):
        logger.info("--- Starting Internal Production Estimation ---")
        
        eco_lf = self.state_loader.load_economy()
        pop_lf = self.state_loader.load_population()
        dem_eco_lf = pop_lf.join(eco_lf, on="country_id", how="inner")
        
        trade_lf = self.trade_aggregator.get_net_trade()
        consumption_lf = self.consumption_model.estimate_consumption(dem_eco_lf)
        
        production_lf = self.calculator.calculate(consumption_lf, trade_lf)
        
        raw_trade_lf = pl.scan_parquet(self.config.trade_output_path)
        production_lf = self.quality_estimator.calculate(raw_trade_lf, eco_lf, production_lf)

        production_lf.sink_parquet(self.config.production_output_path)
        logger.info(f"Domestic production saved to {self.config.production_output_path}")


# ==============================================================================
# ORCHESTRATION
# ==============================================================================

class WorldEconomyGenerator:
    """Master orchestrator combining data pipelines in sequence."""
    def __init__(self, config: EconomyConfig):
        self.config = config
        
        state_loader = GameStateLoader(config)
        
        # Inject dependencies
        mapper = EconomyMapper(GAME_MAPPING)
        service_mapper = ServiceMapper(SERVICES_MAPPING)
        validator = GameDataValidator(config)
        out_processor = OutlierProcessor(config)
        
        self.trade_pipeline = TradeConverterPipeline(
            config, mapper, service_mapper, validator, out_processor, state_loader
        )
        
        quality_estimator = QualityEstimator(config.baseline_gdp_pc)
        self.production_pipeline = InternalProductionPipeline(config, quality_estimator, state_loader)

    def generate(self):
        try:
            self.trade_pipeline.run()
            self.production_pipeline.run()
            logger.info("Global economy generation completed successfully.")
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise

if __name__ == "__main__":
    
    project_root = Path(__file__).resolve().parent.parent.parent
    base_data = project_root / "modules" / "base" / "data"
    
    config = EconomyConfig(
        baci_input_path=Path(".temp//BACI_HS96_Y2001_V202601.csv"),
        itpd_input_path=Path(".temp//ITPD_E_R03.csv"),
        country_map_path=Path(".temp//country_codes_V202601.csv"),
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
    elif not config.itpd_input_path.exists():
        logger.warning(f"ITPD-E input not found at: {config.itpd_input_path}. Please place the dataset.")
    else:
        generator = WorldEconomyGenerator(config)
        generator.generate()