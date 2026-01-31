import numpy as np
from typing import Tuple, Optional


class CameraController:
    """Manages camera controls including rotation, zoom, and matrix calculations."""
    
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
        
        # Rotation state
        self.yaw = np.radians(-120.0)
        self.pitch = np.radians(-10.0)
        self.max_pitch = float(np.radians(89.0))
        self.base_flip = np.pi
        
        # Auto-spin
        self.auto_spin_enabled = False
        self.auto_spin_speed = 0.002
        
        # Mouse drag state
        self._dragging = False
        self._last_mouse_x = 0.0
        self._last_mouse_y = 0.0
        
        # Matrices
        self._u_model = np.eye(4, dtype=np.float32)
        self._u_view = np.eye(4, dtype=np.float32)
        self._u_proj = np.eye(4, dtype=np.float32)
        
        # Cached matrices for picking
        self._u_vp_np: Optional[np.ndarray] = None
        self._u_model_np: Optional[np.ndarray] = None
    
    def update_matrices(self, window_width: int, window_height: int) -> None:
        """Update all camera matrices based on current state."""
        # Auto-spin if enabled and not dragging
        if self.auto_spin_enabled and not self._dragging:
            self.yaw += self.auto_spin_speed
        
        # Clamp pitch to avoid flipping at poles
        self.pitch = float(np.clip(self.pitch, -self.max_pitch, self.max_pitch))
        
        # Model matrix: base flip + user rotations (yaw-pitch order to prevent roll)
        self._u_model = self._rot_x(self.pitch) @ self._rot_y(self.yaw) @ self._rot_x(self.base_flip)
        
        # View matrix: orbit camera
        eye = np.array([0.0, 0.0, self.distance], dtype=np.float32)
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self._u_view = self._look_at(eye, self.target, up)
        
        # Projection matrix
        aspect = float(window_width) / float(max(window_height, 1))
        self._u_proj = self._perspective(self.fov_deg, aspect, self.near, self.far)
        
        # Cache combined matrices for picking
        vp = self._u_proj @ self._u_view
        self._u_vp_np = np.ascontiguousarray(vp, dtype=np.float32)
        self._u_model_np = np.ascontiguousarray(self._u_model, dtype=np.float32)
    
    def get_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get model, view, and projection matrices as tuple-major tuples."""
        return (
            self._mat4_tuple_colmajor(self._u_model),
            self._mat4_tuple_colmajor(self._u_view),
            self._mat4_tuple_colmajor(self._u_proj)
        )
    
    def get_cached_matrices(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get cached view-projection and model matrices for picking."""
        return self._u_vp_np, self._u_model_np
    
    def get_position(self) -> tuple[float, float, float]:
        """Get current camera position in world space."""
        # Calculate position from spherical coordinates
        x = self.distance * np.sin(self.yaw) * np.cos(self.pitch)
        y = self.distance * np.sin(self.pitch)
        z = self.distance * np.cos(self.yaw) * np.cos(self.pitch)
        return (float(x), float(y), float(z))
    
    # Mouse input handlers
    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Handle mouse press for camera rotation."""
        if button == 1:  # Left mouse button
            self._dragging = True
            self._last_mouse_x = x
            self._last_mouse_y = y
            return True
        return False
    
    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Handle mouse release."""
        if button == 1:  # Left mouse button
            self._dragging = False
            return True
        return False
    
    def on_mouse_drag(self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int) -> bool:
        """Handle mouse drag for camera rotation."""
        if not self._dragging:
            return False
        
        sensitivity = 0.005
        self.yaw += dx * sensitivity
        self.pitch -= dy * sensitivity
        
        self._last_mouse_x = x
        self._last_mouse_y = y
        return True
    
    def on_mouse_scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> bool:
        """Handle mouse scroll for zoom."""
        zoom_speed = 0.1
        self.distance -= float(scroll_y) * zoom_speed
        self.distance = float(np.clip(self.distance, self.min_distance, self.max_distance))
        return True
    
    # Matrix utility methods
    def _mat4_tuple_colmajor(self, m: np.ndarray) -> tuple[float, ...]:
        """Convert numpy matrix to column-major tuple for OpenGL."""
        m = np.asarray(m, dtype=np.float32)
        return tuple(m.T.reshape(16))
    
    def _perspective(self, fov_deg: float, aspect: float, z_near: float, z_far: float) -> np.ndarray:
        """Create perspective projection matrix."""
        f = 1.0 / np.tan(np.radians(fov_deg) * 0.5)
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0] = f / max(aspect, 1e-6)
        m[1, 1] = f
        m[2, 2] = (z_far + z_near) / (z_near - z_far)
        m[2, 3] = (2.0 * z_far * z_near) / (z_near - z_far)
        m[3, 2] = -1.0
        return m
    
    def _look_at(self, eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
        """Create look-at view matrix."""
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
        """Create rotation matrix around X axis."""
        c, s = np.cos(a), np.sin(a)
        m = np.eye(4, dtype=np.float32)
        m[1, 1] = c
        m[1, 2] = -s
        m[2, 1] = s
        m[2, 2] = c
        return m
    
    def _rot_y(self, a: float) -> np.ndarray:
        """Create rotation matrix around Y axis."""
        c, s = np.cos(a), np.sin(a)
        m = np.eye(4, dtype=np.float32)
        m[0, 0] = c
        m[0, 2] = s
        m[2, 0] = -s
        m[2, 2] = c
        return m
