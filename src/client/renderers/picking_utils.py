import numpy as np
from typing import Optional
import arcade


class PickingUtils:
    """Utility class for 3D picking operations (mouse to world conversion)."""
    
    @staticmethod
    def ray_sphere_intersect(ray_o: np.ndarray, ray_d: np.ndarray, radius: float) -> Optional[float]:
        """Calculate ray-sphere intersection."""
        # Ray: P = O + t*D, Sphere: |P|^2 = r^2
        # |O + t*D|^2 = r^2 => |D|^2*t^2 + 2*(O·D)*t + |O|^2 - r^2 = 0
        a = float(np.dot(ray_d, ray_d))
        b = 2.0 * float(np.dot(ray_o, ray_d))
        c = float(np.dot(ray_o, ray_o) - radius * radius)
        
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        
        sqrt_disc = float(np.sqrt(disc))
        t0 = (-b - sqrt_disc) / (2.0 * a)
        t1 = (-b + sqrt_disc) / (2.0 * a)
        
        # Return the closest positive intersection
        if t0 > 0.0 and t1 > 0.0:
            return min(t0, t1)
        elif t0 > 0.0:
            return t0
        elif t1 > 0.0:
            return t1
        else:
            return None
    
    @staticmethod
    def screen_to_ray(
        screen_x: float, 
        screen_y: float, 
        window_width: int, 
        window_height: int,
        view_proj_matrix: np.ndarray
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Convert screen coordinates to world ray."""
        if window_width <= 0 or window_height <= 0:
            return None, None
        
        # Convert to NDC coordinates
        # Arcade has origin at bottom-left, OpenGL NDC also has origin at bottom-left
        x = (2.0 * float(screen_x) / float(window_width)) - 1.0
        y = (2.0 * float(screen_y) / float(window_height)) - 1.0
        
        try:
            inv_vp = np.linalg.inv(view_proj_matrix)
        except np.linalg.LinAlgError:
            return None, None
        
        # Near and far points in NDC
        p_near = np.array([x, y, -1.0, 1.0], dtype=np.float32)
        p_far = np.array([x, y, 1.0, 1.0], dtype=np.float32)
        
        # Transform to world space
        w_near = inv_vp @ p_near
        w_far = inv_vp @ p_far
        
        if w_near[3] == 0.0 or w_far[3] == 0.0:
            return None, None
        
        w_near /= w_near[3]
        w_far /= w_far[3]
        
        ray_o = w_near[:3]
        ray_d = w_far[:3] - w_near[:3]
        
        # Normalize direction
        n = float(np.linalg.norm(ray_d))
        if n == 0.0:
            return None, None
        ray_d /= n
        
        return ray_o, ray_d
    
    @staticmethod
    def world_to_uv_coords(hit_point: np.ndarray, model_matrix: np.ndarray) -> Optional[tuple[float, float]]:
        """Convert world hit point to UV coordinates on sphere."""
        try:
            inv_model = np.linalg.inv(model_matrix)
        except np.linalg.LinAlgError:
            return None
        
        # Transform to local sphere coordinates
        local = inv_model @ np.array([hit_point[0], hit_point[1], hit_point[2], 1.0], dtype=np.float32)
        xL, yL, zL = float(local[0]), float(local[1]), float(local[2])
        
        # Normalize to unit sphere
        r = float(np.sqrt(xL * xL + yL * yL + zL * zL))
        if r == 0.0:
            return None
        xL, yL, zL = xL / r, yL / r, zL / r
        
        # Convert to UV coordinates (equirectangular mapping)
        # Match the sphere mesh coordinate system
        u = np.arctan2(zL, xL) / (2.0 * np.pi)
        if u < 0.0:
            u += 1.0  # Wrap around to 0-1 range
        
        v = 0.5 - (np.arcsin(yL) / np.pi)  # Matches sphere mesh: lat = (0.5 - vv) * pi
        
        return u, v
    
    @staticmethod
    def uv_to_pixel_coords(
        u: float, 
        v: float, 
        texture_width: int, 
        texture_height: int
    ) -> tuple[int, int]:
        """Convert UV coordinates to pixel coordinates."""
        px = int(u * texture_width) % texture_width
        py = int((1.0 - v) * texture_height)
        py = max(0, min(py, texture_height - 1))
        return px, py
