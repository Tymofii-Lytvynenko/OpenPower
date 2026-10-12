"""OpenGL texture port for running existing image widgets inside Hello ImGui."""
from __future__ import annotations


class TestTextureUploader:
    def __init__(self):
        self._textures = []

    def __call__(self, image, label):
        from OpenGL import GL
        from src.client.renderers.flag_renderer import FlagTexture
        previous = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
        texture = int(GL.glGenTextures(1))
        self._textures.append(texture)
        try:
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, image.width, image.height, 0,
                            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, image.convert("RGBA").tobytes())
        finally:
            GL.glBindTexture(GL.GL_TEXTURE_2D, previous)
        return FlagTexture(texture, texture, image.width, image.height)

    def close(self):
        from OpenGL import GL
        if self._textures:
            GL.glDeleteTextures(self._textures)
            self._textures.clear()
