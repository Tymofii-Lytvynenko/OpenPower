import polars as pl
from pathlib import Path
from dataclasses import dataclass
import logging

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BaciConverter")

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
        
        # Support both CSV and Parquet based on the file extension
        if self.cfg.baci_input_path.suffix.lower() == '.csv':
            lf = pl.scan_csv(self.cfg.baci_input_path)
        else:
            lf = pl.scan_parquet(self.cfg.baci_input_path)
            
        mapping_lf = self._get_country_mapping()
        
        # Filter by target year early to reduce memory footprint
        lf = lf.filter(pl.col(self.cfg.col_year) == self.cfg.target_year)

        # Map Exporter
        lf = lf.join(
            mapping_lf, left_on=self.cfg.col_exporter, right_on=self.cfg.map_code_col, how="left"
        ).rename({self.cfg.map_iso_col: "exporter_id"})

        # Map Importer
        lf = lf.join(
            mapping_lf, left_on=self.cfg.col_importer, right_on=self.cfg.map_code_col, how="left"
        ).rename({self.cfg.map_iso_col: "importer_id"})
        
        # Drop rows where mapping failed (we need valid ISOs for the engine)
        return lf.drop_nulls(subset=["exporter_id", "importer_id"])


class BaciTransformer:
    """Applies economic logic, categorization, and gap-healing."""
    def __init__(self, config: PipelineConfig):
        self.cfg = config

    def transform(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Applying HS2 categorization and economic transformations...")
        
        # 1. HS6 to HS2 categorization
        # Pad with 0s to ensure 6 digits (e.g., '10111' -> '010111'), then slice first 2
        lf = lf.with_columns(
            pl.col(self.cfg.col_product)
            .cast(pl.Utf8)
            .str.zfill(6)
            .str.slice(0, 2)
            .alias("resource_id")
        )

        # 2. Economic Gap Healing (Impute missing quantities)
        # Some BACI records have value (v) but missing quantity (q).
        # We calculate the global weighted average price for the HS2 category to estimate the missing mass.
        lf = lf.with_columns([
            (pl.col(self.cfg.col_value).sum().over("resource_id") * 1000 / 
             pl.col(self.cfg.col_quantity).sum().over("resource_id")
            ).alias("global_avg_price_per_ton")
        ])
        
        lf = lf.with_columns(
            pl.coalesce(
                pl.col(self.cfg.col_quantity),
                (pl.col(self.cfg.col_value) * 1000) / pl.col("global_avg_price_per_ton")
            ).alias("healed_quantity")
        )

        # 3. Noise Reduction
        lf = lf.filter(pl.col("healed_quantity") >= self.cfg.min_quantity_tons)

        # 4. Aggregation by Exporter, Importer, and Resource
        logger.info("Aggregating bilateral trade flows...")
        lf_agg = lf.group_by(["exporter_id", "importer_id", "resource_id"]).agg([
            pl.col(self.cfg.col_value).sum().alias("total_v"),
            pl.col("healed_quantity").sum().alias("annual_volume_tons")
        ])

        # 5. Calculate final Unit Price and apply Self-Healing rule (drop <= 0)
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
            "exporter_id", "importer_id", "resource_id", 
            "annual_volume_tons", "unit_price_usd"
        ]

    def export(self, lf: pl.LazyFrame):
        logger.info(f"Enforcing schema and exporting to {self.cfg.output_path}...")
        
        # Enforce exact columns and order
        final_lf = lf.select(self.target_schema)
        
        # Execute the lazy graph and stream to disk
        # sink_parquet is highly memory efficient for large datasets
        final_lf.sink_parquet(self.cfg.output_path)
        logger.info("Export complete! Data is ready for the OpenPower engine.")


class TradeConverterPipeline:
    """Orchestrator class utilizing Composition over Inheritance."""
    def __init__(self, config: PipelineConfig):
        self.loader = BaciLoader(config)
        self.transformer = BaciTransformer(config)
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
    # Setup configuration paths
    # (Adjust file names to match your actual local data files)
    config = PipelineConfig(
        baci_input_path=Path("BACI_HS92_Y2001_V202401.csv"),
        country_map_path=Path("country_codes.csv"),
        output_path=Path("OpenPower_Trade_Network.parquet"),
        target_year=2001
    )

    if not config.baci_input_path.exists():
        logger.warning(f"Input not found: {config.baci_input_path}. Please place the data file in the directory.")
    else:
        pipeline = TradeConverterPipeline(config)
        pipeline.run()