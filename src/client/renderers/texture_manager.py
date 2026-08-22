import arcade
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set, Any
from PIL import Image

from src.core.cache_service import CacheService

class TextureManager:
    """
    Manages loading, caching, and updating of textures for rendering.
    Uses CacheService for I/O operations.
    """

    MAX_TERRAIN_TEXTURE_SIZE = (8192, 4096)
    MAX_MAP_TEXTURE_SIZE = (16000, 8000)
    
    def __init__(self, ctx: arcade.gl.Context, cache_service: CacheService, lut_dim: int = 128):
        self.ctx = ctx
        self.cache = cache_service
        self.lut_dim = max(1, int(lut_dim))
        
        # --- Texture Storage ---
        self.map_texture: Optional[arcade.gl.Texture] = None
        self.terrain_texture: Optional[arcade.gl.Texture] = None
        self.lookup_texture: Optional[arcade.gl.Texture] = None
        
        # --- LUT Data (Overlays) ---
        self.lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)
        
        # --- Color Mapping State ---
        self._active_color_map: Dict[int, Tuple[int, ...]] = {}
        
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
        self._ensure_lookup_capacity(len(unique_ids))
        # print(f"[TextureManager] Indexed {len(unique_ids)} unique regions.")
        
        visual_width, visual_height = self.fit_texture_size(
            width,
            height,
            *self.MAX_MAP_TEXTURE_SIZE,
        )

        # 2. Check Visual Cache
        cache_path = self.cache.get_cache_path(
            map_path,
            f"_visual_rgba_{visual_width}x{visual_height}.npy",
        )
        encoded_data = None
        
        if self.cache.is_cache_valid(map_path, cache_path):
            encoded_data = self.cache.load_numpy_array(cache_path)

        # 3. CPU Generation (Fallback)
        if encoded_data is None:
            print("[TextureManager] Generating MAP visual texture (CPU)...")
            visual_map = self.resample_dense_map(
                dense_map,
                width,
                height,
                visual_width,
                visual_height,
            )
            encoded_data = self.encode_map_visual(
                visual_map,
                visual_width,
                visual_height,
            )
            
            # 4. Background Save via Service
            # Note: We pass a COPY to the thread to avoid race conditions 
            # if encoded_data is modified later (though unlikely here)
            self.cache.save_numpy_array(cache_path, encoded_data.copy(), in_background=True)

        # 5. Upload to GPU
        self.map_texture = self.ctx.texture(
            (visual_width, visual_height),
            components=4,
            data=encoded_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.map_texture.wrap_x = self.ctx.REPEAT # type: ignore
        self.map_texture.wrap_y = self.ctx.CLAMP_TO_EDGE # type: ignore

    @staticmethod
    def encode_map_visual(dense_map: np.ndarray, width: int, height: int) -> np.ndarray:
        """Pack dense region IDs and a precomputed border mask into one RGBA texture."""
        dense = dense_map.reshape((height, width)).astype(np.uint32, copy=False)
        right = np.roll(dense, -1, axis=1)
        up = np.empty_like(dense)
        up[:-1] = dense[1:]
        up[-1] = dense[-1]
        borders = ((dense != right) | (dense != up)) & (dense > 0)

        red = ((dense >> 16) & 0xFF).astype(np.uint8)
        green = ((dense >> 8) & 0xFF).astype(np.uint8)
        blue = (dense & 0xFF).astype(np.uint8)
        alpha = borders.astype(np.uint8) * 255
        return np.flipud(np.dstack((red, green, blue, alpha)))

    @staticmethod
    def resample_dense_map(
        dense_map: np.ndarray,
        width: int,
        height: int,
        target_width: int,
        target_height: int,
    ) -> np.ndarray:
        """Downsample discrete region IDs with nearest-neighbour sampling."""
        dense = dense_map.reshape((height, width))
        if (width, height) == (target_width, target_height):
            return dense

        x_indices = np.minimum(
            (np.arange(target_width, dtype=np.uint64) * width) // target_width,
            width - 1,
        )
        y_indices = np.minimum(
            (np.arange(target_height, dtype=np.uint64) * height) // target_height,
            height - 1,
        )
        return dense[np.ix_(y_indices, x_indices)]

    def load_terrain_texture(self, terrain_path: Path) -> None:
        if not terrain_path.exists():
            raise FileNotFoundError(f"[TextureManager] Terrain path not found: {terrain_path}")
        
        max_width, max_height = self.MAX_TERRAIN_TEXTURE_SIZE
        cache_path = self.cache.get_cache_path(
            terrain_path,
            f"_gpu_{max_width}x{max_height}.npy",
        )
        rgba_array = None

        # 1. Try Loading Cache
        if self.cache.is_cache_valid(terrain_path, cache_path):
            rgba_array = self.cache.load_numpy_array(cache_path, mmap_mode='r')

        # 2. Slow Fallback (PNG Decode)
        if rgba_array is None:
            print(f"[TextureManager] Preparing GPU terrain texture: {terrain_path.name}")
            try:
                Image.MAX_IMAGE_PIXELS = None
                with Image.open(terrain_path) as source_image:
                    image = source_image.convert("RGBA")
                    target_size = self.fit_texture_size(
                        image.width,
                        image.height,
                        max_width,
                        max_height,
                    )
                    if image.size != target_size:
                        # The source is far above the useful screen resolution. Reducing it
                        # once prevents excessive VRAM use without changing the visible map.
                        image = image.resize(target_size, Image.Resampling.LANCZOS)
                    rgba_array = np.flipud(np.asarray(image, dtype=np.uint8))
                
                # Retaining this GPU-ready level avoids decoding and resizing on later starts.
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
        # Automatic mipmap generation does not filter across the periodic longitude
        # boundary and exposes it as a one-pixel meridian on the sphere.
        self.terrain_texture.wrap_x = self.ctx.REPEAT # type: ignore
        self.terrain_texture.wrap_y = self.ctx.CLAMP_TO_EDGE # type: ignore

    @staticmethod
    def fit_texture_size(
        width: int,
        height: int,
        max_width: int,
        max_height: int,
    ) -> tuple[int, int]:
        """Return an aspect-preserving size bounded by the GPU texture budget."""
        scale = min(1.0, max_width / width, max_height / height)
        return max(1, round(width * scale)), max(1, round(height * scale))

    def _ensure_lookup_capacity(self, item_count: int) -> None:
        required_dimension = self.required_lut_dimension(item_count, self.lut_dim)
        if required_dimension == self.lut_dim:
            return

        self.lut_dim = required_dimension
        self.lut_data = np.zeros((self.lut_dim * self.lut_dim, 4), dtype=np.uint8)

    @staticmethod
    def required_lut_dimension(item_count: int, minimum_dimension: int = 128) -> int:
        """Return a power-of-two square dimension that can hold every dense ID."""
        minimum = max(1, int(minimum_dimension))
        required = max(1, int(np.ceil(np.sqrt(max(0, item_count)))))
        dimension = 1 << (required - 1).bit_length()
        return max(minimum, dimension)

    def init_lookup_texture(self) -> None:
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.lookup_texture.write(self.lut_data.tobytes()) # type: ignore

    def update_overlay(self, color_map: Dict[int, Tuple[int, ...]]) -> None:
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
                    base_alpha = color[3] if len(color) > 3 else 200
                    alpha = 255 if dense_id in self.multi_select_dense_ids else base_alpha
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
