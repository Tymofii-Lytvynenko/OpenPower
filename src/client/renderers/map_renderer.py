import arcade
import arcade.gl
import numpy as np
import cv2
from array import array
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from pyglet import gl

from src.shared.map.region_atlas import RegionAtlas

# =============================================================================
# SHADER CODE
# =============================================================================

POLITICAL_VS = """
#version 330
in vec2 in_vert;
in vec2 in_uv;

out vec2 v_uv;

// We need both matrices to handle Camera movement (View) and Window resizing (Projection)
uniform mat4 u_view;
uniform mat4 u_projection;

void main() {
    v_uv = in_uv;
    // Apply View (Scroll/Zoom) then Projection (Screen Coordinates)
    gl_Position = u_projection * u_view * vec4(in_vert, 0.0, 1.0);
}
"""

POLITICAL_FS = """
#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_map_texture;    
uniform sampler2D u_lookup_texture; 
uniform vec2      u_texture_size;   
uniform float     u_opacity;        
uniform int       u_selected_id;    
uniform int       u_overlay_mode;   

int get_id(vec2 uv) {
    vec4 c = texture(u_map_texture, uv);
    int r = int(round(c.r * 255.0));
    int g = int(round(c.g * 255.0));
    int b = int(round(c.b * 255.0));
    return b + (g * 256) + (r * 65536);
}

vec4 get_country_color(int id) {
    // Map massive 16M ID into 2D Texture Coordinates (4096 width)
    int width = 4096;
    int x = id % width;
    int y = id / width;
    
    return texelFetch(u_lookup_texture, ivec2(x, y), 0);
}

void main() {
    int region_id = get_id(v_uv);

    if (region_id == 0) discard; 

    // --- SELECTION LOGIC ---
    bool is_selected = (region_id == u_selected_id);
    bool is_selected_border = false;

    // Optimization: Only check neighbors if needed
    vec2 step = 1.0 / u_texture_size;
    
    if (is_selected || u_overlay_mode == 1) {
        int id_r = get_id(v_uv + vec2(step.x, 0.0));
        int id_u = get_id(v_uv + vec2(0.0, step.y));

        if (is_selected) {
            if (id_r != region_id || id_u != region_id) is_selected_border = true;
        }
        
        // --- MODE 1: FULL POLITICAL MAP ---
        if (u_overlay_mode == 1) {
            vec4 country_color = get_country_color(region_id);
            vec3 final_rgb = country_color.rgb;

            // Draw map borders (darken)
            if (region_id != id_r || region_id != id_u) {
                 final_rgb *= 0.6; 
            }

            if (is_selected_border) {
                final_rgb = vec3(1.0, 1.0, 0.0); // Yellow Border
            } else if (is_selected) {
                final_rgb += 0.15; // Highlight body
            }

            f_color = vec4(final_rgb, u_opacity);
            return;
        }
    }

    // --- MODE 0: HIGHLIGHT ONLY (Terrain Mode) ---
    if (u_overlay_mode == 0) {
        if (is_selected_border) {
            f_color = vec4(1.0, 1.0, 0.0, 1.0);
        } else if (is_selected) {
            f_color = vec4(1.0, 1.0, 1.0, 0.15);
        } else {
            f_color = vec4(0.0); // Transparent
        }
    }
}
"""

# =============================================================================
# RENDERER CLASS
# =============================================================================

class MapRenderer:
    def __init__(self, map_path: Path, terrain_path: Path, cache_dir: Path, preloaded_atlas: Optional[RegionAtlas] = None):
        self.window = arcade.get_window()
        self.ctx = self.window.ctx
        self.atlas = preloaded_atlas or RegionAtlas(str(map_path), str(cache_dir))
        self.width = self.atlas.width
        self.height = self.atlas.height

        # Layers
        self.layers = {
            "terrain": arcade.SpriteList(),
            "debug": arcade.SpriteList(),
        }
        self._init_sprites(map_path, terrain_path)
        self._init_glsl(map_path)
        
        self.selected_id = -1

    def _init_sprites(self, map_path: Path, terrain_path: Path):
        debug_sprite = arcade.Sprite(map_path)
        debug_sprite.position = (self.width / 2, self.height / 2)
        self.layers["debug"].append(debug_sprite)

        if terrain_path.exists():
            t_sprite = arcade.Sprite(terrain_path)
            t_sprite.width, t_sprite.height = self.width, self.height
            t_sprite.position = (self.width / 2, self.height / 2)
            self.layers["terrain"].append(t_sprite)

    def _init_glsl(self, map_path: Path):
        # 1. Geometry - World Coordinates (0 to Width, 0 to Height)
        w, h = self.width, self.height
        
        buffer_data = array('f', [
            0.0, 0.0, 0.0, 0.0,  # Bottom Left
              w, 0.0, 1.0, 0.0,  # Bottom Right
            0.0,   h, 0.0, 1.0,  # Top Left
              w,   h, 1.0, 1.0,  # Top Right
        ])
        
        self.quad_buffer = self.ctx.buffer(data=buffer_data)
        self.quad_geometry = self.ctx.geometry(
            [arcade.gl.BufferDescription(self.quad_buffer, '2f 2f', ['in_vert', 'in_uv'])],
            mode=self.ctx.TRIANGLE_STRIP
        )

        # 2. Map Texture
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        
        img = cv2.imread(str(map_path))
        img = cv2.flip(img, 0) 
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        self.map_texture = self.ctx.texture(
            (self.width, self.height),
            components=3,
            data=img_rgb.tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )
        
        del img
        del img_rgb
        import gc; gc.collect()

        # 3. Lookup Texture (2D for 16M support)
        self.lut_dim = 4096 
        self.lookup_texture = self.ctx.texture(
            (self.lut_dim, self.lut_dim),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )

        # 4. Shader
        self.program = self.ctx.program(
            vertex_shader=POLITICAL_VS,
            fragment_shader=POLITICAL_FS
        )
        
        self.program['u_map_texture'] = 0
        self.program['u_lookup_texture'] = 1
        self.program['u_texture_size'] = (float(self.width), float(self.height))
        self.program['u_selected_id'] = -1
        self.program['u_overlay_mode'] = 0

    def update_political_layer(self, region_ownership, country_colors):
        total_pixels = self.lut_dim * self.lut_dim
        flat_data = np.zeros((total_pixels, 4), dtype=np.uint8)
        
        for rid, tag in region_ownership.items():
            if rid < total_pixels:
                c = country_colors.get(tag, (100, 100, 100))
                flat_data[rid] = [c[0], c[1], c[2], 255]

        self.lookup_texture.write(flat_data.tobytes())

    def draw_map(self, mode: str = "terrain"):
        # 1. Draw Background Sprite (Terrain)
        if mode == "debug_regions":
            self.layers["debug"].draw()
            return
            
        self.layers["terrain"].draw()

        # 2. Draw GLSL Layer
        self.ctx.enable(self.ctx.BLEND)
        self.map_texture.use(0)
        self.lookup_texture.use(1)
        
        # --- FIXED: Use Context Matrices directly ---
        # The Camera updates 'view_matrix' and 'projection_2d_matrix' on the context
        self.program['u_view'] = self.window.ctx.view_matrix
        self.program['u_projection'] = self.window.ctx.projection_matrix
        
        # Update Uniforms
        self.program['u_selected_id'] = int(self.selected_id)
        
        if mode == "political":
            self.program['u_overlay_mode'] = 1
            self.program['u_opacity'] = 0.85
        else:
            self.program['u_overlay_mode'] = 0
            self.program['u_opacity'] = 1.0

        self.quad_geometry.render(self.program)

    def set_highlight(self, region_ids: List[int], color=(255, 255, 0)):
        if not region_ids:
            self.selected_id = -1
        else:
            self.selected_id = int(region_ids[0])

    def clear_highlight(self):
        self.selected_id = -1

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> Optional[int]:
        if not (0 <= world_x < self.width and 0 <= world_y < self.height):
            return None
        return self.atlas.get_region_at(int(world_x), int(self.height - world_y))

    def get_center(self) -> Tuple[float, float]:
        return (self.width / 2, self.height / 2)