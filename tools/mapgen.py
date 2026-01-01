"""
Regions Map Generator.

This script processes Natural Earth vector data to create:
1. A visual lookup map (PNG) where every region has a unique color.
2. A database (CSV) mapping those HEX colors to region metadata.

The architecture uses "Color-As-ID":
- The game logic reads the pixel color.
- It converts that color to an Integer ID.
- It looks up the ID in the CSV data.

Data Source: https://www.naturalearthdata.com/downloads/10m-cultural-vectors/
"""

import os
import sys
import csv
import random
import geopandas as gpd
import rasterio
from rasterio import features
from rasterio.transform import from_bounds, rowcol
import numpy as np
import cv2  # OpenCV used for high-performance image writing
from unidecode import unidecode  # Essential for ASCII transliteration

# === CONFIGURATION ===
CONFIG = {
    # Input Shapefile (Must have associated .shx and .dbf files)
    "input_shp": "regions.shp",
    
    # Output Assets
    "output_png": "world_regions_map.png",
    "output_csv": "world_regions_data.csv",
    
    # Texture Resolution (Higher = more detail, more RAM usage)
    "width": 10000,
    "height": 5000,
    
    # WGS84 Global Bounds (Longitude -180 to 180, Latitude -90 to 90)
    "bounds": (-180.0, -90.0, 180.0, 90.0),
    
    # ID 0 (Black) is reserved for the Ocean/Background
    "background_id": 0
}

def generate_random_colors(count):
    """
    Generates a list of unique random RGB tuples.
    
    Why:
        We cannot use mathematical ID generation (ID 1 = #000001) because
        it produces near-black maps that are impossible for modders to edit.
        Random distinct colors allow humans to edit the map in Paint.NET/Photoshop.
    """
    print(f"Generating {count} unique visual colors...")
    colors = set()
    result_list = []
    
    while len(result_list) < count:
        # Avoid very dark colors to prevent confusion with the background (0,0,0)
        r = random.randint(10, 255)
        g = random.randint(10, 255)
        b = random.randint(10, 255)
        color = (r, g, b)
        
        if color not in colors and color != (0, 0, 0):
            colors.add(color)
            result_list.append(color)
            
    return result_list

def rgb_to_hex(r, g, b):
    """Converts RGB tuple to standard HEX string #RRGGBB."""
    return f"#{r:02X}{g:02X}{b:02X}"

def sanitize_text(text):
    """
    Cleans text to ensure compatibility with game fonts and CSV readers.
    
    1. Fixes 'Mojibake' (incorrect decoding of UTF-8 as Windows-1252).
    2. Transliterates to ASCII (removes diacritics).
       Example: 'München' -> 'Munchen', 'Bình' -> 'Binh'.
    """
    if not isinstance(text, str):
        return "Unknown"
    
    # Step 1: Attempt to fix encoding errors common on Windows systems.
    # Data often comes as UTF-8 but is read as CP1252.
    try:
        # We encode back to CP1252 bytes, then decode correctly as UTF-8.
        fixed_text = text.encode('cp1252').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        # If encoding fails, the text was likely correct (or unrecoverable).
        fixed_text = text

    # Step 2: Transliterate to ASCII to support standard game fonts.
    return unidecode(fixed_text).strip()

def main():
    print(f"--- Starting Final Map Generation ---")

    # 1. Input Validation
    if not os.path.exists(CONFIG["input_shp"]):
        print(f"ERROR: File {CONFIG['input_shp']} not found.")
        sys.exit(1)

    print("Reading Shapefile (Forcing UTF-8)...")
    
    # Force UTF-8 encoding. GeoPandas on Windows defaults to system encoding (CP1252),
    # which corrupts Asian and European characters.
    try:
        gdf = gpd.read_file(CONFIG["input_shp"], encoding='utf-8')
    except Exception as e:
        print(f"Warning: Forced UTF-8 read failed ({e}). Falling back to auto-detect.")
        gdf = gpd.read_file(CONFIG["input_shp"])

    total_regions = len(gdf)
    
    # 2. Color Assignment
    # We assign a temporary integer ID to every region to handle rasterization.
    # We will map this Integer -> Color later.
    gdf['temp_id'] = range(1, total_regions + 1)
    
    random_colors = generate_random_colors(total_regions)
    
    # Lookup Table: Temp_ID (int) -> Color (r, g, b)
    # used to construct the final image.
    id_to_color_map = {i + 1: color for i, color in enumerate(random_colors)}

    # Create the coordinate transformation matrix (Lat/Lon -> Pixel X/Y)
    transform = from_bounds(*CONFIG['bounds'], CONFIG['width'], CONFIG['height'])
    
    # 3. Process Metadata & Build CSV
    print("Processing metadata (Sanitizing names, calculating centroids)...")
    
    csv_rows = []
    # Header: HEX is used for modder convenience. Owner code determines initial gameplay state.
    csv_header = ["hex", "name", "country_code", "center_x", "center_y"]
    csv_rows.append(csv_header)
    
    # Dictionary to store centroids for the "island rescue" logic
    center_lookup = {}
    
    for _, row in gdf.iterrows():
        t_id = int(row['temp_id'])
        r, g, b = id_to_color_map[t_id]
        
        # Calculate geometric center (for camera focus or labels)
        geom = row.geometry
        center_geo = geom.centroid
        c_row, c_col = rowcol(transform, center_geo.x, center_geo.y)
        c_x = int(max(0, min(c_col, CONFIG['width'] - 1)))
        c_y = int(max(0, min(c_row, CONFIG['height'] - 1)))

        # Metadata Extraction
        # Priority: English Name > Local Name > Unknown
        raw_name = row.get('name', 'Unknown')
        name_en = row.get('name_en', None)
        
        if name_en and isinstance(name_en, str) and len(name_en) > 1:
            target_name = name_en
        else:
            target_name = raw_name
            
        final_name = sanitize_text(target_name)
        
        # 'adm0_a3' is the standard ISO country code (e.g., UKR, USA).
        country = row.get('adm0_a3', 'UNK').replace('-99', 'UNK')
        
        # Convert RGB to HEX for the CSV output
        hex_color = rgb_to_hex(r, g, b)

        csv_rows.append([hex_color, final_name, country, c_x, c_y])
        center_lookup[t_id] = (c_x, c_y)

    print(f"Saving Database: {CONFIG['output_csv']}...")
    # 'utf-8-sig' adds a BOM so Excel opens the file correctly without configuration.
    with open(CONFIG["output_csv"], "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)

    # 4. Rasterization (Vector -> ID Map)
    print("Rasterizing geometry...")
    
    # Generator expression for memory efficiency
    shapes = ((geom, value) for geom, value in zip(gdf.geometry, gdf['temp_id']))
    
    # Burn vectors into a numpy array of Integers.
    # all_touched=False: Only pixels whose center is inside the polygon are drawn.
    # This gives cleaner borders but can miss small islands.
    raster_ids = features.rasterize(
        shapes=shapes,
        out_shape=(CONFIG['height'], CONFIG['width']),
        transform=transform,
        fill=CONFIG['background_id'],
        dtype=np.uint32,
        all_touched=False
    )

    # 5. Rescue Logic (Small Islands)
    print("Checking for lost regions (small islands)...")
    present_ids = np.unique(raster_ids)
    
    # Find IDs that exist in the dataframe but not in the raster map
    missing_ids = np.setdiff1d(gdf['temp_id'].values, present_ids)
    
    if len(missing_ids) > 0:
        print(f"  -> Rescuing {len(missing_ids)} tiny regions...")
        for m_id in missing_ids:
            if m_id in center_lookup:
                c_x, c_y = center_lookup[m_id]
                # Force-draw the pixel at the centroid
                # Note: numpy uses [y, x] indexing
                raster_ids[c_y, c_x] = m_id

    # 6. Image Generation (ID -> Visual Color)
    print("Encoding visual map...")
    
    # Create a palette for fast mapping: Index -> BGR Color
    # Size = max ID + 2 padding to be safe
    palette = np.zeros((total_regions + 2, 3), dtype=np.uint8)
    
    for t_id, (r, g, b) in id_to_color_map.items():
        # OpenCV uses BGR order, not RGB!
        palette[t_id] = [b, g, r]

    # NumPy 'Fancy Indexing': Replaces every ID in the array with its color from the palette.
    bgr_image = palette[raster_ids]
    
    # 7. Saving
    print(f"Saving Map Image: {CONFIG['output_png']}...")
    # Use compression 0 for maximum speed and to ensure lossless pixel values.
    cv2.imwrite(CONFIG["output_png"], bgr_image, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    
    print("--- Success! Assets generated. ---")

if __name__ == "__main__":
    main()