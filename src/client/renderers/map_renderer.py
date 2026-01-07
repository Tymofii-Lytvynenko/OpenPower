import arcade
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional, List, Tuple

from src.shared.map.region_atlas import RegionAtlas

class MapRenderer:
    """
    Handles map visualization and interacts with the shared RegionAtlas for data.
    """

    def __init__(self, map_path: Path, cache_dir: Path, preloaded_atlas: Optional[RegionAtlas] = None):
        """
        Args:
            map_path: Path to the visual map image.
            cache_dir: Directory for caching compiled data.
            preloaded_atlas: Optional. If provided, skips the heavy Atlas initialization.
                             Used when loading via LoadingView.
        """
        self.map_path = map_path
        
        # --- 1. GPU Path: Main Map Sprite ---
        # NOTE: Sprite creation MUST happen on the Main Thread (OpenGL context).
        # That is why this part is done here, not in the LoadingTask.
        self.sprite_list = arcade.SpriteList()
        self.map_sprite = arcade.Sprite(map_path)
        
        self.map_sprite.center_x = self.map_sprite.width / 2
        self.map_sprite.center_y = self.map_sprite.height / 2
        self.sprite_list.append(self.map_sprite)

        # --- 2. Data Path: Shared Region Atlas (NumPy/OpenCV) ---
        if preloaded_atlas:
            # Use the instance created in the background thread
            self.atlas = preloaded_atlas
        else:
            # Fallback: Load it synchronously (will freeze UI briefly)
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
        if not (0 <= world_x < self.width and 0 <= world_y < self.height):
            return None

        img_x = int(world_x)
        img_y = int(self.height - world_y)

        return self.atlas.get_region_at(img_x, img_y)

    def create_highlight_sprite(self, region_ids: List[int], color: Tuple[int, int, int] = (255, 255, 0)) -> Optional[arcade.Sprite]:
        """Generates a transparent Arcade Sprite containing only the borders of the specified regions."""
        if not region_ids:
            return None

        # Returns: (small_image_bgra, x_offset_in_atlas, y_offset_in_atlas)
        overlay_data, x_off, y_off = self.atlas.render_country_overlay(region_ids, border_color=color, thickness=3)

        if overlay_data is None:
            return None

        # Convert BGRA to RGBA
        overlay_rgba = cv2.cvtColor(overlay_data, cv2.COLOR_BGRA2RGBA)
        image = Image.fromarray(overlay_rgba)

        texture_name = f"highlight_{region_ids[0]}_{id(region_ids)}"
        texture = arcade.Texture(image, hash=texture_name)
        
        sprite = arcade.Sprite(texture)
        
        # Position Sprite Correctly
        small_h, small_w = overlay_data.shape[:2]
        center_img_x = x_off + small_w / 2
        center_img_y = y_off + small_h / 2
        
        sprite.center_x = center_img_x
        sprite.center_y = self.height - center_img_y
        
        return sprite

    def get_center(self) -> Tuple[float, float]:
        return (self.width / 2, self.height / 2)