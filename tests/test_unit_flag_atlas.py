from __future__ import annotations

import os
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from time import perf_counter
from unittest.mock import MagicMock, Mock, patch

import arcade
import numpy as np
from PIL import Image
import pytest
from imgui_bundle import imgui

from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_flag_atlas import (
    FLAG_ATLAS_CELL_HEIGHT,
    FLAG_ATLAS_CELL_WIDTH,
    FLAG_ATLAS_PADDING,
    FlagAtlasEntry,
    UnitFlagAtlas,
)
from src.client.renderers.unit_projection import ProjectedUnit


def _fake_upload(atlas: UnitFlagAtlas, uploaded: list[Image.Image]) -> None:
    def upload(image: Image.Image) -> SimpleNamespace:
        uploaded.append(image.copy())
        return SimpleNamespace(glo=100 + len(uploaded))

    atlas._upload_to_gpu = upload


def test_flag_atlas_builds_rgba_cells_with_transparent_padding(tmp_path: Path) -> None:
    Image.new("RGBA", (64, 44), (220, 10, 20, 255)).save(tmp_path / "AAA.png")
    atlas = UnitFlagAtlas()
    atlas.flags_dir = tmp_path
    uploaded: list[Image.Image] = []
    _fake_upload(atlas, uploaded)

    atlas.ensure_owners(["AAA"])

    image = uploaded[0]
    entry = atlas.entry_for("AAA")
    assert entry is not None
    assert atlas._resize_filter() == Image.Resampling.LANCZOS
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0)) == (0, 0, 0, 0)
    assert image.getpixel((FLAG_ATLAS_PADDING + 8, FLAG_ATLAS_PADDING + 8)) == (220, 10, 20, 255)
    assert image.width % (FLAG_ATLAS_CELL_WIDTH + 2 * FLAG_ATLAS_PADDING) == 0
    assert image.height % (FLAG_ATLAS_CELL_HEIGHT + 2 * FLAG_ATLAS_PADDING) == 0
    assert atlas.texture_id == 101


def test_missing_owner_uses_magenta_fallback_and_dynamic_addition_keeps_old_entries(tmp_path: Path) -> None:
    Image.new("RGBA", (32, 22), (10, 20, 30, 255)).save(tmp_path / "AAA.png")
    atlas = UnitFlagAtlas()
    atlas.flags_dir = tmp_path
    uploaded: list[Image.Image] = []
    _fake_upload(atlas, uploaded)

    atlas.ensure_owners(["AAA"])
    original_texture_id = atlas.texture_id
    atlas.ensure_owners(["BBB"])

    fallback = atlas.entry_for("UNKNOWN")
    assert fallback is not None
    assert atlas.texture_id != original_texture_id
    assert atlas.entry_for("AAA") is not None
    assert atlas.entry_for("BBB") is not None
    fallback_x = round(fallback.u0 * uploaded[-1].width) + 8
    fallback_y = round(fallback.v0 * uploaded[-1].height) + 8
    assert uploaded[-1].getpixel((fallback_x, fallback_y)) == (255, 0, 255, 255)


def test_resized_flag_cache_reuses_unchanged_sources_and_reloads_modified_files(tmp_path: Path) -> None:
    flag_path = tmp_path / "AAA.png"
    Image.new("RGBA", (64, 44), (220, 10, 20, 255)).save(flag_path)
    atlas = UnitFlagAtlas()
    atlas.flags_dir = tmp_path

    first = atlas._load_resized_flag("AAA")
    repeated = atlas._load_resized_flag("AAA")

    assert repeated is first
    previous_mtime_ns = flag_path.stat().st_mtime_ns
    Image.new("RGBA", (64, 44), (10, 220, 20, 255)).save(flag_path)
    current_stat = flag_path.stat()
    if current_stat.st_mtime_ns == previous_mtime_ns:
        os.utime(
            flag_path,
            ns=(current_stat.st_atime_ns, previous_mtime_ns + 1_000_000_000),
        )

    refreshed = atlas._load_resized_flag("AAA")

    assert refreshed is not first
    assert refreshed.getpixel((8, 8)) == (10, 220, 20, 255)


def test_draw_flag_uses_atlas_texture_and_normalized_uv_entry() -> None:
    atlas = UnitFlagAtlas()
    atlas._entries = {"AAA": FlagAtlasEntry(0.1, 0.2, 0.3, 0.4)}
    atlas._texture_id = 77
    draw_list = SimpleNamespace(add_image=Mock())

    with patch.object(imgui, "ImTextureRef", side_effect=lambda texture_id: texture_id):
        assert atlas.draw_flag(draw_list, "AAA", 1, 2, 3, 4)

    draw_list.add_image.assert_called_once_with(
        77,
        imgui.ImVec2(1, 2),
        imgui.ImVec2(3, 4),
        imgui.ImVec2(0.1, 0.2),
        imgui.ImVec2(0.3, 0.4),
    )


def test_batch_renderer_emits_two_triangles_per_billboard() -> None:
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    unit = ProjectedUnit(
        unit_id="u1",
        owner="AAA",
        unit_type="infantry",
        strength=100,
        current_region_id=1,
        target_region_id=0,
        screen_x=50.0,
        screen_y=40.0,
        distance_to_camera=0.0,
        width=20.0,
        height=10.0,
        movement_progress=0.0,
        is_moving=False,
    )
    flags = SimpleNamespace(entry_for=lambda owner: FlagAtlasEntry(0.1, 0.2, 0.3, 0.4))

    vertices = renderer._build_vertices([unit], flags)

    assert vertices.shape == (6, 8)
    np.testing.assert_allclose(vertices[0], [40, 35, 0.1, 0.4, 1, 1, 1, 1])
    np.testing.assert_allclose(vertices[5], [40, 45, 0.1, 0.2, 1, 1, 1, 1])


def test_batch_renderer_binds_one_atlas_and_submits_one_draw_for_two_hundred_flags() -> None:
    renderer = UnitBatchRenderer.__new__(UnitBatchRenderer)
    renderer._program = MagicMock()
    renderer._buffer = MagicMock()
    renderer._geometry = MagicMock()
    renderer._ctx = MagicMock()
    renderer._capacity_vertices = 1_200
    renderer._stride_bytes = 8 * 4
    renderer._vertices_cache_key = None
    renderer._vertices_cache = None
    renderer._uploaded_vertices_key = None
    renderer._error_printed = False
    renderer._ensure_resources = Mock()
    renderer._ensure_capacity = Mock()

    units = [
        ProjectedUnit(
            unit_id=f"u{index}",
            owner=f"C{index % 20:02d}",
            unit_type="infantry",
            strength=100,
            current_region_id=index,
            target_region_id=0,
            screen_x=float(index),
            screen_y=40.0,
            distance_to_camera=0.0,
            width=20.0,
            height=10.0,
            movement_progress=0.0,
            is_moving=False,
        )
        for index in range(200)
    ]
    texture = SimpleNamespace(use=Mock())
    flags = SimpleNamespace(
        texture=texture,
        texture_id=77,
        entry_for=lambda owner: FlagAtlasEntry(0.1, 0.2, 0.3, 0.4),
    )

    assert renderer.render(units, flags, 1280, 720)

    texture.use.assert_called_once_with(0)
    renderer._geometry.render.assert_called_once_with(renderer._program, vertices=1_200)
    renderer._buffer.write.assert_called_once()


@pytest.mark.skipif(
    os.environ.get("RUN_UNIT_ATLAS_GPU_CHECKS") != "1",
    reason="Set RUN_UNIT_ATLAS_GPU_CHECKS=1 to run live OpenGL atlas acceptance checks.",
)
def test_live_gpu_new_owner_atlas_rebuild_stays_under_fifteen_milliseconds() -> None:
    from OpenGL.GL import GL_RENDERER, GL_VENDOR, GL_VERSION, glFinish, glGetString

    flags_dir = Path(__file__).parents[1] / "modules" / "base" / "assets" / "flags"
    owners = sorted(path.stem for path in flags_dir.glob("*.png"))
    assert len(owners) >= 205, "The controlled atlas benchmark needs 205 distinct flag assets."

    window = arcade.Window(
        64,
        64,
        "OpenPower live atlas benchmark",
        visible=False,
        vsync=False,
        antialiasing=False,
        gl_version=(3, 3),
    )
    atlas = UnitFlagAtlas()
    atlas.flags_dir = flags_dir
    try:
        window.switch_to()
        base_owners = owners[:200]
        additions = owners[200:205]
        atlas.ensure_owners(base_owners)
        glFinish()

        samples_ms = []
        for owner in additions:
            started = perf_counter()
            atlas.ensure_owners([owner])
            glFinish()
            samples_ms.append((perf_counter() - started) * 1_000.0)

        vendor = glGetString(GL_VENDOR).decode()
        renderer = glGetString(GL_RENDERER).decode()
        version = glGetString(GL_VERSION).decode()
        rebuild_median_ms = median(samples_ms)
        print(
            "live unit flag atlas rebuild: "
            f"vendor={vendor}; renderer={renderer}; version={version}; "
            f"samples_ms={[round(sample, 3) for sample in samples_ms]}; "
            f"median_ms={rebuild_median_ms:.3f}"
        )
        assert rebuild_median_ms < 15.0, (
            f"New-owner atlas rebuild median was {rebuild_median_ms:.3f} ms "
            f"on {renderer} ({version})."
        )
    finally:
        window.close()


@pytest.mark.skipif(
    os.environ.get("RUN_UNIT_ATLAS_GPU_CHECKS") != "1",
    reason="Set RUN_UNIT_ATLAS_GPU_CHECKS=1 to run live OpenGL atlas acceptance checks.",
)
def test_live_linear_filtering_does_not_sample_adjacent_flag_cells(tmp_path: Path) -> None:
    from OpenGL.GL import (
        GL_BLEND,
        GL_RENDERER,
        GL_VENDOR,
        GL_VERSION,
        GL_UNSIGNED_BYTE,
        GL_RGBA,
        glDisable,
        glFinish,
        glGetString,
        glReadPixels,
        glViewport,
    )

    Image.new("RGBA", (32, 22), (255, 0, 0, 255)).save(tmp_path / "AAA.png")
    Image.new("RGBA", (32, 22), (0, 255, 0, 255)).save(tmp_path / "BBB.png")
    Image.new("RGBA", (32, 22), (0, 0, 255, 255)).save(tmp_path / "CCC.png")
    Image.new("RGBA", (32, 22), (255, 0, 255, 255)).save(tmp_path / "XXX.png")

    window = arcade.Window(
        64,
        64,
        "OpenPower live atlas sampling check",
        visible=False,
        vsync=False,
        antialiasing=False,
        gl_version=(3, 3),
    )
    atlas = UnitFlagAtlas()
    atlas.flags_dir = tmp_path
    try:
        window.switch_to()
        atlas.ensure_owners(["AAA", "BBB"])
        entry_a = atlas.entry_for("AAA")
        entry_b = atlas.entry_for("BBB")
        assert entry_a is not None and entry_b is not None
        assert atlas.texture is not None
        original_texture_id = atlas.texture_id
        atlas.ensure_owners(["CCC"])
        entry_c = atlas.entry_for("CCC")
        assert entry_c is not None
        assert atlas.entry_for("AAA") == entry_a
        assert atlas.entry_for("BBB") == entry_b
        assert atlas.texture_id == original_texture_id

        context = window.ctx
        render_target = context.texture((1, 1), components=4)
        framebuffer = context.framebuffer(color_attachments=[render_target])
        geometry = arcade.gl.geometry.quad_2d_fs()
        program = context.program(
            vertex_shader="""
                #version 330
                in vec2 in_vert;
                void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D source_atlas;
                uniform vec2 sample_uv;
                out vec4 frag_color;
                void main() { frag_color = texture(source_atlas, sample_uv); }
            """,
        )
        program["source_atlas"] = 0

        def sample(uv: tuple[float, float]) -> tuple[int, int, int, int]:
            framebuffer.use()
            glViewport(0, 0, 1, 1)
            glDisable(GL_BLEND)
            atlas.texture.use(0)
            program["sample_uv"] = uv
            geometry.render(program)
            glFinish()
            raw = glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE)
            return tuple(np.frombuffer(raw, dtype=np.uint8).tolist())

        width = 2 * (FLAG_ATLAS_CELL_WIDTH + 2 * FLAG_ATLAS_PADDING)
        center_v = (entry_a.v0 + entry_a.v1) / 2.0
        red_edge = sample((entry_a.u1 - 0.25 / width, center_v))
        transparent_gap = sample(((entry_a.u1 + entry_b.u0) / 2.0, center_v))
        green_edge = sample((entry_b.u0 + 0.25 / width, center_v))
        blue_center = sample(
            (
                (entry_c.u0 + entry_c.u1) / 2.0,
                (entry_c.v0 + entry_c.v1) / 2.0,
            )
        )

        vendor = glGetString(GL_VENDOR).decode()
        renderer = glGetString(GL_RENDERER).decode()
        version = glGetString(GL_VERSION).decode()
        print(
            "live unit flag atlas edge samples: "
            f"vendor={vendor}; renderer={renderer}; version={version}; "
            f"red_edge={red_edge}; transparent_gap={transparent_gap}; "
            f"green_edge={green_edge}; blue_after_partial_upload={blue_center}"
        )
        assert red_edge[0] > 100 and red_edge[1] < 5
        assert transparent_gap == (0, 0, 0, 0)
        assert green_edge[1] > 100 and green_edge[0] < 5
        assert blue_center[2] > 250 and blue_center[0] < 5 and blue_center[1] < 5
    finally:
        window.close()
