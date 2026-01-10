"""
Map & Database Generator.

Architecture: "Color-As-ID"
----------------------------
1. Visual Map: Pixels represent region IDs.
2. Database: Maps HEX colors (Visual IDs) to Game Data.

Features:
- **CLI Options**: Support for reusing colors from previous builds.
- **Micro-Nation Merging**: Automatically fuses tiny subdivisions.
- **TSV Export**: Uses Tab-Separated Values for robust string handling.
- **Smart Rescue**: Spiral search algorithm to save islands.
- **Verification**: Mathematically proves map integrity.

https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_1_states_provinces.zip

Dependencies:
    pip install geopandas pandas rasterio numpy opencv-python unidecode pyproj
"""

import os
import sys
import csv
import random
import argparse
import geopandas as gpd
import pandas as pd
from rasterio import features
from rasterio.transform import from_bounds, rowcol
import numpy as np
import cv2
from unidecode import unidecode

# === CONFIGURATION ===
CONFIG = {
    # Input source (Requires .shp, .shx, .dbf)
    "input_shp": "temp/regions.shp",
    
    # Outputs
    "output_png": "temp/regions.png",
    "output_tsv": "temp/regions.tsv",
    
    # Texture Resolution (10k is standard for detailed HOI4-style maps)
    "width": 10000,
    "height": 5000,
    
    # WGS84 Global Bounds
    "bounds": (-180.0, -90.0, 180.0, 90.0),
    
    # ID 0 is strictly reserved for Ocean/Background
    "background_id": 0,
    
    # List of Country Codes (ISO A3) to force-merge into single regions.
    "merge_list": [
        "LIE", # Liechtenstein
        "SMR", # San Marino
        "VAT", # Vatican
        "MCO", # Monaco
        "AND", # Andorra
        "TUV", # Tuvalu
        "NRU"  # Nauru
    ]
}

def hex_to_rgb(hex_str):
    """Converts #RRGGBB string to (r, g, b) tuple."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r, g, b):
    """Converts RGB tuple to standard HEX string #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"

def generate_random_colors(count, exclude_colors=None):
    """
    Generates unique random RGB tuples, ensuring no collisions with existing colors.
    
    Args:
        count (int): Number of new colors needed.
        exclude_colors (set): Set of (r,g,b) tuples that are already taken.
    """
    print(f"Generating {count} unique visual colors...")
    if exclude_colors is None:
        exclude_colors = set()
    
    # Initialize with excluded colors to prevent duplicates
    colors = set(exclude_colors)
    result_list = []
    
    while len(result_list) < count:
        r = random.randint(10, 255)
        g = random.randint(10, 255)
        b = random.randint(10, 255)
        color = (r, g, b)
        
        # Ensure we never generate Black (0,0,0) or duplicates
        if color not in colors and color != (0, 0, 0):
            colors.add(color)
            result_list.append(color)
            
    return result_list

def sanitize_text(text):
    """
    Sanitizes string data for game engine compatibility.
    1. Fixes 'Mojibake'.
    2. Transliterates to ASCII.
    """
    if not isinstance(text, str):
        return ""
    
    try:
        fixed_text = text.encode('cp1252').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        fixed_text = text

    return unidecode(fixed_text).strip()

def merge_micro_nations(gdf, codes_to_merge):
    """
    Combines all regions of specific countries into a single geometry.
    """
    print(f"Optimizing: Merging micro-nations {codes_to_merge}...")
    
    for code in codes_to_merge:
        subset = gdf[gdf['adm0_a3'] == code]
        
        if subset.empty or len(subset) <= 1:
            continue 
            
        print(f"  -> Merging {len(subset)} regions for {code}...")
        
        unified_geom = subset.geometry.unary_union
        
        new_row = subset.iloc[0].copy()
        new_row['geometry'] = unified_geom
        c_name = subset.iloc[0].get('admin', code) 
        new_row['name'] = c_name
        new_row['name_en'] = c_name
        new_row['type_en'] = "Sovereign State" 
        
        gdf = gdf[gdf['adm0_a3'] != code]
        new_gdf = gpd.GeoDataFrame([new_row], crs=gdf.crs)
        gdf = pd.concat([gdf, new_gdf], ignore_index=True)
        
    return gdf

def load_existing_colors(tsv_path):
    """
    Parses an existing TSV to create a mapping of Regions -> Colors.
    
    Returns:
        tuple: (lookup_dict, used_colors_set)
        lookup_dict format: {(Owner_Code, Region_Name): (r, g, b)}
    """
    print(f"Loading existing colors from {tsv_path}...")
    lookup = {}
    used_colors = set()
    
    if not os.path.exists(tsv_path):
        print("Warning: TSV file not found. Proceeding with fresh generation.")
        return lookup, used_colors

    try:
        df = pd.read_csv(tsv_path, sep='\t')
        for _, row in df.iterrows():
            # Create a unique key based on Owner + Name
            # We must sanitize here because the new Shapefile data will also be sanitized
            # before comparison.
            r_name = str(row.get('name', '')).strip()
            r_owner = str(row.get('owner', '')).strip()
            hex_val = str(row.get('hex', ''))
            
            if hex_val and r_name and r_owner:
                color_rgb = hex_to_rgb(hex_val)
                key = (r_owner, r_name)
                
                lookup[key] = color_rgb
                used_colors.add(color_rgb)
                
    except Exception as e:
        print(f"Error reading TSV: {e}. Proceeding with fresh generation.")
    
    print(f"  -> Loaded {len(lookup)} existing color definitions.")
    return lookup, used_colors

def main():
    # === ARGUMENT PARSING ===
    parser = argparse.ArgumentParser(description="Map & Database Generator")
    parser.add_argument("--reuse-tsv", type=str, help="Path to an existing TSV to reuse HEX colors from.", default=None)
    args = parser.parse_args()

    print(f"--- Starting Map Generation ---")

    # 1. Input Validation
    if not os.path.exists(CONFIG["input_shp"]):
        print(f"ERROR: Input file {CONFIG['input_shp']} not found.")
        sys.exit(1)

    print("Reading Shapefile...")
    try:
        gdf = gpd.read_file(CONFIG["input_shp"], encoding='utf-8')
    except Exception:
        print("Warning: Forced UTF-8 failed. Reverting to auto-detect.")
        gdf = gpd.read_file(CONFIG["input_shp"])

    # 2. Optimization: Merge Micro-Nations
    gdf = merge_micro_nations(gdf, CONFIG['merge_list'])

    # 3. Physics Calculation: Real Area (km²)
    print("Calculating real surface area...")
    gdf_metric = gdf.to_crs({'proj': 'cea'})
    gdf['area_km2'] = (gdf_metric.geometry.area / 1e6).astype(int)

    # 4. ID and Color Assignment Logic
    total_regions = len(gdf)
    gdf['temp_id'] = range(1, total_regions + 1)
    
    # Storage for the final colors
    id_to_color_map = {}
    
    # Logic for Reuse vs New
    existing_lookup = {}
    used_colors = set()
    
    if args.reuse_tsv:
        existing_lookup, used_colors = load_existing_colors(args.reuse_tsv)
    
    regions_needing_new_colors = []
    
    print("Assigning colors to regions...")
    for _, row in gdf.iterrows():
        t_id = row['temp_id']
        
        # Construct the key to match against the TSV
        # 1. Get Name
        raw_name = row.get('name', 'Unknown')
        name_en = row.get('name_en', None)
        if name_en and isinstance(name_en, str) and len(name_en) > 1:
            display_name = sanitize_text(name_en)
        else:
            display_name = sanitize_text(raw_name)
            
        # 2. Get Owner
        owner_code = row.get('adm0_a3', 'UNK').replace('-99', 'UNK')
        
        key = (owner_code, display_name)
        
        # Check if we have this region in history
        if key in existing_lookup:
            # REUSE COLOR
            id_to_color_map[t_id] = existing_lookup[key]
        else:
            # MARK FOR NEW GENERATION
            regions_needing_new_colors.append(t_id)

    # Generate fresh colors for any region not found in the TSV
    if regions_needing_new_colors:
        print(f"  -> Generating {len(regions_needing_new_colors)} NEW colors...")
        new_colors = generate_random_colors(len(regions_needing_new_colors), exclude_colors=used_colors)
        
        for idx, t_id in enumerate(regions_needing_new_colors):
            id_to_color_map[t_id] = new_colors[idx]
    else:
        print("  -> All regions matched existing colors.")

    # 5. Metadata Extraction & TSV Export
    print("Processing metadata and export...")
    transform = from_bounds(*CONFIG['bounds'], CONFIG['width'], CONFIG['height'])
    
    tsv_rows = []
    tsv_header = [
        "hex", "name", "owner", "iso_region", "type", 
        "macro_region", "postal", "area_km2", "center_x", "center_y"
    ]
    tsv_rows.append(tsv_header)
    
    center_lookup = {}
    
    for _, row in gdf.iterrows():
        t_id = int(row['temp_id'])
        r, g, b = id_to_color_map[t_id]
        
        # Calculate pixel centroid
        geom = row.geometry
        center_geo = geom.centroid
        c_row, c_col = rowcol(transform, center_geo.x, center_geo.y)
        c_x = int(max(0, min(c_col, CONFIG['width'] - 1)))
        c_y = int(max(0, min(c_row, CONFIG['height'] - 1)))

        # Metadata extraction
        raw_name = row.get('name', 'Unknown')
        name_en = row.get('name_en', None)
        if name_en and isinstance(name_en, str) and len(name_en) > 1:
            display_name = sanitize_text(name_en)
        else:
            display_name = sanitize_text(raw_name)
            
        owner_code = row.get('adm0_a3', 'UNK').replace('-99', 'UNK')
        iso_reg = row.get('iso_3166_2', 'UNK') if isinstance(row.get('iso_3166_2'), str) else "UNK"
        admin_type = sanitize_text(row.get('type_en', 'Region'))
        macro_reg = sanitize_text(row.get('region', ''))
        postal = sanitize_text(row.get('postal', ''))
        area = int(row['area_km2'])

        hex_color = rgb_to_hex(r, g, b)
        
        tsv_rows.append([
            hex_color, display_name, owner_code, iso_reg, 
            admin_type, macro_reg, postal, area, c_x, c_y
        ])
        
        center_lookup[t_id] = (c_x, c_y)

    print(f"Saving Database: {CONFIG['output_tsv']}...")
    with open(CONFIG["output_tsv"], "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerows(tsv_rows)

    # 6. Rasterization
    print("Rasterizing geometry...")
    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf['temp_id']))
    
    raster_ids = features.rasterize(
        shapes=shapes,
        out_shape=(CONFIG['height'], CONFIG['width']),
        transform=transform,
        fill=CONFIG['background_id'],
        dtype=np.uint32,
        all_touched=False
    )

    # 7. Rescue Logic (Smart Spiral)
    print("Rescuing small regions...")
    present_ids = np.unique(raster_ids)
    missing_ids = np.setdiff1d(gdf['temp_id'].values, present_ids)
    
    if len(missing_ids) > 0:
        print(f"  -> Attempting to rescue {len(missing_ids)} regions...")
        protected_ids = set(missing_ids)
        placed_count = 0
        
        def get_spiral(start_x, start_y, max_r):
            yield start_x, start_y
            for r in range(1, max_r + 1):
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if abs(dx) == r or abs(dy) == r:
                            yield start_x + dx, start_y + dy

        for m_id in missing_ids:
            if m_id not in center_lookup:
                continue
            
            c_x, c_y = center_lookup[m_id]
            best_candidate = None
            
            for try_x, try_y in get_spiral(c_x, c_y, 30):
                if not (0 <= try_x < CONFIG['width'] and 0 <= try_y < CONFIG['height']):
                    continue
                
                current_pixel_val = raster_ids[try_y, try_x]
                
                if current_pixel_val == CONFIG['background_id']:
                    best_candidate = (try_x, try_y)
                    break 
                
                if current_pixel_val not in protected_ids:
                    if best_candidate is None:
                        best_candidate = (try_x, try_y)
            
            if best_candidate:
                final_x, final_y = best_candidate
                raster_ids[final_y, final_x] = m_id
                placed_count += 1
            else:
                print(f"CRITICAL: No space found for ID {m_id} near {c_x},{c_y}")

        print(f"  -> Rescue operation finished. Placed {placed_count}/{len(missing_ids)}.")

    # 8. Integrity Verification
    print("--- Verifying Integrity ---")
    final_present_ids = np.unique(raster_ids)
    expected_set = set(gdf['temp_id'].values)
    found_set = set(final_present_ids)
    lost_regions = expected_set - found_set
    
    if len(lost_regions) == 0:
        print("SUCCESS: 100% Integrity. All regions are present on the map.")
    else:
        print(f"WARNING: Verification FAILED. {len(lost_regions)} regions are missing!")
        missing_info = gdf[gdf['temp_id'].isin(lost_regions)]
        for _, row in missing_info.iterrows():
            r_name = row.get('name_en', row.get('name', 'Unknown'))
            r_country = row.get('adm0_a3', 'UNK')
            print(f" -> ID {row['temp_id']}: {sanitize_text(r_name)} ({r_country})")

    # 9. Image Encoding
    print("Encoding visual map...")
    # Palette index must accommodate the highest temporary ID
    max_id = gdf['temp_id'].max()
    palette = np.zeros((max_id + 2, 3), dtype=np.uint8)
    
    for t_id, (r, g, b) in id_to_color_map.items():
        palette[t_id] = [b, g, r] # BGR for OpenCV

    bgr_image = palette[raster_ids]
    
    print(f"Saving PNG: {CONFIG['output_png']}...")
    cv2.imwrite(CONFIG["output_png"], bgr_image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    
    print("--- Done! ---")

if __name__ == "__main__":
    main()