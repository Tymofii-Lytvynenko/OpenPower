import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import src.client.renderers.mini_map_texture as texture_module
from src.client.renderers.mini_map_texture import (
    MiniMapRasterizer,
    MiniMapTexture,
    MiniMapTextureCache,
)


def _gl_stub(*, version=b"4.6", texture_id=11, fail_upload=False):
    gl = Mock()
    constants = {
        "GL_VERSION": 1,
        "GL_ACTIVE_TEXTURE": 2,
        "GL_TEXTURE0": 3,
        "GL_TEXTURE_BINDING_2D": 4,
        "GL_UNPACK_ALIGNMENT": 5,
        "GL_TEXTURE_2D": 6,
        "GL_TEXTURE_MIN_FILTER": 7,
        "GL_TEXTURE_MAG_FILTER": 8,
        "GL_NEAREST": 9,
        "GL_RGBA": 10,
        "GL_UNSIGNED_BYTE": 11,
    }
    for name, value in constants.items():
        setattr(gl, name, value)
    gl.glGetString.return_value = version
    gl.glGenTextures.return_value = texture_id
    gl.glGetIntegerv.side_effect = lambda name: {
        gl.GL_ACTIVE_TEXTURE: 101,
        gl.GL_TEXTURE_BINDING_2D: 202,
        gl.GL_UNPACK_ALIGNMENT: 4,
    }[name]
    if fail_upload:
        gl.glTexImage2D.side_effect = RuntimeError("upload failed")
    return gl


def _install_gl(monkeypatch, gl):
    monkeypatch.setitem(sys.modules, "OpenGL", SimpleNamespace(GL=gl))


def test_rasterizer_samples_palette_water_unknown_land_and_borders():
    source = np.array(
        [
            [0, 1, 1, 1],
            [0, 1, 2, 2],
            [0, 2, 2, 2],
            [0, 2, 2, 7],
        ],
        dtype=np.int32,
    )
    rasterizer = MiniMapRasterizer((4, 4))

    rgba = rasterizer.rasterize(
        source,
        {
            0: (255, 255, 255),
            1: (200, 10, 20),
            2: (10, 210, 30, 8),
            7: (1, 2),
        },
    )

    assert rgba.shape == (4, 4, 4)
    assert rgba.dtype == np.uint8
    assert rgba.flags.c_contiguous
    assert tuple(rgba[0, 0]) == MiniMapRasterizer.WATER
    assert tuple(rgba[0, 1]) == (200, 10, 20, 255)
    assert tuple(rgba[2, 2]) == (10, 210, 30, 255)
    assert tuple(rgba[3, 3]) == MiniMapRasterizer.BORDER
    unknown = rasterizer.rasterize(np.full((1, 1), 9, dtype=np.int32), {})
    assert np.all(unknown == MiniMapRasterizer.UNKNOWN_LAND)


def test_rasterizer_clamps_output_size_and_rejects_invalid_source_arrays():
    rasterizer = MiniMapRasterizer((0, -3))
    assert (rasterizer.width, rasterizer.height) == (1, 1)
    assert rasterizer.rasterize(np.array([[4, 5], [6, 7]]), {}).shape == (1, 1, 4)

    with pytest.raises(ValueError, match="non-empty two-dimensional"):
        rasterizer.rasterize(np.array([1, 2]), {})
    with pytest.raises(ValueError, match="non-empty two-dimensional"):
        rasterizer.rasterize(np.empty((0, 2)), {})


def test_apply_palette_skips_zero_and_short_colors():
    sampled = np.array([[0, 1, 2]], dtype=np.int64)
    rgba = np.full((1, 3, 4), 99, dtype=np.uint8)

    MiniMapRasterizer._apply_palette(sampled, rgba, {0: (1, 2, 3), 2: (4, 5)})

    assert np.all(rgba == 99)


def test_texture_cache_reuses_key_replaces_old_texture_and_releases_on_close():
    rasterizer = Mock()
    rasterizer.rasterize.return_value = np.zeros((2, 3, 4), dtype=np.uint8)
    old_release = Mock()
    current_release = Mock()
    old = MiniMapTexture(SimpleNamespace(release=old_release), 1, 3, 2)
    current = MiniMapTexture(SimpleNamespace(release=current_release), 2, 3, 2)
    cache = MiniMapTextureCache(rasterizer)
    cache._upload = Mock(side_effect=[old, current])
    map_data = SimpleNamespace(width=3, height=2, packed_map=np.ones((2, 3)))

    assert cache.get_texture(None, {}, mode_key="political", overlay_revision=1) is None
    assert cache.get_texture(map_data, {}, mode_key="political", overlay_revision=1) is old
    assert cache.get_texture(map_data, {}, mode_key="political", overlay_revision=1) is old
    assert cache._upload.call_count == 1

    assert cache.get_texture(map_data, {}, mode_key="political", overlay_revision=2) is current
    old_release.assert_called_once_with()
    cache.close()
    current_release.assert_called_once_with()
    assert cache._texture is None
    assert cache._key is None
    cache.close()
    current_release.assert_called_once_with()


def test_upload_uses_arcade_context_and_extracts_texture_identifier(monkeypatch):
    gl_texture = SimpleNamespace(glo=SimpleNamespace(value=44), release=Mock())
    context = SimpleNamespace(NEAREST=7, texture=Mock(return_value=gl_texture))
    monkeypatch.setattr(
        texture_module,
        "arcade",
        SimpleNamespace(get_window=lambda: SimpleNamespace(ctx=context)),
    )
    cache = MiniMapTextureCache()
    rgba = np.zeros((2, 3, 4), dtype=np.uint8)

    texture = cache._upload(rgba)

    assert texture == MiniMapTexture(gl_texture, 44, 3, 2)
    context.texture.assert_called_once_with(
        (3, 2), components=4, data=rgba.tobytes(), filter=(7, 7),
    )


def test_upload_without_window_uses_current_context_and_reports_failure_once(monkeypatch, capsys):
    cache = MiniMapTextureCache()
    fallback = MiniMapTexture(5, 5, 2, 1)
    cache._upload_with_current_context = Mock(return_value=fallback)
    monkeypatch.setattr(texture_module, "arcade", SimpleNamespace(get_window=lambda: None))
    rgba = np.zeros((1, 2, 4), dtype=np.uint8)

    assert cache._upload(rgba) is fallback
    cache._upload_with_current_context.assert_called_once_with(rgba)

    get_window = Mock(side_effect=RuntimeError("window is unavailable"))
    monkeypatch.setattr(texture_module, "arcade", SimpleNamespace(get_window=get_window))
    assert cache._upload(rgba) is fallback
    get_window.assert_called_once_with()

    cache._upload_with_current_context.side_effect = RuntimeError("no context")
    assert cache._upload(rgba) is None
    assert cache._upload(rgba) is None
    output = capsys.readouterr().out
    assert output.count("GPU upload failed") == 1
    assert cache._upload_error_reported is True


def test_current_context_upload_restores_texture_state(monkeypatch):
    gl = _gl_stub()
    _install_gl(monkeypatch, gl)
    rgba = np.zeros((2, 3, 4), dtype=np.uint8)

    texture = MiniMapTextureCache()._upload_with_current_context(rgba)

    assert texture == MiniMapTexture(11, 11, 3, 2)
    gl.glActiveTexture.assert_any_call(gl.GL_TEXTURE0)
    gl.glActiveTexture.assert_any_call(101)
    gl.glBindTexture.assert_any_call(gl.GL_TEXTURE_2D, 202)
    gl.glPixelStorei.assert_any_call(gl.GL_UNPACK_ALIGNMENT, 4)
    gl.glTexImage2D.assert_called_once()


def test_current_context_upload_returns_none_without_context_or_texture(monkeypatch):
    no_context = _gl_stub(version=None)
    _install_gl(monkeypatch, no_context)
    assert MiniMapTextureCache()._upload_with_current_context(np.zeros((1, 1, 4), dtype=np.uint8)) is None
    no_context.glGenTextures.assert_not_called()

    no_texture = _gl_stub(texture_id=0)
    _install_gl(monkeypatch, no_texture)
    assert MiniMapTextureCache()._upload_with_current_context(np.zeros((1, 1, 4), dtype=np.uint8)) is None
    no_texture.glGetIntegerv.assert_not_called()


def test_current_context_upload_deletes_failed_texture_and_restores_state(monkeypatch):
    gl = _gl_stub(fail_upload=True)
    _install_gl(monkeypatch, gl)

    with pytest.raises(RuntimeError, match="upload failed"):
        MiniMapTextureCache()._upload_with_current_context(np.zeros((1, 1, 4), dtype=np.uint8))

    gl.glDeleteTextures.assert_called_once_with(1, [11])
    gl.glBindTexture.assert_any_call(gl.GL_TEXTURE_2D, 202)
    gl.glActiveTexture.assert_any_call(101)


def test_draw_uses_supported_texture_reference_and_void_pointer_fallback(monkeypatch):
    image = Mock()
    monkeypatch.setattr(
        texture_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=lambda value: ("ref", value),
            ImTextureID=None,
            image=image,
        ),
    )
    cache = MiniMapTextureCache()
    texture = MiniMapTexture(None, 12, 1, 1)

    cache.draw(texture, 10, 20, test_id="mini.map")

    image.assert_called_once_with(("ref", 12), (10.0, 20.0), test_id="mini.map")

    image = Mock(side_effect=[TypeError("binding signature"), None])
    monkeypatch.setattr(
        texture_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=None,
            ImTextureID=None,
            image=image,
        ),
    )
    cache.draw(texture, 10, 20)
    assert image.call_args_list[0].args == (12, (10.0, 20.0))
    pointer = image.call_args_list[1].args[0]
    assert isinstance(pointer, ctypes.c_void_p)
    assert pointer.value == 12

    image = Mock(side_effect=[ValueError("unsupported wrapper"), None])
    monkeypatch.setattr(
        texture_module,
        "imgui",
        SimpleNamespace(
            ImVec2=lambda width, height: (width, height),
            ImTextureRef=lambda value: value,
            ImTextureID=lambda value: ("legacy", value),
            image=image,
        ),
    )
    cache.draw(texture, 10, 20)
    assert image.call_args_list[1].args == (("legacy", 12), (10.0, 20.0))


def test_release_and_texture_id_support_gpu_and_arcade_objects(monkeypatch):
    release = Mock()
    MiniMapTextureCache._release_texture(MiniMapTexture(SimpleNamespace(release=release), 8, 1, 1))
    release.assert_called_once_with()

    bad_release = Mock(side_effect=RuntimeError("context lost"))
    MiniMapTextureCache._release_texture(MiniMapTexture(SimpleNamespace(release=bad_release), 8, 1, 1))
    bad_release.assert_called_once_with()

    gl = _gl_stub()
    _install_gl(monkeypatch, gl)
    MiniMapTextureCache._release_texture(MiniMapTexture(9, 9, 1, 1))
    gl.glDeleteTextures.assert_called_once_with(1, [9])

    unavailable_gl = _gl_stub()
    unavailable_gl.glGetString.side_effect = RuntimeError("context lost")
    _install_gl(monkeypatch, unavailable_gl)
    MiniMapTextureCache._release_texture(MiniMapTexture(10, 10, 1, 1))

    assert MiniMapTextureCache._texture_id(SimpleNamespace(glo=SimpleNamespace(glo_id=21))) == 21
    assert MiniMapTextureCache._texture_id(SimpleNamespace(glo=SimpleNamespace(value=22))) == 22
    assert MiniMapTextureCache._texture_id(SimpleNamespace(glo=23)) == 23
    assert MiniMapTextureCache._texture_id(SimpleNamespace(glo=None)) == 0
