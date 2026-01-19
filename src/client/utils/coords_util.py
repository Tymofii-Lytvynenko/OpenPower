import polars as pl
from typing import Optional

def image_to_world(x: float, y: float, map_height: float) -> tuple[float, float]:
    """
    Converts a single point from Image Space (Top-Left) 
    to Game World coordinates (Origin: Bottom-Left).
    """
    return float(x), map_height - float(y)

def calculate_centroid(regions_df: pl.DataFrame, map_height: float) -> Optional[tuple[float, float]]:
    """
    Calculates the geometric center (World Coordinates) for a DataFrame of regions.
    
    Usage:
        - Center camera on a specific Country (Pass all regions owned by 'USA')
        - Center camera on a specific Province (Pass all regions in 'Texas')
    """
    if regions_df.is_empty():
        return None
        
    # 1. Calculate Average in Image Space (Raw Data)
    # We use Polars mean() which ignores nulls automatically
    avg_x = regions_df["center_x"].mean()
    avg_y = regions_df["center_y"].mean()
    
    if avg_x is None or avg_y is None:
        return None

    # 2. Convert result to World Space (Inverted Y)
    return image_to_world(avg_x, avg_y, map_height) # type: ignore