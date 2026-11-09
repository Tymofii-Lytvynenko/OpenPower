from types import SimpleNamespace

import numpy as np

from src.client.renderers import sphere_mesh


class FakeContext:
    TRIANGLES = "triangles"

    def __init__(self):
        self.buffers = []
        self.geometry_args = None

    def buffer(self, *, data):
        buffer = SimpleNamespace(data=data)
        self.buffers.append(buffer)
        return buffer

    def geometry(self, descriptions, *, index_buffer, mode):
        self.geometry_args = (descriptions, index_buffer, mode)
        return "geometry"


def test_sphere_mesh_interleaves_positions_uvs_normals_and_indices():
    context = FakeContext()

    mesh = sphere_mesh.SphereMesh(context, radius=2.0, seg_u=3, seg_v=2)

    vertices = np.frombuffer(mesh.vbo.data, dtype=np.float32).reshape(-1, 8)
    indices = np.frombuffer(mesh.ibo.data, dtype=np.uint32)
    assert vertices.shape == (12, 8)
    assert np.allclose(np.linalg.norm(vertices[:, :3], axis=1), 2.0)
    assert np.allclose(np.linalg.norm(vertices[:, 5:8], axis=1), 1.0)
    assert np.all((vertices[:, 3:5] >= 0.0) & (vertices[:, 3:5] <= 1.0))
    assert indices.tolist()[:6] == [0, 4, 1, 1, 4, 5]
    assert mesh.index_count == 36
    assert mesh.geo is None


def test_sphere_mesh_clamps_segments_and_builds_shader_geometry(monkeypatch):
    context = FakeContext()
    descriptions = []
    monkeypatch.setattr(
        sphere_mesh.arcade.gl,
        "BufferDescription",
        lambda *args: descriptions.append(args) or ("description", args),
    )

    mesh = sphere_mesh.SphereMesh(context, seg_u=1, seg_v=0)
    geometry = mesh.build_geometry(context, "program")

    assert len(np.frombuffer(mesh.vbo.data, dtype=np.float32).reshape(-1, 8)) == 12
    assert mesh.index_count == 36
    assert geometry is None
    assert mesh.geo == "geometry"
    assert descriptions == [(mesh.vbo, "3f 2f 3f", ["in_pos", "in_uv", "in_nrm"])]
    assert context.geometry_args == (
        [("description", (mesh.vbo, "3f 2f 3f", ["in_pos", "in_uv", "in_nrm"]))],
        mesh.ibo,
        context.TRIANGLES,
    )
