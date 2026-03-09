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
logger = logging.getLogger("BaciConverter")

# OpenPower specific mapping defining the game's economic sectors.
# Kept separate from the pipeline logic for easy balance tweaking.
GAME_MAPPING = {
    "cereals": ["10", "11"],
    "vegetables_and_fruits": ["07", "08", "20"],
    "meat_and_fish": ["01", "02", "03", "16"],
    "dairy": ["04"],
    "tobacco": ["24"],
    "drugs_and_raw_plants": ["06", "09", "12", "13", "14"],
    "other_food_and_beverages": ["05", "15", "17", "18", "19", "21", "22", "23"],
    
    # 2716 is extracted specifically to separate electrical grids from raw fuel reserves.
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


@dataclass
class PipelineConfig:
    """Configuration object for the BACI processing pipeline."""
    baci_input_path: Path
    country_map_path: Path
    output_path: Path
    
    # Processing Thresholds & Rules
    target_year: int = 2001
    min_quantity_tons: float = 1.0
    
    # BACI Raw Schema
    col_year: str = "t"
    col_exporter: str = "i"
    col_importer: str = "j"
    col_product: str = "k"
    col_value: str = "v"  # In thousands of USD
    col_quantity: str = "q"  # In metric tons
    
    # Mapping Schema
    map_code_col: str = "country_code"
    map_iso_col: str = "iso_3"


class EconomyMapper:
    """
    Translates HS product codes into the OpenPower game resource categories.
    
    We build native polars DataFrames for the lookup instead of using standard python 
    dictionaries with `map_elements`. This preserves the C-level execution speed of 
    polars and avoids breaking the lazy computation graph.
    """
    def __init__(self, mapping_dict: Dict[str, List[str]]):
        map_2d, map_4d = {}, {}
        for resource, codes in mapping_dict.items():
            for code in codes:
                if len(code) == 2:
                    map_2d[code] = resource
                elif len(code) == 4:
                    map_4d[code] = resource
                else:
                    # Explaining unidiomatic behavior: We explicitly crash here rather than logging 
                    # a warning to enforce strict schema adherence during development.
                    raise ValueError(f"Invalid HS code length in mapping config: {code}")
        
        # We store the lookup tables as LazyFrames to join directly in the processing pipeline.
        self.lf_map_2d = pl.DataFrame({
            "hs2_code": list(map_2d.keys()), 
            "res_2d": list(map_2d.values())
        }).lazy()
        
        self.lf_map_4d = pl.DataFrame({
            "hs4_code": list(map_4d.keys()), 
            "res_4d": list(map_4d.values())
        }).lazy()

    def map_resources(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        """Joins the lookup tables and resolves the final game resource ID."""
        # 1. Join explicit 4-digit exceptions (e.g., 2716 -> electricity)
        lf = lf.join(self.lf_map_4d, on="hs4_code", how="left")
        
        # 2. Join broad 2-digit chapter categories (e.g., 25 -> minerals)
        lf = lf.join(self.lf_map_2d, on="hs2_code", how="left")
        
        # 3. Coalesce resolves the mapping: 4-digit rules take priority over 2-digit rules.
        # Reference for coalesce logic: https://docs.pola.rs/user-guide/expressions/null/#coalesce
        return lf.with_columns(
            pl.coalesce("res_4d", "res_2d").fill_null("unclassified").alias("game_resource_id")
        ).drop(["res_4d", "res_2d"])


class BaciLoader:
    """Handles raw data ingestion and country code mapping."""
    def __init__(self, config: PipelineConfig):
        self.cfg = config

    def _get_country_mapping(self) -> pl.LazyFrame:
        """Loads and prepares the country mapping table."""
        return pl.scan_csv(self.cfg.country_map_path).select([
            pl.col(self.cfg.map_code_col).cast(pl.Int64),
            pl.col(self.cfg.map_iso_col)
        ])

    def load_data(self) -> pl.LazyFrame:
        """Loads trade data and maps UN codes to ISO-3 codes."""
        logger.info(f"Scanning raw trade data from {self.cfg.baci_input_path}")
        
        if self.cfg.baci_input_path.suffix.lower() == '.csv':
            lf = pl.scan_csv(self.cfg.baci_input_path)
        else:
            lf = pl.scan_parquet(self.cfg.baci_input_path)
            
        mapping_lf = self._get_country_mapping()
        lf = lf.filter(pl.col(self.cfg.col_year) == self.cfg.target_year)

        # Map Exporter
        lf = lf.join(
            mapping_lf, left_on=self.cfg.col_exporter, right_on=self.cfg.map_code_col, how="left"
        ).rename({self.cfg.map_iso_col: "exporter_id"})

        # Map Importer
        lf = lf.join(
            mapping_lf, left_on=self.cfg.col_importer, right_on=self.cfg.map_code_col, how="left"
        ).rename({self.cfg.map_iso_col: "importer_id"})
        
        return lf.drop_nulls(subset=["exporter_id", "importer_id"])


class BaciTransformer:
    """Applies economic logic, categorization, and gap-healing using hierarchical imputation."""
    def __init__(self, config: PipelineConfig, mapper: EconomyMapper):
        self.cfg = config
        self.mapper = mapper

    def transform(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Applying hierarchical categorization and economic transformations...")
        
        # Extract hierarchical HS codes for imputation and mapping
        lf = lf.with_columns(
            pl.col(self.cfg.col_product).cast(pl.Utf8).str.zfill(6).alias("hs6_code")
        ).with_columns(
            pl.col("hs6_code").str.slice(0, 4).alias("hs4_code"),
            pl.col("hs6_code").str.slice(0, 2).alias("hs2_code")
        )

        def calculate_unit_price(level: str) -> pl.Expr:
            # Multiplied by 1000 to convert BACI's 'thousands of USD' into raw USD
            return (
                (pl.col(self.cfg.col_value).sum().over(level) * 1000) / 
                pl.col(self.cfg.col_quantity).sum().over(level)
            )

        # Calculate unit value (price per ton) at multiple aggregation levels for imputation.
        # Methodology from: https://unstats.un.org/unsd/trade/data/imputation.asp
        lf = lf.with_columns(
            calculate_unit_price("hs6_code").alias("price_hs6"),
            calculate_unit_price("hs4_code").alias("price_hs4"),
            calculate_unit_price("hs2_code").alias("price_hs2"),
            ((pl.col(self.cfg.col_value).sum() * 1000) / pl.col(self.cfg.col_quantity).sum()).alias("price_global")
        )

        lf = lf.with_columns(
            pl.coalesce("price_hs6", "price_hs4", "price_hs2", "price_global").alias("best_estimated_price")
        ).with_columns(
            pl.coalesce(
                pl.col(self.cfg.col_quantity),
                (pl.col(self.cfg.col_value) * 1000) / pl.col("best_estimated_price")
            ).alias("healed_quantity")
        )

        lf = lf.filter(pl.col("healed_quantity") >= self.cfg.min_quantity_tons)

        # Map to OpenPower game resources before aggregation
        lf = self.mapper.map_resources(lf)

        logger.info("Aggregating bilateral trade flows into game sectors...")
        
        # Group by the resolved game resource rather than the raw HS code
        lf_agg = lf.group_by(["exporter_id", "importer_id", "game_resource_id"]).agg([
            pl.col(self.cfg.col_value).sum().alias("total_v"),
            pl.col("healed_quantity").sum().alias("annual_volume_tons")
        ])

        # Exclude strict zeroes to prevent division by zero in downstream engine modules.
        # TODO: Engine currently drops zero-volume flows. Evaluate if we need to keep them as 
        # dormant connection edges in the network graph for future dynamic routing.
        lf_agg = lf_agg.filter(
            pl.col("annual_volume_tons").is_not_null() & (pl.col("annual_volume_tons") > 0)
        ).with_columns(
            ((pl.col("total_v") * 1000) / pl.col("annual_volume_tons")).alias("unit_price_usd")
        )
        
        return lf_agg


class BaciExporter:
    """Enforces target schema and handles I/O."""
    def __init__(self, config: PipelineConfig):
        self.cfg = config
        self.target_schema = [
            "exporter_id", "importer_id", "game_resource_id", 
            "annual_volume_tons", "unit_price_usd"
        ]

    def export(self, lf: pl.LazyFrame):
        logger.info(f"Enforcing schema and exporting to {self.cfg.output_path}...")
        
        # Final schema check to guarantee compatibility with OpenPower ingestion
        final_lf = lf.select(self.target_schema)
        final_lf.sink_parquet(self.cfg.output_path)
        logger.info("Export complete! Data is ready for the OpenPower engine.")


class TradeConverterPipeline:
    """Orchestrator class utilizing Composition over Inheritance."""
    def __init__(self, config: PipelineConfig, mapper: EconomyMapper):
        self.loader = BaciLoader(config)
        
        # BaciTransformer relies on the EconomyMapper via composition
        self.transformer = BaciTransformer(config, mapper)
        self.exporter = BaciExporter(config)

    def run(self):
        try:
            raw_lf = self.loader.load_data()
            transformed_lf = self.transformer.transform(raw_lf)
            self.exporter.export(transformed_lf)
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise

if __name__ == "__main__":
    config = PipelineConfig(
        baci_input_path=Path("BACI_HS92_Y2001_V202401.csv"),
        country_map_path=Path("country_codes.csv"),
        output_path=Path("OpenPower_Trade_Network.parquet"),
        target_year=2001
    )

    if not config.baci_input_path.exists():
        logger.warning(f"Input not found: {config.baci_input_path}. Please place the data file in the directory.")
    else:
        # Instantiate mapper and pass it into the pipeline to decouple mapping rules from pipeline logic
        economy_mapper = EconomyMapper(GAME_MAPPING)
        pipeline = TradeConverterPipeline(config, economy_mapper)
        pipeline.run()