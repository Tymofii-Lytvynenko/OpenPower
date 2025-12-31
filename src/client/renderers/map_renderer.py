import arcade
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional, List, Tuple

# Adjust import based on your actual python path structure
from src.shared.map.region_atlas import RegionAtlas

class MapRenderer:
    """
    Handles map visualization and interacts with the shared RegionAtlas for data.
    
    Responsibilities:
    1. Renders the main map texture (GPU).
    2. Acts as a bridge between World Coordinates (Arcade) and Image Coordinates (Atlas).
    3. Generates dynamic textures (e.g., selection borders) from Atlas data.
    """

    def __init__(self, map_path: Path, cache_dir: Path):
        self.map_path = map_path
        
        # 1. GPU Path: Main Map Sprite
        self.sprite_list = arcade.SpriteList()
        self.map_sprite = arcade.Sprite(map_path)
        
        # Center sprite so (0,0) world matches bottom-left of image
        self.map_sprite.center_x = self.map_sprite.width / 2
        self.map_sprite.center_y = self.map_sprite.height / 2
        self.sprite_list.append(self.map_sprite)

        # 2. Data Path: Shared Region Atlas (NumPy/OpenCV)
        # Convert Path objects to strings for cv2/os compatibility if needed
        self.atlas = RegionAtlas(str(map_path), str(cache_dir))
        
        self.width = self.atlas.width
        self.height = self.atlas.height

        print(f"[MapRenderer] Initialized. Map Size: {self.width}x{self.height}")

    def draw_map(self):
        """Draws the base map layer."""
        self.sprite_list.draw()

    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> Optional[int]:
        """
        Converts World Coordinates (Bottom-Left origin) to Atlas Coordinates (Top-Left origin)
        and retrieves the region ID.
        """
        # 1. Bounds check
        if not (0 <= world_x < self.width and 0 <= world_y < self.height):
            return None

        # 2. Coordinate Conversion: Flip Y axis
        # Arcade (y=0 is bottom) -> Image (y=0 is top)
        img_x = int(world_x)
        img_y = int(self.height - world_y)

        return self.atlas.get_region_at(img_x, img_y)

    def get_color_hex_at_world_pos(self, world_x: float, world_y: float) -> Optional[str]:
        """Helper to get HEX color string for UI/Debugging."""
        img_x = int(world_x)
        img_y = int(self.height - world_y)
        
        rgb = self.atlas.get_color_at(img_x, img_y)
        if rgb:
            return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])
        return None

    def create_highlight_sprite(self, region_ids: List[int], color: Tuple[int, int, int] = (255, 255, 0)) -> Optional[arcade.Sprite]:
        """
        Generates a transparent Arcade Sprite containing only the borders of the specified regions.
        Useful for selection highlighting.
        """
        if not region_ids:
            return None

        # 1. Ask Atlas to generate the contour image (returns BGRA numpy array)
        overlay_data = self.atlas.render_country_overlay(region_ids, border_color=color, thickness=3)

        # 2. Convert BGRA (OpenCV) to RGBA (PIL/Arcade)
        # OpenCV uses BGR, Arcade/PIL uses RGB. 
        # The alpha channel is already correct, but R and B need swapping.
        overlay_rgba = cv2.cvtColor(overlay_data, cv2.COLOR_BGRA2RGBA)

        # 3. Create PIL Image
        image = Image.fromarray(overlay_rgba)

        # 4. Create Texture and Sprite
        # We use a hash of IDs to name the texture effectively if we wanted to cache it,
        # but for dynamic editor selection, a unique name is fine.
        texture_name = f"highlight_{region_ids[0]}_{id(region_ids)}"
        texture = arcade.Texture(texture_name, image)
        
        sprite = arcade.Sprite(texture=texture)
        
        # 5. Position Sprite
        # Since the overlay is the size of the whole map, we center it exactly like the map sprite.
        sprite.center_x = self.width / 2
        sprite.center_y = self.height / 2
        
        return sprite

    def get_center(self) -> arcade.math.Vector2:
        return arcade.math.Vector2(self.width / 2, self.height / 2)