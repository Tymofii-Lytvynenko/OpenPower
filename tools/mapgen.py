import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.transform import from_bounds, rowcol
import numpy as np
import cv2
import csv  # Replaced json with csv
import os
import sys

# === CONFIGURATION ===
CONFIG = {
    "input_shp": "ne_10m_admin_1_states_provinces.shp",
    "output_png": "world_provinces_id_map.png",
    "output_csv": "world_provinces_data.csv", # Changed to .csv
    
    "width": 10000,
    "height": 5000,
    "bounds": (-180.0, -90.0, 180.0, 90.0),
    "background_id": 0
}

def id_to_hex(r_id):
    """
    Converts integer ID to HEX color string (#RRGGBB).
    """
    r = r_id & 0xFF
    g = (r_id >> 8) & 0xFF
    b = (r_id >> 16) & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"

def main():
    print(f"--- Starting Map Generation {CONFIG['width']}x{CONFIG['height']} (CSV Output) ---")

    # 1. Load Data
    if not os.path.exists(CONFIG["input_shp"]):
        print(f"ERROR: File {CONFIG['input_shp']} not found.")
        sys.exit(1)

    print("Reading Shapefile...")
    gdf = gpd.read_file(CONFIG["input_shp"])
    gdf['game_id'] = range(1, len(gdf) + 1)
    
    transform = from_bounds(*CONFIG['bounds'], CONFIG['width'], CONFIG['height'])

    # 2. Process Metadata & Centroids
    print("Processing centroids and preparing CSV data...")
    
    # List to hold rows for CSV
    csv_rows = []
    
    # Header row for the CSV
    csv_header = ["id", "hex_color", "name", "country_code", "type", "center_x", "center_y"]
    csv_rows.append(csv_header)

    # Temporary dictionary to store centers for the "Rescue" logic later.
    # We need this because we can't easily query a CSV file in memory.
    center_lookup = {} 
    
    for _, row in gdf.iterrows():
        r_id = int(row['game_id'])
        
        # Calculate Centroid
        geom = row.geometry
        center_geo = geom.centroid
        c_row, c_col = rowcol(transform, center_geo.x, center_geo.y)
        
        center_x = int(max(0, min(c_col, CONFIG['width'] - 1)))
        center_y = int(max(0, min(c_row, CONFIG['height'] - 1)))

        # Prepare data
        hex_color = id_to_hex(r_id)
        name = row.get('name', 'Unknown')
        country_code = row.get('adm0_a3', 'UNK').replace('-99', 'UNK')
        region_type = row.get('type_en', 'Region')

        # Add to CSV list
        csv_rows.append([r_id, hex_color, name, country_code, region_type, center_x, center_y])
        
        # Add to lookup dict (for internal script use only)
        center_lookup[r_id] = (center_x, center_y)

    # Write CSV file
    print(f"Saving CSV: {CONFIG['output_csv']}...")
    with open(CONFIG["output_csv"], "w", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)

    # 3. Rasterization
    print("Rasterizing vectors...")
    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf['game_id']))
    
    raster_ids = features.rasterize(
        shapes=shapes,
        out_shape=(CONFIG['height'], CONFIG['width']),
        transform=transform,
        fill=CONFIG['background_id'],
        dtype=np.uint32,
        all_touched=False
    )

    # 4. Rescue Small Regions
    print("Checking for missing small regions...")
    present_ids = np.unique(raster_ids)
    all_ids = gdf['game_id'].values
    missing_ids = np.setdiff1d(all_ids, present_ids)
    
    if len(missing_ids) > 0:
        print(f"  -> Recovering {len(missing_ids)} tiny regions...")
        for m_id in missing_ids:
            # Use the internal lookup dict
            if m_id in center_lookup:
                c_x, c_y = center_lookup[m_id]
                raster_ids[c_y, c_x] = m_id
        print("  -> Recovery complete.")

    # 5. Convert to BGR for OpenCV
    print("Converting to image...")
    bgr_image = np.zeros((CONFIG['height'], CONFIG['width'], 3), dtype=np.uint8)
    
    bgr_image[..., 0] = ((raster_ids >> 16) & 0xFF).astype(np.uint8) # Blue
    bgr_image[..., 1] = ((raster_ids >> 8) & 0xFF).astype(np.uint8)  # Green
    bgr_image[..., 2] = (raster_ids & 0xFF).astype(np.uint8)         # Red

    # 6. Save Image
    print(f"Saving image: {CONFIG['output_png']}...")
    cv2.imwrite(CONFIG["output_png"], bgr_image, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    
    print("--- Done! ---")

if __name__ == "__main__":
    main()