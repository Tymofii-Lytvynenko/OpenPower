import os
import time
import json
import cv2
import numpy as np
import arcade
import arcade.gl
from typing import List, Tuple, Optional, Dict
from array import array

# Import the shaders strings defined above
from src.shared.map.shader_registry import ShaderRegistry

class RegionAtlas:
    def __init__(self, image_path: str):
        self.image_path = image_path
        # Load Raw Image for CPU queries
        self.raw_img = cv2.imread(image_path)
        if self.raw_img is None:
            raise FileNotFoundError(f"Missing {image_path}")
        
        self.height, self.width, _ = self.raw_img.shape
        
        # Build optimized packed map (B | G<<8 | R<<16)
        b, g, r = cv2.split(self.raw_img)
        self.packed_map = b.astype(np.int32) | (g.astype(np.int32) << 8) | (r.astype(np.int32) << 16)

    def get_region_at(self, x: int, y: int) -> int:
        """CPU query for mouse interaction."""
        if 0 <= x < self.width and 0 <= y < self.height:
            # Note: image coordinates are (y, x)
            return int(self.packed_map[y, x])
        return 0

    def get_lut_buffer(self, 
                       region_owner_map: Dict[int, str], 
                       owner_colors: Dict[str, Tuple[int, int, int]],
                       max_regions: int = 8192) -> bytes:
        """
        Generates a Byte String representing the color of every region.
        The GPU reads this as a texture to color the map.
        """
        # Create an array of RGBA bytes: [R, G, B, A,  R, G, B, A, ...]
        # Size: max_regions * 4 bytes
        # Initialize with Gray (Unclaimed land)
        lut = np.full((max_regions, 4), 128, dtype=np.uint8)
        lut[:, 3] = 255 # Alpha 100%

        for rid, tag in region_owner_map.items():
            if rid < max_regions:
                # Get color or default to pink (error color)
                c = owner_colors.get(tag, (255, 0, 255))
                lut[rid] = [c[0], c[1], c[2], 255]

        # Return raw bytes for texture upload
        return lut.tobytes()
    def render_country_overlay(self, 
                             region_ids: List[int], 
                             border_color: Tuple[int, int, int] = (255, 255, 255),
                             thickness: int = 3) -> Tuple[Optional[np.ndarray], int, int]:
        """
        Generates a small overlay image cropped to the region's bounding box.
        Used for hovering/selection highlights.
        
        Returns:
            Tuple: (image_data, x_offset, y_offset)
        """
        if not region_ids:
            return None, 0, 0

        # 1. Find pixels belonging to these regions
        # np.isin is slower than ==, so we optimize for single region selection
        if len(region_ids) == 1:
            ys, xs = np.where(self.packed_map == region_ids[0])
        else:
            ys, xs = np.where(np.isin(self.packed_map, region_ids))

        if len(xs) == 0:
            return None, 0, 0

        # 2. Calculate crop bounds with padding for the border thickness
        pad = thickness + 2
        x_min, x_max = max(0, np.min(xs) - pad), min(self.width, np.max(xs) + pad)
        y_min, y_max = max(0, np.min(ys) - pad), min(self.height, np.max(ys) + pad)

        # 3. Crop the map to the Region of Interest (ROI) to save processing time
        roi = self.packed_map[y_min:y_max, x_min:x_max]

        # 4. Create binary mask for contours
        if len(region_ids) == 1:
            mask = (roi == region_ids[0])
        else:
            mask = np.isin(roi, region_ids)
            
        mask_uint8 = mask.astype(np.uint8) * 255

        # 5. Find contours (borders) using OpenCV
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 6. Draw contours on a transparent RGBA buffer
        h, w = roi.shape
        overlay = np.zeros((h, w, 4), dtype=np.uint8)
        
        # Draw the border (Color + Alpha 255)
        cv2.drawContours(overlay, contours, -1, border_color + (255,), thickness)

        return overlay, x_min, y_min

class MapRenderer:
    """
    Handles the GPU Context, Shader compilation, and Texture management.
    """
    def __init__(self, window: arcade.Window, atlas: RegionAtlas):
        self.window = window
        self.ctx = window.ctx
        self.atlas = atlas
        self.width = atlas.width
        self.height = atlas.height

        # 1. Setup Quad Geometry (A simple rectangle covering the screen)
        # 4 vertices: x, y, u, v
        buffer_data = array('f', [
            -1.0, -1.0, 0.0, 0.0,  # Bottom Left
             1.0, -1.0, 1.0, 0.0,  # Bottom Right
            -1.0,  1.0, 0.0, 1.0,  # Top Left
             1.0,  1.0, 1.0, 1.0,  # Top Right
        ])
        self.quad_buffer = self.ctx.buffer(data=buffer_data)
        self.quad_geometry = self.ctx.geometry(
            [arcade.gl.BufferDescription(self.quad_buffer, '2f 2f', ['in_vert', 'in_uv'])],
            mode=self.ctx.TRIANGLE_STRIP
        )

        # 2. Create the Map Texture (The Source)
        # IMPORTANT: filter must be NEAREST to prevent color blending at borders
        self.map_texture = self.ctx.texture(
            (self.width, self.height),
            components=3,
            data=cv2.cvtColor(atlas.raw_img, cv2.COLOR_BGR2RGB).tobytes(),
            filter=(self.ctx.NEAREST, self.ctx.NEAREST) 
        )

        # 3. Create the Lookup Texture (The Data)
        # Width = MAX_REGIONS, Height = 1
        self.max_regions = 8192
        self.lut_texture = self.ctx.texture(
            (self.max_regions, 1),
            components=4,
            filter=(self.ctx.NEAREST, self.ctx.NEAREST)
        )

        # 4. Compile Shader
        self.program = self.window.ctx.load_program(
            vertex_shader = str(ShaderRegistry.POLITICAL_VS),
            fragment_shader = str(ShaderRegistry.POLITICAL_FS)
        )
        
        # Set Initial Uniforms
        self.program['u_map_texture'] = 0    # Bound to channel 0
        self.program['u_lookup_texture'] = 1 # Bound to channel 1
        self.program['u_texture_size'] = (float(self.width), float(self.height))

    def update_political_state(self, region_map, color_map):
        """Called whenever territory changes hands."""
        data = self.atlas.get_lut_buffer(region_map, color_map, self.max_regions)
        self.lut_texture.write(data)

    def render(self, hover_id: int = -1, selected_id: int = -1):
        """Draws the map to the screen."""
        self.ctx.enable(self.ctx.BLEND)
        
        # Bind textures to channels
        self.map_texture.use(0)
        self.lut_texture.use(1)
        
        # Update dynamic uniforms
        try:
            self.program['u_hover_id'] = hover_id
            self.program['u_selected_id'] = selected_id
        except KeyError:
            pass # Shader might optimize out uniforms if unused
            
        # Draw
        self.quad_geometry.render(self.program)

# =========================================================================
# GAME IMPLEMENTATION EXAMPLE
# =========================================================================

class StrategyGame(arcade.Window):
    def __init__(self):
        super().__init__(1280, 720, "GLSL Strategy Map", resizable=True)
        
        # Load Data
        # Ensure you have a 'regions.png' in the folder!
        self.atlas = RegionAtlas("regions.png") 
        self.renderer = MapRenderer(self, self.atlas)
        
        # Game State
        self.hover_id = 0
        self.selected_id = -1
        
        # Define Countries
        self.country_colors = {
            "FRA": (50, 50, 200),   # Blue
            "GER": (50, 50, 50),    # Grey
            "ESP": (200, 200, 50),  # Yellow
            "ITA": (50, 200, 50),   # Green
        }
        
        # Assign Regions (Randomly for demo)
        self.region_owners = {}
        tags = list(self.country_colors.keys())
        for i in range(1, 200): # Assuming 200 regions
            self.region_owners[i] = tags[i % len(tags)]
            
        # Initial GPU Upload
        self.renderer.update_political_state(self.region_owners, self.country_colors)

    def on_draw(self):
        self.clear()
        # Render the map
        self.renderer.render(self.hover_id, self.selected_id)
        
        # Draw UI on top
        arcade.draw_text(f"Hover Region: {self.hover_id}", 10, 10, arcade.color.WHITE, 14)

    def on_mouse_motion(self, x, y, dx, dy):
        # 1. Coordinate conversion (Screen -> Image)
        # Since we draw the map full screen stretched:
        scale_x = self.atlas.width / self.width
        scale_y = self.atlas.height / self.height
        
        img_x = int(x * scale_x)
        # Arcade y is bottom-up, Image y is top-down usually
        img_y = int((self.height - y) * scale_y) 
        
        # 2. CPU Lookup (Very fast)
        self.hover_id = self.atlas.get_region_at(img_x, img_y)

    def on_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.selected_id = self.hover_id
            
            # DEMO: Change owner on click
            if self.hover_id > 0:
                current_owner = self.region_owners.get(self.hover_id, "FRA")
                next_owner = "GER" if current_owner == "FRA" else "FRA"
                self.region_owners[self.hover_id] = next_owner
                
                # Instant update!
                self.renderer.update_political_state(self.region_owners, self.country_colors)

if __name__ == "__main__":
    # Create a dummy image if not exists for testing
    if not os.path.exists("regions.png"):
        print("Generating dummy regions.png...")
        dummy = np.zeros((1024, 1024, 3), dtype=np.uint8)
        # Draw some random circles to simulate regions
        for i in range(1, 50):
            color = (i & 255, (i >> 8) & 255, (i >> 16) & 255) # Encode ID in color
            cv2.circle(dummy, (np.random.randint(0,1024), np.random.randint(0,1024)), 
                       np.random.randint(50, 150), color, -1)
        cv2.imwrite("regions.png", dummy)
        
    window = StrategyGame()
    arcade.run()