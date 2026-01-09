import os
import json
import time
import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict, Union

class RegionAtlas:
    """
    Manages the raw region map data, spatial caching, and pixel-level queries.
    
    Responsibility:
        This class is a Data Provider. It does not know about Arcade, rendering contexts,
        or game logic. It simply answers questions like "What region is at (x,y)?"
        or "Generate an image where Region 1 is Red and Region 2 is Blue."
        
    Performance Note:
        Uses memory-mapped NumPy arrays or efficient binary caching to handle 
        high-resolution maps (4k+) without lag.
    """

    def __init__(self, image_path: str, cache_dir: str = ".cache"):
        """
        Initialize the atlas. Loads from cache if valid to speed up startup.

        Args:
            image_path (str): Path to the source 'regions.png' file.
            cache_dir (str): Folder to store the optimized .npy and .json files.
        """
        self.image_path = image_path
        self.cache_dir = cache_dir
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

        # distinct filenames for cache based on the source image name
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        self.cache_file = os.path.join(cache_dir, f"{base_name}_packed.npy")
        self.meta_file = os.path.join(cache_dir, f"{base_name}_meta.json")

        # Load the map data (either from disk or by rebuilding)
        self.packed_map = self._load_map_data()
        
        # Cache dimensions for bounds checking
        self.height, self.width = self.packed_map.shape

    # =========================================================================
    # INTERNAL: Caching & Loading Logic
    # =========================================================================

    def _load_map_data(self) -> np.ndarray:
        """Determines whether to load from cache or rebuild from source."""
        if not os.path.exists(self.image_path):
            raise FileNotFoundError(f"Source image not found: {self.image_path}")

        current_mtime = os.path.getmtime(self.image_path)

        # 1. Try to load valid cache to save startup time (decoding PNGs is slow)
        if self._is_cache_valid(current_mtime):
            # print(f"[RegionAtlas] Loading fast cache from: {self.cache_file}")
            return np.load(self.cache_file)

        # 2. Rebuild if stale or missing
        print("[RegionAtlas] Source map changed. Rebuilding optimized cache...")
        return self._rebuild_cache(current_mtime)

    def _is_cache_valid(self, current_mtime: float) -> bool:
        """Checks if .npy exists and metadata timestamp matches source."""
        if not os.path.exists(self.cache_file) or not os.path.exists(self.meta_file):
            return False
        try:
            with open(self.meta_file, 'r') as f:
                meta = json.load(f)
                return meta.get('mtime') == current_mtime
        except (json.JSONDecodeError, KeyError, OSError):
            return False

    def _rebuild_cache(self, current_mtime: float) -> np.ndarray:
        """
        Reads PNG, packs RGB channels into a single Int32 array, and saves to disk.
        
        Why pack colors?
            A standard image is (Height, Width, 3). Querying it requires checking 3 bytes.
            By packing B, G, R into a single 32-bit integer, the image becomes (Height, Width).
            This reduces memory usage (slightly) but massively speeds up equality checks 
            (checking `pixel == ID` is 1 operation instead of 3).
        """
        t0 = time.time()
        
        # Load standard BGR image via OpenCV
        img = cv2.imread(self.image_path)
        if img is None:
            raise ValueError(f"Failed to decode image at {self.image_path}")

        # --- THE SPEED OPTIMIZATION ---
        # Convert 3-channel (B, G, R) into 1-channel (Int32).
        # Formula: ID = B | (G << 8) | (R << 16)
        # Note: We use .astype(np.int32) to prevent 8-bit overflow during shifting.
        b, g, r = cv2.split(img)
        packed = b.astype(np.int32) | (g.astype(np.int32) << 8) | (r.astype(np.int32) << 16)

        # Save binary data for fast loading next time
        np.save(self.cache_file, packed)

        # Save metadata
        with open(self.meta_file, 'w') as f:
            json.dump({'mtime': current_mtime}, f)

        print(f"[RegionAtlas] Cache built in {time.time() - t0:.2f}s")
        return packed

    # =========================================================================
    # PUBLIC: Helpers (Color <-> ID)
    # =========================================================================

    def pack_color(self, r: int, g: int, b: int) -> int:
        """
        Converts an RGB tuple to the internal Packed ID (int).
        
        Note:
            OpenCV reads images as BGR. Our packing logic puts Blue in the lowest byte.
        """
        return int(b) | (int(g) << 8) | (int(r) << 16)

    def unpack_color(self, packed_id: int) -> Tuple[int, int, int]:
        """Converts an internal Packed ID (int) back to (R, G, B)."""
        b = packed_id & 255
        g = (packed_id >> 8) & 255
        r = (packed_id >> 16) & 255
        return (r, g, b)

    # =========================================================================
    # PUBLIC: Queries & Generators
    # =========================================================================

    def get_region_at(self, x: int, y: int) -> Optional[int]:
        """
        Returns the Region ID (int) at the specific coordinate.
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            return None
        # NumPy array is accessed as [row, col] -> [y, x]
        return int(self.packed_map[y, x])

    def generate_political_view(self, 
                              region_owner_map: Dict[int, str], 
                              owner_colors: Dict[str, Tuple[int, int, int]]) -> np.ndarray:
        """
        Generates a full map texture where regions are colored by their owner.
        
        Algorithm: Look-Up Table (LUT) Vectorization.
            Instead of iterating 2 million pixels, we create a small array (LUT) 
            where index = RegionID and value = Color. 
            NumPy then maps the entire image in one C-level operation.
            
        Args:
            region_owner_map: Dict mapping {region_id: country_tag}
            owner_colors: Dict mapping {country_tag: (R, G, B)}
            
        Returns:
            np.ndarray: An RGBA image array (Height, Width, 4) ready for texture creation.
        """
        t0 = time.time()
        
        # Determine the size of the LUT based on the highest region ID
        max_id = np.max(self.packed_map)
        
        # Safety limit: If max_id is astronomical (e.g. 16 million because sparse colors), 
        # a 16MB array is fine, but we should be aware of memory. 
        # For a standard strategy game (IDs 1-5000), this array is tiny (~5KB).
        
        # Initialize LUTs for R, G, B channels
        lut_r = np.zeros(max_id + 1, dtype=np.uint8)
        lut_g = np.zeros(max_id + 1, dtype=np.uint8)
        lut_b = np.zeros(max_id + 1, dtype=np.uint8)
        
        # Fill the Look-Up Tables
        # This loop only runs N times (where N = number of regions), which is fast.
        for region_id, owner_tag in region_owner_map.items():
            if region_id > max_id: 
                continue # Skip IDs that don't exist on the map map
            
            # Default to Gray if owner has no color defined
            color = owner_colors.get(owner_tag, (128, 128, 128)) 
            
            lut_r[region_id] = color[0]
            lut_g[region_id] = color[1]
            lut_b[region_id] = color[2]

        # Apply the LUT to the whole map at once
        # This replaces every pixel ID in packed_map with its corresponding color channel
        r_layer = lut_r[self.packed_map]
        g_layer = lut_g[self.packed_map]
        b_layer = lut_b[self.packed_map]
        
        # Generate Alpha Channel
        # Logic: Pixels with color (valid owners) get 180 alpha (semi-transparent).
        # Pixels with (0,0,0) (no owner/water) get 0 alpha (fully transparent).
        # We check if any channel has a value > 0.
        a_layer = np.where((r_layer > 0) | (g_layer > 0) | (b_layer > 0), 180, 0).astype(np.uint8)

        # Merge channels into a single RGBA image
        # Note: Arcade/PIL expects RGBA.
        political_map = cv2.merge([r_layer, g_layer, b_layer, a_layer])

        print(f"[RegionAtlas] Political layer generated in {time.time() - t0:.3f}s")
        return political_map

    def render_country_overlay(self, 
                             region_ids: List[int], 
                             border_color: Tuple[int, int, int] = (255, 255, 255),
                             thickness: int = 3) -> Tuple[Optional[np.ndarray], int, int]:
        """
        Generates a small overlay image cropped to the region's bounding box.
        Used for hovering/selection highlights.
        
        Returns:
            Tuple: (image_data, x_offset, y_offset)
        """
        if not region_ids:
            return None, 0, 0

        # Optimization: Only process relevant pixels to find bounding box
        if len(region_ids) == 1:
            ys, xs = np.where(self.packed_map == region_ids[0])
        else:
            ys, xs = np.where(np.isin(self.packed_map, region_ids))

        if len(xs) == 0:
            return None, 0, 0

        # Calculate crop bounds with padding for the border
        pad = thickness + 2
        x_min, x_max = max(0, np.min(xs) - pad), min(self.width, np.max(xs) + pad)
        y_min, y_max = max(0, np.min(ys) - pad), min(self.height, np.max(ys) + pad)

        # Crop the map to the Region of Interest (ROI)
        roi = self.packed_map[y_min:y_max, x_min:x_max]

        # Create mask for contours
        if len(region_ids) == 1:
            mask = (roi == region_ids[0])
        else:
            mask = np.isin(roi, region_ids)
            
        mask_uint8 = mask.astype(np.uint8) * 255

        # Find contours (borders)
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Draw contours on a transparent buffer
        h, w = roi.shape
        overlay = np.zeros((h, w, 4), dtype=np.uint8)
        # OpenCV uses BGR for drawing, but since we output to Arcade, we must supply RGB? 
        # Actually cv2.drawContours takes a color tuple. If we pass (R,G,B), it draws that.
        # But we need to be consistent. Let's assume input is RGB.
        cv2.drawContours(overlay, contours, -1, border_color + (255,), thickness)

        return overlay, x_min, y_min