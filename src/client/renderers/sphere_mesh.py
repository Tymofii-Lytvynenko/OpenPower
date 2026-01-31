from __future__ import annotations

import numpy as np
import arcade


class SphereMesh:
    """
    UV sphere mesh for Arcade/ModernGL.

    Creates:
      - VBO: interleaved float32 [pos.xyz, uv.xy, nrm.xyz]
      - IBO: uint32 indices
      - Geometry: built after you have a Program (for attribute binding)
    """

    def __init__(self, ctx: arcade.gl.Context, radius: float = 1.0, seg_u: int = 256, seg_v: int = 128):
        # seg_u: longitude slices, seg_v: latitude stacks
        seg_u = max(3, int(seg_u))
        seg_v = max(2, int(seg_v))

        u = np.linspace(0.0, 1.0, seg_u + 1, dtype=np.float32)
        v = np.linspace(0.0, 1.0, seg_v + 1, dtype=np.float32)

        uu, vv = np.meshgrid(u, v, indexing="xy")

        # equirectangular mapping:
        # lon 0..2pi, lat -pi/2..pi/2
        lon = uu * (2.0 * np.pi)
        lat = (0.5 - vv) * np.pi

        x = np.cos(lat) * np.cos(lon)
        y = np.sin(lat)
        z = np.cos(lat) * np.sin(lon)

        pos = np.stack([x, y, z], axis=-1).reshape(-1, 3).astype(np.float32) * float(radius)
        uv = np.stack([uu, vv], axis=-1).reshape(-1, 2).astype(np.float32)

        # normals for unit sphere, same direction as position
        nrm = (pos / float(radius)).astype(np.float32)

        # interleave: pos(3), uv(2), nrm(3)
        vtx = np.concatenate([pos, uv, nrm], axis=1).astype(np.float32)

        # indices: 2 triangles per quad
        indices: list[int] = []
        w = seg_u + 1
        for j in range(seg_v):
            for i in range(seg_u):
                a = j * w + i
                b = a + 1
                c = a + w
                d = c + 1
                indices += [a, c, b, b, c, d]

        idx = np.array(indices, dtype=np.uint32)

        # IMPORTANT: Arcade ctx.buffer is keyword-only (data=...)
        self.vbo = ctx.buffer(data=vtx.tobytes())
        self.ibo = ctx.buffer(data=idx.tobytes())
        self.index_count = int(idx.size)

        self.geo: arcade.gl.Geometry | None = None

    def build_geometry(self, ctx: arcade.gl.Context, program: arcade.gl.Program):
        """
        Binds VBO attributes to the shader inputs:
          in_pos (vec3), in_uv (vec2), in_nrm (vec3)
        """
        self.geo = ctx.geometry(
            [
                arcade.gl.BufferDescription(
                    self.vbo,
                    "3f 2f 3f",
                    ["in_pos", "in_uv", "in_nrm"],
                )
            ],
            index_buffer=self.ibo,
            mode=ctx.TRIANGLES,
        )
