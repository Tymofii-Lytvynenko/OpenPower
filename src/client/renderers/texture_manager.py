import arcade
import numpy as np
import os
import threading
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set, Any
from PIL import Image

class TextureManager:
    """
    Manages loading, caching, and updating of textures for rendering.
    
    Optimized Features:
    - Centralized Caching: Stores all binary caches in a local /.cache folder.
    - Terrain: Uses .npy binary cache to bypass slow PNG decoding.
    - Map: Uses background thread for caching to prevent UI freezes during disk writes.
    """
    
    def __init__(self, ctx: arcade.gl.Context, lut_dim: int = 4096):
        self.ctx = ctx
        self.lut_dim = lut_dim
        
        # --- Cache Configuration ---
        # Determines project root based on this file's location
        self.script_dir = Path(__file__).parent.resolve()
        self.project_root = self.script_dir.parents[2] 
        self.cache_dir = self.project_root / ".cache"
        
        # Ensure cache directory exists immediately
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[TextureManager] Warning: Could not create cache dir: {e}")

        # --- Texture Storage ---
        self.map_texture: Optional[arcade.gl.Texture] = None
        self.terrain_texture: Optional[arcade.gl.Texture] = None
        self.lookup_texture: Optional[arcade.gl.Texture] = None
        
        # --- LUT Data (Overlays) ---
        self.lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)
        
        # --- Color Mapping State ---
        self._active_color_map: Dict[int, Tuple[int, int, int]] = {}
        self._default_color = (40, 40, 40)
        
        # --- Selection State ---
        self.multi_select_dense_ids: Set[int] = set()
        self.prev_multi_select_dense_ids: Set[int] = set()
        
        # --- Region ID Mappings ---
        self.real_to_dense: Dict[int, int] = {}
        self.dense_to_real: List[int] = []

    def load_map_texture(
        self, 
        map_path: Path, 
        packed_map: np.ndarray, 
        width: int, 
        height: int,
        indexer: Any
    ) -> None:
        """
        Load and create the map texture using centralized caching.
        """
        # 1. Load Logical Indices (Fast)
        print("[TextureManager] Loading region indices...")
        unique_ids, dense_map = indexer.get_indices(
            source_path=map_path,
            map_data_array=packed_map,
        )
        
        self.dense_to_real = unique_ids
        self.real_to_dense = {real_id: i for i, real_id in enumerate(unique_ids)}
        print(f"[TextureManager] Indexed {len(unique_ids)} unique regions.")
        
        # 2. Check for Visual Cache in Central Folder
        # Naming convention: {map_filename}_visual.npy
        cache_path = self.cache_dir / f"{map_path.stem}_visual.npy"
        encoded_data = None
        
        if self._is_cache_valid(map_path, cache_path):
            try:
                print(f"[TextureManager] Loading cached MAP visual: {cache_path.name}")
                encoded_data = np.load(cache_path)
            except Exception as e:
                print(f"[TextureManager] Cache corrupted, regenerating: {e}")

        # 3. CPU Generation (Fallback)
        if encoded_data is None:
            print("[TextureManager] Generating MAP visual texture (CPU)...")
            
            # Reshape flattened index array to 2D
            dense_map_2d = dense_map.reshape((height, width)).astype(np.uint32)
            
            # Extract RGB channels (Bit shifting is fast)
            r = ((dense_map_2d >> 16) & 0xFF).astype(np.uint8)
            g = ((dense_map_2d >> 8) & 0xFF).astype(np.uint8)
            b = (dense_map_2d & 0xFF).astype(np.uint8)
            
            # Stack and Flip for OpenGL
            encoded_data = np.dstack((r, g, b))
            encoded_data = np.flipud(encoded_data)
            
            # 4. Background Save (Threaded)
            def _save_cache_job():
                try:
                    # Ensure dir exists just in case
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    np.save(cache_path, encoded_data)
                    print(f"[TextureManager] Background Map Cache Saved: {cache_path.name}")
                except Exception as e:
                    print(f"[TextureManager] Background Save Failed: {e}")

            threading.Thread(target=_save_cache_job, daemon=True).start()

        # 5. Upload to GPU
        self.map_texture = self.ctx.texture(
            (width, height),
            components=3,
            data=encoded_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.map_texture.wrap_x = self.ctx.REPEAT # type: ignore
        self.map_texture.wrap_y = self.ctx.CLAMP_TO_EDGE # type: ignore

    def load_terrain_texture(self, terrain_path: Path) -> None:
        """
        Load terrain texture using centralized binary caching.
        """
        if not terrain_path.exists():
            raise FileNotFoundError(f"[TextureManager] Terrain path not found: {terrain_path}")
        
        # Naming convention: {terrain_filename}_terrain.npy
        cache_path = self.cache_dir / f"{terrain_path.stem}.npy"
        rgba_array = None

        # 1. Try Loading Cache
        if self._is_cache_valid(terrain_path, cache_path):
            try:
                print(f"[TextureManager] Loading cached TERRAIN: {cache_path.name}")
                rgba_array = np.load(cache_path, mmap_mode='r')
            except Exception as e:
                print(f"[TextureManager] Cache corrupted, falling back to PNG: {e}")

        # 2. Slow Fallback (PNG Decode)
        if rgba_array is None:
            print(f"[TextureManager] Decoding PNG (Slow): {terrain_path.name}")
            try:
                Image.MAX_IMAGE_PIXELS = None
                img = Image.open(terrain_path).convert("RGBA")
                arr = np.array(img, dtype=np.uint8)
                
                # Flip vertically for OpenGL
                rgba_array = np.flipud(arr)
                
                # Save cache (Terrain files are smaller, safe to save synchronously)
                # Ensure dir exists
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                np.save(cache_path, rgba_array)
            except Exception as e:
                raise RuntimeError(f"[TextureManager] Failed to load terrain texture: {e}")

        # 3. Upload to GPU
        h, w, _ = rgba_array.shape
        
        self.terrain_texture = self.ctx.texture(
            (w, h),
            components=4,
            data=rgba_array.tobytes(),
            filter=(self.ctx.LINEAR, self.ctx.LINEAR),
        )
        self.terrain_texture.wrap_x = self.ctx.REPEAT # type: ignore
        self.terrain_texture.wrap_y = self.ctx.CLAMP_TO_EDGE # type: ignore

    def init_lookup_texture(self) -> None:
        """Initialize the lookup texture for color overlays."""
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.lookup_texture.write(self.lut_data.tobytes()) # type: ignore

    def update_overlay(self, color_map: Dict[int, Tuple[int, int, int]]) -> None:
        """Update the overlay colors and rebuild LUT."""
        self._active_color_map = color_map
        self._rebuild_lut_array()
        if self.lookup_texture:
            self.lookup_texture.write(self.lut_data.tobytes())

    def update_selection(self, multi_select_dense_ids: Set[int]) -> None:
        """Update selection highlighting in the LUT."""
        self.prev_multi_select_dense_ids = self.multi_select_dense_ids.copy()
        self.multi_select_dense_ids = multi_select_dense_ids
        self._update_selection_texture()

    def bind_textures(self, program: arcade.gl.Program) -> None:
        """Bind all textures to the shader program."""
        if self.map_texture:
            self.map_texture.use(0)
            program["u_map_texture"] = 0
        
        if self.lookup_texture:
            self.lookup_texture.use(1)
            program["u_lookup_texture"] = 1
        
        if self.terrain_texture:
            self.terrain_texture.use(2)
            program["u_terrain_texture"] = 2

    def set_uniforms(self, program: arcade.gl.Program) -> None:
        """Set texture-related uniforms."""
        program["u_lut_dim"] = float(self.lut_dim)

    # --- Private Methods ---

    def _is_cache_valid(self, src: Path, cache: Path) -> bool:
        """Returns True if cache exists and is newer than source file."""
        if not cache.exists():
            return False
        try:
            return cache.stat().st_mtime > src.stat().st_mtime
        except OSError:
            return False

    def _rebuild_lut_array(self) -> None:
        """Rebuild the LUT array from current color mappings."""
        self.lut_data.fill(0)
        for real_id, color in self._active_color_map.items():
            if real_id in self.real_to_dense:
                dense_id = self.real_to_dense[real_id]
                if 0 < dense_id < len(self.lut_data):
                    # Default alpha 200 for overlaid colors
                    alpha = 255 if dense_id in self.multi_select_dense_ids else 200
                    self.lut_data[dense_id] = [color[0], color[1], color[2], alpha]

    def _update_selection_texture(self) -> None:
        """Update selection highlighting in the LUT texture."""
        # Reset previous selections to normal alpha
        for idx in self.prev_multi_select_dense_ids:
            if 0 < idx < len(self.lut_data) and self.lut_data[idx, 3] > 0:
                self.lut_data[idx, 3] = 200
        
        # Highlight current selections
        for idx in self.multi_select_dense_ids:
            if 0 < idx < len(self.lut_data) and self.lut_data[idx, 3] > 0:
                self.lut_data[idx, 3] = 255
        
        if self.lookup_texture:
            self.lookup_texture.write(self.lut_data.tobytes())