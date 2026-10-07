from __future__ import annotations

import os
import statistics
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import arcade
import cv2
import numpy as np
import pytest

from src.client.shader_registry import ShaderRegistry
from src.client.controllers.viewport_controller import ViewportController
from src.client.renderers.planar_map_renderer import PlanarMapRenderer, PlanarMapTransform
from src.client.renderers.texture_manager import TextureManager
from src.core.cache_service import CacheService
from src.core.map_data import RegionMapData
from src.core.map_indexer import MapIndexer


def test_region_map_data_packs_bgr_as_24_bit_id_and_handles_bounds(tmp_path: Path) -> None:
    path = tmp_path / "regions.png"
    image = np.array([[[7, 8, 9], [0, 0, 0]]], dtype=np.uint8)
    assert cv2.imwrite(str(path), image)

    map_data = RegionMapData(str(path))

    assert map_data.get_region_id(0, 0) == 9 * 65536 + 8 * 256 + 7
    assert map_data.get_region_id(1, 0) == 0
    assert map_data.get_region_id(-1, 0) == 0
    assert map_data.packed_map.dtype == np.int32
    assert set(map_data.__dict__) == {"height", "width", "packed_map"}
    assert not hasattr(map_data, "raw_img")


def test_region_map_data_lookup_timing_baseline(tmp_path: Path) -> None:
    path = tmp_path / "lookup-regions.png"
    pixels = np.zeros((256, 512, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), pixels)
    map_data = RegionMapData(str(path))
    random = np.random.default_rng(20261007)
    points = list(zip(
        random.integers(0, map_data.width, size=10_000),
        random.integers(0, map_data.height, size=10_000),
    ))

    for x, y in points:
        map_data.get_region_id(int(x), int(y))

    sample_ms_per_query = []
    for _ in range(11):
        started_at = time.perf_counter_ns()
        for x, y in points:
            map_data.get_region_id(int(x), int(y))
        elapsed_ns = time.perf_counter_ns() - started_at
        sample_ms_per_query.append(elapsed_ns / len(points) / 1_000_000)

    median = float(np.median(sample_ms_per_query))
    p95 = float(np.percentile(sample_ms_per_query, 95))
    print(f"RegionMapData.get_region_id baseline: median={median:.6f}ms/query p95={p95:.6f}ms/query")
    assert all(map_data.get_region_id(int(x), int(y)) == 0 for x, y in points[:100])


def _real_cache_service(tmp_path: Path, monkeypatch) -> CacheService:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr("src.core.cache_service.ProjectPaths.cache", lambda: cache_dir)
    return CacheService(tmp_path)


def _make_cache_newer_than_source(cache_path: Path, source_path: Path) -> None:
    source_mtime = source_path.stat().st_mtime
    newer_time = source_mtime + 5.0
    os.utime(cache_path, (newer_time, newer_time))


def test_map_indexer_computes_indices_once_then_uses_verified_cache(tmp_path: Path) -> None:
    class MemoryCache:
        def __init__(self) -> None:
            self.archive = None
            self.saved = 0

        @staticmethod
        def get_cache_path(source_path: Path, suffix: str) -> Path:
            return source_path.parent / f"{source_path.stem}{suffix}"

        @staticmethod
        def compute_file_hash(source_path: Path) -> str:
            return "source-hash"

        def is_cache_valid(self, source_path: Path, cache_path: Path) -> bool:
            return self.archive is not None

        def load_numpy_archive(self, cache_path: Path):
            return self.archive

        def save_numpy_archive(self, cache_path: Path, **values) -> None:
            self.archive = values
            self.saved += 1

    source = tmp_path / "regions.png"
    source.write_bytes(b"source")
    cache = MemoryCache()
    indexer = MapIndexer(cache)
    region_ids = np.array([[2, 1], [2, 3]], dtype=np.int32)

    unique_ids, dense_map = indexer.get_indices(source, region_ids)
    cached_ids, cached_map = indexer.get_indices(source, region_ids)

    np.testing.assert_array_equal(unique_ids, [1, 2, 3])
    np.testing.assert_array_equal(dense_map, [[1, 0], [1, 2]])
    np.testing.assert_array_equal(cached_ids, unique_ids)
    np.testing.assert_array_equal(cached_map, dense_map)
    assert dense_map.shape == region_ids.shape
    assert cache.saved == 1


def test_cache_service_archive_is_copied_closed_and_atomically_replaceable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache = _real_cache_service(tmp_path, monkeypatch)
    archive_path = cache.cache_dir / "indices.npz"
    expected = np.array([[0, 1], [2, 1]], dtype=np.int64)

    cache.save_numpy_archive(archive_path, dense_map=expected, hash=np.asarray("source-hash"))
    first_load = cache.load_numpy_archive(archive_path)

    assert first_load is not None
    first_load["dense_map"][0, 0] = 99
    cache.save_numpy_archive(archive_path, dense_map=expected, hash=np.asarray("source-hash"))
    np.testing.assert_array_equal(cache.load_numpy_archive(archive_path)["dense_map"], expected)
    assert not archive_path.with_name(f"{archive_path.name}.tmp.npz").exists()


@pytest.mark.parametrize(
    "cached_members",
    [
        {"unique_ids": np.array([1, 2]), "dense_map": np.array([[0, 1], [1, 0]])},
        {"hash": np.asarray("wrong-hash"), "unique_ids": np.array([1, 2]), "dense_map": np.array([[0, 1], [1, 0]])},
        {"hash": np.asarray("source-hash"), "unique_ids": np.array([[1, 2]]), "dense_map": np.array([[0, 1], [1, 0]])},
        {"hash": np.asarray("source-hash"), "unique_ids": np.array([1, 2]), "dense_map": np.array([0, 1, 1, 0])},
        {"hash": np.asarray("source-hash"), "unique_ids": np.array([1, 2]), "dense_map": np.array([[0, 1, 1, 0]])},
    ],
    ids=["missing-key", "wrong-hash", "non-vector-ids", "flattened-dense-map", "wrong-grid-shape"],
)
def test_map_indexer_rebuilds_malformed_or_mismatched_archives(
    tmp_path: Path,
    monkeypatch,
    cached_members: dict[str, np.ndarray],
) -> None:
    cache = _real_cache_service(tmp_path, monkeypatch)
    source = tmp_path / "regions.png"
    source.write_bytes(b"source")
    cache_path = cache.get_cache_path(source, "_index.npz")
    cache.save_numpy_archive(cache_path, **cached_members)
    _make_cache_newer_than_source(cache_path, source)
    indexer = MapIndexer(cache)
    region_ids = np.array([[2, 1], [2, 3]], dtype=np.int32)

    with patch("src.core.map_indexer.np.unique", wraps=np.unique) as unique:
        unique_ids, dense_map = indexer.get_indices(source, region_ids)

    unique.assert_called_once()
    np.testing.assert_array_equal(unique_ids, [1, 2, 3])
    np.testing.assert_array_equal(dense_map, [[1, 0], [1, 2]])
    assert dense_map.shape == region_ids.shape


def test_map_indexer_uses_only_fresh_archives_and_rebuilds_stale_mtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache = _real_cache_service(tmp_path, monkeypatch)
    source = tmp_path / "regions.png"
    source.write_bytes(b"source")
    cache_path = cache.get_cache_path(source, "_index.npz")
    current_hash = cache.compute_file_hash(source)
    region_ids = np.array([[2, 1], [2, 3]], dtype=np.int32)
    cache.save_numpy_archive(
        cache_path,
        hash=np.asarray(current_hash),
        unique_ids=np.array([1, 2, 3]),
        dense_map=np.array([[1, 0], [1, 2]]),
    )
    stale_time = source.stat().st_mtime - 5.0
    os.utime(cache_path, (stale_time, stale_time))

    with patch("src.core.map_indexer.np.unique", wraps=np.unique) as unique:
        MapIndexer(cache).get_indices(source, region_ids)

    unique.assert_called_once()


def test_map_indexer_reads_a_fresh_archive_without_recomputing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cache = _real_cache_service(tmp_path, monkeypatch)
    source = tmp_path / "regions.png"
    source.write_bytes(b"source")
    cache_path = cache.get_cache_path(source, "_index.npz")
    current_hash = cache.compute_file_hash(source)
    expected_ids = np.array([1, 2, 3])
    expected_map = np.array([[1, 0], [1, 2]])
    cache.save_numpy_archive(
        cache_path,
        hash=np.asarray(current_hash),
        unique_ids=expected_ids,
        dense_map=expected_map,
    )
    _make_cache_newer_than_source(cache_path, source)

    with patch("src.core.map_indexer.np.unique", wraps=np.unique) as unique:
        unique_ids, dense_map = MapIndexer(cache).get_indices(
            source,
            np.array([[2, 1], [2, 3]], dtype=np.int32),
        )

    unique.assert_not_called()
    np.testing.assert_array_equal(unique_ids, expected_ids)
    np.testing.assert_array_equal(dense_map, expected_map)


def test_map_indexer_rebuilds_an_unreadable_archive(tmp_path: Path, monkeypatch) -> None:
    cache = _real_cache_service(tmp_path, monkeypatch)
    source = tmp_path / "regions.png"
    source.write_bytes(b"source")
    cache_path = cache.get_cache_path(source, "_index.npz")
    cache_path.write_bytes(b"not a valid zip archive")
    _make_cache_newer_than_source(cache_path, source)

    with patch("src.core.map_indexer.np.unique", wraps=np.unique) as unique:
        ids, dense_map = MapIndexer(cache).get_indices(
            source,
            np.array([[3, 1], [3, 2]], dtype=np.int32),
        )

    unique.assert_called_once()
    np.testing.assert_array_equal(ids, [1, 2, 3])
    np.testing.assert_array_equal(dense_map, [[2, 0], [2, 1]])


def test_shader_registry_reads_bundles_and_surfaces_missing_sources(
    tmp_path: Path,
    caplog,
) -> None:
    vertex = tmp_path / "map.vert"
    fragment = tmp_path / "map.frag"
    vertex.write_text("vertex shader", encoding="utf-8")
    fragment.write_text("fragment shader", encoding="utf-8")

    assert ShaderRegistry.load_bundle(vertex, fragment) == {
        "vertex_shader": "vertex shader",
        "fragment_shader": "fragment shader",
    }
    with pytest.raises(FileNotFoundError):
        ShaderRegistry.load_bundle(vertex, tmp_path / "missing.frag")
    assert str((tmp_path / "missing.frag").resolve()) in caplog.text


def test_shader_registry_declares_existing_globe_and_political_bundles() -> None:
    for vertex, fragment in (
        (ShaderRegistry.GLOBE_V, ShaderRegistry.GLOBE_F),
        (ShaderRegistry.POLITICAL_V, ShaderRegistry.POLITICAL_F),
    ):
        assert vertex.is_file()
        assert fragment.is_file()
        sources = ShaderRegistry.load_bundle(vertex, fragment)
        assert sources["vertex_shader"].startswith("#version 330")
        assert sources["fragment_shader"].startswith("#version 330")


def test_planar_transform_uses_letterbox_zoom_and_pan_for_pixel_picking() -> None:
    transform = PlanarMapTransform(map_width=200, map_height=100)
    viewport = (100, 100)

    assert transform.screen_to_pixel(50, 50, viewport) == (101, 49)
    assert transform.screen_to_pixel(50, 5, viewport) is None

    transform.zoom_at(60, 50, 4, viewport)
    assert transform.zoom > 1.0
    zoom_anchor = transform.screen_to_pixel(60, 50, viewport)
    assert zoom_anchor is not None

    transform.pan(12, -7)
    panned_pixel = transform.screen_to_pixel(60, 50, viewport)
    assert panned_pixel is not None
    assert panned_pixel != zoom_anchor

    transform.focus_pixel(40, 25)
    assert transform.pan_x == 0.0
    assert transform.pan_y == 0.0
    assert transform.center_u == pytest.approx(40.5 / 200)
    assert transform.center_v == pytest.approx(1.0 - 25.5 / 100)


def test_planar_transform_keeps_the_cursor_map_point_fixed_during_zoom() -> None:
    transform = PlanarMapTransform(map_width=400, map_height=200)
    viewport = (800, 600)
    cursor = (520, 340)
    before_zoom = transform.screen_to_pixel(*cursor, viewport)

    transform.zoom_at(*cursor, 3, viewport)

    assert transform.screen_to_pixel(*cursor, viewport) == before_zoom


def test_planar_viewport_input_routes_pan_and_zoom_to_the_planar_transform() -> None:
    controller = object.__new__(ViewportController)
    controller.renderer = SimpleNamespace(
        projection_mode="planar",
        pan_planar=MagicMock(),
        zoom_planar_at=MagicMock(),
    )
    controller.cam = MagicMock()

    controller.on_mouse_drag(40, 50, 12.0, -7.0, arcade.MOUSE_BUTTON_RIGHT)
    controller.on_mouse_scroll(40, 50, 0, 2)

    controller.renderer.pan_planar.assert_called_once_with(12.0, -7.0)
    controller.renderer.zoom_planar_at.assert_called_once_with(40, 50, 2)
    controller.cam.drag.assert_not_called()
    controller.cam.zoom_scroll.assert_not_called()


def test_empire_color_change_blends_lookup_textures_without_a_discontinuous_retarget() -> None:
    class FakeTexture:
        def __init__(self) -> None:
            self.data = b""

        def write(self, data: bytes) -> None:
            self.data = data

    class FakeContext:
        NEAREST = 0

        @staticmethod
        def texture(*_args, **_kwargs) -> FakeTexture:
            return FakeTexture()

    manager = TextureManager(FakeContext(), cache_service=None, lut_dim=2)
    manager.real_to_dense = {101: 1}
    manager.init_lookup_texture()
    manager.update_overlay({101: (200, 40, 20, 240)})
    first_transition_start = manager._transition_started_at
    assert first_transition_start is not None
    assert manager.overlay_transition_progress(first_transition_start + 0.125) == pytest.approx(0.5)

    with patch(
        "src.client.renderers.texture_manager.time.perf_counter",
        return_value=first_transition_start + 0.125,
    ):
        manager.update_overlay({101: (20, 40, 200, 240)})

    previous_lut = np.frombuffer(manager.previous_lookup_texture.data, dtype=np.uint8).reshape(-1, 4)
    assert previous_lut[1].tolist() == [100, 20, 10, 120]
    assert manager.overlay_transition_progress(first_transition_start + 0.25) == pytest.approx(0.5)


def test_globe_shader_interpolates_lookup_colors_and_keeps_selection_on_target_palette() -> None:
    shader = ShaderRegistry.load_bundle(ShaderRegistry.GLOBE_V, ShaderRegistry.GLOBE_F)

    assert "u_previous_lookup_texture" in shader["fragment_shader"]
    assert "smoothstep(0.0, 1.0, u_overlay_transition)" in shader["fragment_shader"]
    assert "current_overlay_data.a > 0.95" in shader["fragment_shader"]


@pytest.mark.skipif(
    os.environ.get("RUN_MAP_RENDERER_GPU_CHECKS") != "1",
    reason="Set RUN_MAP_RENDERER_GPU_CHECKS=1 to compile and render the globe shader on OpenGL.",
)
def test_live_map_shaders_compile_and_render_globe_and_planar_outputs() -> None:
    import arcade
    from OpenGL.GL import (
        GL_BLEND,
        GL_DEPTH_TEST,
        GL_RENDERER,
        GL_RGBA,
        GL_UNSIGNED_BYTE,
        GL_VENDOR,
        GL_VERSION,
        glDisable,
        glFinish,
        glGetString,
        glReadPixels,
        glViewport,
    )

    window = arcade.Window(
        64,
        64,
        "OpenPower live globe shader check",
        visible=False,
        vsync=False,
        antialiasing=False,
        gl_version=(3, 3),
    )
    try:
        window.switch_to()
        context = window.ctx
        shader_sources = ShaderRegistry.load_bundle(
            ShaderRegistry.GLOBE_V,
            ShaderRegistry.GLOBE_F,
        )
        context.program(**shader_sources)
        political_sources = ShaderRegistry.load_bundle(
            ShaderRegistry.POLITICAL_V,
            ShaderRegistry.POLITICAL_F,
        )
        context.program(**political_sources)

        probe_program = context.program(
            vertex_shader="""
                #version 330
                in vec2 in_vert;
                out vec2 v_uv;
                out vec3 v_nrm_ws;
                out vec3 v_world_pos;
                void main() {
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                    v_uv = vec2(0.5);
                    v_nrm_ws = vec3(0.0, 0.0, 1.0);
                    v_world_pos = vec3(0.0);
                }
            """,
            fragment_shader=shader_sources["fragment_shader"],
        )
        probe_program["u_terrain_texture"] = 0
        probe_program["u_map_texture"] = 1
        probe_program["u_lookup_texture"] = 2
        probe_program["u_previous_lookup_texture"] = 3
        probe_program["u_lut_dim"] = 1.0
        probe_program["u_selected_id"] = -1
        probe_program["u_overlay_mode"] = 1
        probe_program["u_opacity"] = 1.0
        probe_program["u_light_dir"] = (0.0, 0.0, 1.0)
        probe_program["u_ambient"] = 1.0
        probe_program["u_camera_pos"] = (0.0, 0.0, 1.0)

        def make_texture(rgba: tuple[int, int, int, int]):
            return context.texture(
                (1, 1),
                components=4,
                data=bytes(rgba),
                filter=(context.NEAREST, context.NEAREST),
            )

        terrain = make_texture((0, 0, 0, 255))
        plain_map = make_texture((0, 0, 0, 0))
        bordered_map = make_texture((0, 0, 0, 255))
        target_palette = make_texture((255, 0, 0, 200))
        previous_palette = make_texture((0, 0, 255, 200))
        target = context.texture((1, 1), components=4)
        framebuffer = context.framebuffer(color_attachments=[target])
        geometry = arcade.gl.geometry.quad_2d_fs()

        def sample(transition: float, *, border: bool = False, selected: bool = False):
            framebuffer.use()
            glViewport(0, 0, 1, 1)
            glDisable(GL_BLEND)
            glDisable(GL_DEPTH_TEST)
            for texture, unit in (
                (terrain, 0),
                (bordered_map if border else plain_map, 1),
                (target_palette, 2),
                (previous_palette, 3),
            ):
                texture.use(unit)
            probe_program["u_overlay_transition"] = transition
            probe_program["u_selected_id"] = 0 if selected else -1
            geometry.render(probe_program)
            glFinish()
            raw = glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE)
            return tuple(np.frombuffer(raw, dtype=np.uint8).tolist())

        previous = sample(0.0)
        midpoint = sample(0.5)
        current = sample(1.0)
        plain_edge = sample(1.0)
        border_edge = sample(1.0, border=True)
        selected = sample(1.0, selected=True)

        vendor = glGetString(GL_VENDOR).decode()
        renderer = glGetString(GL_RENDERER).decode()
        version = glGetString(GL_VERSION).decode()
        print(
            "live globe shader pixels: "
            f"vendor={vendor}; renderer={renderer}; version={version}; "
            f"previous={previous}; midpoint={midpoint}; current={current}; "
            f"plain_edge={plain_edge}; border_edge={border_edge}; selected={selected}"
        )

        assert previous[2] > 170 and previous[0] < 10
        assert midpoint[0] in range(90, 111) and midpoint[2] in range(90, 111)
        assert current[0] > 170 and current[2] < 10
        assert plain_edge[0] > 170
        assert 95 < border_edge[0] < 150
        assert selected[1] > 100 and selected[2] > 100

        planar_manager = TextureManager(context, cache_service=None, lut_dim=1)
        planar_manager.map_texture = make_texture((0, 0, 0, 0))
        planar_manager.lookup_texture = make_texture((200, 0, 0, 200))
        planar_manager.previous_lookup_texture = make_texture((0, 0, 200, 200))
        planar_manager.terrain_texture = make_texture((0, 0, 0, 255))
        planar_renderer = PlanarMapRenderer(context, planar_manager, map_width=1, map_height=1)
        planar_target = context.texture((64, 64), components=4)
        planar_framebuffer = context.framebuffer(color_attachments=[planar_target])
        planar_framebuffer.use()
        glViewport(0, 0, 64, 64)
        planar_renderer.draw(
            (64, 64),
            overlay_enabled=True,
            opacity=1.0,
            selected_dense_id=-1,
        )
        glFinish()
        planar_pixel = tuple(
            np.frombuffer(glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE), dtype=np.uint8).tolist()
        )
        print(f"live planar shader center pixel: {planar_pixel}")
        assert planar_pixel[0] > 150
        assert planar_pixel[1] < 10 and planar_pixel[2] < 10
    finally:
        window.close()


@pytest.mark.skipif(
    os.environ.get("RUN_MAP_RENDERER_PERFORMANCE_CHECKS") != "1",
    reason="Set RUN_MAP_RENDERER_PERFORMANCE_CHECKS=1 to measure the production map at 4K.",
)
def test_live_globe_and_planar_map_renderers_meet_4k_frame_budget(tmp_path: Path, monkeypatch) -> None:
    import arcade
    from OpenGL.GL import GL_RENDERER, glFinish, glGetString

    from src.client.controllers.camera_controller import CameraController
    from src.client.renderers.map_renderer import MapRenderer
    from src.core.cache_service import CacheService

    project_root = Path(__file__).resolve().parents[1]
    map_path = project_root / "modules" / "base" / "data" / "regions" / "regions.png"
    terrain_path = project_root / "modules" / "base" / "assets" / "map" / "terrain.png"
    cache_directory = tmp_path / "map-performance-cache"
    monkeypatch.setattr("src.core.cache_service.ProjectPaths.cache", lambda: cache_directory)
    monkeypatch.setattr(CacheService, "save_numpy_archive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(CacheService, "save_numpy_array", lambda *_args, **_kwargs: None)

    window = arcade.Window(
        3840,
        2160,
        "OpenPower 4K map renderer performance check",
        visible=False,
        vsync=False,
        antialiasing=False,
        gl_version=(3, 3),
    )
    try:
        window.switch_to()
        viewport_size = window.get_size()
        assert viewport_size == (3840, 2160), f"4K framebuffer unavailable: {viewport_size}"
        renderer_name = glGetString(GL_RENDERER).decode()
        renderer = MapRenderer(
            camera=CameraController(),
            map_data=RegionMapData(str(map_path)),
            map_img_path=map_path,
            terrain_img_path=terrain_path,
        )

        def measure_mode(mode: str) -> tuple[float, float, float]:
            renderer.set_projection_mode(mode)
            for _ in range(10):
                window.clear()
                renderer.draw()
                glFinish()

            frame_times_ms = []
            for _ in range(60):
                started_at = time.perf_counter_ns()
                window.clear()
                renderer.draw()
                glFinish()
                frame_times_ms.append((time.perf_counter_ns() - started_at) / 1_000_000)
            median_ms = float(statistics.median(frame_times_ms))
            p95_ms = float(np.percentile(frame_times_ms, 95))
            return median_ms, p95_ms, 1000.0 / median_ms

        globe_result = measure_mode("globe")
        planar_result = measure_mode("planar")
        print(
            "4K map-renderer performance: "
            f"gpu={renderer_name}; map={renderer.width}x{renderer.height}; viewport={viewport_size}; "
            f"globe_median={globe_result[0]:.3f}ms; globe_p95={globe_result[1]:.3f}ms; "
            f"globe_median_fps={globe_result[2]:.1f}; "
            f"planar_median={planar_result[0]:.3f}ms; planar_p95={planar_result[1]:.3f}ms; "
            f"planar_median_fps={planar_result[2]:.1f}"
        )
        assert globe_result[2] >= 60.0
        assert planar_result[2] >= 60.0
    finally:
        window.close()
