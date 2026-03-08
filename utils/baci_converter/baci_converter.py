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
    """Applies economic logic, categorization, and gap-healing using hierarchical imputation."""
    def __init__(self, config: 'PipelineConfig'):
        self.cfg = config

    def transform(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        logger.info("Applying hierarchical categorization and economic transformations...")
        
        # Extract hierarchical HS codes. 
        # This allows us to group data at different levels of granularity (Product -> Sub-group -> Chapter)
        # to calculate increasingly broad price proxies when specific data is missing.
        lf = lf.with_columns(
            pl.col(self.cfg.col_product).cast(pl.Utf8).str.zfill(6).alias("hs6_code")
        ).with_columns(
            pl.col("hs6_code").str.slice(0, 4).alias("hs4_code"),
            pl.col("hs6_code").str.slice(0, 2).alias("resource_id")
        )

        # Calculate unit value (price per ton) at multiple aggregation levels.
        # BACI values are in thousands of USD, so we multiply by 1000 to get the raw USD value.
        # Reference for Unit Value methodologies in trade data: 
        # https://unstats.un.org/unsd/trade/data/imputation.asp
        def calculate_unit_price(level: str) -> pl.Expr:
            return (
                (pl.col(self.cfg.col_value).sum().over(level) * 1000) / 
                pl.col(self.cfg.col_quantity).sum().over(level)
            )

        lf = lf.with_columns(
            calculate_unit_price("hs6_code").alias("price_hs6"),
            calculate_unit_price("hs4_code").alias("price_hs4"),
            calculate_unit_price("resource_id").alias("price_hs2"),
            # The ultimate fallback if the entire dataset lacks volume data for a category
            ((pl.col(self.cfg.col_value).sum() * 1000) / pl.col(self.cfg.col_quantity).sum()).alias("price_global")
        )

        # Impute missing quantities.
        # We coalesce prices from most granular to least granular. If a highly specific HS6 price exists, 
        # it is used; otherwise, the engine falls back to the broader HS4 price, and so on.
        lf = lf.with_columns(
            pl.coalesce("price_hs6", "price_hs4", "price_hs2", "price_global").alias("best_estimated_price")
        ).with_columns(
            pl.coalesce(
                pl.col(self.cfg.col_quantity),
                (pl.col(self.cfg.col_value) * 1000) / pl.col("best_estimated_price")
            ).alias("healed_quantity")
        )

        # Filter out negligible dust data that could bloat the game engine's trade network
        lf = lf.filter(pl.col("healed_quantity") >= self.cfg.min_quantity_tons)

        logger.info("Aggregating bilateral trade flows...")
        lf_agg = lf.group_by(["exporter_id", "importer_id", "resource_id"]).agg([
            pl.col(self.cfg.col_value).sum().alias("total_v"),
            pl.col("healed_quantity").sum().alias("annual_volume_tons")
        ])

        # Final pass to calculate the unified price for the simulated economy.
        # Excludes strict zeroes to prevent division by zero in downstream engine modules.
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