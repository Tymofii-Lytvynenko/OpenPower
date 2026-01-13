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
        
        # MAPPINGS
        self.real_to_dense: Dict[int, int] = {}
        self.dense_to_real: List[int] = []

        # HYBRID STATE
        self.single_select_dense_id = -1
        self.multi_select_dense_ids = set()
        
        # OPTIMIZED: 256x256 covers 65,536 regions.
        self.lut_dim = 4096
        # Init with 0 (Transparent)
        self.lut_data = np.full((self.lut_dim * self.lut_dim, 4), 0, dtype=np.uint8)

        self._cached_ownership: Dict[int, str] = {}
        self._cached_colors: Dict[str, Tuple[int, int, int]] = {}
        self.prev_multi_select_dense_ids = set()

        self.terrain_sprite: Optional[arcade.Sprite] = None
        
        # --- ORDER MATTERS HERE ---
        self._init_resources(terrain_img_path) 
        self._init_glsl()

    def _init_resources(self, terrain_path: Path):
        # Create a SpriteList to hold the terrain
        self.terrain_list = arcade.SpriteList()

        if terrain_path.exists():
            self.terrain_sprite = arcade.Sprite(terrain_path)
            self.terrain_sprite.width = self.width
            self.terrain_sprite.height = self.height
            self.terrain_sprite.center_x = self.width / 2
            self.terrain_sprite.center_y = self.height / 2
            
            # Add the sprite to the list
            self.terrain_list.append(self.terrain_sprite)
        else:
            print(f"CRITICAL ERROR: Terrain path not found: {terrain_path}")
            self.terrain_sprite = None

        # 2. Re-Index Map (The Optimization)
        print(f"[MapRenderer] Indexing regions...")
        unique_ids, dense_map = np.unique(self.map_data.packed_map, return_inverse=True)
        
        self.dense_to_real = unique_ids
        self.real_to_dense = { real_id: i for i, real_id in enumerate(unique_ids) }
        
        print(f"[MapRenderer] Remapped {len(unique_ids)} regions.")

        # 3. Create Map Texture (Dense Indices)
        dense_map = dense_map.reshape((self.height, self.width)).astype(np.uint32)
        r = ((dense_map >> 16) & 0xFF).astype(np.uint8)
        g = ((dense_map >> 8) & 0xFF).astype(np.uint8)
        b = (dense_map & 0xFF).astype(np.uint8)
        
        encoded_data = np.dstack((r, g, b))
        encoded_data = np.flipud(encoded_data)

        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

        self.map_texture = self.ctx.texture(
            (self.width, self.height),
            components=3,
            data=encoded_data.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )
        
        # 4. Create AND WRITE Lookup Texture
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )
        # FIX: Write the initial transparent data immediately!
        self.lookup_texture.write(self.lut_data.tobytes())

    def _init_glsl(self):
        # Standard full-screen quad
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
        self.program['u_lut_dim'] = float(self.lut_dim)
        self.program['u_selected_id'] = -1

    def update_political_layer(self, region_ownership: Dict[int, str], country_colors: Dict[str, Tuple[int, int, int]]):
        self._cached_ownership = region_ownership
        self._cached_colors = country_colors
        self._rebuild_lut_array()
        self.lookup_texture.write(self.lut_data.tobytes())

    def _rebuild_lut_array(self):
        # Reset to 0 (Transparent)
        self.lut_data.fill(0) 

        for real_id, tag in self._cached_ownership.items():
            if real_id in self.real_to_dense:
                dense_id = self.real_to_dense[real_id]
                
                # Safety check for size
                if dense_id < len(self.lut_data):
                    # Background (ID 0) should generally remain ignored/transparent
                    # unless your game treats the sea as an ownable province.
                    if dense_id == 0: continue 

                    color = self._cached_colors.get(tag, (100, 100, 100))
                    alpha = 255 if dense_id in self.multi_select_dense_ids else 200
                    self.lut_data[dense_id] = [color[0], color[1], color[2], alpha]

    def _update_selection_texture(self):
        # Turn OFF old
        for idx in self.prev_multi_select_dense_ids:
            if idx < len(self.lut_data) and idx != 0: 
                self.lut_data[idx, 3] = 200

        # Turn ON new
        for idx in self.multi_select_dense_ids:
            if idx < len(self.lut_data) and idx != 0: 
                self.lut_data[idx, 3] = 255

        self.prev_multi_select_dense_ids = self.multi_select_dense_ids.copy()
        self.lookup_texture.write(self.lut_data.tobytes())

    def set_highlight(self, real_region_ids: List[int]):
        if not real_region_ids:
            self.clear_highlight()
            return

        valid_dense_ids = []
        for rid in real_region_ids:
            if rid in self.real_to_dense:
                valid_dense_ids.append(self.real_to_dense[rid])

        if not valid_dense_ids:
            return

        if len(valid_dense_ids) == 1:
            self.single_select_dense_id = valid_dense_ids[0]
            if self.multi_select_dense_ids:
                self.multi_select_dense_ids = set()
                self._update_selection_texture()
        else:
            self.single_select_dense_id = -1
            new_set = set(valid_dense_ids)
            if new_set != self.multi_select_dense_ids:
                self.multi_select_dense_ids = new_set
                self._update_selection_texture()

    def clear_highlight(self):
        self.single_select_dense_id = -1
        if self.multi_select_dense_ids:
            self.multi_select_dense_ids = set()
            self._update_selection_texture()

    def draw(self, mode: str = "terrain"):
        # 1. Draw Terrain
        # FIX: Always draw terrain if it exists. 
        # Even in political mode, you usually want the map underneath.
        if self.terrain_list:
            self.terrain_list.draw()

        # 2. OPTIMIZATION: 
        # Only skip if in terrain mode AND nothing is selected.
        if mode == "terrain" and self.single_select_dense_id == -1 and not self.multi_select_dense_ids:
            return

        # 3. GL Setup
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.BLEND_DEFAULT
        
        self.map_texture.use(0)
        self.lookup_texture.use(1)
        
        self.program['u_view'] = self.window.ctx.view_matrix
        self.program['u_projection'] = self.window.ctx.projection_matrix
        self.program['u_selected_id'] = int(self.single_select_dense_id)
        
        # 4. Mode Logic
        if mode == "political":
            self.program['u_overlay_mode'] = 1
            self.program['u_opacity'] = 0.9
        else:
            self.program['u_overlay_mode'] = 0
            self.program['u_opacity'] = 1.0 # Ensure opacity is set even in terrain mode

        self.quad_geometry.render(self.program)

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> int:
        img_y = int(self.height - world_y)
        if not (0 <= world_x < self.width and 0 <= img_y < self.height):
            return 0
        return self.map_data.get_region_id(int(world_x), img_y)