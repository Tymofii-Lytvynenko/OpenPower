"""
=========================================================================================
ARCHIVAL NOTE: HISTORICAL PHYSICAL VOLUME ESTIMATION (TONS/UNITS)
=========================================================================================
Previous iterations of this generator attempted to calculate physical production volumes 
(e.g., tons, Megawatts) by dividing WIOD monetary output by BACI export prices. 

This approach was archived in favor of a purely USD-based monetary simulation (similar to 
SuperPower 2) due to fundamental macroeconomic dataset incompatibilities:

1. The Aggregation Illusion: WIOD groups high-value goods (meat, dairy) and low-value 
   bulk goods (cereals) into a single "Agriculture" sector. Dividing this by a bulk export 
   price mathematically erased hundreds of millions of tons of basic resources.
2. Export vs. Domestic Price Gap: BACI prices include international logistics and port fees. 
   Domestic consumption prices (especially for Electricity or base materials) are vastly 
   lower, leading to severely deflated physical production estimates.

If future development requires reverting to physical units, the following logic represents 
the most accurate algorithmic approximation achieved before archiving:

- Gross Trade Proportionality: Instead of basing internal resource distribution on Import 
  shares (which zeroes out net-exporters like US Cereals), use:
  (Import + Export) / (Total Sector Import + Total Sector Export).
- Hybrid Local Price Matrix: Do not use a global median price. Use a cascading fallback:
  1st priority: Local Export Price (from BACI).
  2nd priority: Local Import Price (from BACI).
  3rd priority: Global Median Price * sqrt(GDP Deflator). This acts as a PPP proxy.
- Macroeconomic Sanity Healing: Use the formula C = P + I - E. If Apparent Consumption (C) 
  is < 0, mathematically force Domestic Production (P) up to exactly cover (E - I) to 
  prevent negative inventory states in the game engine.
=========================================================================================
"""

import polars as pl
from pathlib import Path
from dataclasses import dataclass
import logging
from typing import Dict, List
import random

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("EconomyGenerator")

# --- MACROECONOMIC CONFIGURATION ---

QUALITY_SENSITIVE_GOODS = [
    "appliances", 
    "vehicles", 
    "machinery_and_instruments", 
    "arms_and_ammunition", 
    "pharmaceuticals",
    "luxury_commodities",
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
}

WIOD_MAPPING = {
    "Agriculture, Hunting, Forestry and Fishing": ["cereals", "vegetables_and_fruits", "meat_and_fish", "dairy", "drugs_and_raw_plants"],
    "Mining and Quarrying": ["fossil_fuels", "minerals", "precious_stones"],
    "Food, Beverages and Tobacco": ["other_food_and_beverages", "tobacco"],
    "Textiles and Textile Products": ["fabrics_and_leather"],
    "Leather, Leather and Footwear": ["fabrics_and_leather"],
    "Wood and Products of Wood and Cork": ["wood_and_paper"],
    "Pulp, Paper, Paper , Printing and Publishing": ["wood_and_paper"],
    "Coke, Refined Petroleum and Nuclear Fuel": ["fossil_fuels"],
    "Chemicals and Chemical Products": ["chemicals", "pharmaceuticals"],
    "Rubber and Plastics": ["plastics_and_rubber"],
    "Other Non-Metallic Mineral": ["construction_materials"],
    "Basic Metals and Fabricated Metal": ["iron_and_steel", "non_ferrous_metals", "arms_and_ammunition"],
    "Machinery, Nec": ["machinery_and_instruments"],
    "Electrical and Optical Equipment": ["appliances"],
    "Transport Equipment": ["vehicles"],
    "Manufacturing, Nec; Recycling": ["commodities", "luxury_commodities"],
    "Electricity, Gas and Water Supply": ["electricity"],
    "Construction": ["construction_services"],
    "Sale, Maintenance and Repair of Motor Vehicles and Motorcycles; Retail Sale of Fuel": ["industrial_services"],
    "Wholesale Trade and Commission Trade, Except of Motor Vehicles and Motorcycles": ["business_services"],
    "Retail Trade, Except of Motor Vehicles and Motorcycles; Repair of Household Goods": ["business_services"],
    "Hotels and Restaurants": ["tourism_services"],
    "Inland Transport": ["transport_services"],
    "Water Transport": ["transport_services"],
    "Air Transport": ["transport_services"],
    "Other Supporting and Auxiliary Transport Activities; Activities of Travel Agencies": ["transport_services"],
    "Post and Telecommunications": ["it_and_telecom_services"],
    "Financial Intermediation": ["financial_services"],
    "Real Estate Activities": ["business_services"],
    "Renting of M&Eq and Other Business Activities": ["business_services"],
    "Public Admin and Defence; Compulsory Social Security": ["government_services"],
    "Education": ["education_services"],
    "Health and Social Work": ["health_services"],
    "Other Community, Social and Personal Services": ["recreational_services"],
    "Private Households with Employed Persons": ["recreational_services"]
}

@dataclass
class EconomyConfig:
    """Unified configuration for trade conversion, services, and production estimation."""
    baci_input_path: Path
    itpd_input_path: Path
    wiod_input_path: Path
    country_map_path: Path
    valid_countries_path: Path
    pop_data_path: Path
    eco_data_path: Path
    trade_output_path: Path
    production_output_path: Path
    
    target_year: int = 2001
    
    min_quantity_tons: float = 0.0  
    working_hours_per_year: float = 1750.0  
    
    baci_value_multiplier: float = 1000.0       
    itpd_value_multiplier: float = 1_000_000.0  
    wiod_value_multiplier: float = 1_000_000.0  
    
    missing_country_gdp_weight: float = 1.0     
    
    enable_percentile_clipping: bool = True
    clip_lower_percentile: float = 0.01 
    clip_upper_percentile: float = 0.99 


# ==============================================================================
# DATA LOADERS & STATE ACCESS
# ==============================================================================

class GameStateLoader:
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
    def __init__(self, mapping_dict: Dict[str, List[str]]):
        map_2d, map_4d = {}, {}
        for resource, codes in mapping_dict.items():
            for code in codes:
                if len(code) == 2:
                    map_2d[code] = resource
                elif len(code) == 4:
                    map_4d[code] = resource
                else:
                    raise ValueError(f"Invalid HS code length in mapping config: {code}")
        
        self.lf_map_2d = pl.DataFrame({"hs2_code": list(map_2d.keys()), "res_2d": list(map_2d.values())}).lazy()
        self.lf_map_4d = pl.DataFrame({"hs4_code": list(map_4d.keys()), "res_4d": list(map_4d.values())}).lazy()

    def map_resources(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        lf = lf.join(self.lf_map_4d, on="hs4_code", how="left")
        lf = lf.join(self.lf_map_2d, on="hs2_code", how="left")
        return lf.with_columns(
            pl.coalesce("res_4d", "res_2d").fill_null("unclassified").alias("game_resource_id")
        ).drop(["res_4d", "res_2d"])


class ServiceMapper:
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
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_data(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.baci_input_path) if self.cfg.baci_input_path.suffix.lower() == '.csv' else pl.scan_parquet(self.cfg.baci_input_path)
        mapping_lf = pl.scan_csv(self.cfg.country_map_path).select([pl.col("country_code").cast(pl.Int64), pl.col("country_iso3")])

        lf = lf.filter(pl.col("t") == self.cfg.target_year)
        lf = lf.join(mapping_lf, left_on="i", right_on="country_code", how="left").rename({"country_iso3": "exporter_id"})
        lf = lf.join(mapping_lf, left_on="j", right_on="country_code", how="left").rename({"country_iso3": "importer_id"})
        
        return lf.drop_nulls(subset=["exporter_id", "importer_id"])


class BaciTransformer:
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
            q_sum = pl.col("q").sum().over(level)
            return pl.when(q_sum > 0).then((pl.col("v").sum().over(level) * self.cfg.baci_value_multiplier) / q_sum).otherwise(None)

        q_sum_global = pl.col("q").sum()

        lf = lf.with_columns(
            calculate_unit_price("hs6_code").alias("price_hs6"),
            calculate_unit_price("hs4_code").alias("price_hs4"),
            calculate_unit_price("hs2_code").alias("price_hs2"),
            pl.when(q_sum_global > 0).then((pl.col("v").sum() * self.cfg.baci_value_multiplier) / q_sum_global).otherwise(None).alias("price_global")
        )

        lf = lf.with_columns(
            pl.coalesce("price_hs6", "price_hs4", "price_hs2", "price_global").alias("best_estimated_price")
        ).with_columns(
            pl.coalesce(pl.col("q"), (pl.col("v") * self.cfg.baci_value_multiplier) / pl.col("best_estimated_price")).alias("healed_quantity")
        )

        lf = lf.filter(pl.col("healed_quantity") >= self.cfg.min_quantity_tons)
        lf = self.mapper.map_resources(lf)

        # Output trade_value_usd as the primary volume metric, keeping unit_price_usd ONLY for Quality Estimator
        lf_agg = lf.group_by(["exporter_id", "importer_id", "game_resource_id"]).agg([
            (pl.col("v").sum() * self.cfg.baci_value_multiplier).alias("trade_value_usd"),
            pl.col("healed_quantity").sum().alias("physical_volume")
        ])

        lf_agg = lf_agg.filter(
            pl.col("trade_value_usd").is_not_null() & (pl.col("trade_value_usd") > 0)
        ).with_columns(
            (pl.col("trade_value_usd") / pl.col("physical_volume")).alias("unit_price_usd")
        ).drop("physical_volume")
        
        return lf_agg


class ItpdServicesLoader:
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def load_data(self) -> pl.LazyFrame:
        lf = pl.scan_csv(self.cfg.itpd_input_path)
        return lf.filter(
            (pl.col("year") == self.cfg.target_year) & 
            (pl.col("broad_sector") == "Services") &
            (pl.col("exporter_iso3") != pl.col("importer_iso3"))
        ).with_columns(
            pl.col("industry_descr").str.replace(r"^\d+\s+", "")
        ).rename({
            "exporter_iso3": "exporter_id",
            "importer_iso3": "importer_id"
        }).select(["exporter_id", "importer_id", "industry_descr", "trade"])


class ServicesManHourConverter:
    def __init__(self, config: EconomyConfig, state_loader: GameStateLoader, mapper: ServiceMapper):
        self.cfg = config
        self.state_loader = state_loader
        self.mapper = mapper

    def convert(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        eco_lf = self.state_loader.load_economy()
        lf = lf.join(eco_lf, left_on="exporter_id", right_on="country_id", how="left")
        
        mean_gdp = eco_lf.select(pl.col("gdp_per_capita").mean()).collect().item()
        lf = lf.with_columns(pl.col("gdp_per_capita").fill_null(mean_gdp))
        lf = self.mapper.map_services(lf)

        # Output trade_value_usd directly
        lf = lf.with_columns(
            (pl.col("gdp_per_capita") / self.cfg.working_hours_per_year).alias("unit_price_usd"),
            (pl.col("trade") * self.cfg.itpd_value_multiplier).alias("trade_value_usd")
        )

        return lf.select([
            "exporter_id", "importer_id", "game_resource_id", 
            "trade_value_usd", "unit_price_usd"
        ])


class OutlierProcessor:
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def process(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if not self.cfg.enable_percentile_clipping:
            return lf
            
        lower_bound = pl.col("unit_price_usd").quantile(self.cfg.clip_lower_percentile).over("game_resource_id")
        upper_bound = pl.col("unit_price_usd").quantile(self.cfg.clip_upper_percentile).over("game_resource_id")

        return lf.with_columns(
            pl.when(pl.col("unit_price_usd") > upper_bound).then(upper_bound)
            .when(pl.col("unit_price_usd") < lower_bound).then(lower_bound)
            .otherwise(pl.col("unit_price_usd"))
            .alias("unit_price_usd")
        )


class TradeConverterPipeline:
    def __init__(self, config: EconomyConfig, mapper: EconomyMapper, service_mapper: ServiceMapper, validator: GameDataValidator, out_processor: OutlierProcessor, state_loader: GameStateLoader):
        self.config = config
        self.validator = validator
        
        self.baci_loader = BaciLoader(config)
        self.baci_transformer = BaciTransformer(config, mapper)
        self.out_processor = out_processor
        
        self.itpd_loader = ItpdServicesLoader(config)
        self.services_converter = ServicesManHourConverter(config, state_loader, service_mapper)

    def run(self):
        logger.info("--- Starting International Trade Pipeline (USD VALUE MODE) ---")
        
        goods_lf = self.baci_loader.load_data()
        goods_lf = self.baci_transformer.transform(goods_lf)
        goods_lf = self.out_processor.process(goods_lf)
        
        services_lf = self.itpd_loader.load_data()
        services_lf = self.services_converter.convert(services_lf)
        
        combined_lf = pl.concat([goods_lf, services_lf])
        combined_lf = self.validator.validate(combined_lf) 
        
        target_schema = ["exporter_id", "importer_id", "game_resource_id", "trade_value_usd", "unit_price_usd"]
        combined_lf.select(target_schema).sink_parquet(self.config.trade_output_path)
        logger.info(f"Trade network (in USD) saved to {self.config.trade_output_path}")


# ==============================================================================
# PHASE 2: INTERNAL PRODUCTION PIPELINE (WIOD INTEGRATION)
# ==============================================================================

class TradeAggregator:
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def get_net_trade(self) -> pl.LazyFrame:
        trade_lf = pl.scan_parquet(self.cfg.trade_output_path)
        
        exports = trade_lf.group_by([pl.col("exporter_id").alias("country_id"), "game_resource_id"]).agg(
            pl.col("trade_value_usd").sum().alias("total_export")
        )

        imports = trade_lf.group_by([pl.col("importer_id").alias("country_id"), "game_resource_id"]).agg(
            pl.col("trade_value_usd").sum().alias("total_import")
        )

        return exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)


class QualityEstimator:
    def __init__(self, price_weight: float = 0.5, tech_weight: float = 0.5):
        self.w_price = price_weight
        self.w_tech = tech_weight

    def calculate(self, trade_lf: pl.LazyFrame, eco_lf: pl.LazyFrame, production_lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Calculating Quality Index (Using abstract unit prices)...")

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
            (pl.col("local_price") / pl.col("global_median_price")).alias("price_ratio"),
            (pl.col("gdp_per_capita") / pl.col("gdp_per_capita").mean()).alias("tech_ratio")
        ).with_columns(
            ((pl.col("price_ratio") ** self.w_price) * (pl.col("tech_ratio") ** self.w_tech)).alias("raw_quality")
        )

        eval_lf = eval_lf.with_columns(
            pl.col("raw_quality").max().alias("max_raw_quality")
        ).with_columns(
            pl.when(pl.col("game_resource_id").is_in(QUALITY_SENSITIVE_GOODS))
            .then(
                ((pl.col("raw_quality") / pl.col("max_raw_quality")) * 100).round(0).clip(1.0, 100.0)
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


class WiodLoader:
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def _detect_separator(self, file_path: Path) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if '\t' in first_line: return '\t'
            return ','

    def load_data(self) -> pl.LazyFrame:
        detected_sep = self._detect_separator(self.cfg.wiod_input_path)
        lf = pl.scan_csv(self.cfg.wiod_input_path, separator=detected_sep)

        lf = lf.with_columns(
            pl.col("total_output")
            .cast(pl.Utf8)
            .str.replace_all(",", ".")
            .str.replace_all("\xa0", "")
            .str.replace_all(" ", "")
            .str.strip_chars()
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
        return lf

class WiodProductionEstimator:
    """
    Distributes WIOD monetary output into game resources using Gross Trade Proportionality.
    Uses Trade Affinity Profiles to intelligently distribute missing RoW data.
    """
    def __init__(self, config: EconomyConfig, mapping_dict: Dict[str, List[str]]):
        self.cfg = config
        self.mapping_dict = mapping_dict
        records = []
        for wiod_cat, res_list in mapping_dict.items():
            for res in res_list:
                records.append({"category": wiod_cat, "game_resource_id": res})
        self.mapping_lf = pl.DataFrame(records).lazy()

    def estimate(self, wiod_lf: pl.LazyFrame, trade_agg_lf: pl.LazyFrame, dem_eco_lf: pl.LazyFrame) -> pl.LazyFrame:
        # Extract trade values from aggregator
        country_trade = trade_agg_lf.rename({
            "total_export": "export_usd", 
            "total_import": "import_usd"
        }).join(self.mapping_lf, on="game_resource_id", how="left")

        cat_trade = country_trade.group_by(["country_id", "category"]).agg(
            pl.col("export_usd").sum().alias("cat_export_usd"),
            pl.col("import_usd").sum().alias("cat_import_usd")
        )

        wiod_val = wiod_lf.with_columns(
            (pl.col("total_output") * self.cfg.wiod_value_multiplier).alias("wiod_output_usd")
        ).rename({"iso3": "country_id"}).select(["country_id", "category", "wiod_output_usd"])

        wiod_countries = wiod_val.filter(~pl.col("country_id").is_in(["RoW", "TOT"]))

        # Domestic Absorption (A_C = Y_C - X_C + M_C) for primary WIOD nations
        cat_macro = wiod_countries.join(cat_trade, on=["country_id", "category"], how="left").fill_null(0.0)
        cat_macro = cat_macro.with_columns(
            (pl.col("wiod_output_usd") - pl.col("cat_export_usd") + pl.col("cat_import_usd")).alias("absorption_usd")
        ).with_columns(
            pl.when(pl.col("absorption_usd") < 0).then(0.0)
            .otherwise(pl.col("absorption_usd")).alias("absorption_usd")
        )

        global_trade = country_trade.group_by("game_resource_id").agg(
            (pl.col("import_usd").sum() + pl.col("export_usd").sum()).alias("global_res_trade")
        ).join(self.mapping_lf, on="game_resource_id", how="left")
        
        global_trade = global_trade.with_columns(
            pl.when(pl.col("global_res_trade").sum().over("category") > 0)
            .then(pl.col("global_res_trade") / pl.col("global_res_trade").sum().over("category"))
            .otherwise(1.0 / pl.col("game_resource_id").count().over("category"))
            .alias("global_trade_weight")
        ).fill_null(0.0)

        res_macro = country_trade.join(cat_macro, on=["country_id", "category"], how="inner")
        res_macro = res_macro.join(
            global_trade.select(["game_resource_id", "global_trade_weight"]), 
            on="game_resource_id", how="left"
        )

        res_macro = res_macro.with_columns(
            pl.when((pl.col("cat_import_usd") + pl.col("cat_export_usd")) > 0)
            .then((pl.col("import_usd") + pl.col("export_usd")) / (pl.col("cat_import_usd") + pl.col("cat_export_usd")))
            .otherwise(pl.col("global_trade_weight"))
            .alias("resource_weight")
        )

        res_macro = res_macro.with_columns(
            (pl.col("absorption_usd") * pl.col("resource_weight")).alias("res_absorption_usd")
        )

        # Base Production for WIOD nations
        known_production = res_macro.with_columns(
            (pl.col("res_absorption_usd") + pl.col("export_usd") - pl.col("import_usd")).alias("domestic_production")
        ).with_columns(
            pl.when(pl.col("domestic_production") < 0).then(0.0)
            .otherwise(pl.col("domestic_production")).alias("domestic_production")
        ).select(["country_id", "game_resource_id", "domestic_production"])


        # --- RoW (Rest of World) Interpolation with Macro-Consumption Identity ---
        
        row_wiod = wiod_val.filter(pl.col("country_id") == "RoW")
        
        # 1. Total RoW Production per resource
        row_res = row_wiod.join(self.mapping_lf, on="category", how="inner").join(
            global_trade, on="game_resource_id", how="left"
        ).with_columns(
            (pl.col("wiod_output_usd") * pl.col("global_trade_weight")).alias("row_total_production")
        ).select(["game_resource_id", "row_total_production"])

        # Prepare demographic data for missing countries
        dem_eco_lf = dem_eco_lf.with_columns(
            (pl.col("gdp_per_capita") * pl.col("total_population")).alias("total_gdp")
        )
        missing_countries_lf = dem_eco_lf.join(
            wiod_countries.select("country_id").unique(), on="country_id", how="anti"
        )
        
        total_missing_gdp = missing_countries_lf.select(pl.col("total_gdp").sum()).collect().item() or 1.0
        total_missing_pop = missing_countries_lf.select(pl.col("total_population").sum()).collect().item() or 1.0
        
        gdp_w = self.cfg.missing_country_gdp_weight
        pop_w = 1.0 - gdp_w

        # 2. Base Macro Weight (Economic mass for CONSUMPTION capacity)
        missing_countries_lf = missing_countries_lf.with_columns(
            (((pl.col("total_gdp") / total_missing_gdp) * gdp_w) + 
             ((pl.col("total_population") / total_missing_pop) * pop_w)).alias("macro_weight")
        )

        all_resources_df = self.mapping_lf.select("game_resource_id").unique()
        missing_grid = missing_countries_lf.select(["country_id", "macro_weight"]).join(all_resources_df, how="cross")
        
        # 3. Pull in actual trade data for RoW countries
        missing_trade = missing_grid.join(
            country_trade.select(["country_id", "game_resource_id", "export_usd", "import_usd"]),
            on=["country_id", "game_resource_id"], how="left"
        ).fill_null(0.0)

        # 4. Calculate Total RoW Exports and Imports per resource
        row_trade_totals = missing_trade.group_by("game_resource_id").agg(
            pl.col("export_usd").sum().alias("row_total_export"),
            pl.col("import_usd").sum().alias("row_total_import")
        )

        # 5. Calculate Total RoW Consumption (C = P - E + I)
        row_macro = row_res.join(row_trade_totals, on="game_resource_id", how="left").fill_null(0.0)
        row_macro = row_macro.with_columns(
            (pl.col("row_total_production") - pl.col("row_total_export") + pl.col("row_total_import")).alias("row_total_consumption")
        ).with_columns(
            pl.when(pl.col("row_total_consumption") < 0).then(0.0)
            .otherwise(pl.col("row_total_consumption")).alias("row_total_consumption")
        )

        # 6. Apportion Consumption by Macro Weight, then derive Production (P = C + E - I)
        missing_production = missing_trade.join(row_macro.select(["game_resource_id", "row_total_consumption"]), on="game_resource_id", how="left")
        missing_production = missing_production.with_columns(
            (pl.col("row_total_consumption") * pl.col("macro_weight")).alias("country_consumption_usd")
        ).with_columns(
            (pl.col("country_consumption_usd") + pl.col("export_usd") - pl.col("import_usd")).alias("domestic_production")
        ).with_columns(
            # Clamp negative production to 0 (happens if a country imports drastically more than their macro_weight suggests)
            pl.when(pl.col("domestic_production") < 0).then(0.0)
            .otherwise(pl.col("domestic_production")).alias("domestic_production")
        ).select(["country_id", "game_resource_id", "domestic_production"])

        # Combine WIOD and RoW
        combined_production = pl.concat([known_production, missing_production]).group_by(["country_id", "game_resource_id"]).agg(
            pl.col("domestic_production").sum()
        )
        
        all_countries_df = dem_eco_lf.select("country_id").unique()
        complete_grid = all_countries_df.join(all_resources_df, how="cross")
        
        final_production = complete_grid.join(combined_production, on=["country_id", "game_resource_id"], how="left").with_columns(
            pl.col("domestic_production").fill_null(0.0).fill_nan(0.0)
        )
        
        return final_production

class MacroeconomicSanityChecker:
    def verify_and_heal(self, prod_lf: pl.LazyFrame, trade_agg_lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Executing mathematical sanity verification (C = P + I - E)...")
        
        eval_lf = prod_lf.join(trade_agg_lf, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)

        eval_lf = eval_lf.with_columns(
            (pl.col("domestic_production") + pl.col("total_import") - pl.col("total_export")).alias("apparent_consumption")
        )

        healed_lf = eval_lf.with_columns(
            pl.when(pl.col("apparent_consumption") < 0)
            .then(pl.col("total_export") - pl.col("total_import"))
            .otherwise(pl.col("domestic_production"))
            .alias("healed_production")
        )

        return healed_lf.select([
            "country_id", 
            "game_resource_id", 
            pl.col("healed_production").alias("domestic_production")
        ])


class InternalProductionPipeline:
    def __init__(self, config: EconomyConfig, quality_estimator: QualityEstimator, state_loader: GameStateLoader):
        self.config = config
        self.state_loader = state_loader
        
        self.wiod_loader = WiodLoader(config)
        self.trade_aggregator = TradeAggregator(config)
        self.production_estimator = WiodProductionEstimator(config, WIOD_MAPPING)
        
        self.sanity_checker = MacroeconomicSanityChecker()
        self.quality_estimator = quality_estimator

    def run(self):
        logger.info("--- Starting Internal Production Estimation (USD VALUE MODE) ---")
        
        eco_lf = self.state_loader.load_economy()
        pop_lf = self.state_loader.load_population()
        dem_eco_lf = pop_lf.join(eco_lf, on="country_id", how="inner")
        
        raw_trade_lf = pl.scan_parquet(self.config.trade_output_path)
        trade_agg_lf = self.trade_aggregator.get_net_trade()
        
        wiod_lf = self.wiod_loader.load_data()
        
        production_lf = self.production_estimator.estimate(wiod_lf, trade_agg_lf, dem_eco_lf)
        
        production_lf = self.sanity_checker.verify_and_heal(production_lf, trade_agg_lf)
        
        production_lf = self.quality_estimator.calculate(raw_trade_lf, eco_lf, production_lf)

        production_lf = production_lf.with_columns(
            pl.col("domestic_production").fill_null(0.0).fill_nan(0.0),
            pl.col("quality_index").fill_null(1).fill_nan(1)
        )

        production_lf.sink_parquet(self.config.production_output_path)
        logger.info(f"Domestic production (in USD) saved to {self.config.production_output_path}")


# ==============================================================================
# ORCHESTRATION & LOGGING
# ==============================================================================

class WorldEconomyGenerator:
    def __init__(self, config: EconomyConfig):
        self.config = config
        
        state_loader = GameStateLoader(config)
        
        mapper = EconomyMapper(GAME_MAPPING)
        service_mapper = ServiceMapper(SERVICES_MAPPING)
        validator = GameDataValidator(config)
        out_processor = OutlierProcessor(config)
        
        self.trade_pipeline = TradeConverterPipeline(
            config, mapper, service_mapper, validator, out_processor, state_loader
        )
        
        quality_estimator = QualityEstimator()
        self.production_pipeline = InternalProductionPipeline(config, quality_estimator, state_loader)

    def log_isolated_countries(self):
        prod_lf = pl.scan_parquet(self.config.production_output_path)
        trade_lf = pl.scan_parquet(self.config.trade_output_path)
        
        all_countries = prod_lf.select("country_id").unique().collect()
        
        trade_exporters = trade_lf.select(pl.col("exporter_id").alias("country_id"))
        trade_importers = trade_lf.select(pl.col("importer_id").alias("country_id"))
        trading_countries = pl.concat([trade_exporters, trade_importers]).unique().collect()
        
        isolated_countries = all_countries.join(trading_countries, on="country_id", how="anti")
        
        logger.info(f"Isolated countries (autarkies) missing from trade network: {isolated_countries['country_id'].to_list()}")

    def log_random_validation_samples(self):
        trade_lf = pl.scan_parquet(self.config.trade_output_path)
        trade_df = trade_lf.collect()
        
        if not trade_df.is_empty():
            logger.info("\n--- Random Trade Network Samples (USD) ---")
            sample_trade = trade_df.sample(n=min(5, len(trade_df))).iter_rows(named=True)
            for row in sample_trade:
                logger.info(f"  {row['exporter_id']} -> {row['importer_id']} [{row['game_resource_id']}]: ${row['trade_value_usd']:,.2f}")

        prod_lf = pl.scan_parquet(self.config.production_output_path)
        prod_df = prod_lf.collect()
        
        wiod_loader = WiodLoader(self.config)
        wiod_lf = wiod_loader.load_data()
        wiod_iso3 = wiod_lf.filter(~pl.col("iso3").is_in(["RoW", "TOT"])).select("iso3").unique().collect()["iso3"].to_list()
        
        wiod_prod_df = prod_df.filter(pl.col("country_id").is_in(wiod_iso3))
        row_prod_df = prod_df.filter(~pl.col("country_id").is_in(wiod_iso3))
        
        logger.info("\n--- Random Production Samples (USD) ---")
        if not wiod_prod_df.is_empty():
            sample_wiod = wiod_prod_df.sample(n=min(30, len(wiod_prod_df))).iter_rows(named=True)
            for row in sample_wiod:
                logger.info(f"  [WIOD Base] {row['country_id']} - {row['game_resource_id']}: ${row['domestic_production']:>15,.2f} | QI: {row['quality_index']}")
                
        if not row_prod_df.is_empty():
            sample_row = row_prod_df.sample(n=min(30, len(row_prod_df))).iter_rows(named=True)
            for row in sample_row:
                logger.info(f"  [RoW Interpolated] {row['country_id']} - {row['game_resource_id']}: ${row['domestic_production']:>15,.2f} | QI: {row['quality_index']}")

    def generate(self):
        try:
            self.trade_pipeline.run()
            self.production_pipeline.run()
            
            self.log_isolated_countries()
            self.log_random_validation_samples()
            logger.info("Global monetary economy generation completed successfully.")
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise

if __name__ == "__main__":
    
    project_root = Path(__file__).resolve().parent.parent.parent
    base_data = project_root / "modules" / "base" / "data"
    
    config = EconomyConfig(
        baci_input_path=Path(".temp//BACI_HS96_Y2001_V202601.csv"),
        itpd_input_path=Path(".temp//ITPD_E_R03.csv"),
        wiod_input_path=Path(".temp//WIOT01_ROW_Apr12.tsv"),
        country_map_path=Path(".temp//country_codes_V202601.csv"),
        valid_countries_path=base_data / "countries" / "countries.tsv",
        pop_data_path=base_data / "regions" / "regions_pop.tsv",
        eco_data_path=base_data / "countries" / "countries_eco.tsv",
        trade_output_path=base_data / "world" / "trade_network.parquet",
        production_output_path=base_data / "world" / "domestic_production.parquet",
        target_year=2001,
        enable_percentile_clipping=True
    )

    if not config.baci_input_path.exists():
        logger.warning(f"BACI input not found at: {config.baci_input_path}. Please place the dataset.")
    elif not config.itpd_input_path.exists():
        logger.warning(f"ITPD-E input not found at: {config.itpd_input_path}. Please place the dataset.")
    elif not config.wiod_input_path.exists():
        logger.warning(f"WIOD input not found at: {config.wiod_input_path}. Please place the dataset.")
    else:
        generator = WorldEconomyGenerator(config)
        generator.generate()