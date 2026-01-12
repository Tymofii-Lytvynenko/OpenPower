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
import rtoml

# === CONFIG LOADING ===
def load_config(config_path="mapgen.toml"):
    """Loads configuration from TOML file."""
    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
    with open(config_path, 'r') as f:
        return rtoml.load(f)

# Global Config Placeholder
CFG = {}

def hex_to_rgb(hex_str):
    """Converts #RRGGBB string to (r, g, b) tuple."""
    hex_str = str(hex_str).lstrip('#')
    if len(hex_str) != 6:
        return (0, 0, 0)
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r, g, b):
    """Converts RGB tuple to standard HEX string #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"

def generate_random_colors(count, exclude_colors=None):
    """Generates unique random RGB tuples."""
    if exclude_colors is None:
        exclude_colors = set()
    
    colors = set(exclude_colors)
    result_list = []
    
    attempts = 0
    max_attempts = count * 100
    
    while len(result_list) < count and attempts < max_attempts:
        attempts += 1
        r = random.randint(10, 255)
        g = random.randint(10, 255)
        b = random.randint(10, 255)
        color = (r, g, b)
        
        if color not in colors and color != (0, 0, 0):
            colors.add(color)
            result_list.append(color)
            
    return result_list

def sanitize_ne_id(val):
    """Normalizes ne_id to a stable string."""
    if pd.isna(val) or val is None or val == "":
        return None
    try:
        return str(int(float(val)))
    except:
        return str(val).strip()

def sanitize_text(text):
    """Sanitizes string data."""
    if pd.isna(text) or text is None:
        return ""
    text = str(text)
    try:
        fixed_text = text.encode('cp1252').decode('utf-8')
    except:
        fixed_text = text
    return unidecode(fixed_text).strip()

def merge_micro_nations(gdf, codes_to_merge):
    """Combines all regions of specific countries into a single geometry."""
    print(f"Optimizing: Merging micro-nations {codes_to_merge}...")
    
    for code in codes_to_merge:
        subset = gdf[gdf['adm0_a3'] == code]
        
        if subset.empty or len(subset) <= 1:
            continue 
            
        print(f"  -> Merging {len(subset)} regions for {code}...")
        
        if hasattr(subset.geometry, 'union_all'):
            unified_geom = subset.geometry.union_all()
        else:
            unified_geom = subset.geometry.unary_union
        
        new_row = subset.iloc[0].copy()
        new_row['geometry'] = unified_geom
        c_name = subset.iloc[0].get('admin', code) 
        new_row['name'] = c_name
        new_row['name_en'] = c_name
        new_row['type_en'] = "Sovereign State" 
        new_row['postal'] = "" 
        
        gdf = gdf[gdf['adm0_a3'] != code]
        new_gdf = gpd.GeoDataFrame([new_row], crs=gdf.crs)
        gdf = pd.concat([gdf, new_gdf], ignore_index=True)
        
    return gdf

def load_old_database_by_ne_id(tsv_path):
    """Parses existing TSV and builds lookup index by ne_id."""
    print(f"Loading existing colors from {tsv_path}...")
    data_map = {}
    used_colors = set()
    
    if not os.path.exists(tsv_path):
        print("Warning: TSV file not found. Proceeding with fresh generation.")
        return data_map, used_colors

    try:
        df = pd.read_csv(tsv_path, sep='\t', dtype=str)
        
        for _, row in df.iterrows():
            nid = sanitize_ne_id(row.get('ne_id'))
            hex_val = row.get('hex', '')
            
            if not nid or not hex_val: 
                continue

            color_rgb = hex_to_rgb(hex_val)
            used_colors.add(color_rgb)
            
            # Store full row data to preserve metadata
            data_map[nid] = {
                'color': color_rgb,
                'row_data': row.to_dict()
            }
                
    except Exception as e:
        print(f"Error reading TSV: {e}. Proceeding with fresh generation.")
    
    print(f"  -> Loaded {len(data_map)} existing records.")
    return data_map, used_colors

def main():
    global CFG
    CFG = load_config()

    parser = argparse.ArgumentParser(description="Map & Database Generator")
    parser.add_argument("--reuse-tsv", type=str, help="Path to existing TSV.", default=None)
    args = parser.parse_args()

    print(f"--- Starting Map Generation ---")

    # 1. Input Validation
    input_shp = CFG['io']['input_shp']
    if not os.path.exists(input_shp):
        print(f"ERROR: Input file {input_shp} not found.")
        sys.exit(1)

    print("Reading Shapefile...")
    try:
        gdf = gpd.read_file(input_shp, encoding='utf-8')
    except Exception:
        print("Warning: Forced UTF-8 failed. Reverting to auto-detect.")
        gdf = gpd.read_file(input_shp)

    # 2. Optimization
    gdf = merge_micro_nations(gdf, CFG['processing']['merge_list'])

    # 3. Physics Calculation
    print("Calculating real surface area...")
    gdf_metric = gdf.to_crs({'proj': 'cea'})
    gdf['area_km2'] = (gdf_metric.geometry.area / 1e6).astype(int)

    # 4. ID Assignment
    total_regions = len(gdf)
    gdf['temp_id'] = range(1, total_regions + 1)
    
    id_to_color_map = {}
    
    # Load reuse data
    old_db_map = {}
    used_colors = set()
    
    if args.reuse_tsv:
        old_db_map, used_colors = load_old_database_by_ne_id(args.reuse_tsv)
    
    regions_needing_new_colors = []
    final_metadata = {} # Stores the final row data for TSV export

    print("Assigning colors to regions...")
    matches_found = 0
    
    for _, row in gdf.iterrows():
        t_id = row['temp_id']
        current_ne_id = sanitize_ne_id(row.get('ne_id'))
        
        # Prepare fresh metadata from current Shapefile as default
        raw_name = sanitize_text(row.get('name', ''))
        name_en = sanitize_text(row.get('name_en', ''))
        display_name = name_en if len(name_en) > 1 else raw_name
        if not display_name: display_name = sanitize_text(row.get('iso_3166_2', 'UNK'))

        fresh_meta = {
            "name": display_name,
            "owner": row.get('adm0_a3', 'UNK').replace('-99', 'UNK'),
            "iso_region": sanitize_text(row.get('iso_3166_2', 'UNK')),
            "type": sanitize_text(row.get('type_en', 'Region')),
            "macro_region": sanitize_text(row.get('region', '')),
            "postal": sanitize_text(row.get('postal', '')),
            "wikidataid": sanitize_text(row.get('wikidataid', '')),
            "ne_id": current_ne_id if current_ne_id else ""
        }

        # MATCHING LOGIC: ne_id only
        if current_ne_id and current_ne_id in old_db_map:
            matches_found += 1
            entry = old_db_map[current_ne_id]
            
            # Reuse Color
            id_to_color_map[t_id] = entry['color']
            
            # Reuse Metadata (Merge old DB values over fresh ones)
            old_row = entry['row_data']
            merged = fresh_meta.copy()
            
            # Fields to strictly preserve from old DB
            preserve_keys = ["name", "owner", "iso_region", "type", "macro_region", "postal", "wikidataid"]
            for k in preserve_keys:
                if k in old_row:
                    merged[k] = old_row[k]
            
            final_metadata[t_id] = merged
        else:
            regions_needing_new_colors.append(t_id)
            final_metadata[t_id] = fresh_meta

    print(f"  -> Matched {matches_found} regions using ne_id.")

    # Generate fresh colors for unmatched regions
    if regions_needing_new_colors:
        print(f"  -> Generating colors for {len(regions_needing_new_colors)} new regions...")
        new_colors = generate_random_colors(len(regions_needing_new_colors), exclude_colors=used_colors)
        
        for idx, t_id in enumerate(regions_needing_new_colors):
            id_to_color_map[t_id] = new_colors[idx]
            used_colors.add(new_colors[idx])
    
    # 5. Collision Resolution
    print("Scanning for duplicate color assignments...")
    color_to_ids = {}
    for tid, color in id_to_color_map.items():
        if color not in color_to_ids:
            color_to_ids[color] = []
        color_to_ids[color].append(tid)
    
    collisions = {c: ids for c, ids in color_to_ids.items() if len(ids) > 1}
    
    if collisions:
        print(f"  -> WARNING: Found {len(collisions)} color collisions. Resolving...")
        for color, conflicting_ids in collisions.items():
            # Keep first, change rest
            for i, tid in enumerate(conflicting_ids):
                if i == 0: continue
                
                new_color_list = generate_random_colors(1, exclude_colors=used_colors)
                if new_color_list:
                    new_c = new_color_list[0]
                    id_to_color_map[tid] = new_c
                    used_colors.add(new_c)

    # 6. Metadata Extraction & TSV Export
    print("Processing metadata and export...")
    width = CFG['map']['width']
    height = CFG['map']['height']
    bounds = CFG['map']['bounds']
    
    transform = from_bounds(*bounds, width, height)
    
    tsv_rows = []
    tsv_header = [
        "hex", "name", "owner", "iso_region", "type", 
        "macro_region", "postal", "area_km2", "center_x", "center_y",
        "ne_id", "wikidataid"
    ]
    tsv_rows.append(tsv_header)
    
    center_lookup = {}
    
    for _, row in gdf.iterrows():
        t_id = int(row['temp_id'])
        meta = final_metadata[t_id]
        r, g, b = id_to_color_map[t_id]
        
        # Geometry Math (Always recalculated)
        geom = row.geometry
        center_geo = geom.centroid
        c_row, c_col = rowcol(transform, center_geo.x, center_geo.y)
        c_x = int(max(0, min(c_col, width - 1)))
        c_y = int(max(0, min(c_row, height - 1)))

        area = int(row['area_km2'])
        hex_color = rgb_to_hex(r, g, b)
        
        tsv_rows.append([
            hex_color, meta['name'], meta['owner'], meta['iso_region'], 
            meta['type'], meta['macro_region'], meta['postal'], area, c_x, c_y,
            meta['ne_id'], meta['wikidataid']
        ])
        
        center_lookup[t_id] = (c_x, c_y)

    out_tsv = CFG['io']['output_tsv']
    print(f"Saving Database: {out_tsv}...")
    with open(out_tsv, "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerows(tsv_rows)

    # 7. Rasterization
    print("Rasterizing geometry...")
    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf['temp_id']))
    
    raster_ids = features.rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=CFG['map']['background_id'],
        dtype=np.uint32,
        all_touched=False
    )

    # 8. Rescue Logic (ORIGINAL SPIRAL SEARCH)
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
                if not (0 <= try_x < width and 0 <= try_y < height):
                    continue
                
                current_pixel_val = raster_ids[try_y, try_x]
                
                if current_pixel_val == CFG['map']['background_id']:
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

    # 9. Integrity Verification
    print("--- Verifying Integrity ---")
    final_present_ids = np.unique(raster_ids)
    expected_set = set(gdf['temp_id'].values)
    found_set = set(final_present_ids)
    lost_regions = expected_set - found_set
    
    if len(lost_regions) == 0:
        print("SUCCESS: 100% Integrity. All regions are present on the map.")
    else:
        print(f"WARNING: Verification FAILED. {len(lost_regions)} regions are missing!")

    # 10. Image Encoding
    print("Encoding visual map...")
    max_id = gdf['temp_id'].max()
    palette = np.zeros((max_id + 2, 3), dtype=np.uint8)
    
    for t_id, (r, g, b) in id_to_color_map.items():
        palette[t_id] = [b, g, r] # BGR for OpenCV

    bgr_image = palette[raster_ids]
    
    out_png = CFG['io']['output_png']
    print(f"Saving PNG: {out_png}...")
    cv2.imwrite(out_png, bgr_image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    
    print("--- Done! ---")

if __name__ == "__main__":
    main()