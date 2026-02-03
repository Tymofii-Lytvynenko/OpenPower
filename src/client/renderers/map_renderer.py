import arcade
import arcade.gl
import numpy as np
from typing import Optional, List, Dict, Tuple, Set, Any
from pathlib import Path

from src.core.map_data import RegionMapData
from src.core.map_indexer import MapIndexer
from src.client.shader_registry import ShaderRegistry
from src.client.renderers.sphere_mesh import SphereMesh
from src.client.renderers.base_renderer import BaseRenderer
from src.client.controllers.camera_controller import CameraController
from src.client.renderers.texture_manager import TextureManager
from src.client.utils.picking_utils import PickingUtils
from src.client.services.cache_service import CacheService

class MapRenderer(BaseRenderer):
    """
    Interactive globe renderer.
    """

    def __init__(
        self,
        camera: CameraController,
        map_data: RegionMapData,
        map_img_path: Path,
        terrain_img_path: Path,
    ):
        super().__init__()
        
        self.camera = camera
        self.map_data = map_data
        self.width = map_data.width
        self.height = map_data.height

        # --- CACHE SERVICE INIT ---
        # Robust root finding: Go up until we find "modules" or "main.py"
        root = Path(__file__).resolve().parents[3] # Or pass this in from main.py via config
        self.cache_service = CacheService(root)

        # --- COMPONENTS ---
        # Pass service to components using Dependency Injection (Composition)
        self.texture_manager = TextureManager(self.ctx, self.cache_service)
        self.indexer = MapIndexer(self.cache_service)

        # --- STATE ---
        self.single_select_dense_id: int = -1
        self._overlay_enabled: bool = True
        self._overlay_opacity: float = 0.90
        self.globe_radius: float = 1.0

        # --- GL RESOURCES ---
        self.program: Optional[arcade.gl.Program] = None
        self.sphere: Optional[SphereMesh] = None

        self._init_resources(terrain_img_path, map_img_path)
        self._init_glsl_globe()

    def _init_resources(self, terrain_path: Path, map_path: Path):
        self.texture_manager.load_map_texture(
            map_path, 
            self.map_data.packed_map, 
            self.width, 
            self.height, 
            self.indexer
        )
        self.texture_manager.load_terrain_texture(terrain_path)
        self.texture_manager.init_lookup_texture()

    # ... (Rest of the file remains exactly the same: _init_glsl_globe, draw, etc.)
    # ...
    def _init_glsl_globe(self):
        """Initialize the globe shader and geometry."""
        shader_source = ShaderRegistry.load_bundle(ShaderRegistry.GLOBE_V, ShaderRegistry.GLOBE_F)
        self.program = self.ctx.program(
            vertex_shader=shader_source["vertex_shader"],
            fragment_shader=shader_source["fragment_shader"],
        )

        self._set_uniform_if_present("u_map_texture", 0)
        self._set_uniform_if_present("u_lookup_texture", 1)
        self._set_uniform_if_present("u_terrain_texture", 2)

        self.texture_manager.set_uniforms(self.program)
        
        self._set_uniform_if_present("u_selected_id", -1)
        self._set_uniform_if_present("u_overlay_mode", 1)
        self._set_uniform_if_present("u_opacity", 0.90)
        self._set_uniform_if_present("u_light_dir", (0.4, 0.3, 1.0))
        self._set_uniform_if_present("u_ambient", 0.35)
        self._set_uniform_if_present("u_texture_size", (float(self.width), float(self.height)))

        self.sphere = SphereMesh(self.ctx, radius=self.globe_radius, seg_u=256, seg_v=128)
        self.sphere.build_geometry(self.ctx, self.program)

    def _set_uniform_if_present(self, name: str, value: Any):
        super()._set_uniform_if_present(self.program, name, value)

    def set_overlay_style(self, enabled: bool, opacity: float):
        self._overlay_enabled = enabled
        self._overlay_opacity = opacity

    def update_overlay(self, color_map: Dict[int, Tuple[int, int, int]]):
        self.texture_manager.update_overlay(color_map)

    def set_highlight(self, real_region_ids: List[int]):
        if not real_region_ids:
            self.clear_highlight()
            return

        valid_dense_ids: List[int] = []
        for rid in real_region_ids:
            if rid in self.texture_manager.real_to_dense:
                valid_dense_ids.append(self.texture_manager.real_to_dense[rid])

        if len(valid_dense_ids) == 1:
            self.single_select_dense_id = valid_dense_ids[0]
            self.texture_manager.update_selection(set())
        else:
            self.single_select_dense_id = -1
            self.texture_manager.update_selection(set(valid_dense_ids))

    def clear_highlight(self):
        self.single_select_dense_id = -1
        self.texture_manager.update_selection(set())

    def draw(self):
        if self.program is None or self.sphere is None or self.sphere.geo is None:
            return
        
        w, h = self.window.get_size()
        self.camera.update_matrices(w, h)
        
        self._enable_rendering_state()
        self.texture_manager.bind_textures(self.program)
        
        model, view, proj = self.camera.get_matrices()
        self.program["u_model"] = model
        self.program["u_view"] = view
        self.program["u_projection"] = proj
        
        self.program["u_selected_id"] = int(self.single_select_dense_id)
        
        camera_pos = self.camera.get_position()
        self._set_uniform_if_present("u_camera_pos", camera_pos)
        
        mode_int = 1 if self._overlay_enabled else 0
        self._set_uniform_if_present("u_overlay_mode", mode_int)
        self._set_uniform_if_present("u_opacity", self._overlay_opacity)
        
        self.sphere.geo.render(self.program)
        self._disable_rendering_state()

    def get_region_id_at_screen_pos(self, sx: float, sy: float) -> int:
        w, h = self.window.get_size()
        if w <= 0 or h <= 0: return 0

        self.camera.update_matrices(w, h)
        vp_matrix, model_matrix = self.camera.get_cached_matrices()
        
        if vp_matrix is None or model_matrix is None:
            return 0

        ray_o, ray_d = PickingUtils.screen_to_ray(sx, sy, w, h, vp_matrix)
        if ray_o is None or ray_d is None: return 0

        t = PickingUtils.ray_sphere_intersect(ray_o, ray_d, self.globe_radius)
        if t is None: return 0

        hit = ray_o + ray_d * t
        uv_result = PickingUtils.world_to_uv_coords(hit, model_matrix)
        if uv_result is None: return 0
        
        u, v = uv_result
        px, py = PickingUtils.uv_to_pixel_coords(u, v, self.width, self.height)

        return self.map_data.get_region_id(px, py)