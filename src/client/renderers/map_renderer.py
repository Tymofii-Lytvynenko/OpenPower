import arcade
import time
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from PIL import Image
from pyglet import gl
from src.shared.map.region_atlas import RegionAtlas

class MapRenderer:
    def __init__(self, map_path: Path, terrain_path: Path, cache_dir: Path, preloaded_atlas: Optional[RegionAtlas] = None):
        self.width = 0
        self.height = 0
        
        # Layers
        self.layers = {
            "terrain": arcade.SpriteList(),
            "political": arcade.SpriteList(),
            "debug": arcade.SpriteList(),
            "highlight": arcade.SpriteList()
        }
        
        # Logic Helpers
        self.atlas = preloaded_atlas or RegionAtlas(str(map_path), str(cache_dir))
        self._init_sprites(map_path, terrain_path)

    def _init_sprites(self, map_path: Path, terrain_path: Path):
        """Internal setup of base sprites."""
        # 1. Debug/Size reference
        debug_sprite = arcade.Sprite(map_path)
        self.width, self.height = debug_sprite.width, debug_sprite.height
        debug_sprite.position = (self.width / 2, self.height / 2)
        self.layers["debug"].append(debug_sprite)

        # 2. Terrain
        if terrain_path.exists():
            t_sprite = arcade.Sprite(terrain_path)
            t_sprite.width, t_sprite.height = self.width, self.height
            t_sprite.position = (self.width / 2, self.height / 2)
            self.layers["terrain"].append(t_sprite)

    def update_political_layer(self, region_ownership: Dict[int, str], country_colors: Dict[str, Tuple[int, int, int]]):
        """Generates the political texture."""
        raw_image = self.atlas.generate_political_view(region_ownership, country_colors)
        image = Image.fromarray(raw_image)
        texture = arcade.Texture(image, hash=f"pol_{time.time()}")
        
        sprite = arcade.Sprite(texture)
        sprite.position = (self.width / 2, self.height / 2)
        
        self.layers["political"].clear()
        self.layers["political"].append(sprite)

    def draw_map(self, mode: str = "terrain"):
        if mode == "debug_regions":
            self.layers["debug"].draw()
        elif mode == "political":
            self.layers["terrain"].draw()
            self.layers["political"].draw()
        else:
            self.layers["terrain"].draw()
            
        # Draw highlights with additive blending
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE)
        self.layers["highlight"].draw()
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def set_highlight(self, region_ids: List[int], color=(255, 255, 0)):
        self.clear_highlight()
        if not region_ids: return

        overlay, x_off, y_off = self.atlas.render_country_overlay(region_ids, border_color=color, thickness=3)
        if overlay is None: return

        texture = arcade.Texture(Image.fromarray(overlay), hash=f"hl_{time.time()}")
        sprite = arcade.Sprite(texture)
        
        # Align Sprite Center based on Top-Left offset
        h, w = overlay.shape[:2]
        sprite.center_x = x_off + (w / 2)
        sprite.center_y = self.height - (y_off + (h / 2))
        
        self.layers["highlight"].append(sprite)

    def clear_highlight(self):
        self.layers["highlight"].clear()

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> Optional[int]:
        if not (0 <= world_x < self.width and 0 <= world_y < self.height):
            return None
        # Invert Y for Atlas lookup
        return self.atlas.get_region_at(int(world_x), int(self.height - world_y))

    def get_center(self) -> Tuple[float, float]:
        return (self.width / 2, self.height / 2)