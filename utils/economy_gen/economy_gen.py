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

        lf = lf.join(eco_lf, left_on="exporter_id", right_on="country_id", how="left")
        lf = lf.with_columns(
            pl.col("gdp_per_capita").fill_null(self.cfg.baseline_gdp_pc)
        )

        lf = self.mapper.map_services(lf)

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
# PHASE 2: INTERNAL PRODUCTION PIPELINE (WIOD INTEGRATION)
# ==============================================================================

class TradeAggregator:
    """Extracts aggregate import/export volumes from the previously generated trade network."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def get_net_trade(self) -> pl.LazyFrame:
        trade_lf = pl.scan_parquet(self.cfg.trade_output_path)
        
        exports = trade_lf.group_by([pl.col("exporter_id").alias("country_id"), "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("total_export")
        )

        imports = trade_lf.group_by([pl.col("importer_id").alias("country_id"), "game_resource_id"]).agg(
            pl.col("annual_volume").sum().alias("total_import")
        )

        return exports.join(imports, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)


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


class WiodLoader:
    """Handles parsing of the WIOD dataset."""
    def __init__(self, config: EconomyConfig):
        self.cfg = config

    def _detect_separator(self, file_path: Path) -> str:
        """Автоматично визначає роздільник, перевіряючи перший рядок файлу."""
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if '\t' in first_line:
                return '\t'
            return ','

    def load_data(self) -> pl.LazyFrame:
        detected_sep = self._detect_separator(self.cfg.wiod_input_path)
        
        lf = pl.scan_csv(self.cfg.wiod_input_path, separator=detected_sep)

        lf = lf.with_columns(
            pl.col("total_output")
            .cast(pl.Utf8)
            .str.replace_all(",", ".")
            .str.strip_chars()
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
        
        return lf

class WiodProductionEstimator:
    """Distributes WIOD monetary output into physical volumes and interpolates missing countries."""
    def __init__(self, mapping_dict: Dict[str, List[str]]):
        records = []
        for wiod_cat, res_list in mapping_dict.items():
            for res in res_list:
                records.append({"category": wiod_cat, "game_resource_id": res})
        self.mapping_lf = pl.DataFrame(records).lazy()

    def estimate(self, wiod_lf: pl.LazyFrame, trade_lf: pl.LazyFrame, dem_eco_lf: pl.LazyFrame) -> pl.LazyFrame:
        resource_values = trade_lf.group_by("game_resource_id").agg(
            (pl.col("annual_volume") * pl.col("unit_price_usd")).sum().alias("global_trade_value"),
            pl.col("unit_price_usd").median().alias("global_median_price")
        )

        mapping_shares = self.mapping_lf.join(resource_values, on="game_resource_id", how="left")
        mapping_shares = mapping_shares.with_columns(
            pl.col("global_trade_value").fill_null(1.0)
        ).with_columns(
            (pl.col("global_trade_value") / pl.col("global_trade_value").sum().over("category")).alias("share_in_category")
        )

        wiod_mapped = wiod_lf.join(mapping_shares, on="category", how="inner")
        
        wiod_mapped = wiod_mapped.with_columns(
            ((pl.col("total_output") * 1_000_000 * pl.col("share_in_category")) / pl.col("global_median_price"))
            .alias("domestic_production")
        )

        wiod_countries = wiod_mapped.filter(~pl.col("iso3").is_in(["RoW", "TOT"])).select(pl.col("iso3").unique())
        
        dem_eco_lf = dem_eco_lf.with_columns(
            (pl.col("gdp_per_capita") * pl.col("total_population")).alias("total_gdp")
        )
        
        missing_countries_lf = dem_eco_lf.join(wiod_countries, left_on="country_id", right_on="iso3", how="anti")
        
        total_missing_gdp = missing_countries_lf.select(pl.col("total_gdp").sum()).collect().item()
        
        row_data = wiod_mapped.filter(pl.col("iso3") == "RoW").select([
            "game_resource_id", "domestic_production"
        ]).rename({"domestic_production": "row_total_production"})
        
        missing_production = missing_countries_lf.join(row_data, how="cross").with_columns(
            (pl.col("row_total_production") * (pl.col("total_gdp") / total_missing_gdp)).alias("domestic_production")
        ).select(["country_id", "game_resource_id", "domestic_production"])

        known_production = wiod_mapped.filter(~pl.col("iso3").is_in(["RoW", "TOT"])).select([
            pl.col("iso3").alias("country_id"), "game_resource_id", "domestic_production"
        ])

        final_production = pl.concat([known_production, missing_production]).group_by(["country_id", "game_resource_id"]).agg(
            pl.col("domestic_production").sum()
        )
        
        return final_production


class MacroeconomicSanityChecker:
    """
    Validates the physical limits of the generated economy to prevent negative consumption.
    Formula: Consumption (C) = Production (P) + Imports (I) - Exports (E)
    Rule: C >= 0. If C < 0, a country exported goods it neither produced nor imported.
    """
    def verify_and_heal(self, prod_lf: pl.LazyFrame, trade_agg_lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Executing mathematical sanity verification (C = P + I - E)...")
        
        # Merge production with aggregate imports and exports
        eval_lf = prod_lf.join(trade_agg_lf, on=["country_id", "game_resource_id"], how="full", coalesce=True).fill_null(0.0)

        # Calculate Apparent Consumption
        eval_lf = eval_lf.with_columns(
            (pl.col("domestic_production") + pl.col("total_import") - pl.col("total_export")).alias("apparent_consumption")
        )

        # Explaining unidiomatic code: We don't eagerly evaluate (collect) here just to log the number of anomalies 
        # to keep memory usage low. Instead, we mathematically "heal" the violations directly in the LazyFrame graph.
        # Healing rule: If Consumption is negative, raise Production to the exact minimum needed to cover Net Exports.
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
        self.production_estimator = WiodProductionEstimator(WIOD_MAPPING)
        
        self.sanity_checker = MacroeconomicSanityChecker()
        self.quality_estimator = quality_estimator

    def run(self):
        logger.info("--- Starting Internal Production Estimation (WIOD based) ---")
        
        eco_lf = self.state_loader.load_economy()
        pop_lf = self.state_loader.load_population()
        dem_eco_lf = pop_lf.join(eco_lf, on="country_id", how="inner")
        
        raw_trade_lf = pl.scan_parquet(self.config.trade_output_path)
        trade_agg_lf = self.trade_aggregator.get_net_trade()
        
        wiod_lf = self.wiod_loader.load_data()
        
        # 1. Estimate base production from WIOD
        production_lf = self.production_estimator.estimate(wiod_lf, raw_trade_lf, dem_eco_lf)
        
        # 2. Sanity Check & Heal: Ensure P + I >= E
        production_lf = self.sanity_checker.verify_and_heal(production_lf, trade_agg_lf)
        
        # 3. Calculate Quality Index based on healed physical data
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
        
        mapper = EconomyMapper(GAME_MAPPING)
        service_mapper = ServiceMapper(SERVICES_MAPPING)
        validator = GameDataValidator(config)
        out_processor = OutlierProcessor(config)
        
        self.trade_pipeline = TradeConverterPipeline(
            config, mapper, service_mapper, validator, out_processor, state_loader
        )
        
        quality_estimator = QualityEstimator(config.baseline_gdp_pc)
        self.production_pipeline = InternalProductionPipeline(config, quality_estimator, state_loader)

    def log_isolated_countries(self):
        """Identifies and logs countries present in the game world but missing from the trade network."""
        prod_lf = pl.scan_parquet(self.config.production_output_path)
        trade_lf = pl.scan_parquet(self.config.trade_output_path)
        
        all_countries = prod_lf.select("country_id").unique().collect()
        
        trade_exporters = trade_lf.select(pl.col("exporter_id").alias("country_id"))
        trade_importers = trade_lf.select(pl.col("importer_id").alias("country_id"))
        trading_countries = pl.concat([trade_exporters, trade_importers]).unique().collect()
        
        isolated_countries = all_countries.join(trading_countries, on="country_id", how="anti")
        
        logger.info(f"Isolated countries (autarkies) missing from trade network: {isolated_countries['country_id'].to_list()}")

    def generate(self):
        try:
            self.trade_pipeline.run()
            self.production_pipeline.run()
            self.log_isolated_countries()
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
        wiod_input_path=Path(".temp//WIOT01_ROW_Apr12.tsv"),
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
    elif not config.wiod_input_path.exists():
        logger.warning(f"WIOD input not found at: {config.wiod_input_path}. Please place the dataset.")
    else:
        generator = WorldEconomyGenerator(config)
        generator.generate()