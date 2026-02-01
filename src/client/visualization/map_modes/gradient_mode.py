import polars as pl
import math
from typing import Dict, Tuple
from src.server.state import GameState
from src.client.visualization.map_modes.base_map_mode import BaseMapMode
from src.client.utils.gradient import get_heatmap_color, lerp_color


class GradientMapMode(BaseMapMode):
    def __init__(self,
                 mode_name: str,
                 column_name: str,
                 fallback_to_country: bool = True,
                 use_percentile: bool = False,  # <--- Fixes "All Blue"
                 steps: int = 0):  # <--- Creates "Groups"

        self._name = mode_name
        self.column_name = column_name
        self.fallback_to_country = fallback_to_country
        self.use_percentile = use_percentile
        self.steps = steps

    @property
    def name(self) -> str:
        return self._name

    @property
    def merge_borders(self) -> bool:
        return self.fallback_to_country

    def calculate_colors(self, state: GameState) -> Dict[int, Tuple[int, int, int]]:
        if "regions" not in state.tables: return {}

        regions_df = state.get_table("regions")
        target_col = self.column_name

        # 1. Prepare Data Join (Same as before)
        work_df = None
        if target_col in regions_df.columns:
            work_df = regions_df.select(["id", target_col])
        elif self.fallback_to_country and "countries" in state.tables:
            countries_df = state.get_table("countries")
            if target_col in countries_df.columns:
                # We join to get the value, but we keep the Region ID
                work_df = regions_df.join(
                    countries_df,
                    left_on="owner",
                    right_on="id",
                    how="left"
                ).select(["id", target_col])

        if work_df is None: return {}

        # 2. Filter valid data
        # We need to compute ranks on the *unique values* first to handle ties correctly?
        # Actually, Polars rank() works on the whole series.

        # Drop nulls for calculation safety
        valid_df = work_df.drop_nulls(subset=[target_col])
        if valid_df.is_empty(): return {}

        # --- KEY FIX: PERCENTILE CALCULATION ---
        if self.use_percentile:
            # Calculate rank (0.0 to 1.0) for every row
            # "dense" ranking ensures groups are evenly filled
            work_df = work_df.with_columns(
                pl.col(target_col).rank("dense").alias("rank")
            )

            # Normalize rank to 0..1
            max_rank = work_df.select(pl.col("rank").max()).item()
            if max_rank > 1:
                work_df = work_df.with_columns(
                    (pl.col("rank") - 1) / (max_rank - 1)
                )
            else:
                work_df = work_df.with_columns(pl.lit(0.5).alias("rank"))

            # Use the rank column for coloring
            value_col = "rank"
            min_val, max_val = 0.0, 1.0

        else:
            # Standard Linear Logic
            value_col = target_col
            min_val = valid_df.select(pl.col(target_col).min()).item()
            max_val = valid_df.select(pl.col(target_col).max()).item()
            if max_val == min_val: max_val = min_val + 1.0

        # 3. Generate Colors
        result = {}
        for row in work_df.iter_rows(named=True):
            rid = row["id"]
            val = row[value_col]

            if val is None:
                result[rid] = (40, 40, 40)  # Grey
                continue

            t = (float(val) - min_val) / (max_val - min_val)

            # --- OPTIONAL: QUANTIZE INTO GROUPS ---
            # If steps=5, t becomes 0.0, 0.2, 0.4, 0.6, 0.8, 1.0
            if self.steps > 1:
                t = math.floor(t * self.steps) / self.steps

            result[rid] = get_heatmap_color(t)

        return result