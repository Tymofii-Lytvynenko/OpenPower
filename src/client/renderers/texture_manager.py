import arcade
import numpy as np
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Set
from PIL import Image


class TextureManager:
    """Manages loading, caching, and updating of textures for rendering."""
    
    def __init__(self, ctx: arcade.gl.Context, lut_dim: int = 4096):
        self.ctx = ctx
        self.lut_dim = lut_dim
        
        # Texture storage
        self.map_texture: Optional[arcade.gl.Texture] = None
        self.terrain_texture: Optional[arcade.gl.Texture] = None
        self.lookup_texture: Optional[arcade.gl.Texture] = None
        
        # LUT data for overlays
        self.lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)
        
        # Color mapping state
        self._active_color_map: Dict[int, Tuple[int, int, int]] = {}
        self._default_color = (40, 40, 40)
        
        # Selection state
        self.multi_select_dense_ids: Set[int] = set()
        self.prev_multi_select_dense_ids: Set[int] = set()
        
        # Region ID mappings
        self.real_to_dense: Dict[int, int] = {}
        self.dense_to_real: List[int] = []
    
    def load_map_texture(
        self, 
        map_path: Path, 
        packed_map: np.ndarray, 
        width: int, 
        height: int,
        indexer
    ) -> None:
        """Load and create the map texture from packed map data."""
        print("[TextureManager] Loading region indices...")
        unique_ids, dense_map = indexer.get_indices(
            source_path=map_path,
            map_data_array=packed_map,
        )
        
        self.dense_to_real = unique_ids
        self.real_to_dense = {real_id: i for i, real_id in enumerate(unique_ids)}
        print(f"[TextureManager] Indexed {len(unique_ids)} unique regions.")
        
        # Encode dense map into RGB texture
        dense_map = dense_map.reshape((height, width)).astype(np.uint32)
        r = ((dense_map >> 16) & 0xFF).astype(np.uint8)
        g = ((dense_map >> 8) & 0xFF).astype(np.uint8)
        b = (dense_map & 0xFF).astype(np.uint8)
        
        encoded_data = np.dstack((r, g, b))
        encoded_data = np.flipud(encoded_data)
        
        self.map_texture = self.ctx.texture(
            (width, height),
            components=3,
            data=encoded_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.map_texture.wrap_x = self.ctx.REPEAT
        self.map_texture.wrap_y = self.ctx.CLAMP_TO_EDGE
    
    def load_terrain_texture(self, terrain_path: Path) -> None:
        """Load the terrain texture from file."""
        if not terrain_path.exists():
            raise FileNotFoundError(f"[TextureManager] Terrain path not found: {terrain_path}")
        
        tw, th, rgba = self._load_image_rgba_flipped(terrain_path)
        self.terrain_texture = self.ctx.texture(
            (tw, th),
            components=4,
            data=rgba,
            filter=(self.ctx.LINEAR, self.ctx.LINEAR),
        )
        self.terrain_texture.wrap_x = self.ctx.REPEAT
        self.terrain_texture.wrap_y = self.ctx.CLAMP_TO_EDGE
    
    def init_lookup_texture(self) -> None:
        """Initialize the lookup texture for color overlays."""
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST),
        )
        self.lookup_texture.write(self.lut_data.tobytes())
    
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
    
    # Private methods
    @staticmethod
    def _load_image_rgba_flipped(path: Path) -> Tuple[int, int, bytes]:
        """Load image as RGBA and flip vertically."""
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(path).convert("RGBA")
        arr = np.array(img, dtype=np.uint8)
        arr = np.flipud(arr)
        h, w, _ = arr.shape
        return w, h, arr.tobytes()
    
    def _rebuild_lut_array(self) -> None:
        """Rebuild the LUT array from current color mappings."""
        self.lut_data.fill(0)
        for real_id, color in self._active_color_map.items():
            if real_id in self.real_to_dense:
                dense_id = self.real_to_dense[real_id]
                if 0 < dense_id < len(self.lut_data):
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
