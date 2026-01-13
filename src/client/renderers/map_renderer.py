import arcade
import arcade.gl
import numpy as np
import cv2
from array import array
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from pyglet import gl

from src.core.map_data import RegionMapData
from src.client.shader_registry import ShaderRegistry

class MapRenderer:
    def __init__(self, 
                 map_data: RegionMapData, 
                 map_img_path: Path, # Kept for debug sprites only, not used for main texture
                 terrain_img_path: Path):
        
        self.window = arcade.get_window()
        self.ctx = self.window.ctx
        self.map_data = map_data
        self.width = map_data.width
        self.height = map_data.height
        
        self.selected_id = -1
        self.lut_dim = 4096 

        self.terrain_sprite: Optional[arcade.Sprite] = None
        self._init_resources(terrain_img_path)
        self._init_glsl()

    def _init_resources(self, terrain_path: Path):
        # 1. Terrain Background
        if terrain_path.exists():
            self.terrain_sprite = arcade.Sprite(terrain_path)
            self.terrain_sprite.width = self.width
            self.terrain_sprite.height = self.height
            self.terrain_sprite.center_x = self.width / 2
            self.terrain_sprite.center_y = self.height / 2

        # 2. Main Map Texture (Generated from Logic Data)
        # RELIABILITY FIX: Derive texture from map_data directly.
        # This ensures the Visuals (RGB) match the Logic (Int ID) 100%.
        
        # packed_map is (H, W) Int32: B | G<<8 | R<<16
        # We need RGB uint8.
        
        # Extract channels using bitwise ops (fast numpy vectorization)
        # Note: packed_map is BGR based on the Core implementation
        b = (self.map_data.packed_map & 0xFF).astype(np.uint8)
        g = ((self.map_data.packed_map >> 8) & 0xFF).astype(np.uint8)
        r = ((self.map_data.packed_map >> 16) & 0xFF).astype(np.uint8)
        
        # Stack into (H, W, 3) -> RGB order
        rgb_data = np.dstack((r, g, b))
        
        # Vertical Flip for OpenGL (Top-Left Origin -> Bottom-Left Origin)
        rgb_data = np.flipud(rgb_data)

        # SAFETY: Ensure byte alignment for odd-width images
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

        self.map_texture = self.ctx.texture(
            (self.width, self.height),
            components=3,
            data=rgb_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )
        
        # Clean up large arrays immediately
        del r, g, b, rgb_data
        import gc; gc.collect()

        # 3. Lookup Texture
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )

    def _init_glsl(self):
        # Standard full-screen quad setup
        buffer_data = array('f', [
            0.0, 0.0, 0.0, 0.0,
             self.width, 0.0, 1.0, 0.0,
            0.0,  self.height, 0.0, 1.0,
             self.width,  self.height, 1.0, 1.0,
        ])
        
        self.quad_buffer = self.ctx.buffer(data=buffer_data)
        self.quad_geometry = self.ctx.geometry(
            [arcade.gl.BufferDescription(self.quad_buffer, '2f 2f', ['in_vert', 'in_uv'])],
            mode=self.ctx.TRIANGLE_STRIP
        )

        shader_source = ShaderRegistry.load_bundle(
            ShaderRegistry.POLITICAL_V, 
            ShaderRegistry.POLITICAL_F
        )

        self.program = self.ctx.program(
            vertex_shader=shader_source["vertex_shader"],
            fragment_shader=shader_source["fragment_shader"]
        )
        
        self.program['u_map_texture'] = 0
        self.program['u_lookup_texture'] = 1
        self.program['u_texture_size'] = (float(self.width), float(self.height))

    def update_political_layer(self, region_ownership: Dict[int, str], country_colors: Dict[str, Tuple[int, int, int]]):
        lut_data = np.full((self.lut_dim * self.lut_dim, 4), 100, dtype=np.uint8)
        lut_data[:, 3] = 255 

        for rid, tag in region_ownership.items():
            if rid < len(lut_data):
                color = country_colors.get(tag, (255, 0, 255))
                lut_data[rid] = [color[0], color[1], color[2], 255]

        self.lookup_texture.write(lut_data.tobytes())

    def draw(self, mode: str = "terrain"):
        if self.terrain_sprite and mode == "terrain":
            self.terrain_sprite.draw()

        self.ctx.enable(self.ctx.BLEND)
        self.map_texture.use(0)
        self.lookup_texture.use(1)
        
        self.program['u_view'] = self.window.ctx.view_matrix
        self.program['u_projection'] = self.window.ctx.projection_matrix
        self.program['u_selected_id'] = int(self.selected_id)
        
        if mode == "political":
            self.program['u_overlay_mode'] = 1
            self.program['u_opacity'] = 0.9
        else:
            self.program['u_overlay_mode'] = 0
            self.program['u_opacity'] = 1.0

        self.quad_geometry.render(self.program)

    # --- API Compatibility ---

    def set_highlight(self, region_ids: List[int]):
        """Accepts a list of IDs to match Controller API."""
        if not region_ids:
            self.selected_id = -1
        else:
            self.selected_id = region_ids[0]

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> int:
        """Proxies to Core Data."""
        img_y = int(self.height - world_y)
        if not (0 <= world_x < self.width and 0 <= img_y < self.height):
            return 0
        return self.map_data.get_region_id(int(world_x), img_y)

    def get_center(self) -> Tuple[float, float]:
        return (self.width / 2, self.height / 2)