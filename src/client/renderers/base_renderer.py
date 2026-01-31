from abc import ABC, abstractmethod
from typing import Optional
import arcade
import numpy as np


class BaseRenderer(ABC):
    """Base class for all 3D renderers providing common functionality."""
    
    def __init__(self):
        self.window = arcade.get_window()
        self.ctx = self.window.ctx
        
    @abstractmethod
    def draw(self) -> None:
        """Render the scene."""
        pass
    
    def _set_uniform_if_present(self, program: arcade.gl.Program, name: str, value) -> None:
        """Safely set uniform if it exists in the shader."""
        try:
            program[name] = value
        except KeyError:
            pass
    
    def _enable_rendering_state(self) -> None:
        """Enable common OpenGL rendering state."""
        self.ctx.enable(self.ctx.DEPTH_TEST)
        self.ctx.enable(self.ctx.BLEND)
        self.ctx.blend_func = self.ctx.BLEND_DEFAULT
    
    def _disable_rendering_state(self) -> None:
        """Disable common OpenGL rendering state."""
        self.ctx.disable(self.ctx.DEPTH_TEST)
