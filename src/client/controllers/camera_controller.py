import numpy as np
from typing import Tuple, Optional

class CameraController:
    """
    3D Orbit Camera Controller.
    Manages View and Projection matrices for the Globe.
    """
    
    def __init__(
        self,
        distance: float = 2.6,
        min_distance: float = 1.1,
        max_distance: float = 6.0,
        fov_deg: float = 60.0,
        near: float = 0.1,
        far: float = 100.0
    ):
        # Camera parameters
        self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.distance = distance
        self.min_distance = min_distance
        self.max_distance = max_distance
        
        self.fov_deg = fov_deg
        self.near = near
        self.far = far
        
        # Rotation state (Radians)
        self.yaw = np.radians(-120.0)
        self.pitch = np.radians(-10.0)
        self.max_pitch = float(np.radians(89.0))
        self.base_flip = np.pi
        
        # Matrices (Cached)
        self._u_model = np.eye(4, dtype=np.float32)
        self._u_view = np.eye(4, dtype=np.float32)
        self._u_proj = np.eye(4, dtype=np.float32)
        
        # Cached matrices for picking
        self._u_vp_np: Optional[np.ndarray] = None
        self._u_model_np: Optional[np.ndarray] = None

    def update_matrices(self, window_width: int, window_height: int) -> None:
        """Recalculate matrices based on current Yaw/Pitch/Zoom."""
        
        # 1. Clamp Pitch
        self.pitch = float(np.clip(self.pitch, -self.max_pitch, self.max_pitch))
        
        # 2. Model Matrix: Rotate the Globe (Base Flip + User Rotation)
        # Note: We rotate the MODEL, not the Camera eye, to simulate orbiting.
        self._u_model = self._rot_x(self.pitch) @ self._rot_y(self.yaw) @ self._rot_x(self.base_flip)
        
        # 3. View Matrix: Camera is fixed at 'distance' looking at 0,0,0
        eye = np.array([0.0, 0.0, self.distance], dtype=np.float32)
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self._u_view = self._look_at(eye, self.target, up)
        
        # 4. Projection Matrix
        aspect = float(window_width) / float(max(window_height, 1))
        self._u_proj = self._perspective(self.fov_deg, aspect, self.near, self.far)
        
        # 5. Cache for picking
        vp = self._u_proj @ self._u_view
        self._u_vp_np = np.ascontiguousarray(vp, dtype=np.float32)
        self._u_model_np = np.ascontiguousarray(self._u_model, dtype=np.float32)

    # --- INPUT HANDLING ---

    def drag(self, dx: float, dy: float):
        """Orbit the camera based on mouse drag."""
        sensitivity = 0.005
        self.yaw += dx * sensitivity
        self.pitch -= dy * sensitivity

    def zoom_scroll(self, scroll_y: int):
        """Zoom in/out."""
        zoom_speed = 0.1
        self.distance -= float(scroll_y) * zoom_speed
        self.distance = float(np.clip(self.distance, self.min_distance, self.max_distance))

    def look_at_pixel_coords(self, px: float, py: float, texture_width: float, texture_height: float):
        """
        Rotates the camera so the specific pixel on the texture map is centered.
        Used for 'Focus on Region'.
        """
        # 1. Normalize Pixel to UV (0..1)
        u = px / texture_width
        v = py / texture_height

        # 2. Convert UV to Spherical Angles (matching sphere_mesh.py mapping)
        # lon = u * 2pi
        # lat = (0.5 - v) * pi
        lon = u * (2.0 * np.pi)
        lat = (0.5 - v) * np.pi

        # 3. Apply to Camera
        # We need to invert the logic because rotating the model is inverse to rotating the camera.
        # This alignment might need slight tweaking depending on texture phase.
        self.yaw = -lon - (np.pi / 2.0) 
        self.pitch = lat

    def sync_with_arcade(self, arcade_cam):
        """Compatibility stub. Not used in 3D mode."""
        pass

    # --- GETTERS ---

    def get_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get model, view, and projection matrices as column-major tuples."""
        return (
            self._mat4_tuple_colmajor(self._u_model),
            self._mat4_tuple_colmajor(self._u_view),
            self._mat4_tuple_colmajor(self._u_proj)
        )
    
    def get_cached_matrices(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        return self._u_vp_np, self._u_model_np

    def get_position(self) -> tuple[float, float, float]:
        """Get camera position in World Space."""
        # Spherical to Cartesian
        x = self.distance * np.sin(self.yaw) * np.cos(self.pitch)
        y = self.distance * np.sin(self.pitch)
        z = self.distance * np.cos(self.yaw) * np.cos(self.pitch)
        return (float(x), float(y), float(z))

    # --- MATH UTILS ---
    
    def _mat4_tuple_colmajor(self, m: np.ndarray) -> tuple[float, ...]:
        m = np.asarray(m, dtype=np.float32)
        return tuple(m.T.reshape(16))
    
    def _perspective(self, fov_deg: float, aspect: float, z_near: float, z_far: float) -> np.ndarray:
        f = 1.0 / np.tan(np.radians(fov_deg) * 0.5)
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0] = f / max(aspect, 1e-6)
        m[1, 1] = f
        m[2, 2] = (z_far + z_near) / (z_near - z_far)
        m[2, 3] = (2.0 * z_far * z_near) / (z_near - z_far)
        m[3, 2] = -1.0
        return m
    
    def _look_at(self, eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
        f = target - eye
        f = f / (np.linalg.norm(f) + 1e-8)
        u = up / (np.linalg.norm(up) + 1e-8)
        s = np.cross(f, u)
        s = s / (np.linalg.norm(s) + 1e-8)
        u = np.cross(s, f)
        m = np.eye(4, dtype=np.float32)
        m[0, 0:3] = s
        m[1, 0:3] = u
        m[2, 0:3] = -f
        m[0, 3] = -np.dot(s, eye)
        m[1, 3] = -np.dot(u, eye)
        m[2, 3] = np.dot(f, eye)
        return m
    
    def _rot_x(self, a: float) -> np.ndarray:
        c, s = np.cos(a), np.sin(a)
        m = np.eye(4, dtype=np.float32)
        m[1, 1] = c; m[1, 2] = -s
        m[2, 1] = s; m[2, 2] = c
        return m
    
    def _rot_y(self, a: float) -> np.ndarray:
        c, s = np.cos(a), np.sin(a)
        m = np.eye(4, dtype=np.float32)
        m[0, 0] = c; m[0, 2] = s
        m[2, 0] = -s; m[2, 2] = c
        return m