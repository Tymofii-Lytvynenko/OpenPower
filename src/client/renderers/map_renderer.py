import arcade
import arcade.gl
import numpy as np
from array import array
from typing import Optional, List, Dict, Tuple, Set
from pathlib import Path
from pyglet import gl

from src.core.map_data import RegionMapData
from src.client.shader_registry import ShaderRegistry

class MapRenderer:
    def __init__(self, 
                 map_data: RegionMapData, 
                 map_img_path: Path, 
                 terrain_img_path: Path):
        
        self.window = arcade.get_window()
        self.ctx = self.window.ctx
        self.map_data = map_data
        self.width = map_data.width
        self.height = map_data.height
        
        # Store a Set for O(1) lookups during texture generation
        self.selected_ids: Set[int] = set()
        
        # NOTE: 4096*4096 is large. Ensure your IDs fit within 16 million.
        self.lut_dim = 4096 

        # State cache
        self._cached_ownership: Dict[int, str] = {}
        self._cached_colors: Dict[str, Tuple[int, int, int]] = {}

        self.terrain_sprite: Optional[arcade.Sprite] = None
        self._init_resources(terrain_img_path)
        self._init_glsl()

    def _init_resources(self, terrain_path: Path):
        if terrain_path.exists():
            self.terrain_sprite = arcade.Sprite(terrain_path)
            self.terrain_sprite.width = self.width
            self.terrain_sprite.height = self.height
            self.terrain_sprite.center_x = self.width / 2
            self.terrain_sprite.center_y = self.height / 2

        # Main Texture Generation (RGB = Region ID)
        b = (self.map_data.packed_map & 0xFF).astype(np.uint8)
        g = ((self.map_data.packed_map >> 8) & 0xFF).astype(np.uint8)
        r = ((self.map_data.packed_map >> 16) & 0xFF).astype(np.uint8)
        rgb_data = np.dstack((r, g, b))
        rgb_data = np.flipud(rgb_data)

        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

        self.map_texture = self.ctx.texture(
            (self.width, self.height),
            components=3,
            data=rgb_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )
        
        # Lookup Texture: RGBA (RGB=Color, A=SelectionStatus)
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )

    def _init_glsl(self):
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

        shader_source = ShaderRegistry.load_bundle(ShaderRegistry.POLITICAL_V, ShaderRegistry.POLITICAL_F)
        self.program = self.ctx.program(
            vertex_shader=shader_source["vertex_shader"],
            fragment_shader=shader_source["fragment_shader"]
        )
        
        self.program['u_map_texture'] = 0
        self.program['u_lookup_texture'] = 1
        self.program['u_texture_size'] = (float(self.width), float(self.height))

    def update_political_layer(self, region_ownership: Dict[int, str], country_colors: Dict[str, Tuple[int, int, int]]):
        """Updates internal state and pushes new colors to GPU."""
        self._cached_ownership = region_ownership
        self._cached_colors = country_colors
        self._upload_lut()

    def _upload_lut(self):
        """
        Writes data to the Lookup Texture.
        Key Mechanism: We use the Alpha channel to indicate selection.
        Alpha 255 (1.0) = Selected
        Alpha 200 (~0.78) = Unselected
        """
        # Initialize huge buffer
        lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)
        
        # Default unselected state (Alpha 200)
        lut_data[:, 3] = 200 

        for rid, tag in self._cached_ownership.items():
            if rid < len(lut_data):
                color = self._cached_colors.get(tag, (100, 100, 100))
                
                # If this ID is in our selected set, bump Alpha to 255
                alpha = 255 if rid in self.selected_ids else 200
                
                lut_data[rid] = [color[0], color[1], color[2], alpha]

        # Upload to GPU
        self.lookup_texture.write(lut_data.tobytes())

    def draw(self, mode: str = "terrain"):
        if self.terrain_sprite and mode == "terrain":
            self.terrain_sprite.draw()

        self.ctx.enable(self.ctx.BLEND)
        self.map_texture.use(0)
        self.lookup_texture.use(1)
        
        self.program['u_view'] = self.window.ctx.view_matrix
        self.program['u_projection'] = self.window.ctx.projection_matrix
        
        # FIX: Removed self.program['u_selected_id'] assignment. 
        # The shader no longer has this uniform, so setting it caused the crash.
        
        if mode == "political":
            self.program['u_overlay_mode'] = 1
            self.program['u_opacity'] = 0.9
        else:
            self.program['u_overlay_mode'] = 0
            self.program['u_opacity'] = 1.0

        self.quad_geometry.render(self.program)

    def set_highlight(self, region_ids: List[int]):
        """Sets the active selection and updates the texture."""
        if not region_ids:
            self.selected_ids = set()
        else:
            self.selected_ids = set(region_ids)
            
        # Re-upload texture so the shader sees the new Alpha values
        self._upload_lut()

    def clear_highlight(self):
        self.selected_ids = set()
        self._upload_lut()

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> int:
        img_y = int(self.height - world_y)
        if not (0 <= world_x < self.width and 0 <= img_y < self.height):
            return 0
        return self.map_data.get_region_id(int(world_x), img_y)