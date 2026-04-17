"""
=========================================================================================
ARCHIVAL NOTE: HISTORICAL PHYSICAL VOLUME ESTIMATION & MACRO-ABSORPTION
=========================================================================================
Previous iterations of this generator attempted to calculate physical production volumes 
(e.g., tons, Megawatts) and strict Macroeconomic Consumption (C = P + I - E). 

Those approaches were archived in favor of a "Top-Down GDP Profile" simulation (similar 
to classic Grand Strategy engines like SuperPower 2). Macroeconomic datasets (WIOD/BACI) 
contain fundamental incompatibilities that prevent 1:1 physical or absolute monetary extraction:
1. The Aggregation Illusion: WIOD groups high-value goods (meat, dairy) and low-value 
   bulk goods (cereals) into a single "Agriculture" sector, making physical extraction impossible.
2. Export vs. Domestic Price Gap: BACI prices include international logistics. Domestic 
   prices are vastly lower, severely deflating physical estimates if divided directly.
3. Interpolation Artifacts: Trying to mathematically derive production from trade 
   (P = C + E - I) for missing countries (RoW) generates anomalies (e.g., oil nations 
   spawning massive textile industries due to their high GDP vs. low import reporting).

CURRENT ARCHITECTURE (TOP-DOWN GDP PERCENTAGE):
The engine now creates a 'Unique Percentage Profile' (Sector Weights) for each country.
- WIOD Countries: Sector weights are directly extracted from the WIOD Input-Output tables.
- RoW Countries: Sector weights are a normalized blend of the Global Average Profile 
  (ensuring base services/food exist) + their local BACI Export Profile (ensuring 
  natural monopolies like Oil or Minerals are preserved).
- Final Production: Country Total GDP * Unique Percentage Profile. 
This guarantees 100% mathematical stability, 0 negative values, and perfect scaling.
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
        pop_lf = self.load_population()
        eco_lf = pl.scan_csv(self.cfg.eco_data_path, separator='\t').rename({"id": "country_id"})
        
        return eco_lf.join(pop_lf, on="country_id", how="left").with_columns(
            pl.col("gdp").alias("total_gdp"),
            pl.when(pl.col("total_population") > 0)
            .then(pl.col("gdp") / pl.col("total_population"))
            .otherwise(0.0)
            .alias("gdp_per_capita")
        ).select(["country_id", "total_gdp", "gdp_per_capita"])


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
# PHASE 2: INTERNAL PRODUCTION PIPELINE (TOP-DOWN GDP PERCENTAGE)
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
    Distributes monetary output using Top-Down Percentage Profiles derived from WIOD and GDP.
    - WIOD nations use explicit sector weights from the dataset.
    - RoW nations use a blended profile (Global Average + Local Export Intensity).
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
        all_resources_df = self.mapping_lf.select("game_resource_id").unique()
        all_countries_df = dem_eco_lf.select("country_id").unique()
        
        base_grid = all_countries_df.join(all_resources_df, how="cross").join(
            self.mapping_lf, on="game_resource_id", how="left"
        )

        country_trade = base_grid.join(
            trade_agg_lf.rename({"total_export": "export_usd", "total_import": "import_usd"}),
            on=["country_id", "game_resource_id"], 
            how="left"
        ).fill_null(0.0)

        country_trade = country_trade.with_columns(
            pl.col("export_usd").sum().over(["country_id", "category"]).alias("cat_export_usd"),
            pl.col("export_usd").sum().over("game_resource_id").alias("global_res_export"),
            pl.col("export_usd").sum().over("category").alias("global_cat_export")
        )

        country_trade = country_trade.with_columns(
            pl.when(pl.col("cat_export_usd") > 0)
            .then(pl.col("export_usd") / pl.col("cat_export_usd"))
            .otherwise(
                pl.when(pl.col("global_cat_export") > 0)
                .then(pl.col("global_res_export") / pl.col("global_cat_export"))
                .otherwise(1.0 / pl.col("game_resource_id").count().over("category"))
            ).alias("intra_cat_weight")
        )

        wiod_val = wiod_lf.with_columns(
            (pl.col("total_output") * self.cfg.wiod_value_multiplier).alias("wiod_output_usd")
        ).rename({"iso3": "country_id"}).select(["country_id", "category", "wiod_output_usd"])

        wiod_countries_list = wiod_val.filter(~pl.col("country_id").is_in(["RoW", "TOT"])).select("country_id").unique()

        wiod_macro = country_trade.join(wiod_countries_list, on="country_id", how="inner")
        wiod_macro = wiod_macro.join(wiod_val, on=["country_id", "category"], how="left").fill_null(0.0)

        wiod_macro = wiod_macro.with_columns(
            pl.col("wiod_output_usd").sum().over("country_id").alias("country_wiod_total")
        ).with_columns(
            pl.when(pl.col("country_wiod_total") > 0)
            .then(pl.col("wiod_output_usd") / pl.col("country_wiod_total"))
            .otherwise(0.0).alias("cat_weight")
        )

        wiod_macro = wiod_macro.with_columns(
            (pl.col("cat_weight") * pl.col("intra_cat_weight")).alias("profile_weight")
        )

        wiod_macro = wiod_macro.with_columns(
            (pl.col("profile_weight") / pl.col("profile_weight").sum().over("country_id")).alias("profile_weight")
        ).fill_null(0.0).fill_nan(0.0)

        global_profile = wiod_macro.group_by("game_resource_id").agg(
            pl.col("profile_weight").mean().alias("global_avg_profile")
        )
        global_profile = global_profile.with_columns(
            (pl.col("global_avg_profile") / pl.col("global_avg_profile").sum()).alias("global_avg_profile")
        )

        row_macro = country_trade.join(wiod_countries_list, on="country_id", how="anti")
        row_macro = row_macro.join(global_profile, on="game_resource_id", how="left")

        row_macro = row_macro.with_columns(
            pl.col("export_usd").sum().over("country_id").alias("country_total_export")
        )

        row_macro = row_macro.with_columns(
            pl.when(pl.col("country_total_export") > 0)
            .then(pl.col("global_avg_profile") + (pl.col("export_usd") / pl.col("country_total_export")))
            .otherwise(pl.col("global_avg_profile")).alias("raw_profile_weight")
        )

        row_macro = row_macro.with_columns(
            (pl.col("raw_profile_weight") / pl.col("raw_profile_weight").sum().over("country_id")).alias("profile_weight")
        ).fill_null(0.0).fill_nan(0.0)

        # Merge profiles and attach origin types for debugging
        all_profiles = pl.concat([
            wiod_macro.select([
                "country_id", "game_resource_id", "profile_weight", 
                pl.lit("WIOD").alias("origin_type"), "cat_weight", "intra_cat_weight"
            ]),
            row_macro.select([
                "country_id", "game_resource_id", "profile_weight", 
                pl.lit("RoW").alias("origin_type"), "global_avg_profile", "export_usd", "country_total_export"
            ])
        ], how="diagonal")

        final_production = all_profiles.join(dem_eco_lf.select(["country_id", "total_gdp"]), on="country_id", how="left")
        
        final_production = final_production.with_columns(
            (pl.col("total_gdp") * pl.col("profile_weight")).alias("domestic_production")
        ).fill_null(0.0).fill_nan(0.0)

        # --- DEBUG EXPORT ---
        debug_df = final_production.filter(
            (pl.col("domestic_production") > 0) & (pl.col("domestic_production") < 100000)
        ).collect()

        if not debug_df.is_empty():
            logger.info("\n" + "="*80)
            logger.info("DEBUG: CALCULATION CHAIN FOR PRODUCTION < $100,000")
            logger.info("="*80)
            
            sample_records = debug_df.sample(n=min(50, len(debug_df))) 
            
            for row in sample_records.iter_rows(named=True):
                country = row['country_id']
                res = row['game_resource_id']
                prod = row['domestic_production']
                gdp = row['total_gdp']
                pw = row['profile_weight']
                
                if row['origin_type'] == "WIOD":
                    cw = row.get('cat_weight') or 0.0
                    icw = row.get('intra_cat_weight') or 0.0
                    logger.info(f"[WIOD] {country} | {res:<25} | Prod: ${prod:>9,.2f}")
                    logger.info(f"       Chain: GDP (${gdp:,.0f}) * Final Profile Weight ({pw:.8%})")
                    logger.info(f"       Derivation: Category Weight ({cw:.6%}) * Intra-Category Weight ({icw:.6%})")
                else:
                    ga = row.get('global_avg_profile') or 0.0
                    exp = row.get('export_usd') or 0.0
                    tot_exp = row.get('country_total_export') or 0.0
                    exp_share = (exp / tot_exp) if tot_exp > 0 else 0.0
                    logger.info(f"[RoW ] {country} | {res:<25} | Prod: ${prod:>9,.2f}")
                    logger.info(f"       Chain: GDP (${gdp:,.0f}) * Final Profile Weight ({pw:.8%})")
                    logger.info(f"       Derivation: Global Avg ({ga:.6%}) + Local Export Share ({exp_share:.6%} from ${exp:,.0f}/${tot_exp:,.0f})")
            logger.info("="*80 + "\n")
        # --------------------

        return final_production.select(["country_id", "game_resource_id", "domestic_production"])


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
        logger.info("--- Starting Internal Production Estimation (TOP-DOWN GDP PERCENTAGE MODE) ---")
        
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
            sample_wiod = wiod_prod_df.sample(n=min(10, len(wiod_prod_df))).iter_rows(named=True)
            for row in sample_wiod:
                logger.info(f"  [WIOD Base] {row['country_id']} - {row['game_resource_id']}: ${row['domestic_production']:>15,.2f} | QI: {row['quality_index']}")
                
        if not row_prod_df.is_empty():
            sample_row = row_prod_df.sample(n=min(10, len(row_prod_df))).iter_rows(named=True)
            for row in sample_row:
                logger.info(f"  [RoW Interpolated] {row['country_id']} - {row['game_resource_id']}: ${row['domestic_production']:>15,.2f} | QI: {row['quality_index']}")

    def generate(self):
        try:
            self.trade_pipeline.run()
            self.production_pipeline.run()
            
            self.log_isolated_countries()
            self.log_random_validation_samples()
            logger.info("Global Top-Down monetary economy generation completed successfully.")
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