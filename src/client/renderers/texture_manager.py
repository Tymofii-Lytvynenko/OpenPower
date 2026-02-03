import arcade
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set, Any
from PIL import Image

from src.client.services.cache_service import CacheService

class TextureManager:
    """
    Manages loading, caching, and updating of textures for rendering.
    Uses CacheService for I/O operations.
    """
    
    def __init__(self, ctx: arcade.gl.Context, cache_service: CacheService, lut_dim: int = 4096):
        self.ctx = ctx
        self.cache = cache_service
        self.lut_dim = lut_dim
        
        # --- Texture Storage ---
        self.map_texture: Optional[arcade.gl.Texture] = None
        self.terrain_texture: Optional[arcade.gl.Texture] = None
        self.lookup_texture: Optional[arcade.gl.Texture] = None
        
        # --- LUT Data (Overlays) ---
        self.lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)
        
        # --- Color Mapping State ---
        self._active_color_map: Dict[int, Tuple[int, int, int]] = {}
        
        # --- Selection State ---
        self.multi_select_dense_ids: Set[int] = set()
        self.prev_multi_select_dense_ids: Set[int] = set()
        
        # --- Region ID Mappings ---
        self.real_to_dense: Dict[int, int] = {}
        self.dense_to_real: List[int] = []

    def load_map_texture(self, 
        map_path: Path, 
        packed_map: np.ndarray, 
        width: int, 
        height: int,
        indexer: Any
    ) -> None:
        
        # NOTE: Ideally, indexer.get_indices should handle its own caching internally.
        # If get_indices is slow, this line will block startup every time.
        unique_ids, dense_map = indexer.get_indices(source_path=map_path, map_data_array=packed_map)
        
        self.dense_to_real = unique_ids
        self.real_to_dense = {real_id: i for i, real_id in enumerate(unique_ids)}
        # print(f"[TextureManager] Indexed {len(unique_ids)} unique regions.")
        
        # 2. Check Visual Cache
        cache_path = self.cache.get_cache_path(map_path, "_visual.npy")
        encoded_data = None
        
        if self.cache.is_cache_valid(map_path, cache_path):
            encoded_data = self.cache.load_numpy_array(cache_path)

        # 3. CPU Generation (Fallback)
        if encoded_data is None:
            print("[TextureManager] Generating MAP visual texture (CPU)...")
            dense_map_2d = dense_map.reshape((height, width)).astype(np.uint32)
            
            # Use bit shifting to pack ID into RGB
            r = ((dense_map_2d >> 16) & 0xFF).astype(np.uint8)
            g = ((dense_map_2d >> 8) & 0xFF).astype(np.uint8)
            b = (dense_map_2d & 0xFF).astype(np.uint8)
            
            encoded_data = np.dstack((r, g, b))
            encoded_data = np.flipud(encoded_data)
            
            # 4. Background Save via Service
            # Note: We pass a COPY to the thread to avoid race conditions 
            # if encoded_data is modified later (though unlikely here)
            self.cache.save_numpy_array(cache_path, encoded_data.copy(), in_background=True)

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
        if not terrain_path.exists():
            raise FileNotFoundError(f"[TextureManager] Terrain path not found: {terrain_path}")
        
        cache_path = self.cache.get_cache_path(terrain_path, ".npy")
        rgba_array = None

        # 1. Try Loading Cache
        if self.cache.is_cache_valid(terrain_path, cache_path):
            rgba_array = self.cache.load_numpy_array(cache_path, mmap_mode='r')

        # 2. Slow Fallback (PNG Decode)
        if rgba_array is None:
            print(f"[TextureManager] Decoding PNG (Slow): {terrain_path.name}")
            try:
                Image.MAX_IMAGE_PIXELS = None
                img = Image.open(terrain_path).convert("RGBA")
                arr = np.array(img, dtype=np.uint8)
                rgba_array = np.flipud(arr)
                
                # Save cache (Terrain is fast enough to save sync usually, but async is safer)
                self.cache.save_numpy_array(cache_path, rgba_array, in_background=True)
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
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.lookup_texture.write(self.lut_data.tobytes()) # type: ignore

    def update_overlay(self, color_map: Dict[int, Tuple[int, int, int]]) -> None:
        self._active_color_map = color_map
        self._rebuild_lut_array()
        if self.lookup_texture:
            self.lookup_texture.write(self.lut_data.tobytes())

    def update_selection(self, multi_select_dense_ids: Set[int]) -> None:
        self.prev_multi_select_dense_ids = self.multi_select_dense_ids.copy()
        self.multi_select_dense_ids = multi_select_dense_ids
        self._update_selection_texture()

    def bind_textures(self, program: arcade.gl.Program) -> None:
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
        program["u_lut_dim"] = float(self.lut_dim)

    def _rebuild_lut_array(self) -> None:
        self.lut_data.fill(0)
        for real_id, color in self._active_color_map.items():
            if real_id in self.real_to_dense:
                dense_id = self.real_to_dense[real_id]
                if 0 < dense_id < len(self.lut_data):
                    alpha = 255 if dense_id in self.multi_select_dense_ids else 200
                    self.lut_data[dense_id] = [color[0], color[1], color[2], alpha]

    def _update_selection_texture(self) -> None:
        for idx in self.prev_multi_select_dense_ids:
            if 0 < idx < len(self.lut_data) and self.lut_data[idx, 3] > 0:
                self.lut_data[idx, 3] = 200
        for idx in self.multi_select_dense_ids:
            if 0 < idx < len(self.lut_data) and self.lut_data[idx, 3] > 0:
                self.lut_data[idx, 3] = 255
        if self.lookup_texture:
            self.lookup_texture.write(self.lut_data.tobytes())