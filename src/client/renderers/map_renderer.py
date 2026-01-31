import arcade
import arcade.gl
import numpy as np
from typing import Optional, List, Dict, Tuple, Set
from pathlib import Path

from src.core.map_data import RegionMapData
from src.core.map_indexer import MapIndexer
from src.client.shader_registry import ShaderRegistry
from src.client.renderers.sphere_mesh import SphereMesh
from src.client.renderers.base_renderer import BaseRenderer
from src.client.renderers.camera_controller import CameraController
from src.client.renderers.texture_manager import TextureManager
from src.client.renderers.picking_utils import PickingUtils


class MapRenderer(BaseRenderer):
    """
    Interactive globe renderer with LUT overlay + picking.

    Controls:
      - LMB drag: rotate globe
      - Mouse wheel: zoom in/out
    """

    def __init__(
        self,
        map_data: RegionMapData,
        map_img_path: Path,
        terrain_img_path: Path,
    ):
        super().__init__()
        
        self.map_data = map_data
        self.width = map_data.width
        self.height = map_data.height

        # --- COMPONENTS ---
        self.camera = CameraController()
        self.texture_manager = TextureManager(self.ctx)
        
        # --- CACHING COMPONENT ---
        self.indexer = MapIndexer(map_img_path.parent / ".cache")

        # --- SELECTION STATE ---
        self.single_select_dense_id: int = -1

        # --- GLOBE STATE ---
        self.globe_radius: float = 1.0

        # --- GL RESOURCES ---
        self.program: Optional[arcade.gl.Program] = None
        self.sphere: Optional[SphereMesh] = None

        self._init_resources(terrain_img_path, map_img_path)
        self._init_glsl_globe()

    # -------------------------------------------------------------------------
    # Resource init
    # -------------------------------------------------------------------------


    def _init_resources(self, terrain_path: Path, map_path: Path):
        """Initialize all textures and resources."""
        # Load map texture
        self.texture_manager.load_map_texture(
            map_path, 
            self.map_data.packed_map, 
            self.width, 
            self.height,
            self.indexer
        )
        
        # Load terrain texture
        self.texture_manager.load_terrain_texture(terrain_path)
        
        # Initialize lookup texture
        self.texture_manager.init_lookup_texture()

    # -------------------------------------------------------------------------
    # Shader / geometry init
    # -------------------------------------------------------------------------

    def _set_uniform_if_present(self, name: str, value):
        """Safely set uniform if it exists in the shader."""
        super()._set_uniform_if_present(self.program, name, value)

    def _init_glsl_globe(self):
        """Initialize the globe shader and geometry."""
        shader_source = ShaderRegistry.load_bundle(ShaderRegistry.GLOBE_V, ShaderRegistry.GLOBE_F)
        self.program = self.ctx.program(
            vertex_shader=shader_source["vertex_shader"],
            fragment_shader=shader_source["fragment_shader"],
        )

        # Set texture uniforms
        self._set_uniform_if_present("u_map_texture", 0)
        self._set_uniform_if_present("u_lookup_texture", 1)
        self._set_uniform_if_present("u_terrain_texture", 2)

        # Set LUT uniforms
        self.texture_manager.set_uniforms(self.program)
        
        # Set other uniforms
        self._set_uniform_if_present("u_selected_id", -1)
        self._set_uniform_if_present("u_overlay_mode", 1)
        self._set_uniform_if_present("u_opacity", 0.90)
        self._set_uniform_if_present("u_light_dir", (0.4, 0.3, 1.0))
        self._set_uniform_if_present("u_ambient", 0.35)

        # Create sphere geometry
        self.sphere = SphereMesh(self.ctx, radius=self.globe_radius, seg_u=256, seg_v=128)
        self.sphere.build_geometry(self.ctx, self.program)

    def reload_shader(self):
        """Reload the shader - useful for development/testing."""
        if hasattr(self.program, 'release'):
            self.program.release() # type: ignore
        self._init_glsl_globe()

    # -------------------------------------------------------------------------
    # LUT / overlay updates
    # -------------------------------------------------------------------------

    def update_overlay(self, color_map: Dict[int, Tuple[int, int, int]]):
        """Update overlay colors using texture manager."""
        self.texture_manager.update_overlay(color_map)

    # -------------------------------------------------------------------------
    # Selection API
    # -------------------------------------------------------------------------

    def set_highlight(self, real_region_ids: List[int]):
        """Set highlighted regions using texture manager."""
        if not real_region_ids:
            self.clear_highlight()
            return

        valid_dense_ids: List[int] = []
        for rid in real_region_ids:
            if rid in self.texture_manager.real_to_dense:
                valid_dense_ids.append(self.texture_manager.real_to_dense[rid])

        if not valid_dense_ids:
            return

        if len(valid_dense_ids) == 1:
            self.single_select_dense_id = valid_dense_ids[0]
            self.texture_manager.update_selection(set())
        else:
            self.single_select_dense_id = -1
            new_set = set(valid_dense_ids)
            self.texture_manager.update_selection(new_set)

    def clear_highlight(self):
        """Clear all highlights."""
        self.single_select_dense_id = -1
        self.texture_manager.update_selection(set())

    # -------------------------------------------------------------------------
    # Input handlers (call these from your View)
    # -------------------------------------------------------------------------

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Handle mouse press using camera controller."""
        return self.camera.on_mouse_press(x, y, button, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Handle mouse release using camera controller."""
        return self.camera.on_mouse_release(x, y, button, modifiers)

    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        """Handle mouse drag using camera controller."""
        return self.camera.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> bool:
        """Handle mouse scroll using camera controller."""
        return self.camera.on_mouse_scroll(x, y, scroll_x, scroll_y)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def draw(self, mode: str = "overlay"):
        """Render the globe."""
        if self.program is None or self.sphere is None or self.sphere.geo is None:
            return
        
        # Update camera matrices
        w, h = self.window.get_size()
        self.camera.update_matrices(w, h)
        
        # Enable rendering state
        self._enable_rendering_state()
        
        # Bind textures
        self.texture_manager.bind_textures(self.program)
        
        # Set matrix uniforms
        model, view, proj = self.camera.get_matrices()
        self.program["u_model"] = model
        self.program["u_view"] = view
        self.program["u_projection"] = proj
        
        # Set selection uniform
        self.program["u_selected_id"] = int(self.single_select_dense_id)
        
        # Set camera position for atmospheric effects
        camera_pos = self.camera.get_position()
        self._set_uniform_if_present("u_camera_pos", camera_pos)
        
        # Set rendering mode
        if mode in ("overlay", "political"):
            self._set_uniform_if_present("u_overlay_mode", 1)
            self._set_uniform_if_present("u_opacity", 0.90)
        else:
            self._set_uniform_if_present("u_overlay_mode", 0)
            self._set_uniform_if_present("u_opacity", 1.00)
        
        # Render sphere
        self.sphere.geo.render(self.program)
        
        # Disable rendering state
        self._disable_rendering_state()

    # -------------------------------------------------------------------------
    # Picking
    # -------------------------------------------------------------------------

    def get_region_id_at_screen_pos(self, sx: float, sy: float) -> int:
        """Get region ID at screen position using picking utilities."""
        w, h = self.window.get_size()
        if w <= 0 or h <= 0:
            return 0

        # Update camera matrices if needed
        self.camera.update_matrices(w, h)
        
        # Get cached matrices
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        if vp_matrix is None or model_matrix is None:
            return 0

        # Try both coordinate systems - Arcade bottom-left and potential UI top-left
        for test_sy in [sy, h - sy]:
            ray_o, ray_d = PickingUtils.screen_to_ray(sx, test_sy, w, h, vp_matrix)
            if ray_o is None or ray_d is None:
                continue

            # Intersect ray with sphere
            t = PickingUtils.ray_sphere_intersect(ray_o, ray_d, self.globe_radius)
            if t is None:
                continue

            hit = ray_o + ray_d * t

            # Convert hit to UV coordinates
            uv_result = PickingUtils.world_to_uv_coords(hit, model_matrix)
            if uv_result is None:
                continue
            
            u, v = uv_result

            # Convert UV to pixel coordinates
            px, py = PickingUtils.uv_to_pixel_coords(u, v, self.width, self.height)

            region_id = self.map_data.get_region_id(px, py)
            if region_id > 0:
                return region_id
        
        return 0

    # Backwards-compatible alias
    def get_region_id_at_world_pos(self, world_x: float, world_y: float) -> int:
        return self.get_region_id_at_screen_pos(world_x, world_y)
