from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import numpy as np

from src.client.renderers import unit_batch_renderer as renderer_module
from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_flag_atlas import FlagAtlasEntry
from src.client.renderers.unit_projection import ProjectedUnit


def _unit(owner="AAA", screen_x=50.0):
    return ProjectedUnit(
        unit_id=f"unit-{owner}",
        owner=owner,
        unit_type="infantry",
        strength=100,
        current_region_id=1,
        target_region_id=0,
        screen_x=screen_x,
        screen_y=40.0,
        distance_to_camera=0.0,
        width=20.0,
        height=10.0,
        movement_progress=0.0,
        is_moving=False,
    )


def _bare_renderer():
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    renderer._program = MagicMock()
    renderer._buffer = MagicMock()
    renderer._geometry = MagicMock()
    renderer._ctx = SimpleNamespace(
        BLEND="blend",
        BLEND_DEFAULT="default",
        enable_only=Mock(),
    )
    renderer._capacity_vertices = 1024
    renderer._stride_bytes = 8 * 4
    renderer._error_printed = False
    renderer._vertices_cache_key = None
    renderer._vertices_cache = None
    renderer._uploaded_vertices_key = None
    renderer._ensure_resources = Mock()
    renderer._ensure_capacity = Mock()
    return renderer


def _flags(*, texture=True, texture_id=7, entry=None):
    return SimpleNamespace(
        texture=SimpleNamespace(use=Mock()) if texture else None,
        texture_id=texture_id,
        entry_for=lambda _owner: entry or FlagAtlasEntry(0.1, 0.2, 0.3, 0.4),
    )


def test_init_captures_window_context_and_initializes_cache(monkeypatch):
    context = object()
    window = SimpleNamespace(ctx=context)
    monkeypatch.setattr(renderer_module.arcade, "get_window", lambda: window)

    renderer = UnitBatchRenderer()

    assert renderer._window is window
    assert renderer._ctx is context
    assert renderer._capacity_vertices == 0
    assert renderer._stride_bytes == 32
    assert not renderer._error_printed
    assert renderer._vertices_cache is None
    assert renderer._uploaded_vertices_key is None


def test_render_short_circuits_invalid_size_empty_units_and_missing_texture():
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    unit = _unit()
    flags = _flags()

    assert renderer.render([unit], flags, 0, 100)
    assert renderer.render([], flags, 100, 100)
    assert not renderer.render([unit], _flags(texture=False), 100, 100)


def test_render_returns_false_when_gpu_resources_are_missing():
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    renderer._program = None
    renderer._buffer = None
    renderer._geometry = None
    renderer._ensure_resources = Mock()

    assert not renderer.render([_unit()], _flags(), 100, 100)


def test_render_caches_uploaded_vertices_and_skips_empty_cache():
    renderer = _bare_renderer()
    units = [_unit()]
    flags = _flags()
    cache_key = (id(units), 100, 100, flags.texture_id)
    renderer._vertices_cache_key = cache_key
    renderer._vertices_cache = None

    assert renderer.render(units, flags, 100, 100)
    renderer._vertices_cache = np.empty((0, 8), dtype=np.float32)
    renderer._vertices_cache_key = None
    renderer._build_vertices = Mock(return_value=renderer._vertices_cache)
    assert renderer.render(units, flags, 100, 100)


def test_render_rebuilds_once_and_reuses_uploaded_geometry():
    renderer = _bare_renderer()
    units = [_unit()]
    flags = _flags()
    vertices = np.ones((6, 8), dtype=np.float32)
    renderer._build_vertices = Mock(return_value=vertices)

    assert renderer.render(units, flags, 1280, 720)
    assert renderer.render(units, flags, 1280, 720)

    renderer._build_vertices.assert_called_once_with(units, flags)
    renderer._buffer.orphan.assert_called_once_with()
    renderer._buffer.write.assert_called_once_with(vertices)
    assert renderer._geometry.render.call_count == 2
    assert flags.texture.use.call_count == 2
    assert renderer._ctx.viewport == (0, 0, 1280, 720)


def test_render_handles_capacity_failure_and_reports_fallback_only_once(capsys):
    renderer = _bare_renderer()
    vertices = np.ones((6, 8), dtype=np.float32)
    renderer._build_vertices = Mock(return_value=vertices)
    renderer._ensure_capacity.side_effect = lambda _count: setattr(renderer, "_buffer", None)

    assert not renderer.render([_unit()], _flags(), 100, 100)

    renderer = _bare_renderer()
    renderer._ensure_resources.side_effect = RuntimeError("context lost")
    assert not renderer.render([_unit()], _flags(), 100, 100)
    assert not renderer.render([_unit()], _flags(), 100, 100)
    assert capsys.readouterr().out.count("Falling back to ImGui unit rendering") == 1


def test_ensure_resources_compiles_program_and_allocates_initial_capacity():
    renderer = _bare_renderer()
    del renderer._ensure_resources
    renderer._program = None
    renderer._buffer = None
    renderer._geometry = None
    renderer._ctx.program = Mock(return_value="program")

    renderer._ensure_resources()

    renderer._ctx.program.assert_called_once()
    renderer._ensure_capacity.assert_called_once_with(1024)
    assert renderer._program == "program"


def test_ensure_capacity_reuses_then_grows_gpu_buffer(monkeypatch):
    renderer = _bare_renderer()
    del renderer._ensure_capacity
    renderer._capacity_vertices = 1024
    renderer._uploaded_vertices_key = "uploaded"
    description = object()
    buffer = object()
    geometry = object()
    renderer._ctx = SimpleNamespace(
        buffer=Mock(return_value=buffer),
        geometry=Mock(return_value=geometry),
        TRIANGLES="triangles",
    )
    monkeypatch.setattr(
        renderer_module.arcade.gl,
        "BufferDescription",
        lambda *args, **kwargs: description,
    )

    renderer._ensure_capacity(512)
    renderer._ctx.buffer.assert_not_called()

    renderer._ensure_capacity(1500)

    assert renderer._capacity_vertices == 2048
    renderer._ctx.buffer.assert_called_once_with(reserve=2048 * 32, usage="dynamic")
    renderer._ctx.geometry.assert_called_once_with([description], mode="triangles")
    assert renderer._buffer is buffer
    assert renderer._geometry is geometry
    assert renderer._uploaded_vertices_key is None


def test_build_vertices_skips_units_without_atlas_entries():
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    flags = SimpleNamespace(
        entry_for=lambda owner: FlagAtlasEntry(0.1, 0.2, 0.3, 0.4) if owner == "AAA" else None
    )

    vertices = renderer._build_vertices([_unit("AAA"), _unit("MISSING")], flags)

    assert vertices.shape == (6, 8)
    np.testing.assert_allclose(vertices[0], [40, 35, 0.1, 0.4, 1, 1, 1, 1])
